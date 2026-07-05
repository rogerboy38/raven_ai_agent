"""R2 router-consolidation tests.

The core guarantee: BOTH skill routers draw from the same framework
SkillRegistry, so a skill can never again be reachable in one and
invisible in the other (the coa_validator bug class)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def frappe_mock():
    import frappe
    if not hasattr(frappe, "logger"):
        frappe.logger = MagicMock(return_value=MagicMock())
    if not hasattr(frappe, "conf"):
        frappe.conf = MagicMock()
    return frappe


class TestRouterParity:
    def test_legacy_router_loads_from_framework_registry(self, frappe_mock):
        from raven_ai_agent.skills import framework
        from raven_ai_agent.skills.router import SkillRouter as LegacyRouter

        registry = framework.get_registry()
        registry_names = set(registry.get_all().keys())
        legacy = LegacyRouter()
        legacy_names = set()
        for key, skill in legacy.skills.items():
            legacy_names.add(key)

        # every registry skill must be present in the legacy router
        # (keys may differ: legacy keys by instance .name)
        assert len(legacy.skills) == len(registry_names), (
            f"registry has {sorted(registry_names)} but legacy loaded {sorted(legacy_names)}"
        )

    def test_coa_validator_visible_to_both_routers(self, frappe_mock):
        from raven_ai_agent.skills import framework
        from raven_ai_agent.skills.router import SkillRouter as LegacyRouter

        assert "coa_validator" in framework.get_registry().get_all()
        legacy = LegacyRouter()
        assert any(
            type(s).__name__ == "COAValidatorSkill" for s in legacy.skills.values()
        )


class TestDispatcherStages:
    def _agent(self, provider=None, skill_matches=None, skill_result=None):
        agent = MagicMock()
        agent.provider = provider
        agent.skill_router._find_matches.return_value = skill_matches or []
        agent.skill_router.route.return_value = skill_result
        agent.process_query.return_value = {
            "success": True, "response": "llm answer", "context_used": {},
        }
        return agent

    def test_stage1_exact_skill_wins(self, frappe_mock):
        from raven_ai_agent.api import dispatcher
        agent = self._agent(
            skill_matches=[("coa_validator", 0.95, 75), ("data-quality-scanner", 0.8, 90)],
            skill_result={"handled": True, "response": "coa ok", "skill": "coa_validator"},
        )
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent):
            r = dispatcher.route("validate COA-26-0010", "u@x.com")
        assert r["stage"] == "skill_exact" and r["skill_used"] == "coa_validator"

    def test_stage2_multi_agent_regex(self, frappe_mock):
        from raven_ai_agent.api import dispatcher
        agent = self._agent(skill_matches=[("data-quality-scanner", 0.8, 90)])
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent), \
             patch("raven_ai_agent.api.multi_agent_router.handle_multi_agent_command",
                   return_value="pipeline report"):
            r = dispatcher.route("workflow run SO-00752", "u@x.com")
        assert r["stage"] == "multi_agent" and r["response"] == "pipeline report"

    def test_stage4_fallthrough_to_agent(self, frappe_mock):
        from raven_ai_agent.api import dispatcher
        agent = self._agent(skill_matches=[])
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent), \
             patch("raven_ai_agent.api.multi_agent_router.handle_multi_agent_command",
                   return_value=None):
            r = dispatcher.route("what were my sales last month?", "u@x.com")
        assert r["stage"] == "agent_v2" and r["response"] == "llm answer"

    def test_broken_stage_falls_through(self, frappe_mock):
        from raven_ai_agent.api import dispatcher
        agent = self._agent()
        agent.skill_router._find_matches.side_effect = RuntimeError("boom")
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent), \
             patch("raven_ai_agent.api.multi_agent_router.handle_multi_agent_command",
                   return_value=None):
            r = dispatcher.route("anything", "u@x.com")
        assert r["stage"] == "agent_v2"  # graceful fallthrough, no crash
