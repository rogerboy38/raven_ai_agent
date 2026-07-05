"""
raven_ai_agent/patterns/tests/test_planner.py
═══════════════════════════════════════════════════════════════════════════════
Standalone tests for the planner module.

Tests cover:
- Step / Plan dataclass behaviour
- Planner goal-category routing
- SkillDispatcher: execution order, dependency handling, guardrails gating,
  error isolation

Run with:
    cd apps/raven_ai_agent && python -m pytest raven_ai_agent/patterns/tests/ -v
"""
from __future__ import annotations

# Install frappe stub before importing planner (planner imports guardrails)
from raven_ai_agent.patterns.crm.tests.conftest import reset_frappe_mock

from raven_ai_agent.patterns.crm.planner import (
    Planner,
    Plan,
    Step,
    SkillDispatcher,
    plan as module_plan,
)


# ─── Step ────────────────────────────────────────────────────────────────

class TestStep:
    def test_defaults(self):
        s = Step(description="do something")
        assert s.skill == ""
        assert s.action == ""
        assert s.params == {}
        assert s.depends_on == []
        assert s.result is None

    def test_is_done_false_initially(self):
        s = Step(description="a")
        assert not s.is_done()
        s.result = "ok"
        assert s.is_done()

    def test_is_blocked(self):
        s = Step(description="b", result="BLOCKED")
        assert s.is_blocked()
        s.result = "ok"
        assert not s.is_blocked()


# ─── Plan ────────────────────────────────────────────────────────────────

class TestPlan:
    def test_pending_completed_partitions(self):
        p = Plan(goal="test", steps=[
            Step(description="a", result=None),
            Step(description="b", result="done"),
            Step(description="c", result="BLOCKED"),
        ])
        assert len(p.pending()) == 1
        assert len(p.completed()) == 2
        assert len(p.blocked()) == 1

    def test_to_dict_is_json_safe(self):
        import json
        p = Plan(
            goal="g",
            steps=[Step(description="x", skill="s", action="a")],
            metadata={"version": "0.1"},
        )
        d = p.to_dict()
        json.dumps(d)  # must not raise
        assert d["goal"] == "g"
        assert d["metadata"]["version"] == "0.1"
        assert d["steps"][0]["description"] == "x"


# ─── Planner routing ─────────────────────────────────────────────────────

class TestPlannerRouting:
    def setup_method(self):
        reset_frappe_mock()
        self.planner = Planner()

    def test_empty_goal_returns_empty_plan(self):
        plan = self.planner.plan("")
        assert plan.steps == []
        assert plan.metadata.get("warning") == "empty goal"

    def test_returns_plan_object(self):
        plan = self.planner.plan("Do something")
        assert isinstance(plan, Plan)
        assert plan.goal == "Do something"

    def test_deal_coach_plan_structure(self):
        plan = self.planner.plan(
            "Coach the deal", context={"opportunity": "OPP-001"}
        )
        assert len(plan.steps) == 3
        assert plan.steps[0].skill == "lead_enricher"
        assert plan.steps[0].action == "enrich"
        assert plan.steps[1].depends_on == [0]
        assert plan.steps[2].depends_on == [1]
        # All steps carry the opportunity context
        for step in plan.steps:
            assert step.params.get("opportunity") == "OPP-001"

    def test_lead_enricher_plan(self):
        plan = self.planner.plan(
            "Enrich this lead", context={"lead": "CRM-LEAD-0001"}
        )
        assert len(plan.steps) == 2
        assert plan.steps[0].action == "fetch"
        assert plan.steps[1].action == "enrich"

    def test_followup_plan(self):
        plan = self.planner.plan(
            "Write a follow-up", context={"lead": "CRM-LEAD-0001"}
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "draft"
        assert plan.steps[0].params.get("lead") == "CRM-LEAD-0001"

    def test_pipeline_summary_plan(self):
        plan = self.planner.plan("Summarize the pipeline", context={"user": "alice"})
        assert plan.steps[0].action == "summarize"
        assert plan.steps[0].params.get("user") == "alice"

    def test_unknown_goal_returns_observe_step(self):
        plan = self.planner.plan("Do something completely novel")
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "read"  # always-allowed action


# ─── SkillDispatcher ─────────────────────────────────────────────────────

class TestSkillDispatcherBasic:
    def setup_method(self):
        reset_frappe_mock()

    def test_executes_callable_handler(self):
        called = {}

        def my_handler(**kwargs):
            called.update(kwargs)
            return "result-from-callable"

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("my_skill", my_handler)

        plan = Plan(goal="t", steps=[
            Step(description="s1", skill="my_skill", action="read",
                 params={"x": 1, "y": 2}),
        ])
        result = dispatcher.execute(plan)

        assert result.steps[0].result == "result-from-callable"
        assert called == {"x": 1, "y": 2}

    def test_executes_method_on_instance_handler(self):
        class FakeAgent:
            def enrich(self, lead):
                return f"enriched:{lead}"

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("lead_enricher", FakeAgent())

        plan = Plan(goal="t", steps=[
            Step(description="s", skill="lead_enricher", action="enrich",
                 params={"lead": "L1"}),
        ])
        result = dispatcher.execute(plan)
        assert result.steps[0].result == "enriched:L1"

    def test_missing_handler_yields_no_handler_marker(self):
        dispatcher = SkillDispatcher(autonomy_level=4)
        plan = Plan(goal="t", steps=[
            Step(description="s", skill="ghost", action="read"),
        ])
        result = dispatcher.execute(plan)
        assert "NO_HANDLER" in str(result.steps[0].result)

    def test_handler_exception_caught_and_reported(self):
        def boom(**_):
            raise ValueError("kapow")

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("x", boom)

        plan = Plan(goal="t", steps=[
            Step(description="s", skill="x", action="read"),
        ])
        result = dispatcher.execute(plan)
        assert "ERROR" in str(result.steps[0].result)
        assert "kapow" in str(result.steps[0].result)


class TestSkillDispatcherGating:
    def setup_method(self):
        reset_frappe_mock()

    def test_low_autonomy_blocks_high_action(self):
        """Dispatcher at autonomy=0 cannot do `send_email` (needs 4)."""
        sent = []

        def send(**kwargs):
            sent.append(kwargs)
            return "sent"

        dispatcher = SkillDispatcher(autonomy_level=0)
        dispatcher.register("mailer", send)

        plan = Plan(goal="t", steps=[
            Step(description="s", skill="mailer", action="send_email",
                 params={"to": "a@b.com"}),
        ])
        result = dispatcher.execute(plan)
        assert result.steps[0].result == "BLOCKED"
        assert sent == []  # handler never called

    def test_high_autonomy_allows_high_action(self):
        sent = []

        def send(**kwargs):
            sent.append(kwargs)
            return "sent"

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("mailer", send)

        plan = Plan(goal="t", steps=[
            Step(description="s", skill="mailer", action="send_email",
                 params={"to": "a@b.com"}),
        ])
        result = dispatcher.execute(plan)
        assert result.steps[0].result == "sent"
        assert len(sent) == 1


class TestSkillDispatcherDependencies:
    def setup_method(self):
        reset_frappe_mock()

    def test_depends_on_executes_in_order(self):
        order = []

        def make_handler(name):
            def h(**_):
                order.append(name)
                return name
            return h

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("a", make_handler("a"))
        dispatcher.register("b", make_handler("b"))
        dispatcher.register("c", make_handler("c"))

        plan = Plan(goal="t", steps=[
            Step(description="s0", skill="a", action="read"),
            Step(description="s1", skill="b", action="read", depends_on=[0]),
            Step(description="s2", skill="c", action="read", depends_on=[1]),
        ])
        result = dispatcher.execute(plan)
        assert order == ["a", "b", "c"]
        assert all(s.result for s in result.steps)

    def test_missed_dependency_skips_downstream(self):
        """If step 0 is blocked, step 1 (which depends on 0) must SKIP."""
        # Step 0 will be BLOCKED because autonomy=0 < send_email needs 4
        # Step 1 depends on 0 → its dependency *did complete* (with BLOCKED)
        #   so per the spec, step 1 still runs. This tests the case where
        #   dependency genuinely never enters completed_indices (e.g. due
        #   to an upstream skip).
        order = []

        def good(**_):
            order.append("good")
            return "ok"

        dispatcher = SkillDispatcher(autonomy_level=4)
        dispatcher.register("a", good)
        dispatcher.register("b", good)

        # Step 1 depends on a NON-EXISTENT step index (99) → must skip
        plan = Plan(goal="t", steps=[
            Step(description="s0", skill="a", action="read"),
            Step(description="s1", skill="b", action="read", depends_on=[99]),
        ])
        result = dispatcher.execute(plan)
        assert result.steps[0].result == "ok"
        assert "SKIPPED" in str(result.steps[1].result)


# ─── End-to-end integration ──────────────────────────────────────────────

class TestModulePlanShim:
    """Tests for the module-level planner.plan(...) shim used by deal_coach.py."""

    def setup_method(self):
        reset_frappe_mock()

    def test_module_plan_returns_string(self):
        result = module_plan(system="sys", user="user", steps=3)
        assert isinstance(result, str)

    def test_module_plan_empty_inputs_returns_empty_string(self):
        result = module_plan()
        assert result == ""

    def test_module_plan_goal_path_returns_markdown(self):
        result = module_plan(goal="Coach deal", context={"opportunity": "O-1"}, steps=3)
        assert isinstance(result, str)
        assert "1." in result


class TestEndToEnd:
    def setup_method(self):
        reset_frappe_mock()

    def test_full_deal_coach_dry_run(self):
        """Planner → Dispatcher with mocked sub-agents end-to-end."""
        results = {}

        class FakeEnricher:
            def enrich(self, **kw):
                results["enriched"] = kw
                return {"enriched": True}

        class FakeCoach:
            def score(self, **kw):
                results["scored"] = kw
                return 0.85
            def suggest(self, **kw):
                results["suggested"] = kw
                return ["call CFO", "send pricing"]

        plan = Planner().plan(
            "Coach deal OPP-001",
            context={"opportunity": "OPP-001"},
        )

        dispatcher = SkillDispatcher(autonomy_level=2)
        dispatcher.register("lead_enricher", FakeEnricher())
        dispatcher.register("deal_coach", FakeCoach())

        executed = dispatcher.execute(plan)

        # All three steps ran in order
        assert executed.steps[0].result == {"enriched": True}
        assert executed.steps[1].result == 0.85
        assert executed.steps[2].result == ["call CFO", "send pricing"]

        # Context flowed through
        assert results["enriched"]["opportunity"] == "OPP-001"
        assert results["scored"]["opportunity"] == "OPP-001"


if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
