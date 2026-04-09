from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from .errors import StorageError

StorageProvider = str
StorageUrlStyle = str
StorageOperation = str
StorageKey = str | Sequence[object]
StorageMetadata = dict[str, str]
StorageTags = dict[str, str | int | bool]
StoragePresignHandler = Callable[[BaseClient, str, dict[str, Any], int], str]
ResolveKeyHook = Callable[[str, "StorageOperationContext"], str]
BuildPublicUrlHook = Callable[["ResolvedStoragePublicUrlInput"], str]

DEFAULT_S3_REGION = "us-east-1"
DEFAULT_R2_REGION = "auto"
DEFAULT_UPLOAD_EXPIRES_IN = 900
DEFAULT_DOWNLOAD_EXPIRES_IN = 3_600
MAX_PRESIGN_EXPIRES_IN = 604_800


@dataclass(slots=True)
class StorageOperationContext:
    operation: StorageOperation
    bucket: str
    provider: StorageProvider


@dataclass(slots=True)
class ResolvedStoragePublicUrlInput:
    bucket: str
    key: str
    provider: StorageProvider
    region: str
    endpoint: str | None
    account_id: str | None
    url_style: StorageUrlStyle
    public_base_url: str | None


@dataclass(slots=True)
class StorageObjectDescriptor:
    bucket: str
    key: str
    provider: StorageProvider
    public_url: str | None


@dataclass(slots=True)
class PutObjectResult(StorageObjectDescriptor):
    etag: str | None
    version_id: str | None
    checksum_crc32: str | None
    checksum_crc32c: str | None
    checksum_sha1: str | None
    checksum_sha256: str | None


@dataclass(slots=True)
class HeadObjectResult(StorageObjectDescriptor):
    exists: bool
    etag: str | None
    version_id: str | None
    last_modified: str | None
    expires_at: str | None
    content_length: int | None
    content_type: str | None
    cache_control: str | None
    content_disposition: str | None
    content_encoding: str | None
    content_language: str | None
    metadata: StorageMetadata
    raw: dict[str, Any]


@dataclass(slots=True)
class DeleteObjectResult(StorageObjectDescriptor):
    version_id: str | None
    delete_marker: bool
    raw: dict[str, Any]


@dataclass(slots=True)
class PresignedRequest(StorageObjectDescriptor):
    method: str
    url: str
    headers: dict[str, str]
    expires_in: int
    expires_at: str


class StorageClient:
    def __init__(
        self,
        *,
        bucket: str,
        provider: StorageProvider = "s3",
        region: str | None = None,
        endpoint: str | None = None,
        account_id: str | None = None,
        credentials: Mapping[str, str | None] | None = None,
        public_base_url: str | None = None,
        key_prefix: StorageKey | None = None,
        force_path_style: bool | None = None,
        url_style: StorageUrlStyle | None = None,
        default_metadata: Mapping[str, str] | None = None,
        default_tags: Mapping[str, str | int | bool] | None = None,
        default_content_type: str | None = None,
        default_cache_control: str | None = None,
        default_content_disposition: str | None = None,
        default_content_encoding: str | None = None,
        default_content_language: str | None = None,
        default_upload_expires_in: int = DEFAULT_UPLOAD_EXPIRES_IN,
        default_download_expires_in: int = DEFAULT_DOWNLOAD_EXPIRES_IN,
        client: BaseClient | None = None,
        presign_url: StoragePresignHandler | None = None,
        s3_client_config: Mapping[str, Any] | None = None,
        resolve_key: ResolveKeyHook | None = None,
        build_public_url: BuildPublicUrlHook | None = None,
    ) -> None:
        self.provider = provider
        self.bucket = _assert_bucket(bucket)
        self.region = _resolve_region(provider, region)
        self.account_id = _normalize_optional_value(account_id)
        self.endpoint = _resolve_endpoint(
            provider=provider, endpoint=endpoint, account_id=self.account_id
        )
        self.public_base_url = _normalize_optional_base_url(public_base_url)
        self.url_style = _resolve_url_style(provider, url_style, force_path_style)
        self.key_prefix = _normalize_optional_key(key_prefix)
        self.default_upload_expires_in = _validate_expires_in(
            default_upload_expires_in,
            "default_upload_expires_in",
        )
        self.default_download_expires_in = _validate_expires_in(
            default_download_expires_in,
            "default_download_expires_in",
        )
        self._defaults = {
            "metadata": dict(default_metadata or {}) or None,
            "tags": dict(default_tags or {}) or None,
            "content_type": _normalize_optional_value(default_content_type),
            "cache_control": _normalize_optional_value(default_cache_control),
            "content_disposition": _normalize_optional_value(default_content_disposition),
            "content_encoding": _normalize_optional_value(default_content_encoding),
            "content_language": _normalize_optional_value(default_content_language),
        }
        self._resolve_key_hook = resolve_key
        self._build_public_url_hook = build_public_url
        self._presign_url = presign_url or _default_presign_url
        self.client = client or self._build_client(credentials, s3_client_config)

    def _build_client(
        self,
        credentials: Mapping[str, str | None] | None,
        s3_client_config: Mapping[str, Any] | None,
    ) -> BaseClient:
        options = dict(s3_client_config or {})
        supplied_config = options.pop("config", None)
        base_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if self.url_style == "path" else "virtual"},
        )
        config = (
            supplied_config.merge(base_config)
            if isinstance(supplied_config, Config)
            else base_config
        )
        session = boto3.session.Session()
        return session.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint,
            aws_access_key_id=credentials.get("access_key_id") if credentials else None,
            aws_secret_access_key=credentials.get("secret_access_key") if credentials else None,
            aws_session_token=credentials.get("session_token") if credentials else None,
            config=config,
            **options,
        )

    def put_object(
        self,
        *,
        key: StorageKey,
        body: bytes | bytearray | str | Any,
        bucket: str | None = None,
        metadata: Mapping[str, str] | None = None,
        tags: Mapping[str, str | int | bool] | None = None,
        content_type: str | None = None,
        cache_control: str | None = None,
        content_disposition: str | None = None,
        content_encoding: str | None = None,
        content_language: str | None = None,
        content_md5: str | None = None,
        expires: datetime | None = None,
        public_url: bool = True,
        command_input: Mapping[str, Any] | None = None,
    ) -> PutObjectResult:
        resolved = self._resolve_target("putObject", key=key, bucket=bucket)
        command = _build_put_object_input(
            defaults=self._defaults,
            bucket=resolved["bucket"],
            key=resolved["key"],
            body=body,
            metadata=metadata,
            tags=tags,
            content_type=content_type,
            cache_control=cache_control,
            content_disposition=content_disposition,
            content_encoding=content_encoding,
            content_language=content_language,
            content_md5=content_md5,
            expires=expires,
            command_input=command_input,
        )
        try:
            output = self.client.put_object(**command)
            descriptor = self._describe_object(resolved["bucket"], resolved["key"], public_url)
            return PutObjectResult(
                bucket=descriptor.bucket,
                key=descriptor.key,
                provider=descriptor.provider,
                public_url=descriptor.public_url,
                etag=output.get("ETag"),
                version_id=output.get("VersionId"),
                checksum_crc32=output.get("ChecksumCRC32"),
                checksum_crc32c=output.get("ChecksumCRC32C"),
                checksum_sha1=output.get("ChecksumSHA1"),
                checksum_sha256=output.get("ChecksumSHA256"),
            )
        except Exception as error:
            raise self._wrap_error(
                "putObject", resolved["bucket"], resolved["key"], error, "Failed to store object."
            ) from error

    def head_object(
        self,
        *,
        key: StorageKey,
        bucket: str | None = None,
        not_found: str = "null",
        public_url: bool = True,
        command_input: Mapping[str, Any] | None = None,
    ) -> HeadObjectResult | None:
        resolved = self._resolve_target("headObject", key=key, bucket=bucket)
        command = dict(command_input or {})
        command["Bucket"] = resolved["bucket"]
        command["Key"] = resolved["key"]
        try:
            output = self.client.head_object(**command)
            descriptor = self._describe_object(resolved["bucket"], resolved["key"], public_url)
            return HeadObjectResult(
                bucket=descriptor.bucket,
                key=descriptor.key,
                provider=descriptor.provider,
                public_url=descriptor.public_url,
                exists=True,
                etag=output.get("ETag"),
                version_id=output.get("VersionId"),
                last_modified=_to_iso(output.get("LastModified")),
                expires_at=_to_iso(output.get("Expires")),
                content_length=output.get("ContentLength"),
                content_type=output.get("ContentType"),
                cache_control=output.get("CacheControl"),
                content_disposition=output.get("ContentDisposition"),
                content_encoding=output.get("ContentEncoding"),
                content_language=output.get("ContentLanguage"),
                metadata=dict(output.get("Metadata") or {}),
                raw=dict(output),
            )
        except Exception as error:
            if _is_not_found_error(error):
                if not_found == "error":
                    raise self._wrap_error(
                        "headObject",
                        resolved["bucket"],
                        resolved["key"],
                        error,
                        "Object was not found.",
                    ) from error
                return None
            raise self._wrap_error(
                "headObject",
                resolved["bucket"],
                resolved["key"],
                error,
                "Failed to fetch object metadata.",
            ) from error

    def object_exists(self, *, key: StorageKey, bucket: str | None = None) -> bool:
        return (
            self.head_object(key=key, bucket=bucket, not_found="null", public_url=False) is not None
        )

    def delete_object(
        self,
        *,
        key: StorageKey,
        bucket: str | None = None,
        public_url: bool = True,
        command_input: Mapping[str, Any] | None = None,
    ) -> DeleteObjectResult:
        resolved = self._resolve_target("deleteObject", key=key, bucket=bucket)
        command = dict(command_input or {})
        command["Bucket"] = resolved["bucket"]
        command["Key"] = resolved["key"]
        try:
            output = self.client.delete_object(**command)
            descriptor = self._describe_object(resolved["bucket"], resolved["key"], public_url)
            return DeleteObjectResult(
                bucket=descriptor.bucket,
                key=descriptor.key,
                provider=descriptor.provider,
                public_url=descriptor.public_url,
                version_id=output.get("VersionId"),
                delete_marker=bool(output.get("DeleteMarker", False)),
                raw=dict(output),
            )
        except Exception as error:
            raise self._wrap_error(
                "deleteObject",
                resolved["bucket"],
                resolved["key"],
                error,
                "Failed to delete object.",
            ) from error

    def create_presigned_upload_url(
        self,
        *,
        key: StorageKey,
        bucket: str | None = None,
        expires_in: int | None = None,
        metadata: Mapping[str, str] | None = None,
        tags: Mapping[str, str | int | bool] | None = None,
        content_type: str | None = None,
        cache_control: str | None = None,
        content_disposition: str | None = None,
        content_encoding: str | None = None,
        content_language: str | None = None,
        content_md5: str | None = None,
        public_url: bool = True,
        command_input: Mapping[str, Any] | None = None,
    ) -> PresignedRequest:
        resolved = self._resolve_target("createPresignedUploadUrl", key=key, bucket=bucket)
        ttl = _validate_expires_in(expires_in or self.default_upload_expires_in, "expires_in")
        command = _build_put_object_input(
            defaults=self._defaults,
            bucket=resolved["bucket"],
            key=resolved["key"],
            body=None,
            metadata=metadata,
            tags=tags,
            content_type=content_type,
            cache_control=cache_control,
            content_disposition=content_disposition,
            content_encoding=content_encoding,
            content_language=content_language,
            content_md5=content_md5,
            expires=None,
            command_input=command_input,
        )
        command.pop("Body", None)
        try:
            url = self._presign_url(self.client, "put_object", command, ttl)
            descriptor = self._describe_object(resolved["bucket"], resolved["key"], public_url)
            return PresignedRequest(
                bucket=descriptor.bucket,
                key=descriptor.key,
                provider=descriptor.provider,
                public_url=descriptor.public_url,
                method="PUT",
                url=url,
                headers=_build_presigned_put_headers(command),
                expires_in=ttl,
                expires_at=_future_iso(ttl),
            )
        except Exception as error:
            raise self._wrap_error(
                "createPresignedUploadUrl",
                resolved["bucket"],
                resolved["key"],
                error,
                "Failed to create presigned upload URL.",
            ) from error

    def create_presigned_download_url(
        self,
        *,
        key: StorageKey,
        bucket: str | None = None,
        expires_in: int | None = None,
        public_url: bool = True,
        command_input: Mapping[str, Any] | None = None,
    ) -> PresignedRequest:
        resolved = self._resolve_target("createPresignedDownloadUrl", key=key, bucket=bucket)
        ttl = _validate_expires_in(expires_in or self.default_download_expires_in, "expires_in")
        command = dict(command_input or {})
        command["Bucket"] = resolved["bucket"]
        command["Key"] = resolved["key"]
        try:
            url = self._presign_url(self.client, "get_object", command, ttl)
            descriptor = self._describe_object(resolved["bucket"], resolved["key"], public_url)
            return PresignedRequest(
                bucket=descriptor.bucket,
                key=descriptor.key,
                provider=descriptor.provider,
                public_url=descriptor.public_url,
                method="GET",
                url=url,
                headers={},
                expires_in=ttl,
                expires_at=_future_iso(ttl),
            )
        except Exception as error:
            raise self._wrap_error(
                "createPresignedDownloadUrl",
                resolved["bucket"],
                resolved["key"],
                error,
                "Failed to create presigned download URL.",
            ) from error

    def create_public_url(self, key: StorageKey, *, bucket: str | None = None) -> str:
        resolved = self._resolve_target("createPublicUrl", key=key, bucket=bucket)
        try:
            return self._create_public_url_from_resolved_target(resolved["bucket"], resolved["key"])
        except StorageError:
            raise
        except Exception as error:
            raise self._wrap_error(
                "createPublicUrl",
                resolved["bucket"],
                resolved["key"],
                error,
                "Failed to create public URL.",
            ) from error

    def _resolve_target(
        self,
        operation: StorageOperation,
        *,
        key: StorageKey,
        bucket: str | None,
    ) -> dict[str, str]:
        resolved_bucket = _assert_bucket(bucket or self.bucket)
        raw_key = join_storage_key(key)
        prefixed = join_storage_key(self.key_prefix, raw_key) if self.key_prefix else raw_key
        resolved_key = (
            self._resolve_key_hook(
                prefixed, StorageOperationContext(operation, resolved_bucket, self.provider)
            )
            if self._resolve_key_hook
            else prefixed
        )
        return {"bucket": resolved_bucket, "key": _assert_key(resolved_key)}

    def _create_public_url_from_resolved_target(self, bucket: str, key: str) -> str:
        resolved = ResolvedStoragePublicUrlInput(
            bucket=bucket,
            key=key,
            provider=self.provider,
            region=self.region,
            endpoint=self.endpoint,
            account_id=self.account_id,
            url_style=self.url_style,
            public_base_url=self.public_base_url,
        )
        if self._build_public_url_hook:
            return self._build_public_url_hook(resolved)
        if resolved.public_base_url:
            return _append_url_path(resolved.public_base_url, resolved.key)
        if resolved.endpoint:
            return _build_endpoint_url(
                resolved.endpoint, resolved.bucket, resolved.key, resolved.url_style
            )
        if resolved.provider == "s3":
            return _build_aws_public_url(
                resolved.bucket, resolved.key, resolved.region, resolved.url_style
            )
        raise TypeError(
            "R2 public URL generation requires an endpoint, public_base_url, or account_id."
        )

    def _describe_object(
        self, bucket: str, key: str, include_public_url: bool
    ) -> StorageObjectDescriptor:
        public_url = None
        if include_public_url:
            try:
                public_url = self._create_public_url_from_resolved_target(bucket, key)
            except Exception:
                public_url = None
        return StorageObjectDescriptor(
            bucket=bucket, key=key, provider=self.provider, public_url=public_url
        )

    def _wrap_error(
        self,
        operation: StorageOperation,
        bucket: str,
        key: str,
        error: Exception,
        message: str,
    ) -> StorageError:
        if isinstance(error, StorageError):
            return error
        status_code = _extract_status_code(error)
        return StorageError(
            message,
            code=_storage_error_code_for(operation),
            operation=operation,
            provider=self.provider,
            bucket=bucket,
            key=key,
            status_code=status_code,
            retryable=status_code is None or status_code >= 500 or status_code == 429,
            details={"httpStatusCode": status_code} if status_code is not None else None,
            cause=error,
        )


def create_storage_client(**kwargs: Any) -> StorageClient:
    return StorageClient(**kwargs)


def join_storage_key(*parts: StorageKey | None) -> str:
    normalized_parts: list[str] = []
    for part in parts:
        normalized_parts.extend(_flatten_key_part(part))
    cleaned = [
        entry.strip().strip("/")
        for entry in normalized_parts
        if isinstance(entry, str) and entry.strip().strip("/")
    ]
    return "/".join(cleaned).replace("//", "/")


def _build_put_object_input(
    *,
    defaults: dict[str, Any],
    bucket: str,
    key: str,
    body: Any,
    metadata: Mapping[str, str] | None,
    tags: Mapping[str, str | int | bool] | None,
    content_type: str | None,
    cache_control: str | None,
    content_disposition: str | None,
    content_encoding: str | None,
    content_language: str | None,
    content_md5: str | None,
    expires: datetime | None,
    command_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    command = dict(command_input or {})
    merged_metadata = _merge_string_records(defaults["metadata"], metadata)
    merged_tags = _merge_tag_records(defaults["tags"], tags)
    result = {
        **command,
        "Bucket": bucket,
        "Key": key,
        "Metadata": merged_metadata or None,
        "Tagging": _serialize_tags(merged_tags) if merged_tags else None,
        "ContentType": content_type or command.get("ContentType") or defaults["content_type"],
        "CacheControl": cache_control or command.get("CacheControl") or defaults["cache_control"],
        "ContentDisposition": content_disposition
        or command.get("ContentDisposition")
        or defaults["content_disposition"],
        "ContentEncoding": content_encoding
        or command.get("ContentEncoding")
        or defaults["content_encoding"],
        "ContentLanguage": content_language
        or command.get("ContentLanguage")
        or defaults["content_language"],
        "ContentMD5": content_md5 or command.get("ContentMD5"),
        "Expires": expires or command.get("Expires"),
    }
    if body is not None:
        result["Body"] = body
    return {k: v for k, v in result.items() if v is not None}


def _build_presigned_put_headers(command: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    scalar_map = {
        "ContentType": "content-type",
        "CacheControl": "cache-control",
        "ContentDisposition": "content-disposition",
        "ContentEncoding": "content-encoding",
        "ContentLanguage": "content-language",
        "ContentMD5": "content-md5",
        "ACL": "x-amz-acl",
        "ChecksumCRC32": "x-amz-checksum-crc32",
        "ChecksumCRC32C": "x-amz-checksum-crc32c",
        "ChecksumSHA1": "x-amz-checksum-sha1",
        "ChecksumSHA256": "x-amz-checksum-sha256",
        "ServerSideEncryption": "x-amz-server-side-encryption",
        "SSEKMSKeyId": "x-amz-server-side-encryption-aws-kms-key-id",
        "SSECustomerAlgorithm": "x-amz-server-side-encryption-customer-algorithm",
        "SSECustomerKey": "x-amz-server-side-encryption-customer-key",
        "SSECustomerKeyMD5": "x-amz-server-side-encryption-customer-key-md5",
        "StorageClass": "x-amz-storage-class",
        "WebsiteRedirectLocation": "x-amz-website-redirect-location",
    }
    for source_key, header_key in scalar_map.items():
        value = command.get(source_key)
        if value is not None:
            headers[header_key] = str(value)
    for key, value in dict(command.get("Metadata") or {}).items():
        headers[f"x-amz-meta-{key}"] = str(value)
    return headers


def _resolve_region(provider: StorageProvider, region: str | None) -> str:
    normalized = _normalize_optional_value(region)
    if normalized:
        return normalized
    return DEFAULT_R2_REGION if provider == "r2" else DEFAULT_S3_REGION


def _resolve_endpoint(
    *, provider: StorageProvider, endpoint: str | None, account_id: str | None
) -> str | None:
    explicit = _normalize_optional_base_url(endpoint)
    if explicit:
        return explicit
    if provider == "r2" and account_id:
        return f"https://{account_id}.r2.cloudflarestorage.com"
    return None


def _resolve_url_style(
    provider: StorageProvider,
    url_style: StorageUrlStyle | None,
    force_path_style: bool | None,
) -> StorageUrlStyle:
    if url_style:
        return url_style
    if isinstance(force_path_style, bool):
        return "path" if force_path_style else "virtual-hosted"
    return "path" if provider == "r2" else "virtual-hosted"


def _assert_bucket(bucket: str) -> str:
    normalized = _normalize_optional_value(bucket)
    if not normalized:
        raise TypeError("Storage bucket is required.")
    return normalized


def _assert_key(key: str) -> str:
    normalized = _normalize_optional_key(key)
    if not normalized:
        raise TypeError("Storage key must contain at least one path segment.")
    return normalized


def _normalize_optional_key(value: StorageKey | None) -> str | None:
    if value is None:
        return None
    normalized = join_storage_key(value)
    return normalized or None


def _flatten_key_part(value: StorageKey | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        output: list[str] = []
        for entry in value:
            output.extend(_flatten_key_part(entry if isinstance(entry, (str, Sequence)) else None))
        return output
    return []


def _normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_base_url(value: str | None) -> str | None:
    normalized = _normalize_optional_value(value)
    if not normalized:
        return None
    return normalized.rstrip("/")


def _append_url_path(base_url: str, *segments: str) -> str:
    parts = urlsplit(base_url)
    path_segments = [parts.path, *segments]
    normalized = "/".join(
        segment.strip().strip("/") for segment in path_segments if segment.strip().strip("/")
    )
    return urlunsplit((parts.scheme, parts.netloc, f"/{normalized}", parts.query, parts.fragment))


def _build_endpoint_url(endpoint: str, bucket: str, key: str, url_style: StorageUrlStyle) -> str:
    parts = urlsplit(endpoint)
    base_path = parts.path.rstrip("/")
    encoded_key = _encode_storage_key_for_url(key)
    hostname = parts.netloc
    if url_style == "virtual-hosted":
        hostname = f"{bucket}.{hostname}"
        path = "/".join(filter(None, [base_path.strip("/"), encoded_key]))
    else:
        path = "/".join(filter(None, [base_path.strip("/"), bucket, encoded_key]))
    return urlunsplit((parts.scheme, hostname, f"/{path}", parts.query, parts.fragment))


def _build_aws_public_url(bucket: str, key: str, region: str, url_style: StorageUrlStyle) -> str:
    encoded_key = _encode_storage_key_for_url(key)
    host = "s3.amazonaws.com" if region == "us-east-1" else f"s3.{region}.amazonaws.com"
    if url_style == "path":
        return f"https://{host}/{bucket}/{encoded_key}"
    return f"https://{bucket}.{host}/{encoded_key}"


def _encode_storage_key_for_url(key: str) -> str:
    return "/".join(quote(segment, safe="") for segment in key.split("/"))


def _merge_string_records(
    defaults: Mapping[str, str] | None,
    values: Mapping[str, str] | None,
) -> dict[str, str]:
    return dict(defaults or {}) | dict(values or {})


def _merge_tag_records(
    defaults: Mapping[str, str | int | bool] | None,
    values: Mapping[str, str | int | bool] | None,
) -> dict[str, str | int | bool]:
    return dict(defaults or {}) | dict(values or {})


def _serialize_tags(tags: Mapping[str, str | int | bool]) -> str:
    return urlencode([(key, str(value)) for key, value in tags.items()])


def _validate_expires_in(value: int, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise TypeError(f"{field_name} must be a positive integer.")
    if value > MAX_PRESIGN_EXPIRES_IN:
        raise ValueError(f"{field_name} must not exceed {MAX_PRESIGN_EXPIRES_IN} seconds.")
    return value


def _storage_error_code_for(operation: StorageOperation) -> str:
    return {
        "putObject": "STORAGE_PUT_FAILED",
        "headObject": "STORAGE_HEAD_FAILED",
        "deleteObject": "STORAGE_DELETE_FAILED",
        "createPresignedUploadUrl": "STORAGE_PRESIGN_UPLOAD_FAILED",
        "createPresignedDownloadUrl": "STORAGE_PRESIGN_DOWNLOAD_FAILED",
        "createPublicUrl": "STORAGE_PUBLIC_URL_FAILED",
    }[operation]


def _extract_status_code(error: Exception) -> int | None:
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    http_status = metadata.get("HTTPStatusCode")
    if isinstance(http_status, int):
        return http_status
    return None


def _is_not_found_error(error: Exception) -> bool:
    status = _extract_status_code(error)
    if status == 404:
        return True
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        return code in {"404", "NotFound", "NoSuchKey"}
    for attr in ("code", "Code", "name"):
        value = getattr(error, attr, None)
        if value in {"NotFound", "NoSuchKey"}:
            return True
    return False


def _default_presign_url(
    client: BaseClient, operation: str, params: dict[str, Any], expires_in: int
) -> str:
    return client.generate_presigned_url(operation, Params=params, ExpiresIn=expires_in)


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return None


def _future_iso(expires_in: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
