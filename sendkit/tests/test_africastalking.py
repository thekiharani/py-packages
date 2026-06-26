from __future__ import annotations

import pytest
from support import FakeAsyncClient, FakeSyncClient, json_response, run

from sendkit import (
    AFRICASTALKING_SMS_BASE_URL,
    AfricasTalkingFetchMessagesRequest,
    AfricasTalkingPremiumSmsRequest,
    AfricasTalkingSmsClient,
    AfricasTalkingSubscriptionRequest,
    AsyncAfricasTalkingSmsClient,
    ConfigurationError,
    SmsMessage,
    SmsSendRequest,
    parse_africastalking_delivery_report,
)

CLIENTS = [(AfricasTalkingSmsClient, False), (AsyncAfricasTalkingSmsClient, True)]


def _make(cls, is_async):
    def handler(call):
        url = call["url"]
        method = call["method"]
        data = call.get("data") or {}

        if "/user" in url:
            return json_response({"UserData": {"balance": "KES 1,024.50"}})
        if url.endswith("/messaging/premium"):
            return json_response(
                {
                    "SMSMessageData": {
                        "Message": "Sent to 1/1",
                        "Recipients": [
                            {
                                "number": data.get("to"),
                                "status": "Success",
                                "statusCode": 101,
                                "messageId": "premium-1",
                            }
                        ],
                    }
                }
            )
        if url.endswith("/messaging") and method == "GET":
            return json_response(
                {
                    "SMSMessageData": {
                        "Messages": [
                            {
                                "id": "inbound-1",
                                "from": "+254700123456",
                                "to": "22384",
                                "text": "JOIN",
                                "linkId": "link-1",
                                "date": "2026-06-25T03:00:00.000Z",
                                "networkCode": "63902",
                            }
                        ]
                    }
                }
            )
        if url.endswith("/messaging") and method == "POST":
            recipients = [
                {
                    "number": number,
                    "status": "Success",
                    "statusCode": 101,
                    "messageId": f"at-{index + 1}",
                    "cost": "KES 0.8000",
                }
                for index, number in enumerate(str(data.get("to")).split(","))
            ]
            return json_response({"SMSMessageData": {"Recipients": recipients}})
        if "/subscription/create" in url or "/subscription/delete" in url:
            return json_response({"status": "Success", "description": "Queued"})
        return json_response({"SMSMessageData": {"Recipients": []}})

    fake = (FakeAsyncClient if is_async else FakeSyncClient)(handler)
    client = cls(api_key="api-key", username="sandbox", default_sender_id="NORIA", client=fake)
    return client, fake


def test_africastalking_validates_required_config():
    with pytest.raises(ConfigurationError):
        AfricasTalkingSmsClient(api_key="", username="sandbox")


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_africastalking_send_groups_by_text(cls, is_async):
    client, fake = _make(cls, is_async)

    result = run(
        client.send(
            SmsSendRequest(
                messages=[
                    SmsMessage(recipient="+254700123456", text="One", reference="r1"),
                    SmsMessage(recipient="+254711111111", text="One", reference="r2"),
                    SmsMessage(recipient="+254722222222", text="Two", reference="r3"),
                ],
                provider_options={"enqueue": "1"},
            )
        )
    )

    assert AFRICASTALKING_SMS_BASE_URL == "https://api.africastalking.com/version1"
    assert fake.calls[0]["headers"]["apiKey"] == "api-key"
    assert fake.calls[0]["data"]["username"] == "sandbox"
    assert fake.calls[0]["data"]["from"] == "NORIA"
    assert fake.calls[0]["data"]["message"] == "One"
    assert fake.calls[0]["data"]["to"] == "+254700123456,+254711111111"
    assert fake.calls[0]["data"]["enqueue"] == "1"
    assert fake.calls[1]["data"]["message"] == "Two"
    assert result.submitted_count == 3
    assert result.messages[0].provider_message_id == "at-1"


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_africastalking_balance_premium_inbox_subscriptions(cls, is_async):
    client, fake = _make(cls, is_async)

    balance = run(client.get_balance())
    assert balance.entries[0].credits == 1024.5

    premium = run(
        client.send_premium(
            AfricasTalkingPremiumSmsRequest(
                recipient="+254733333333",
                text="Premium response",
                short_code="22384",
                keyword="NORIA",
                link_id="link-1",
                retry_duration_in_hours=2,
            )
        )
    )
    assert premium.messages[0].provider_message_id == "premium-1"
    premium_call = fake.calls[-1]
    assert premium_call["data"]["from"] == "22384"
    assert premium_call["data"]["keyword"] == "NORIA"
    assert premium_call["data"]["linkId"] == "link-1"
    assert premium_call["data"]["retryDurationInHours"] == "2"

    inbox = run(client.fetch_messages(AfricasTalkingFetchMessagesRequest(last_received_id=42)))
    assert inbox.messages[0].provider_message_id == "inbound-1"
    assert inbox.messages[0].sender == "+254700123456"
    assert inbox.messages[0].recipient == "22384"
    assert inbox.messages[0].link_id == "link-1"
    assert inbox.messages[0].text == "JOIN"
    assert fake.calls[-1]["params"]["lastReceivedId"] == 42

    created = run(
        client.create_subscription(
            AfricasTalkingSubscriptionRequest(
                phone_number="+254700123456", short_code="22384", keyword="NORIA"
            )
        )
    )
    assert created.success is True
    assert fake.calls[-1]["data"]["phoneNumber"] == "+254700123456"

    deleted = run(
        client.delete_subscription(
            AfricasTalkingSubscriptionRequest(
                phone_number="+254700123456", short_code="22384", keyword="NORIA"
            )
        )
    )
    assert deleted.description == "Queued"


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_africastalking_parses_delivery_reports(cls, is_async):
    client, _fake = _make(cls, is_async)

    event = client.parse_delivery_report(
        {
            "id": "at-1",
            "phoneNumber": "+254700123456",
            "status": "Success",
            "networkCode": "63902",
            "retryCount": "0",
        }
    )
    assert event is not None
    assert event.provider_message_id == "at-1"
    assert event.state == "delivered"

    report = parse_africastalking_delivery_report(
        {"message_id": "at-2", "phone_number": "+254711111111", "failure_reason": "Rejected"}
    )
    assert report.id == "at-2"
    assert report.phone_number == "+254711111111"
    assert report.failure_reason == "Rejected"
