"""Feature 6 commuter LINE webhook (STC-06/STC-07 automation at controller level).

Covers: forged signature rejection (TC-06-2), Thai text conversation flow
(TC-06-1), and location-share travel-ETA flow (TC-07-2) with the LINE
Messaging API mocked out.
"""

from unittest.mock import MagicMock, patch

import pytest
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    LocationMessageContent,
    MessageEvent,
    TextMessageContent,
    UserSource,
)

WEBHOOK_URL = "/webhook/line/user"
HEADERS = {"X-Line-Signature": "forged-signature"}


def _message_event(message):
    # model_construct: the controller only reads attributes, so we skip the
    # SDK's full webhook payload validation (mode/deliveryContext/etc.)
    return MessageEvent.construct(
        type="message",
        timestamp=123,
        source=UserSource.construct(type="user", user_id="Ucommuter1"),
        reply_token="reply-token-1",
        message=message,
    )


# ---------- TC-06-2: forged webhook request rejected ----------

def test_invalid_signature_is_rejected_with_400(client):
    parser = MagicMock()
    parser.parse.side_effect = InvalidSignatureError("bad signature")

    with patch("routes.webhook_controller.user_parser", parser):
        response = client.post(
            WEBHOOK_URL,
            headers=HEADERS,
            content=b'{"events":[]}',
        )

    assert response.status_code == 400
    assert "Invalid signature" in response.json()["detail"]


def test_invalid_signature_sends_no_reply(client):
    parser = MagicMock()
    parser.parse.side_effect = InvalidSignatureError("bad signature")
    messaging = MagicMock()

    with patch("routes.webhook_controller.user_parser", parser), patch(
        "routes.webhook_controller.ApiClient"
    ), patch("routes.webhook_controller.MessagingApi", return_value=messaging):
        client.post(WEBHOOK_URL, headers=HEADERS, content=b'{"events":[]}')

    messaging.return_value.reply_message.assert_not_called()


# ---------- TC-06-1: Thai text message gets occupancy reply ----------

def test_text_event_replies_with_chatbot_answer(client):
    event = _message_event(TextMessageContent.construct(type="text", id="1", text="มีที่จอดไหม"))
    parser = MagicMock()
    parser.parse.return_value = [event]
    messaging = MagicMock()

    chatbot = MagicMock()
    chatbot.get_reply.return_value = {"type": "text", "text": "ตอนนี้มีที่ว่าง 14 คัน"}

    with patch("routes.webhook_controller.user_parser", parser), patch(
        "routes.webhook_controller.ApiClient"
    ), patch("routes.webhook_controller.MessagingApi", return_value=messaging), patch(
        "routes.webhook_controller.ChatbotService", return_value=chatbot
    ):
        response = client.post(WEBHOOK_URL, headers=HEADERS, content=b"{}")

    assert response.status_code == 200
    chatbot.get_reply.assert_called_once_with("มีที่จอดไหม")
    request = messaging.reply_message.call_args.args[0]
    assert request.reply_token == "reply-token-1"
    assert request.messages[0].text == "ตอนนี้มีที่ว่าง 14 คัน"


def test_quick_reply_request_attaches_location_button(client):
    event = _message_event(
        TextMessageContent.construct(type="text", id="1", text="ประเมินเวลาเดินทาง")
    )
    parser = MagicMock()
    parser.parse.return_value = [event]
    messaging = MagicMock()

    chatbot = MagicMock()
    chatbot.get_reply.return_value = {
        "type": "quick_reply_location",
        "text": "รบกวนแชร์ตำแหน่งปัจจุบันของคุณ",
    }

    with patch("routes.webhook_controller.user_parser", parser), patch(
        "routes.webhook_controller.ApiClient"
    ), patch("routes.webhook_controller.MessagingApi", return_value=messaging), patch(
        "routes.webhook_controller.ChatbotService", return_value=chatbot
    ):
        client.post(WEBHOOK_URL, headers=HEADERS, content=b"{}")

    message = messaging.reply_message.call_args.args[0].messages[0]
    assert message.quick_reply is not None
    assert message.quick_reply.items[0].action.type == "location"


# ---------- TC-07-2: location share gets travel-time reply ----------

def test_location_event_replies_with_travel_eta(client):
    event = _message_event(
        LocationMessageContent.construct(
            type="location",
            id="1",
            title="ที่ของฉัน",
            address="CAMT",
            latitude=18.802,
            longitude=98.951,
        )
    )
    parser = MagicMock()
    parser.parse.return_value = [event]
    messaging = MagicMock()

    chatbot = MagicMock()
    chatbot.calculate_travel_eta.return_value = "ใช้เวลาเดินทางประมาณ 1 นาที"

    with patch("routes.webhook_controller.user_parser", parser), patch(
        "routes.webhook_controller.ApiClient"
    ), patch("routes.webhook_controller.MessagingApi", return_value=messaging), patch(
        "routes.webhook_controller.ChatbotService", return_value=chatbot
    ):
        response = client.post(WEBHOOK_URL, headers=HEADERS, content=b"{}")

    assert response.status_code == 200
    chatbot.calculate_travel_eta.assert_called_once_with(18.802, 98.951)
    assert (
        messaging.reply_message.call_args.args[0].messages[0].text
        == "ใช้เวลาเดินทางประมาณ 1 นาที"
    )
