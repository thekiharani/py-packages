from __future__ import annotations

import pytest
from support import FakeAsyncClient, FakeSyncClient, json_response, run

from sendkit import (
    ONFON_SMS_BASE_URL,
    AsyncOnfonSmsClient,
    ConfigurationError,
    OnfonSmsClient,
    ProviderError,
    SmsGroupUpsertRequest,
    SmsMessage,
    SmsSendRequest,
    SmsTemplateUpsertRequest,
)

CLIENTS = [(OnfonSmsClient, False), (AsyncOnfonSmsClient, True)]


def _make(cls, is_async, handler):
    fake = (FakeAsyncClient if is_async else FakeSyncClient)(handler)
    client = cls(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=fake,
    )
    return client, fake


def _send_handler(call):
    url = call["url"]
    method = call["method"]
    if url.endswith("/SendBulkSMS"):
        return json_response(
            {
                "ErrorCode": "000",
                "ErrorDescription": "Success",
                "Data": [
                    {"MessageId": "msg-1", "MobileNumber": "254700123456"},
                    {"MobileNumber": "254711111111"},
                ],
            }
        )
    if "/Balance" in url:
        return json_response(
            {
                "ErrorCode": "000",
                "ErrorDescription": "Success",
                "Data": [{"PluginType": "SMS", "Credits": "1,024.50"}],
            }
        )
    if "/Group" in url and method == "GET":
        return json_response(
            {
                "ErrorCode": "000",
                "ErrorDescription": "Success",
                "Data": [{"GroupId": "group-1", "GroupName": "VIP", "ContactCount": "3"}],
            }
        )
    if "/Template" in url and method == "GET":
        return json_response(
            {
                "ErrorCode": "000",
                "ErrorDescription": "Success",
                "Data": [
                    {
                        "TemplateId": "tmpl-1",
                        "TemplateName": "otp",
                        "MessageTemplate": "Use {{1}}",
                        "IsApproved": "true",
                        "IsActive": "1",
                    }
                ],
            }
        )
    return json_response({"ErrorCode": "000", "ErrorDescription": "Success", "Data": "Success"})


def test_onfon_validates_required_config():
    with pytest.raises(ConfigurationError):
        OnfonSmsClient(access_key="", api_key="a", client_id="b")


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_onfon_full_flow(cls, is_async):
    client, fake = _make(cls, is_async, _send_handler)

    send_result = run(
        client.send(
            SmsSendRequest(
                messages=[
                    SmsMessage(recipient="254700123456", text="One", reference="r1"),
                    SmsMessage(recipient="254711111111", text="Two", reference="r2"),
                ]
            )
        )
    )

    assert ONFON_SMS_BASE_URL == "https://api.onfonmedia.co.ke/v1/sms"
    assert send_result.submitted_count == 1
    assert send_result.failed_count == 1
    assert send_result.messages[0].provider_message_id == "msg-1"
    assert send_result.messages[1].provider_error_code == "MISSING_MESSAGE_ID"
    assert fake.calls[0]["headers"]["AccessKey"] == "access-key"
    assert fake.calls[0]["json"]["SenderId"] == "NORIA"

    balance = run(client.get_balance())
    assert balance.entries[0].credits == 1024.5

    groups = run(client.list_groups())
    assert groups[0].group_id == "group-1"

    create_group = run(client.create_group(SmsGroupUpsertRequest(name="VIP")))
    assert create_group.success is True

    templates = run(client.list_templates())
    assert templates[0].template_id == "tmpl-1"

    create_template = run(
        client.create_template(SmsTemplateUpsertRequest(name="otp", body="Use {{1}}"))
    )
    assert create_template.success is True

    report = client.parse_delivery_report(
        {"messageId": "msg-1", "mobile": "254700123456", "status": "Delivered"}
    )
    assert report is not None
    assert report.provider_message_id == "msg-1"
    assert report.state == "delivered"


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_onfon_group_and_template_mutations(cls, is_async):
    client, fake = _make(cls, is_async, _send_handler)

    updated = run(client.update_group("group-1", SmsGroupUpsertRequest(name="Priority")))
    assert updated.resource_id == "group-1"
    assert fake.calls[-1]["params"]["id"] == "group-1"

    deleted = run(client.delete_group("group-1"))
    assert deleted.resource_id == "group-1"

    updated_template = run(
        client.update_template("tmpl-1", SmsTemplateUpsertRequest(name="otp", body="Use {{1}}"))
    )
    assert updated_template.resource_id == "tmpl-1"

    deleted_template = run(client.delete_template("tmpl-1"))
    assert deleted_template.resource_id == "tmpl-1"


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_onfon_raises_provider_error(cls, is_async):
    def handler(_call):
        return json_response({"ErrorCode": "101", "ErrorDescription": "Invalid sender"})

    client, _fake = _make(cls, is_async, handler)

    with pytest.raises(ProviderError):
        run(client.send(SmsSendRequest(messages=[SmsMessage(recipient="254700123456", text="hi")])))
