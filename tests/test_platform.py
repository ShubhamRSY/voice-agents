"""Unit tests for core platform components."""

import pytest

from src.telephony.call_router import CallMetadata, CallRouter, RoutingRule


class TestCallRouter:
    def test_skill_based_routing(self):
        router = CallRouter()
        router.add_rule(RoutingRule("vip", "from:+1555", "+15559999999", priority=10))
        router.add_rule(RoutingRule("default", "from:+1", "+15551111111", priority=1))
        router.set_fallback("+15550000000")

        metadata = CallMetadata(
            call_sid="CA123",
            from_number="+14155551234",
            to_number="+1800ACME",
        )
        assert router.route(metadata) == "+15551111111"

    def test_vip_routing(self):
        router = CallRouter()
        router.add_rule(RoutingRule("vip", "from:+1555", "+15559999999", priority=10))
        router.set_fallback("+15550000000")

        metadata = CallMetadata(
            call_sid="CA456",
            from_number="+15559876543",
            to_number="+1800ACME",
        )
        assert router.route(metadata) == "+15559999999"

    def test_fallback_routing(self):
        router = CallRouter()
        router.set_fallback("+15550000000")

        metadata = CallMetadata(
            call_sid="CA789",
            from_number="+442071234567",
            to_number="+1800ACME",
        )
        assert router.route(metadata) == "+15550000000"


class TestPromptTemplates:
    def test_registry_has_all_channels(self):
        from src.prompts.templates import PROMPT_REGISTRY
        assert "voice" in PROMPT_REGISTRY
        assert "chat" in PROMPT_REGISTRY
        assert "copilot" in PROMPT_REGISTRY


class TestToolRegistry:
    def test_all_configured_tools_exist(self):
        from src.agents.tools import TOOL_REGISTRY
        from src.config import load_agent_config

        config = load_agent_config()
        for agent_id, agent_cfg in config["agents"].items():
            for tool_name in agent_cfg.get("tools", []):
                assert tool_name in TOOL_REGISTRY, f"Tool {tool_name} missing for agent {agent_id}"


class TestCRMIntegration:
    @pytest.mark.asyncio
    async def test_mock_customer_lookup(self):
        from src.integrations.crm import HubSpotClient

        client = HubSpotClient(api_key="")
        customer = await client.lookup_customer("test@example.com")
        assert customer is not None
        assert customer["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_mock_ticket_creation(self):
        from src.integrations.crm import HubSpotClient

        client = HubSpotClient(api_key="")
        ticket = await client.create_ticket("Test issue", "Description", "cust-001")
        assert ticket["status"] == "open"
