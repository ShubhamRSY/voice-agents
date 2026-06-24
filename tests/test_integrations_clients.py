"""Tests for enterprise integration clients (Salesforce, ServiceNow, Zendesk, Slack, WhatsApp)."""
import pytest
from unittest.mock import AsyncMock, patch

from src.integrations.salesforce import SalesforceClient
from src.integrations.servicenow import ServiceNowClient
from src.integrations.zendesk import ZendeskClient
from src.integrations.slack import SlackNotifier
from src.integrations.whatsapp import WhatsAppMessenger


class TestSalesforceClient:
    def test_not_configured_returns_mock(self):
        client = SalesforceClient(client_id=None, client_secret=None)
        assert not client._is_configured()

    @pytest.mark.asyncio
    async def test_lookup_customer_mock_when_not_configured(self):
        client = SalesforceClient(client_id=None, client_secret=None)
        result = await client.lookup_customer("test@example.com")
        assert result is not None
        assert result["name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_create_ticket_mock_when_not_configured(self):
        client = SalesforceClient(client_id=None, client_secret=None)
        result = await client.create_ticket("Test Subject", "Test Desc", "cust-001")
        assert result["id"] == "sf-mock-case-001"
        assert result["subject"] == "Test Subject"

    @pytest.mark.asyncio
    async def test_update_record_mock_when_not_configured(self):
        client = SalesforceClient(client_id=None, client_secret=None)
        result = await client.update_record("cust-001", {"email": "new@example.com"})
        assert result["id"] == "cust-001"
        assert result["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_authenticate_fails_gracefully(self):
        client = SalesforceClient(client_id="test-id", client_secret="test-secret")
        with patch.object(client, "_authenticate", AsyncMock(return_value=None)):
            result = await client.lookup_customer("test@example.com")
            assert result is None or result.get("name") == "Jane Doe"


class TestServiceNowClient:
    def test_not_configured(self):
        client = ServiceNowClient(instance=None, api_key=None)
        assert not client._is_configured()

    @pytest.mark.asyncio
    async def test_create_incident_mock(self):
        client = ServiceNowClient(instance=None, api_key=None)
        result = await client.create_incident("Short desc", "Long desc", "test@example.com")
        assert result["id"] == "INC0010001"
        assert result["short_description"] == "Short desc"

    @pytest.mark.asyncio
    async def test_create_request_mock(self):
        client = ServiceNowClient(instance=None, api_key=None)
        result = await client.create_request("Need help", "user@example.com")
        assert result["id"] == "REQ0010001"

    @pytest.mark.asyncio
    async def test_update_incident_mock(self):
        client = ServiceNowClient(instance=None, api_key=None)
        result = await client.update_incident("INC001", {"state": "2"})
        assert result["id"] == "INC001"
        assert result["state"] == "2"


class TestZendeskClient:
    def test_not_configured(self):
        client = ZendeskClient(subdomain=None, api_key=None)
        assert not client._is_configured()

    @pytest.mark.asyncio
    async def test_create_ticket_mock(self):
        client = ZendeskClient(subdomain=None, api_key=None)
        result = await client.create_ticket("Test", "Details", "user@example.com")
        assert result["id"] == "zd-mock-001"
        assert result["subject"] == "Test"

    @pytest.mark.asyncio
    async def test_search_contacts_mock(self):
        client = ZendeskClient(subdomain=None, api_key=None)
        result = await client.search_contacts("test@example.com")
        assert len(result) == 1
        assert result[0]["id"] == "mock-001"

    @pytest.mark.asyncio
    async def test_update_ticket_mock(self):
        client = ZendeskClient(subdomain=None, api_key=None)
        result = await client.update_ticket("123", {"status": "solved"})
        assert result["id"] == "123"
        assert result["status"] == "solved"


class TestSlackNotifier:
    def test_not_configured(self):
        notifier = SlackNotifier(webhook_url=None)
        assert not notifier._is_configured()

    @pytest.mark.asyncio
    async def test_send_alert_mock(self):
        notifier = SlackNotifier(webhook_url=None)
        result = await notifier.send_alert("#general", "Test message")
        assert result["status"] == "mock_sent"

    @pytest.mark.asyncio
    async def test_notify_escalation_mock(self):
        notifier = SlackNotifier(webhook_url=None)
        result = await notifier.notify_escalation("sess-1", "Jane", "Needs help")
        assert result["status"] == "mock_sent"

    @pytest.mark.asyncio
    async def test_notify_ticket_created_mock(self):
        notifier = SlackNotifier(webhook_url=None)
        result = await notifier.notify_ticket_created("TKT-1", "Issue", "Jane", "Zendesk")
        assert result["status"] == "mock_sent"

    @pytest.mark.asyncio
    async def test_notify_agent_handoff_mock(self):
        notifier = SlackNotifier(webhook_url=None)
        result = await notifier.notify_agent_handoff("sess-1", "Jane", "Summary here")
        assert result["status"] == "mock_sent"

    @pytest.mark.asyncio
    async def test_notify_metric_alert_mock(self):
        notifier = SlackNotifier(webhook_url=None)
        result = await notifier.notify_metric_alert("containment", 0.75, 0.8)
        assert result["status"] == "mock_sent"


class TestWhatsAppMessenger:
    def test_not_configured(self):
        with patch("src.integrations.whatsapp.get_settings") as mock_settings:
            mock_settings.return_value.twilio_account_sid = ""
            mock_settings.return_value.twilio_auth_token = ""
            mock_settings.return_value.twilio_phone_number = ""
            msg = WhatsAppMessenger()
            assert not msg._is_configured()

    @pytest.mark.asyncio
    async def test_send_message_mock(self, monkeypatch):
        monkeypatch.setattr("src.integrations.whatsapp.get_settings", lambda: type("obj", (object,), {
            "twilio_account_sid": "",
            "twilio_auth_token": "",
            "twilio_phone_number": "",
        })())
        msg = WhatsAppMessenger()
        result = await msg.send_message("+15551234567", "Hello", "whatsapp")
        assert result["status"] == "mock_sent"
        assert "Hello" in result["body_preview"]

    @pytest.mark.asyncio
    async def test_handle_inbound_webhook(self, monkeypatch):
        monkeypatch.setattr("src.integrations.whatsapp.get_settings", lambda: type("obj", (object,), {
            "twilio_account_sid": "",
            "twilio_auth_token": "",
            "twilio_phone_number": "",
        })())
        msg = WhatsAppMessenger()
        form = {"From": "whatsapp:+15551234567", "To": "whatsapp:+18005551234", "Body": "Hi", "MessageSid": "SM123"}
        result = await msg.handle_inbound_webhook(form)
        assert result["channel"] == "whatsapp"
        assert result["body"] == "Hi"

    @pytest.mark.asyncio
    async def test_handle_inbound_sms(self, monkeypatch):
        monkeypatch.setattr("src.integrations.whatsapp.get_settings", lambda: type("obj", (object,), {
            "twilio_account_sid": "",
            "twilio_auth_token": "",
            "twilio_phone_number": "",
        })())
        msg = WhatsAppMessenger()
        form = {"From": "+15551234567", "To": "+18005551234", "Body": "Hello via SMS", "MessageSid": "SM456"}
        result = await msg.handle_inbound_webhook(form)
        assert result["channel"] == "sms"
