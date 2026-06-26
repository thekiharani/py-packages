"""Meta WhatsApp Cloud API client (sync and async)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...core.config import EnvLike, get_env_number, get_optional_env, get_required_env
from ...core.errors import ConfigurationError, ProviderError
from ...core.http import AsyncHttpClient, HttpClient
from ...core.types import HttpRequestOptions, RequestOptions
from ...core.utils import (
    coerce_int,
    coerce_number,
    coerce_string,
    compact_record,
    first_text,
    require_string,
    to_object,
)
from ...events import DeliveryEvent
from .types import (
    WhatsAppCatalogMessageRequest,
    WhatsAppContact,
    WhatsAppContactAddress,
    WhatsAppContactEmail,
    WhatsAppContactName,
    WhatsAppContactOrg,
    WhatsAppContactPhone,
    WhatsAppContactsRequest,
    WhatsAppContactUrl,
    WhatsAppFlowMessageRequest,
    WhatsAppInboundLocation,
    WhatsAppInboundMedia,
    WhatsAppInboundMessage,
    WhatsAppInboundReaction,
    WhatsAppInboundReply,
    WhatsAppInteractiveButton,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppInteractiveRow,
    WhatsAppInteractiveSection,
    WhatsAppLocationRequest,
    WhatsAppManagedTemplate,
    WhatsAppMediaDeleteResult,
    WhatsAppMediaInfo,
    WhatsAppMediaRequest,
    WhatsAppMediaUploadRequest,
    WhatsAppMediaUploadResult,
    WhatsAppProductItem,
    WhatsAppProductListRequest,
    WhatsAppProductMessageRequest,
    WhatsAppProductSection,
    WhatsAppReactionRequest,
    WhatsAppReadRequest,
    WhatsAppSendReceipt,
    WhatsAppSendResult,
    WhatsAppStatusResult,
    WhatsAppTemplateButtonDefinition,
    WhatsAppTemplateComponent,
    WhatsAppTemplateComponentDefinition,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateDeleteResult,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateListResult,
    WhatsAppTemplateListSummary,
    WhatsAppTemplateMutationResult,
    WhatsAppTemplateParameter,
    WhatsAppTemplateRequest,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTextRequest,
)

META_GRAPH_BASE_URL = "https://graph.facebook.com"
META_GRAPH_API_VERSION = "v25.0"

MEDIA_TYPES = frozenset({"image", "audio", "document", "sticker", "video"})


class _MetaWhatsAppClientBase:
    """Shared configuration, path building, and webhook parsing for Meta WhatsApp."""

    provider_name = "meta"

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        whatsapp_business_account_id: str | None = None,
        app_secret: str | None = None,
        webhook_verify_token: str | None = None,
        api_version: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> None:
        access_token = require_string(access_token, "access_token")
        self._phone_number_id = require_string(phone_number_id, "phone_number_id")
        self._whatsapp_business_account_id = coerce_string(whatsapp_business_account_id)
        self.app_secret = coerce_string(app_secret)
        self.webhook_verify_token = coerce_string(webhook_verify_token)
        self._api_version = require_string(
            api_version if api_version is not None else META_GRAPH_API_VERSION, "api_version"
        )
        self._http_options = {
            "base_url": base_url or META_GRAPH_BASE_URL,
            "timeout_seconds": timeout_seconds if timeout_seconds is not None else 30.0,
            "default_headers": {
                "Authorization": f"Bearer {access_token}",
                **(dict(default_headers) if default_headers else {}),
            },
            "retry": retry,
            "hooks": hooks,
        }

    # -- path helpers ------------------------------------------------------- #

    def _messages_path(self) -> str:
        return f"/{self._api_version}/{self._phone_number_id}/messages"

    def _template_collection_path(self) -> str:
        return f"/{self._api_version}/{self._require_waba_id()}/message_templates"

    def _template_path(self, template_id: str) -> str:
        return f"/{self._api_version}/{require_string(template_id, 'template_id')}"

    def _media_upload_path(self) -> str:
        return f"/{self._api_version}/{self._phone_number_id}/media"

    def _media_path(self, media_id: str) -> str:
        return f"/{self._api_version}/{require_string(media_id, 'media_id')}"

    def _media_query(self) -> dict[str, str]:
        return {"phone_number_id": self._phone_number_id}

    def _require_waba_id(self) -> str:
        if not self._whatsapp_business_account_id:
            raise ConfigurationError(
                "Meta WhatsApp template management requires whatsapp_business_account_id."
            )
        return self._whatsapp_business_account_id

    # -- webhook parsing (pure) --------------------------------------------- #

    def parse_events(self, payload: Mapping[str, Any]) -> list[DeliveryEvent]:
        events: list[DeliveryEvent] = []
        for value in _iterate_value_objects(payload):
            statuses = value.get("statuses")
            if not isinstance(statuses, list):
                continue
            for row in statuses:
                event = _build_status_event(self.provider_name, row)
                if event is not None:
                    events.append(event)
        return events

    def parse_inbound_messages(
        self, payload: Mapping[str, Any]
    ) -> list[WhatsAppInboundMessage]:
        messages: list[WhatsAppInboundMessage] = []
        for value in _iterate_value_objects(payload):
            inbound_rows = value.get("messages")
            if not isinstance(inbound_rows, list):
                continue
            profiles = _build_profile_lookup(value.get("contacts"))
            metadata = _as_record(value.get("metadata"))
            for row in inbound_rows:
                message = _build_inbound_message(
                    provider_name=self.provider_name,
                    payload=row,
                    profiles=profiles,
                    webhook_metadata=metadata,
                )
                if message is not None:
                    messages.append(message)
        return messages

    def parse_event(self, payload: Mapping[str, Any]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_message(
        self, payload: Mapping[str, Any]
    ) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    @classmethod
    def _from_env_kwargs(
        cls,
        *,
        prefix: str,
        env: EnvLike | None,
        api_version: str | None,
        base_url: str | None,
        timeout_seconds: float | None,
        default_headers: Mapping[str, str] | None,
        retry: object,
        hooks: object,
    ) -> dict[str, Any]:
        return {
            "access_token": get_required_env(f"{prefix}ACCESS_TOKEN", env),
            "phone_number_id": get_required_env(f"{prefix}PHONE_NUMBER_ID", env),
            "whatsapp_business_account_id": get_optional_env(
                f"{prefix}WHATSAPP_BUSINESS_ACCOUNT_ID", env
            ),
            "app_secret": get_optional_env(f"{prefix}APP_SECRET", env),
            "webhook_verify_token": get_optional_env(f"{prefix}WEBHOOK_VERIFY_TOKEN", env),
            "api_version": api_version or get_optional_env(f"{prefix}API_VERSION", env),
            "base_url": base_url or get_optional_env(f"{prefix}BASE_URL", env),
            "timeout_seconds": timeout_seconds
            if timeout_seconds is not None
            else get_env_number(f"{prefix}TIMEOUT_SECONDS", env),
            "default_headers": default_headers,
            "retry": retry,
            "hooks": hooks,
        }


class MetaWhatsAppClient(_MetaWhatsAppClientBase):
    """Synchronous Meta WhatsApp Cloud API client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = HttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "META_WHATSAPP_",
        env: EnvLike | None = None,
        api_version: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> MetaWhatsAppClient:
        return cls(
            client=client,
            **cls._from_env_kwargs(
                prefix=prefix,
                env=env,
                api_version=api_version,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                default_headers=default_headers,
                retry=retry,
                hooks=hooks,
            )
        )

    def _request(
        self,
        path: str,
        method: str,
        *,
        body: object = None,
        form: Mapping[str, str] | None = None,
        files: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                body=body,
                form=form,
                files=files,
                query=query,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _validate_response(self.provider_name, response)

    def _send(
        self, recipient: str, payload: Mapping[str, Any], options: RequestOptions | None
    ) -> WhatsAppSendResult:
        response = self._request(self._messages_path(), "POST", body=payload, options=options)
        return _build_send_result(self.provider_name, recipient, response)

    def send_text(
        self, request: WhatsAppTextRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_text_payload(request), options)

    def send_template(
        self, request: WhatsAppTemplateRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_template_payload(request), options)

    def send_media(
        self, request: WhatsAppMediaRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_media_payload(request), options)

    def send_location(
        self, request: WhatsAppLocationRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_location_payload(request), options)

    def send_contacts(
        self, request: WhatsAppContactsRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_contacts_payload(request), options)

    def send_reaction(
        self, request: WhatsAppReactionRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_reaction_payload(request), options)

    def send_interactive(
        self, request: WhatsAppInteractiveRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_interactive_payload(request), options)

    def send_catalog(
        self, request: WhatsAppCatalogMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_catalog_message_payload(request), options)

    def send_product(
        self, request: WhatsAppProductMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_product_message_payload(request), options)

    def send_product_list(
        self, request: WhatsAppProductListRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_product_list_payload(request), options)

    def send_flow(
        self, request: WhatsAppFlowMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return self._send(request.recipient, _build_flow_message_payload(request), options)

    def mark_message_read(
        self, request: WhatsAppReadRequest, options: RequestOptions | None = None
    ) -> WhatsAppStatusResult:
        response = self._request(
            self._messages_path(), "POST", body=_build_read_payload(request, False), options=options
        )
        return _build_status_result(self.provider_name, request.message_id, response)

    def send_typing_indicator(
        self, request: WhatsAppReadRequest, options: RequestOptions | None = None
    ) -> WhatsAppStatusResult:
        response = self._request(
            self._messages_path(), "POST", body=_build_read_payload(request, True), options=options
        )
        return _build_status_result(self.provider_name, request.message_id, response)

    def upload_media(
        self, request: WhatsAppMediaUploadRequest, options: RequestOptions | None = None
    ) -> WhatsAppMediaUploadResult:
        form, files = _build_media_upload(request)
        response = self._request(
            self._media_upload_path(), "POST", form=form, files=files, options=options
        )
        return _build_media_upload_result(self.provider_name, response)

    def get_media(
        self, media_id: str, options: RequestOptions | None = None
    ) -> WhatsAppMediaInfo:
        normalized_media_id = require_string(media_id, "media_id")
        response = self._request(
            self._media_path(normalized_media_id), "GET", query=self._media_query(), options=options
        )
        return _build_media_info(self.provider_name, normalized_media_id, response)

    def delete_media(
        self, media_id: str, options: RequestOptions | None = None
    ) -> WhatsAppMediaDeleteResult:
        normalized_media_id = require_string(media_id, "media_id")
        response = self._request(
            self._media_path(normalized_media_id), "DELETE",
            query=self._media_query(), options=options,
        )
        return _build_media_delete_result(self.provider_name, normalized_media_id, response)

    def list_templates(
        self, request: WhatsAppTemplateListRequest | None = None,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        response = self._request(
            self._template_collection_path(), "GET",
            query=_build_template_list_query(request), options=options,
        )
        return _build_template_list_result(self.provider_name, response)

    def get_template(
        self, template_id: str, fields: list[str] | None = None,
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        response = self._request(
            self._template_path(template_id), "GET",
            query=_build_template_fields_query(fields or []), options=options,
        )
        template = _build_managed_template(self.provider_name, response)
        if template is None:
            raise ProviderError(
                "Meta WhatsApp template lookup did not return a template id.",
                provider=self.provider_name,
                response_body=response,
            )
        return template

    def create_template(
        self, request: WhatsAppTemplateCreateRequest, options: RequestOptions | None = None
    ) -> WhatsAppTemplateMutationResult:
        response = self._request(
            self._template_collection_path(), "POST",
            body=_build_template_create_payload(request), options=options,
        )
        return _build_template_mutation_result(self.provider_name, response)

    def update_template(
        self, template_id: str, request: WhatsAppTemplateUpdateRequest,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        normalized_template_id = require_string(template_id, "template_id")
        response = self._request(
            self._template_path(normalized_template_id), "POST",
            body=_build_template_update_payload(request), options=options,
        )
        return _build_template_mutation_result(
            self.provider_name, response, normalized_template_id
        )

    def delete_template(
        self, request: WhatsAppTemplateDeleteRequest, options: RequestOptions | None = None
    ) -> WhatsAppTemplateDeleteResult:
        response = self._request(
            self._template_collection_path(), "DELETE",
            query=_build_template_delete_query(request), options=options,
        )
        return _build_template_delete_result(self.provider_name, request, response)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MetaWhatsAppClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class AsyncMetaWhatsAppClient(_MetaWhatsAppClientBase):
    """Asynchronous Meta WhatsApp Cloud API client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = AsyncHttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "META_WHATSAPP_",
        env: EnvLike | None = None,
        api_version: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> AsyncMetaWhatsAppClient:
        return cls(
            client=client,
            **cls._from_env_kwargs(
                prefix=prefix,
                env=env,
                api_version=api_version,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                default_headers=default_headers,
                retry=retry,
                hooks=hooks,
            )
        )

    async def _request(
        self,
        path: str,
        method: str,
        *,
        body: object = None,
        form: Mapping[str, str] | None = None,
        files: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = await self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                body=body,
                form=form,
                files=files,
                query=query,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _validate_response(self.provider_name, response)

    async def _send(
        self, recipient: str, payload: Mapping[str, Any], options: RequestOptions | None
    ) -> WhatsAppSendResult:
        response = await self._request(
            self._messages_path(), "POST", body=payload, options=options
        )
        return _build_send_result(self.provider_name, recipient, response)

    async def send_text(
        self, request: WhatsAppTextRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_text_payload(request), options)

    async def send_template(
        self, request: WhatsAppTemplateRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_template_payload(request), options)

    async def send_media(
        self, request: WhatsAppMediaRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_media_payload(request), options)

    async def send_location(
        self, request: WhatsAppLocationRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_location_payload(request), options)

    async def send_contacts(
        self, request: WhatsAppContactsRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_contacts_payload(request), options)

    async def send_reaction(
        self, request: WhatsAppReactionRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_reaction_payload(request), options)

    async def send_interactive(
        self, request: WhatsAppInteractiveRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_interactive_payload(request), options)

    async def send_catalog(
        self, request: WhatsAppCatalogMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_catalog_message_payload(request), options)

    async def send_product(
        self, request: WhatsAppProductMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_product_message_payload(request), options)

    async def send_product_list(
        self, request: WhatsAppProductListRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_product_list_payload(request), options)

    async def send_flow(
        self, request: WhatsAppFlowMessageRequest, options: RequestOptions | None = None
    ) -> WhatsAppSendResult:
        return await self._send(request.recipient, _build_flow_message_payload(request), options)

    async def mark_message_read(
        self, request: WhatsAppReadRequest, options: RequestOptions | None = None
    ) -> WhatsAppStatusResult:
        response = await self._request(
            self._messages_path(), "POST", body=_build_read_payload(request, False), options=options
        )
        return _build_status_result(self.provider_name, request.message_id, response)

    async def send_typing_indicator(
        self, request: WhatsAppReadRequest, options: RequestOptions | None = None
    ) -> WhatsAppStatusResult:
        response = await self._request(
            self._messages_path(), "POST", body=_build_read_payload(request, True), options=options
        )
        return _build_status_result(self.provider_name, request.message_id, response)

    async def upload_media(
        self, request: WhatsAppMediaUploadRequest, options: RequestOptions | None = None
    ) -> WhatsAppMediaUploadResult:
        form, files = _build_media_upload(request)
        response = await self._request(
            self._media_upload_path(), "POST", form=form, files=files, options=options
        )
        return _build_media_upload_result(self.provider_name, response)

    async def get_media(
        self, media_id: str, options: RequestOptions | None = None
    ) -> WhatsAppMediaInfo:
        normalized_media_id = require_string(media_id, "media_id")
        response = await self._request(
            self._media_path(normalized_media_id), "GET", query=self._media_query(), options=options
        )
        return _build_media_info(self.provider_name, normalized_media_id, response)

    async def delete_media(
        self, media_id: str, options: RequestOptions | None = None
    ) -> WhatsAppMediaDeleteResult:
        normalized_media_id = require_string(media_id, "media_id")
        response = await self._request(
            self._media_path(normalized_media_id), "DELETE",
            query=self._media_query(), options=options,
        )
        return _build_media_delete_result(self.provider_name, normalized_media_id, response)

    async def list_templates(
        self, request: WhatsAppTemplateListRequest | None = None,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        response = await self._request(
            self._template_collection_path(), "GET",
            query=_build_template_list_query(request), options=options,
        )
        return _build_template_list_result(self.provider_name, response)

    async def get_template(
        self, template_id: str, fields: list[str] | None = None,
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        response = await self._request(
            self._template_path(template_id), "GET",
            query=_build_template_fields_query(fields or []), options=options,
        )
        template = _build_managed_template(self.provider_name, response)
        if template is None:
            raise ProviderError(
                "Meta WhatsApp template lookup did not return a template id.",
                provider=self.provider_name,
                response_body=response,
            )
        return template

    async def create_template(
        self, request: WhatsAppTemplateCreateRequest, options: RequestOptions | None = None
    ) -> WhatsAppTemplateMutationResult:
        response = await self._request(
            self._template_collection_path(), "POST",
            body=_build_template_create_payload(request), options=options,
        )
        return _build_template_mutation_result(self.provider_name, response)

    async def update_template(
        self, template_id: str, request: WhatsAppTemplateUpdateRequest,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        normalized_template_id = require_string(template_id, "template_id")
        response = await self._request(
            self._template_path(normalized_template_id), "POST",
            body=_build_template_update_payload(request), options=options,
        )
        return _build_template_mutation_result(
            self.provider_name, response, normalized_template_id
        )

    async def delete_template(
        self, request: WhatsAppTemplateDeleteRequest, options: RequestOptions | None = None
    ) -> WhatsAppTemplateDeleteResult:
        response = await self._request(
            self._template_collection_path(), "DELETE",
            query=_build_template_delete_query(request), options=options,
        )
        return _build_template_delete_result(self.provider_name, request, response)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncMetaWhatsAppClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# Media upload + result builders
# --------------------------------------------------------------------------- #


def _build_media_upload(
    request: WhatsAppMediaUploadRequest,
) -> tuple[dict[str, str], dict[str, Any]]:
    mime_type = require_string(request.mime_type, "mime_type")
    filename = require_string(request.filename, "filename")

    form: dict[str, str] = {}
    for key, value in (request.provider_options or {}).items():
        form[key] = require_string(coerce_string(value), f"provider_options[{key}]")

    form["messaging_product"] = "whatsapp"
    form["type"] = mime_type
    files = {"file": (filename, bytes(request.content), mime_type)}
    return form, files


def _build_media_upload_result(
    provider_name: str, response: Mapping[str, Any]
) -> WhatsAppMediaUploadResult:
    media_id = coerce_string(response.get("id"))
    if media_id is None:
        raise ProviderError(
            "Meta media upload did not return a media id.",
            provider=provider_name,
            response_body=response,
        )
    return WhatsAppMediaUploadResult(provider=provider_name, media_id=media_id, raw=response)


def _build_status_result(
    provider_name: str, message_id: str, response: Mapping[str, Any]
) -> WhatsAppStatusResult:
    return WhatsAppStatusResult(
        provider=provider_name,
        success=bool(response.get("success")),
        message_id=message_id,
        raw=response,
    )


def _build_media_info(
    provider_name: str, media_id: str, response: Mapping[str, Any]
) -> WhatsAppMediaInfo:
    return WhatsAppMediaInfo(
        provider=provider_name,
        media_id=coerce_string(response.get("id")) or media_id,
        url=coerce_string(response.get("url")),
        mime_type=coerce_string(response.get("mime_type")),
        sha256=coerce_string(response.get("sha256")),
        file_size=coerce_int(response.get("file_size")),
        raw=response,
    )


def _build_media_delete_result(
    provider_name: str, media_id: str, response: Mapping[str, Any]
) -> WhatsAppMediaDeleteResult:
    return WhatsAppMediaDeleteResult(
        provider=provider_name,
        media_id=media_id,
        deleted=bool(response.get("success")),
        raw=response,
    )


# --------------------------------------------------------------------------- #
# Template management builders/parsers
# --------------------------------------------------------------------------- #


def _build_template_list_query(
    request: WhatsAppTemplateListRequest | None,
) -> dict[str, str] | None:
    if request is None:
        return None

    query: dict[str, str] = {}
    for key, value in (request.provider_options or {}).items():
        query[key] = require_string(coerce_string(value), f"provider_options[{key}]")

    _set_query_value(query, "category", request.category, uppercase=True)
    _set_query_value(query, "content", request.content)
    _set_query_value(query, "language", request.language)
    _set_query_value(query, "name", request.name)
    _set_query_value(query, "name_or_content", request.name_or_content)
    _set_query_value(query, "quality_score", request.quality_score, uppercase=True)
    _set_query_value(query, "since", request.since)
    _set_query_value(query, "status", request.status, uppercase=True)
    _set_query_value(query, "until", request.until)
    _set_query_value(query, "fields", request.fields)
    _set_query_value(query, "limit", request.limit)
    _set_query_value(query, "before", request.before)
    _set_query_value(query, "after", request.after)

    if request.summary_fields:
        joined = ",".join(request.summary_fields)
        query["fields"] = f"{query['fields']},{joined}" if query.get("fields") else joined
        query["include_template_quality"] = "true"

    return query or None


def _build_template_fields_query(fields: list[str]) -> dict[str, str] | None:
    return {"fields": ",".join(fields)} if fields else None


def _build_template_create_payload(
    request: WhatsAppTemplateCreateRequest,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(dict(request.provider_options) if request.provider_options else {}),
        "name": require_string(request.name, "name"),
        "language": require_string(request.language, "language"),
        "category": _normalize_template_enum(request.category, "category"),
    }

    if request.components:
        payload["components"] = [
            _build_template_component_definition(component) for component in request.components
        ]

    if request.allow_category_change is not None:
        payload["allow_category_change"] = request.allow_category_change

    if request.parameter_format:
        payload["parameter_format"] = request.parameter_format

    if request.sub_category:
        payload["sub_category"] = request.sub_category

    if request.message_send_ttl_seconds is not None:
        payload["message_send_ttl_seconds"] = request.message_send_ttl_seconds

    if request.library_template_name:
        payload["library_template_name"] = request.library_template_name

    if request.is_primary_device_delivery_only is not None:
        payload["is_primary_device_delivery_only"] = request.is_primary_device_delivery_only

    if request.creative_sourcing_spec:
        payload["creative_sourcing_spec"] = request.creative_sourcing_spec

    if request.library_template_body_inputs:
        payload["library_template_body_inputs"] = request.library_template_body_inputs

    if request.library_template_button_inputs:
        payload["library_template_button_inputs"] = request.library_template_button_inputs

    return payload


def _build_template_update_payload(
    request: WhatsAppTemplateUpdateRequest,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(dict(request.provider_options) if request.provider_options else {})
    }

    if request.category:
        payload["category"] = _normalize_template_enum(request.category, "category")

    if request.components:
        payload["components"] = [
            _build_template_component_definition(component) for component in request.components
        ]

    if request.parameter_format:
        payload["parameter_format"] = request.parameter_format

    if request.message_send_ttl_seconds is not None:
        payload["message_send_ttl_seconds"] = request.message_send_ttl_seconds

    if request.creative_sourcing_spec:
        payload["creative_sourcing_spec"] = request.creative_sourcing_spec

    return payload


def _build_template_delete_query(
    request: WhatsAppTemplateDeleteRequest,
) -> dict[str, str]:
    query: dict[str, str] = {}
    for key, value in (request.provider_options or {}).items():
        query[key] = require_string(coerce_string(value), f"provider_options[{key}]")

    _set_query_value(query, "name", request.name)
    _set_query_value(query, "hsm_id", request.template_id)
    _set_query_value(query, "template_ids", request.template_ids)
    return query


def _build_template_component_definition(
    component: WhatsAppTemplateComponentDefinition,
) -> dict[str, Any]:
    return compact_record(
        {
            **(dict(component.provider_options) if component.provider_options else {}),
            "type": require_string(component.type, "components[].type"),
            "format": coerce_string(component.format),
            "text": coerce_string(component.text),
            "buttons": [
                _build_template_button_definition(button) for button in component.buttons
            ]
            if component.buttons
            else None,
            "example": dict(component.example)
            if component.example and len(component.example)
            else None,
        }
    )


def _build_template_button_definition(
    button: WhatsAppTemplateButtonDefinition,
) -> dict[str, Any]:
    return compact_record(
        {
            **(dict(button.provider_options) if button.provider_options else {}),
            "type": require_string(button.type, "buttons[].type"),
            "text": coerce_string(button.text),
            "phone_number": coerce_string(button.phone_number),
            "url": coerce_string(button.url),
            "example": list(button.example) if button.example else None,
            "flow_id": coerce_string(button.flow_id),
            "flow_name": coerce_string(button.flow_name),
            "flow_json": coerce_string(button.flow_json),
            "flow_action": coerce_string(button.flow_action),
            "navigate_screen": coerce_string(button.navigate_screen),
            "otp_type": coerce_string(button.otp_type),
            "zero_tap_terms_accepted": button.zero_tap_terms_accepted,
            "supported_apps": list(button.supported_apps) if button.supported_apps else None,
        }
    )


def _build_template_list_result(
    provider_name: str, response: Mapping[str, Any]
) -> WhatsAppTemplateListResult:
    data = response.get("data") if isinstance(response.get("data"), list) else []
    paging = _as_record(response.get("paging"))
    cursors = _as_record(paging.get("cursors"))

    templates = [
        template
        for template in (_build_managed_template(provider_name, _as_record(row)) for row in data)
        if template is not None
    ]

    return WhatsAppTemplateListResult(
        provider=provider_name,
        templates=templates,
        before=coerce_string(cursors.get("before")),
        after=coerce_string(cursors.get("after")),
        summary=_build_template_list_summary(response.get("summary")),
        raw=response,
    )


def _build_template_list_summary(value: object) -> WhatsAppTemplateListSummary | None:
    payload = _as_record(value)
    if not payload:
        return None

    return WhatsAppTemplateListSummary(
        total_count=coerce_int(payload.get("total_count")),
        message_template_count=coerce_int(payload.get("message_template_count")),
        message_template_limit=coerce_int(payload.get("message_template_limit")),
        are_translations_complete=payload.get("are_translations_complete")
        if isinstance(payload.get("are_translations_complete"), bool)
        else None,
        raw=payload,
    )


def _build_managed_template(
    provider_name: str, payload: Mapping[str, Any]
) -> WhatsAppManagedTemplate | None:
    template_id = coerce_string(payload.get("id"))
    if template_id is None:
        return None

    return WhatsAppManagedTemplate(
        provider=provider_name,
        template_id=template_id,
        name=coerce_string(payload.get("name")),
        language=coerce_string(payload.get("language")),
        category=coerce_string(payload.get("category")),
        status=coerce_string(payload.get("status")),
        components=[
            _parse_template_component_definition(component)
            for component in _normalize_rows(payload.get("components"))
        ],
        parameter_format=coerce_string(payload.get("parameter_format")),
        sub_category=coerce_string(payload.get("sub_category")),
        previous_category=coerce_string(payload.get("previous_category")),
        correct_category=coerce_string(payload.get("correct_category")),
        rejected_reason=coerce_string(payload.get("rejected_reason")),
        quality_score=coerce_string(payload.get("quality_score")),
        cta_url_link_tracking_opted_out=payload.get("cta_url_link_tracking_opted_out")
        if isinstance(payload.get("cta_url_link_tracking_opted_out"), bool)
        else None,
        library_template_name=coerce_string(payload.get("library_template_name")),
        message_send_ttl_seconds=coerce_int(payload.get("message_send_ttl_seconds")),
        metadata=compact_record(
            {
                "previousCategory": coerce_string(payload.get("previous_category")),
                "correctCategory": coerce_string(payload.get("correct_category")),
            }
        ),
        raw=payload,
    )


def _parse_template_component_definition(
    payload: Mapping[str, Any],
) -> WhatsAppTemplateComponentDefinition:
    return WhatsAppTemplateComponentDefinition(
        type=coerce_string(payload.get("type")) or "",
        format=coerce_string(payload.get("format")),
        text=coerce_string(payload.get("text")),
        buttons=[
            _parse_template_button_definition(button)
            for button in _normalize_rows(payload.get("buttons"))
        ],
        example=_as_record(payload.get("example")),
        provider_options={},
    )


def _parse_template_button_definition(
    payload: Mapping[str, Any],
) -> WhatsAppTemplateButtonDefinition:
    example_value = payload.get("example")
    example = (
        [text for text in (coerce_string(item) for item in example_value) if text]
        if isinstance(example_value, list)
        else []
    )
    supported_apps_value = payload.get("supported_apps")
    supported_apps = (
        [item for item in supported_apps_value if isinstance(item, dict)]
        if isinstance(supported_apps_value, list)
        else []
    )

    return WhatsAppTemplateButtonDefinition(
        type=coerce_string(payload.get("type")) or "",
        text=coerce_string(payload.get("text")),
        phone_number=coerce_string(payload.get("phone_number")),
        url=coerce_string(payload.get("url")),
        example=example,
        flow_id=coerce_string(payload.get("flow_id")),
        flow_name=coerce_string(payload.get("flow_name")),
        flow_json=coerce_string(payload.get("flow_json")),
        flow_action=coerce_string(payload.get("flow_action")),
        navigate_screen=coerce_string(payload.get("navigate_screen")),
        otp_type=coerce_string(payload.get("otp_type")),
        zero_tap_terms_accepted=payload.get("zero_tap_terms_accepted")
        if isinstance(payload.get("zero_tap_terms_accepted"), bool)
        else None,
        supported_apps=supported_apps,
        provider_options={},
    )


def _build_template_mutation_result(
    provider_name: str, response: Mapping[str, Any], fallback_template_id: str | None = None
) -> WhatsAppTemplateMutationResult:
    return WhatsAppTemplateMutationResult(
        provider=provider_name,
        success=True,
        template_id=coerce_string(response.get("id")) or fallback_template_id,
        name=coerce_string(response.get("name")),
        category=coerce_string(response.get("category")),
        status=coerce_string(response.get("status")),
        raw=response,
    )


def _build_template_delete_result(
    provider_name: str, request: WhatsAppTemplateDeleteRequest, response: Mapping[str, Any]
) -> WhatsAppTemplateDeleteResult:
    return WhatsAppTemplateDeleteResult(
        provider=provider_name,
        deleted=bool(response.get("success")),
        name=coerce_string(request.name),
        template_id=coerce_string(request.template_id),
        template_ids=list(request.template_ids) if request.template_ids else [],
        raw=response,
    )


# --------------------------------------------------------------------------- #
# Outbound message payload builders
# --------------------------------------------------------------------------- #


def _build_text_payload(request: WhatsAppTextRequest) -> dict[str, Any]:
    body: dict[str, Any] = {"body": require_string(request.text, "text")}
    if request.preview_url is not None:
        body["preview_url"] = request.preview_url

    return _build_message_payload(
        recipient=request.recipient,
        message_type="text",
        message_body=body,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_template_payload(request: WhatsAppTemplateRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": require_string(request.template_name, "template_name"),
        "language": {"code": require_string(request.language_code, "language_code")},
    }

    if request.components:
        payload["components"] = [
            _build_template_component(component) for component in request.components
        ]

    return _build_message_payload(
        recipient=request.recipient,
        message_type="template",
        message_body=payload,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_media_payload(request: WhatsAppMediaRequest) -> dict[str, Any]:
    media_payload = _build_media_object(
        media_id=request.media_id, link=request.link, field_name="media"
    )

    if request.caption and request.media_type in ("image", "video", "document"):
        media_payload["caption"] = request.caption

    if request.filename and request.media_type == "document":
        media_payload["filename"] = request.filename

    return _build_message_payload(
        recipient=request.recipient,
        message_type=request.media_type,
        message_body=media_payload,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_location_payload(request: WhatsAppLocationRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="location",
        message_body=compact_record(
            {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "name": coerce_string(request.name),
                "address": coerce_string(request.address),
            }
        ),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_contacts_payload(request: WhatsAppContactsRequest) -> dict[str, Any]:
    if not request.contacts:
        raise ValueError("contacts must not be empty.")

    return _build_message_payload(
        recipient=request.recipient,
        message_type="contacts",
        message_body=[_build_contact(contact) for contact in request.contacts],
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_reaction_payload(request: WhatsAppReactionRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="reaction",
        message_body={
            "message_id": require_string(request.message_id, "message_id"),
            "emoji": require_string(request.emoji, "emoji"),
        },
        provider_options=request.provider_options,
    )


def _build_interactive_payload(request: WhatsAppInteractiveRequest) -> dict[str, Any]:
    interactive: dict[str, Any] = {
        "type": request.interactive_type,
        "body": {"text": require_string(request.body_text, "body_text")},
    }

    if request.header:
        interactive["header"] = _build_interactive_header(request.header)

    if request.footer_text:
        interactive["footer"] = {"text": request.footer_text}

    if request.interactive_type == "button":
        if not request.buttons:
            raise ValueError("buttons must not be empty for button interactive messages.")
        interactive["action"] = {
            "buttons": [_build_interactive_button(button) for button in request.buttons]
        }
    else:
        sections = [_build_interactive_section(section) for section in (request.sections or [])]
        if not sections:
            raise ValueError("sections must not be empty for list interactive messages.")
        interactive["action"] = {
            "button": require_string(request.button_text, "button_text"),
            "sections": sections,
        }

    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_catalog_message_payload(request: WhatsAppCatalogMessageRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=_build_catalog_interactive_payload(request),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_product_message_payload(request: WhatsAppProductMessageRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=_build_product_interactive_payload(request),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_product_list_payload(request: WhatsAppProductListRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=_build_product_list_interactive_payload(request),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_flow_message_payload(request: WhatsAppFlowMessageRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=_build_flow_interactive_payload(request),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_read_payload(
    request: WhatsAppReadRequest, include_typing_indicator: bool
) -> dict[str, Any]:
    return compact_record(
        {
            **(dict(request.provider_options) if request.provider_options else {}),
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": require_string(request.message_id, "message_id"),
            "typing_indicator": {"type": request.typing_indicator_type or "text"}
            if include_typing_indicator
            else None,
        }
    )


def _build_message_payload(
    *,
    recipient: str,
    message_type: str,
    message_body: object,
    reply_to_message_id: str | None = None,
    provider_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(dict(provider_options) if provider_options else {}),
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": require_string(recipient, "recipient"),
        "type": message_type,
        message_type: message_body,
    }

    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}

    return payload


def _build_template_component(component: WhatsAppTemplateComponent) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": component.type}

    if component.sub_type:
        payload["sub_type"] = component.sub_type

    if component.index is not None:
        payload["index"] = component.index

    if component.parameters:
        payload["parameters"] = [
            _build_template_parameter(parameter) for parameter in component.parameters
        ]

    return payload


def _build_template_parameter(parameter: WhatsAppTemplateParameter) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(dict(parameter.provider_options) if parameter.provider_options else {}),
        "type": parameter.type,
    }

    if parameter.value is not None:
        if parameter.type == "text":
            payload["text"] = parameter.value
        elif parameter.type == "payload":
            payload["payload"] = parameter.value
        elif parameter.type in ("image", "video", "document"):
            if not payload.get(parameter.type):
                payload[parameter.type] = {"id": parameter.value}
        elif "text" not in payload:
            payload["text"] = parameter.value

    return payload


def _build_media_object(
    *, media_id: str | None, link: str | None, field_name: str
) -> dict[str, str]:
    normalized_media_id = coerce_string(media_id)
    normalized_link = coerce_string(link)

    if normalized_media_id and normalized_link:
        raise ValueError(f"{field_name} accepts either media_id or link, not both.")

    if not normalized_media_id and not normalized_link:
        raise ValueError(f"{field_name} requires either media_id or link.")

    return {"id": normalized_media_id} if normalized_media_id else {"link": normalized_link or ""}


def _build_contact(contact: WhatsAppContact) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": compact_record(
            {
                "formatted_name": require_string(
                    contact.name.formatted_name, "contacts[].name.formatted_name"
                ),
                "first_name": coerce_string(contact.name.first_name),
                "last_name": coerce_string(contact.name.last_name),
                "middle_name": coerce_string(contact.name.middle_name),
                "suffix": coerce_string(contact.name.suffix),
                "prefix": coerce_string(contact.name.prefix),
            }
        )
    }

    if contact.phones:
        payload["phones"] = [_build_contact_phone(phone) for phone in contact.phones]

    if contact.emails:
        payload["emails"] = [_build_contact_email(email) for email in contact.emails]

    if contact.urls:
        payload["urls"] = [_build_contact_url(url) for url in contact.urls]

    if contact.addresses:
        payload["addresses"] = [_build_contact_address(addr) for addr in contact.addresses]

    if contact.org:
        payload["org"] = _build_contact_org(contact.org)

    if contact.birthday:
        payload["birthday"] = contact.birthday

    return payload


def _build_contact_phone(phone: WhatsAppContactPhone) -> dict[str, Any]:
    return compact_record(
        {
            "phone": require_string(phone.phone, "contacts[].phones[].phone"),
            "type": coerce_string(phone.type),
            "wa_id": coerce_string(phone.wa_id),
        }
    )


def _build_contact_email(email: WhatsAppContactEmail) -> dict[str, Any]:
    return compact_record(
        {
            "email": require_string(email.email, "contacts[].emails[].email"),
            "type": coerce_string(email.type),
        }
    )


def _build_contact_url(url: WhatsAppContactUrl) -> dict[str, Any]:
    return compact_record(
        {
            "url": require_string(url.url, "contacts[].urls[].url"),
            "type": coerce_string(url.type),
        }
    )


def _build_contact_address(address: WhatsAppContactAddress) -> dict[str, Any]:
    return compact_record(
        {
            "street": coerce_string(address.street),
            "city": coerce_string(address.city),
            "state": coerce_string(address.state),
            "zip": coerce_string(address.zip),
            "country": coerce_string(address.country),
            "country_code": coerce_string(address.country_code),
            "type": coerce_string(address.type),
        }
    )


def _build_contact_org(org: WhatsAppContactOrg) -> dict[str, Any]:
    return compact_record(
        {
            "company": coerce_string(org.company),
            "department": coerce_string(org.department),
            "title": coerce_string(org.title),
        }
    )


def _build_interactive_header(header: WhatsAppInteractiveHeader) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **(dict(header.provider_options) if header.provider_options else {}),
        "type": header.type,
    }

    if header.type == "text":
        payload["text"] = require_string(header.text, "header.text")
        return payload

    media_payload = _build_media_object(
        media_id=header.media_id, link=header.link, field_name="header"
    )

    if header.filename and header.type == "document":
        media_payload["filename"] = header.filename

    payload[header.type] = media_payload
    return payload


def _build_interactive_button(button: WhatsAppInteractiveButton) -> dict[str, Any]:
    return {
        "type": "reply",
        "reply": {
            "id": require_string(button.identifier, "buttons[].identifier"),
            "title": require_string(button.title, "buttons[].title"),
        },
    }


def _build_interactive_section(section: WhatsAppInteractiveSection) -> dict[str, Any]:
    if not section.rows:
        raise ValueError("sections[].rows must not be empty.")

    return compact_record(
        {
            "title": coerce_string(section.title),
            "rows": [_build_interactive_row(row) for row in section.rows],
        }
    )


def _build_interactive_row(row: WhatsAppInteractiveRow) -> dict[str, Any]:
    return compact_record(
        {
            "id": require_string(row.identifier, "sections[].rows[].identifier"),
            "title": require_string(row.title, "sections[].rows[].title"),
            "description": coerce_string(row.description),
        }
    )


def _build_catalog_interactive_payload(
    request: WhatsAppCatalogMessageRequest,
) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="catalog_message",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )

    action: dict[str, Any] = {"name": "catalog_message"}

    if request.thumbnail_product_retailer_id:
        action["parameters"] = {
            "thumbnail_product_retailer_id": require_string(
                request.thumbnail_product_retailer_id, "thumbnail_product_retailer_id"
            )
        }

    interactive["action"] = action
    return interactive


def _build_product_interactive_payload(
    request: WhatsAppProductMessageRequest,
) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="product",
        body_text=request.body_text,
        footer_text=request.footer_text,
    )

    interactive["action"] = {
        "catalog_id": require_string(request.catalog_id, "catalog_id"),
        "product_retailer_id": require_string(request.product_retailer_id, "product_retailer_id"),
    }

    return interactive


def _build_product_list_interactive_payload(
    request: WhatsAppProductListRequest,
) -> dict[str, Any]:
    sections = [_build_product_section(section) for section in request.sections]

    if not sections:
        raise ValueError("sections must not be empty for productList interactive messages.")

    if not request.header:
        raise ValueError("header is required for productList interactive messages.")

    interactive = _build_common_interactive_payload(
        interactive_type="product_list",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )

    interactive["action"] = {
        "catalog_id": require_string(request.catalog_id, "catalog_id"),
        "sections": sections,
    }

    return interactive


def _build_flow_interactive_payload(request: WhatsAppFlowMessageRequest) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="flow",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )

    parameters: dict[str, Any] = compact_record(
        {
            "flow_message_version": require_string(
                request.flow_message_version or "3", "flow_message_version"
            ),
            "flow_token": coerce_string(request.flow_token),
            "flow_id": coerce_string(request.flow_id),
            "flow_name": coerce_string(request.flow_name),
            "flow_cta": require_string(request.flow_cta, "flow_cta"),
            "flow_action": require_string(request.flow_action or "navigate", "flow_action"),
        }
    )

    if bool(parameters.get("flow_id")) == bool(parameters.get("flow_name")):
        raise ValueError("flow messages require exactly one of flow_id or flow_name.")

    if request.flow_action_payload:
        parameters["flow_action_payload"] = request.flow_action_payload

    interactive["action"] = {"name": "flow", "parameters": parameters}
    return interactive


def _build_common_interactive_payload(
    *,
    interactive_type: str,
    body_text: str | None = None,
    header: WhatsAppInteractiveHeader | None = None,
    footer_text: str | None = None,
) -> dict[str, Any]:
    interactive: dict[str, Any] = {"type": interactive_type}

    if body_text:
        interactive["body"] = {"text": require_string(body_text, "body_text")}

    if header:
        interactive["header"] = _build_interactive_header(header)

    if footer_text:
        interactive["footer"] = {"text": footer_text}

    return interactive


def _build_product_section(section: WhatsAppProductSection) -> dict[str, Any]:
    if not section.product_items:
        raise ValueError("sections[].product_items must not be empty.")

    return {
        "title": require_string(section.title, "sections[].title"),
        "product_items": [_build_product_item(item) for item in section.product_items],
    }


def _build_product_item(item: WhatsAppProductItem) -> dict[str, Any]:
    return {
        "product_retailer_id": require_string(
            item.product_retailer_id, "sections[].product_items[].product_retailer_id"
        )
    }


# --------------------------------------------------------------------------- #
# Webhook / inbound parsing
# --------------------------------------------------------------------------- #


def _iterate_value_objects(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = _as_record(payload)
    entries = root.get("entry") if isinstance(root.get("entry"), list) else []
    values: list[dict[str, Any]] = []

    for entry in entries:
        raw_changes = _as_record(entry).get("changes")
        changes = raw_changes if isinstance(raw_changes, list) else []
        for change in changes:
            values.append(_as_record(_as_record(change).get("value")))

    return values


def _build_profile_lookup(value: object) -> dict[str, str | None]:
    contacts = value if isinstance(value, list) else []
    profiles: dict[str, str | None] = {}

    for row in contacts:
        payload = _as_record(row)
        wa_id = coerce_string(payload.get("wa_id"))
        if wa_id:
            profiles[wa_id] = coerce_string(_as_record(payload.get("profile")).get("name"))

    return profiles


def _build_inbound_message(
    *,
    provider_name: str,
    payload: object,
    profiles: Mapping[str, str | None],
    webhook_metadata: Mapping[str, Any],
) -> WhatsAppInboundMessage | None:
    message = _as_record(payload)
    sender_id = coerce_string(message.get("from"))
    message_id = coerce_string(message.get("id"))

    if not sender_id or not message_id:
        return None

    raw_type = coerce_string(message.get("type")) or "unsupported"
    context = _as_record(message.get("context"))
    referral = _as_record(message.get("referral"))
    metadata: dict[str, Any] = compact_record(
        {
            "displayPhoneNumber": coerce_string(webhook_metadata.get("display_phone_number")),
            "phoneNumberId": coerce_string(webhook_metadata.get("phone_number_id")),
            "referral": referral if referral else None,
            "providerMessageType": raw_type if raw_type == "unsupported" else None,
        }
    )

    text: str | None = None
    media: WhatsAppInboundMedia | None = None
    location: WhatsAppInboundLocation | None = None
    contacts: list[WhatsAppContact] = []
    reply: WhatsAppInboundReply | None = None
    reaction: WhatsAppInboundReaction | None = None
    message_type = raw_type

    if raw_type == "text":
        text = coerce_string(_as_record(message.get("text")).get("body"))
    elif raw_type in MEDIA_TYPES:
        media = _build_inbound_media(raw_type, message.get(raw_type))
    elif raw_type == "location":
        location = _build_inbound_location(message.get("location"))
    elif raw_type == "contacts":
        contacts = _parse_contact_list(message.get("contacts"))
    elif raw_type == "button":
        reply = _build_button_reply(message.get("button"))
    elif raw_type == "interactive":
        reply = _build_interactive_reply(message.get("interactive"))
    elif raw_type == "reaction":
        reaction = _build_inbound_reaction(message.get("reaction"))
    else:
        message_type = "unsupported"
        metadata = {**metadata, "providerMessageType": raw_type}

    return WhatsAppInboundMessage(
        provider=provider_name,
        sender_id=sender_id,
        message_id=message_id,
        message_type=message_type,  # type: ignore[arg-type]
        timestamp=coerce_string(message.get("timestamp")),
        profile_name=profiles.get(sender_id),
        context_message_id=coerce_string(context.get("message_id")),
        forwarded=context.get("forwarded") if isinstance(context.get("forwarded"), bool) else None,
        frequently_forwarded=context.get("frequently_forwarded")
        if isinstance(context.get("frequently_forwarded"), bool)
        else None,
        text=text,
        media=media,
        location=location,
        contacts=contacts,
        reply=reply,
        reaction=reaction,
        metadata=metadata,
        raw=message,
    )


def _build_inbound_media(message_type: str, payload: object) -> WhatsAppInboundMedia | None:
    data = _as_record(payload)
    if not data:
        return None

    return WhatsAppInboundMedia(
        media_type=message_type,  # type: ignore[arg-type]
        media_id=coerce_string(data.get("id")),
        mime_type=coerce_string(data.get("mime_type")),
        sha256=coerce_string(data.get("sha256")),
        caption=coerce_string(data.get("caption")),
        filename=coerce_string(data.get("filename")),
        raw=data,
    )


def _build_inbound_location(payload: object) -> WhatsAppInboundLocation | None:
    data = _as_record(payload)
    if not data:
        return None

    return WhatsAppInboundLocation(
        latitude=coerce_number(data.get("latitude")),
        longitude=coerce_number(data.get("longitude")),
        name=coerce_string(data.get("name")),
        address=coerce_string(data.get("address")),
        url=coerce_string(data.get("url")),
        raw=data,
    )


def _build_button_reply(payload: object) -> WhatsAppInboundReply | None:
    data = _as_record(payload)
    if not data:
        return None

    return WhatsAppInboundReply(
        reply_type="button",
        payload=coerce_string(data.get("payload")),
        title=coerce_string(data.get("text")),
        raw=data,
    )


def _build_interactive_reply(payload: object) -> WhatsAppInboundReply | None:
    data = _as_record(payload)
    reply_type = coerce_string(data.get("type"))

    if reply_type == "button_reply":
        reply = _as_record(data.get("button_reply"))
        return WhatsAppInboundReply(
            reply_type="button_reply",
            identifier=coerce_string(reply.get("id")),
            title=coerce_string(reply.get("title")),
            raw=data,
        )

    if reply_type == "list_reply":
        reply = _as_record(data.get("list_reply"))
        return WhatsAppInboundReply(
            reply_type="list_reply",
            identifier=coerce_string(reply.get("id")),
            title=coerce_string(reply.get("title")),
            description=coerce_string(reply.get("description")),
            raw=data,
        )

    return None


def _build_inbound_reaction(payload: object) -> WhatsAppInboundReaction | None:
    data = _as_record(payload)
    if not data:
        return None

    return WhatsAppInboundReaction(
        emoji=coerce_string(data.get("emoji")),
        related_message_id=coerce_string(data.get("message_id")),
        raw=data,
    )


def _parse_contact_list(value: object) -> list[WhatsAppContact]:
    return [
        contact
        for contact in (_parse_contact(row) for row in _normalize_rows(value))
        if contact is not None
    ]


def _parse_contact(value: Mapping[str, Any]) -> WhatsAppContact | None:
    name_payload = _as_record(value.get("name"))
    formatted_name = coerce_string(name_payload.get("formatted_name"))

    if formatted_name is None:
        return None

    return WhatsAppContact(
        name=WhatsAppContactName(
            formatted_name=formatted_name,
            first_name=coerce_string(name_payload.get("first_name")),
            last_name=coerce_string(name_payload.get("last_name")),
            middle_name=coerce_string(name_payload.get("middle_name")),
            suffix=coerce_string(name_payload.get("suffix")),
            prefix=coerce_string(name_payload.get("prefix")),
        ),
        phones=[_parse_contact_phone(row) for row in _normalize_rows(value.get("phones"))],
        emails=[_parse_contact_email(row) for row in _normalize_rows(value.get("emails"))],
        urls=[_parse_contact_url(row) for row in _normalize_rows(value.get("urls"))],
        addresses=[
            _parse_contact_address(row) for row in _normalize_rows(value.get("addresses"))
        ],
        org=_parse_contact_org(value.get("org")),
        birthday=coerce_string(value.get("birthday")),
    )


def _parse_contact_phone(value: Mapping[str, Any]) -> WhatsAppContactPhone:
    return WhatsAppContactPhone(
        phone=coerce_string(value.get("phone")) or "",
        type=coerce_string(value.get("type")),
        wa_id=coerce_string(value.get("wa_id")),
    )


def _parse_contact_email(value: Mapping[str, Any]) -> WhatsAppContactEmail:
    return WhatsAppContactEmail(
        email=coerce_string(value.get("email")) or "",
        type=coerce_string(value.get("type")),
    )


def _parse_contact_url(value: Mapping[str, Any]) -> WhatsAppContactUrl:
    return WhatsAppContactUrl(
        url=coerce_string(value.get("url")) or "",
        type=coerce_string(value.get("type")),
    )


def _parse_contact_address(value: Mapping[str, Any]) -> WhatsAppContactAddress:
    return WhatsAppContactAddress(
        street=coerce_string(value.get("street")),
        city=coerce_string(value.get("city")),
        state=coerce_string(value.get("state")),
        zip=coerce_string(value.get("zip")),
        country=coerce_string(value.get("country")),
        country_code=coerce_string(value.get("country_code")),
        type=coerce_string(value.get("type")),
    )


def _parse_contact_org(value: object) -> WhatsAppContactOrg | None:
    payload = _as_record(value)
    if not payload:
        return None

    return WhatsAppContactOrg(
        company=coerce_string(payload.get("company")),
        department=coerce_string(payload.get("department")),
        title=coerce_string(payload.get("title")),
    )


def _build_status_event(provider_name: str, payload: object) -> DeliveryEvent | None:
    status = _as_record(payload)
    provider_message_id = coerce_string(status.get("id"))

    if provider_message_id is None:
        return None

    error = _first_mapping(status.get("errors"))
    conversation = _as_record(status.get("conversation"))
    pricing = _as_record(status.get("pricing"))
    provider_status = coerce_string(status.get("status"))

    return DeliveryEvent(
        channel="whatsapp",
        provider=provider_name,
        provider_message_id=provider_message_id,
        state=_map_whatsapp_state(provider_status),
        recipient=coerce_string(status.get("recipient_id")),
        provider_status=provider_status,
        error_code=coerce_string(error.get("code")),
        error_description=first_text(
            error.get("message"), error.get("title"), error.get("details")
        ),
        occurred_at=coerce_string(status.get("timestamp")),
        metadata=compact_record(
            {
                "conversationId": coerce_string(conversation.get("id")),
                "conversationOriginType": coerce_string(
                    _as_record(conversation.get("origin")).get("type")
                ),
                "pricingModel": coerce_string(pricing.get("pricing_model")),
                "billable": pricing.get("billable"),
                "category": coerce_string(pricing.get("category")),
            }
        ),
        raw=status,
    )


def _build_send_result(
    provider_name: str, recipient: str, response: Mapping[str, Any]
) -> WhatsAppSendResult:
    contact = _first_mapping(response.get("contacts"))
    message = _first_mapping(response.get("messages"))
    provider_message_id = coerce_string(message.get("id"))

    if provider_message_id is None:
        raise ProviderError(
            "Meta WhatsApp Cloud API did not return a message id.",
            provider=provider_name,
            response_body=response,
        )

    receipt = WhatsAppSendReceipt(
        provider=provider_name,
        recipient=coerce_string(contact.get("wa_id")) or recipient,
        status="submitted",
        provider_message_id=provider_message_id,
        provider_status=coerce_string(message.get("message_status")),
        raw=message if message else response,
    )

    return WhatsAppSendResult(
        provider=provider_name,
        accepted=True,
        messages=[receipt],
        submitted_count=1,
        failed_count=0,
        raw=response,
    )


def _validate_response(provider_name: str, response: object) -> dict[str, Any]:
    payload = to_object(response)
    if not payload:
        raise ProviderError(
            "Meta WhatsApp Cloud API returned a non-object response.",
            provider=provider_name,
            response_body=response,
        )

    error = _as_record(payload.get("error"))
    if error:
        description = (
            coerce_string(error.get("error_user_msg"))
            or coerce_string(error.get("message"))
            or "Provider request failed."
        )
        raise ProviderError(
            f"Meta WhatsApp request failed: {description}",
            provider=provider_name,
            error_code=coerce_string(error.get("code")),
            error_description=description,
            response_body=payload,
        )

    return payload


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #


def _first_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        return _as_record(value[0]) if value else {}
    return _as_record(value)


def _normalize_rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    return []


def _as_record(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _set_query_value(
    query: dict[str, str], key: str, value: object, *, uppercase: bool = False
) -> None:
    if value is None:
        return

    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        normalized = require_string(coerce_string(value), key)
        query[key] = normalized.upper() if uppercase else normalized
        return

    if isinstance(value, list):
        items = [require_string(coerce_string(item), f"{key}[]") for item in value]
        if not items:
            return
        joined = ",".join(item.upper() for item in items) if uppercase else ",".join(items)
        query[key] = joined
        return

    normalized = require_string(coerce_string(value), key)
    query[key] = normalized.upper() if uppercase else normalized


def _normalize_template_enum(value: str, field_name: str) -> str:
    return require_string(value, field_name).upper()


def _map_whatsapp_state(status: str | None) -> Any:
    normalized = (status or "").lower()

    if normalized in ("accepted", "sent"):
        return "submitted"

    if normalized in ("delivered", "read", "failed"):
        return normalized

    return "unknown"
