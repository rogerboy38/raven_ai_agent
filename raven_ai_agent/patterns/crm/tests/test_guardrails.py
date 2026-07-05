"""
raven_ai_agent/patterns/tests/test_guardrails.py
═══════════════════════════════════════════════════════════════════════════════
Standalone tests for the guardrails module.

Run with:
    cd apps/raven_ai_agent && python -m pytest raven_ai_agent/patterns/tests/ -v

Or via the smoke harness:
    python raven_ai_agent/patterns/tests/run_smoke.py

These tests use a MagicMock'd `frappe` module (installed by conftest.py) so
no Frappe site is required. This matches the test style used by
crm_agent/tests/run_smoke.py.
"""
from __future__ import annotations

# Install frappe stub before any guardrails import
from raven_ai_agent.patterns.crm.tests.conftest import reset_frappe_mock

from raven_ai_agent.patterns.crm.guardrails import (
    is_action_allowed,
    get_required_level,
    OBSERVE,
    SUGGEST,
    ENRICH,
    STAGE_MOVE,
    AUTONOMOUS,
)


# ─── Default ladder behaviour ──────────────────────────────────────────────

class TestDefaultLadder:
    """No AI Action Policy DocType installed — falls back to _DEFAULT_POLICY."""

    def setup_method(self):
        reset_frappe_mock()

    def test_read_always_allowed(self):
        assert is_action_allowed("any_skill", "read", OBSERVE) is True
        assert is_action_allowed("any_skill", "read", AUTONOMOUS) is True

    def test_draft_requires_suggest(self):
        assert is_action_allowed("follow_up_writer", "draft", SUGGEST) is True
        assert is_action_allowed("follow_up_writer", "draft", OBSERVE) is False

    def test_enrich_requires_level_2(self):
        assert is_action_allowed("lead_enricher", "enrich", ENRICH) is True
        assert is_action_allowed("lead_enricher", "enrich", SUGGEST) is False

    def test_stage_move_requires_level_3(self):
        assert is_action_allowed("opportunity_mover", "stage_move", STAGE_MOVE) is True
        assert is_action_allowed("opportunity_mover", "stage_move", ENRICH) is False

    def test_send_email_requires_autonomous(self):
        assert is_action_allowed("follow_up_writer", "send_email", AUTONOMOUS) is True
        assert is_action_allowed("follow_up_writer", "send_email", STAGE_MOVE) is False

    def test_unknown_action_defaults_to_stage_move(self):
        """Conservative default: unknown action requires level 3."""
        assert is_action_allowed("x", "wibble", STAGE_MOVE) is True
        assert is_action_allowed("x", "wibble", ENRICH) is False

    def test_get_required_level_lookup(self):
        assert get_required_level("read") == OBSERVE
        assert get_required_level("draft") == SUGGEST
        assert get_required_level("enrich") == ENRICH
        assert get_required_level("stage_move") == STAGE_MOVE
        assert get_required_level("send_email") == AUTONOMOUS
        assert get_required_level("totally_unknown") == STAGE_MOVE  # conservative


# ─── AI Action Policy DocType override behaviour ──────────────────────────

class TestPolicyDocTypeOverride:
    """Simulate AI Action Policy rows tightening / loosening the default."""

    def setup_method(self):
        self.frappe = reset_frappe_mock()
        self.frappe.db.table_exists.return_value = True

    def test_blocked_action_returns_false_regardless_of_autonomy(self):
        self.frappe.db.get_value.return_value = {
            "min_autonomy_level": 0,
            "require_human_approval": 0,
            "blocked": 1,
            "notes": "blocked by admin pending compliance review",
        }
        assert is_action_allowed("lead_enricher", "enrich", AUTONOMOUS) is False

    def test_higher_min_autonomy_via_policy(self):
        """Policy can RAISE the bar above the default ladder."""
        self.frappe.db.get_value.return_value = {
            "min_autonomy_level": AUTONOMOUS,
            "require_human_approval": 0,
            "blocked": 0,
            "notes": "",
        }
        # `suggest` normally needs level 1, but policy raised it to 4
        assert is_action_allowed("deal_coach", "suggest", STAGE_MOVE) is False
        assert is_action_allowed("deal_coach", "suggest", AUTONOMOUS) is True

    def test_lower_min_autonomy_via_policy(self):
        """Policy can also LOWER the bar (e.g. trusted skill)."""
        self.frappe.db.get_value.return_value = {
            "min_autonomy_level": OBSERVE,
            "require_human_approval": 0,
            "blocked": 0,
            "notes": "trusted IoT bot",
        }
        # `send_email` normally needs level 4, but policy dropped it to 0
        assert is_action_allowed("iot_bot", "send_email", OBSERVE) is True

    def test_require_human_approval_allows_but_flags(self):
        """v0.1 behaviour: allowed=True, but audit row gets escalation flag."""
        self.frappe.db.get_value.return_value = {
            "min_autonomy_level": 0,
            "require_human_approval": 1,
            "blocked": 0,
            "notes": "needs CFO approval over $50k",
        }
        assert is_action_allowed("deal_coach", "send_email", AUTONOMOUS) is True


# ─── Fault tolerance — must never raise to caller ─────────────────────────

class TestFaultTolerance:
    def setup_method(self):
        self.frappe = reset_frappe_mock()

    def test_policy_table_exception_falls_back(self):
        """If table_exists() raises, we fall back to the default ladder."""
        self.frappe.db.table_exists.side_effect = RuntimeError("db connection lost")
        result = is_action_allowed("any", "read", OBSERVE)
        # `read` is OBSERVE-level, so even fallback says yes
        assert result is True

    def test_get_value_exception_falls_back(self):
        """If get_value() raises, treat as 'no row' and use ladder."""
        self.frappe.db.table_exists.return_value = True
        self.frappe.db.get_value.side_effect = RuntimeError("query timeout")
        # Should not raise; should fall back to ladder
        result = is_action_allowed("any", "stage_move", STAGE_MOVE)
        assert result is True

    def test_non_int_autonomy_coerced_safely(self):
        """If caller passes a non-int autonomy, we coerce to SUGGEST."""
        result = is_action_allowed("any", "draft", "1")  # type: ignore[arg-type]
        assert result is True  # "1" → 1 → SUGGEST, draft needs SUGGEST
        result2 = is_action_allowed("any", "draft", None)  # type: ignore[arg-type]
        assert result2 is True  # None → SUGGEST default → draft needs SUGGEST

    def test_returns_bool_not_truthy(self):
        """Strict bool contract — never returns 0/1/None to caller."""
        result = is_action_allowed("x", "read", OBSERVE)
        assert isinstance(result, bool)
        assert result is True
        result = is_action_allowed("x", "send_email", OBSERVE)
        assert isinstance(result, bool)
        assert result is False


# ─── Wildcard skill policy ────────────────────────────────────────────────

class TestWildcardPolicy:
    def setup_method(self):
        self.frappe = reset_frappe_mock()
        self.frappe.db.table_exists.return_value = True

    def test_skill_wildcard_falls_through(self):
        """If skill-specific row missing, try skill='*' wildcard."""
        call_count = {"n": 0}

        def fake_get_value(doctype, filters, fields, as_dict=False):
            call_count["n"] += 1
            # First call (skill="iot_bot") returns None
            if filters["skill"] == "iot_bot":
                return None
            # Second call (skill="*") returns policy
            if filters["skill"] == "*":
                return {
                    "min_autonomy_level": 0,
                    "require_human_approval": 0,
                    "blocked": 1,
                    "notes": "global block",
                }
            return None

        self.frappe.db.get_value.side_effect = fake_get_value
        # Despite high autonomy, the wildcard block applies
        assert is_action_allowed("iot_bot", "send_email", AUTONOMOUS) is False
        assert call_count["n"] >= 2  # both specific + wildcard queried


if __name__ == "__main__":
    # Allow `python test_guardrails.py` for quick sanity check
    import pytest
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
