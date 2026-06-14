"""
raven_ai_agent/patterns/planner.py
═══════════════════════════════════════════════════════════════════════════════
Minimal Planner for raven_ai_agent sub-agents.

This module decomposes a high-level goal (e.g. "coach the deal on OPP-001 to
close") into an ordered list of `Step` objects that sub-agents can execute
one-by-one. Each Step carries enough metadata for the guardrails layer to
evaluate it independently.

────────────────────────────────────────────────────────────────────────────────
v0.1 SCOPE (this file)
────────────────────────────────────────────────────────────────────────────────

• Typed `Step` and `Plan` dataclasses with serialization helpers
• `Planner.plan()` returns rule-based plans for known goal categories
  (deal_coach, lead_enricher, follow_up_writer, pipeline_summarizer)
• Unknown goals return a single "observe" step — safe fallback
• `SkillDispatcher` helper executes a Plan, respecting:
    - `depends_on` ordering (LLMCompiler-style DAG semantics)
    - `is_action_allowed()` gating on every step
    - graceful per-step error isolation (one bad step doesn't kill the plan)

The rule-based stubs in `_llm_plan()` are intentionally trivial — they exist
to satisfy `from raven_ai_agent.patterns import planner` in deal_coach.py
without requiring an LLM call. They are also useful as a smoke-test floor
for plan execution integration tests.

────────────────────────────────────────────────────────────────────────────────
v0.2 UPGRADE PATH (LangGraph Plan-and-Execute)
────────────────────────────────────────────────────────────────────────────────

Replace `Planner._llm_plan()` with a LangGraph chain. Sketch:

    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field

    class LGPlan(BaseModel):
        steps: list[Step] = Field(description="ordered steps to execute")

    planner_chain = (
        ChatPromptTemplate.from_messages([
            ("system", "Decompose CRM goals into Step objects ..."),
            ("user", "{goal}\\n\\nContext: {context}"),
        ])
        | ChatOpenAI(model="gpt-4o").with_structured_output(LGPlan)
    )

    def _llm_plan(self, goal, context):
        return planner_chain.invoke({"goal": goal, "context": context}).steps

The public `Planner.plan()` signature does NOT change. Callers don't update.

See: https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/

────────────────────────────────────────────────────────────────────────────────
v0.3 UPGRADE PATH (LLMCompiler parallel DAG)
────────────────────────────────────────────────────────────────────────────────

The `Step.depends_on: list[int]` field already encodes a DAG. To enable
parallel execution, swap `SkillDispatcher.execute()` for an async variant
that uses asyncio.gather() on the independent set at each topological layer.

See: https://arxiv.org/pdf/2312.04511.pdf (Kim et al., 2023)

────────────────────────────────────────────────────────────────────────────────
REFERENCES
────────────────────────────────────────────────────────────────────────────────
- LangGraph Plan-and-Execute tutorial
  https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/
- ReAct (Yao et al., ICLR 2023): https://arxiv.org/abs/2210.03629
- LLMCompiler (Kim et al., 2023): https://arxiv.org/pdf/2312.04511.pdf
- Reflexion (Shinn et al., NeurIPS 2023): https://arxiv.org/abs/2303.11366
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Step:
    """
    A single planned step for a sub-agent to execute.

    Designed to be a stable contract between Planner (producer) and
    SkillDispatcher (consumer). The `depends_on` field is the seam for
    future LLMCompiler-style parallel execution.

    Attributes
    ----------
    description : str
        Human-readable description. Shown in audit logs and Raven channel
        previews. Keep under 140 chars for clean display.
    skill : str
        Snake_case sub-agent name. Must match a registered handler in
        SkillDispatcher AND a recognized `skill` value in the guardrails
        policy table. Examples: "lead_enricher", "follow_up_writer".
    action : str
        Action keyword passed to `is_action_allowed()`. Must match a key
        in `_DEFAULT_POLICY` (guardrails.py) or have a corresponding
        AI Action Policy row.
    params : dict[str, Any]
        Keyword arguments passed to the skill callable.
    depends_on : list[int]
        Zero-based indices of steps that must complete before this one.
        Empty list = no dependency (may run first, or in parallel with
        other no-dependency steps in v0.3).
    result : Any
        Populated by SkillDispatcher after execution. None until executed.
        Becomes the literal return value of the skill callable, OR one of:
            "BLOCKED"   — guardrails rejected the action
            "SKIPPED (dependency not met)" — upstream step didn't complete
            "NO_HANDLER for skill=..." — skill not registered
            "ERROR: ..." — exception during execution
    """

    description: str
    skill: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)
    result: Any = None

    def is_done(self) -> bool:
        """True if this step has been executed (result is not None)."""
        return self.result is not None

    def is_blocked(self) -> bool:
        """True if guardrails rejected the action."""
        return self.result == "BLOCKED"


@dataclass
class Plan:
    """
    An ordered list of Steps produced by Planner.plan().

    Pure data container — no methods that mutate state beyond the helpers
    below. Serialization via `to_dict()` is safe for audit log payloads.
    """

    goal: str
    steps: list[Step] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def pending(self) -> list[Step]:
        """Return steps that haven't been executed yet."""
        return [s for s in self.steps if not s.is_done()]

    def completed(self) -> list[Step]:
        """Return steps that have been executed (regardless of outcome)."""
        return [s for s in self.steps if s.is_done()]

    def blocked(self) -> list[Step]:
        """Return steps that were rejected by guardrails."""
        return [s for s in self.steps if s.is_blocked()]

    def to_dict(self) -> dict:
        """JSON-safe representation. Used for audit log context payloads."""
        return {
            "goal": self.goal,
            "metadata": self.metadata,
            "steps": [
                {
                    "description": s.description,
                    "skill": s.skill,
                    "action": s.action,
                    "params": s.params,
                    "depends_on": s.depends_on,
                    "result": (
                        str(s.result) if s.result is not None else None
                    ),
                }
                for s in self.steps
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

class Planner:
    """
    Decomposes a high-level goal into an ordered list of Steps.

    v0.1 implementation: keyword-driven rule-based planning. Sufficient for
    the four known sub-agent goal categories (deal_coach, lead_enricher,
    follow_up_writer, pipeline_summarizer). Unknown goals return a single
    "observe" step that simply records the input for later analysis.

    v0.2 upgrade: replace `_llm_plan()` with a LangGraph chain. Signature
    is stable.

    Thread safety
    -------------
    Planner is stateless. Multiple sub-agents can share a single instance.

    Examples
    --------
    >>> planner = Planner()
    >>> plan = planner.plan(
    ...     "Coach the deal on opportunity OPP-001",
    ...     context={"opportunity": "OPP-001", "stage": "Proposal"},
    ... )
    >>> for step in plan.steps:
    ...     print(step.description)
    Enrich lead data for this opportunity
    Score deal health and identify risks
    Suggest next best actions
    """

    def plan(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> Plan:
        """
        Produce a Plan for the given *goal*.

        Parameters
        ----------
        goal : str
            Natural-language goal string. Routed to the appropriate
            sub-planner based on keyword matching.
        context : dict | None
            Contextual metadata propagated into Step.params.

        Returns
        -------
        Plan
            Ordered list of Steps. May be empty if `goal` is empty.
            Always returns a valid Plan object — never raises.
        """
        ctx = context or {}
        goal_clean = (goal or "").strip()

        if not goal_clean:
            return Plan(goal="", steps=[], metadata={"warning": "empty goal"})

        steps = self._llm_plan(goal_clean, ctx)
        return Plan(goal=goal_clean, steps=steps, metadata={"planner_version": "0.1"})

    # ──────────────────────────────────────────────────────────────────────
    # v0.1 RULE-BASED STUB — replace this entire method in v0.2
    # ──────────────────────────────────────────────────────────────────────

    def _llm_plan(self, goal: str, context: dict) -> list[Step]:
        """
        Keyword-driven heuristic planner. Returns sensible defaults for
        known goal categories. Order matters — first match wins.

        Replace this in v0.2 with a LangGraph Plan-and-Execute chain. The
        return type (`list[Step]`) is stable, so callers don't change.
        """
        g = goal.lower()

        # Order matters — more-specific patterns first.
        if "follow" in g or "follow-up" in g or "followup" in g:
            return self._followup_plan(context)
        if "summarize" in g or "pipeline" in g or "digest" in g:
            return self._pipeline_summary_plan(context)
        if "enrich" in g or ("lead" in g and "coach" not in g and "deal" not in g):
            return self._lead_enricher_plan(context)
        if "coach" in g or "deal" in g or "opportunity" in g or "next" in g:
            return self._deal_coach_plan(context)

        # Fallback: single observe step that captures the request for
        # later analysis. Returns a "read" action (always allowed at
        # autonomy=0), so it never gets blocked.
        return [
            Step(
                description=f"Observe goal: {goal[:120]}",
                skill="",
                action="read",
                params={"goal": goal, **context},
            )
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Goal-category templates
    # ──────────────────────────────────────────────────────────────────────
    # Each returns an ordered list[Step] with explicit depends_on edges
    # so v0.3 parallel execution will Just Work.

    def _deal_coach_plan(self, context: dict) -> list[Step]:
        """
        Three-step deal coaching: enrich → score → suggest.

        Step 0 enriches the lead (no dependencies — may run immediately).
        Step 1 scores deal health (depends on enriched data).
        Step 2 suggests next actions (depends on score).
        """
        opp = context.get("opportunity", "")
        return [
            Step(
                description="Enrich lead data for this opportunity",
                skill="lead_enricher",
                action="enrich",
                params={"opportunity": opp},
                depends_on=[],
            ),
            Step(
                description="Score deal health and identify risks",
                skill="deal_coach",
                action="score",
                params={"opportunity": opp},
                depends_on=[0],
            ),
            Step(
                description="Suggest next best actions",
                skill="deal_coach",
                action="suggest",
                params={"opportunity": opp},
                depends_on=[1],
            ),
        ]

    def _lead_enricher_plan(self, context: dict) -> list[Step]:
        """Two-step lead enrichment: fetch raw → enrich with external data."""
        lead = context.get("lead", "")
        return [
            Step(
                description="Fetch raw lead data",
                skill="lead_enricher",
                action="fetch",
                params={"lead": lead},
                depends_on=[],
            ),
            Step(
                description="Enrich lead with external data",
                skill="lead_enricher",
                action="enrich",
                params={"lead": lead},
                depends_on=[0],
            ),
        ]

    def _followup_plan(self, context: dict) -> list[Step]:
        """Single-step draft. Sending is a separate, higher-autonomy step."""
        lead = context.get("lead", "")
        return [
            Step(
                description="Draft follow-up message",
                skill="follow_up_writer",
                action="draft",
                params={"lead": lead, **{k: v for k, v in context.items() if k != "lead"}},
                depends_on=[],
            ),
        ]

    def _pipeline_summary_plan(self, context: dict) -> list[Step]:
        """Single-step pipeline summary. Read-only — always allowed."""
        return [
            Step(
                description="Summarize pipeline status",
                skill="pipeline_summarizer",
                action="summarize",
                params=dict(context),
                depends_on=[],
            ),
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL COMPATIBILITY SHIM
# ═══════════════════════════════════════════════════════════════════════════════
# PR #16 `crm_agent/agents/deal_coach.py:60` does:
#
#     from raven_ai_agent.patterns import planner
#     plan = planner.plan(system=SYSTEM_PROMPT, user=user, steps=3)
#
# i.e. it calls `planner.plan(...)` as a MODULE-LEVEL function with an LLM-style
# (system, user) signature, not as a `Planner().plan()` method. The function
# below provides that surface for backward compatibility while the Planner
# class remains the canonical entry point.
#
# Behaviour: try to call the configured LLM via raven_ai_agent.providers; if
# unavailable, fall back to a rule-based stub. Returns a markdown string —
# NOT a Plan object — because deal_coach embeds the result directly in a
# Raven channel message.
#
# v0.2 upgrade: replace this with a real LangGraph Plan-and-Execute chain
# whose `.invoke(...)` returns markdown.

def plan(
    system: str = "",
    user: str = "",
    steps: int = 3,
    goal: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Module-level convenience function. Returns a markdown plan string.

    This is the backward-compatible entry point for call sites that pass
    LLM-style prompts (system+user). For the structured Planner API, use
    `Planner().plan(goal, context)` which returns a `Plan` object.

    Parameters
    ----------
    system : str
        System prompt for the LLM (deal_coach style).
    user : str
        User prompt with the actual planning input.
    steps : int
        Target number of plan steps. Default 3.
    goal : str | None
        Alternative entry point: if `user` is empty, treat `goal` as the
        natural-language goal and route through the rule-based planner.
    context : dict | None
        Context propagated to the rule-based planner if used.

    Returns
    -------
    str
        Markdown-formatted plan, suitable for embedding in a Raven channel
        message. Empty string if all paths fail.
    """
    # Path 1: LLM-backed plan via configured provider
    if system or user:
        try:
            from raven_ai_agent.providers import openai_provider  # type: ignore
            import frappe
            settings = frappe.get_single("AI Agent Settings")
            choice = (getattr(settings, "default_provider", "OpenAI") or "OpenAI").lower()
            # Lazy import for each provider to avoid hard dependency
            provider_cls = openai_provider.OpenAIProvider
            if choice == "claude":
                from raven_ai_agent.providers import claude  # type: ignore
                provider_cls = claude.ClaudeProvider
            elif choice == "deepseek":
                from raven_ai_agent.providers import deepseek  # type: ignore
                provider_cls = deepseek.DeepSeekProvider
            elif choice == "minimax":
                from raven_ai_agent.providers import minimax  # type: ignore
                provider_cls = minimax.MiniMaxProvider

            provider = provider_cls()
            prompt_suffix = f"\n\nProvide exactly {steps} steps as a numbered markdown list."
            result = provider.complete(
                system=system,
                user=(user or "") + prompt_suffix,
                temperature=0.3,
            )
            if result:
                return result.strip()
        except Exception:
            # Fall through to rule-based path
            pass

    # Path 2: rule-based stub from the Planner class
    if goal:
        structured = Planner().plan(goal, context or {})
        if structured.steps:
            lines = [f"{i + 1}. {s.description}" for i, s in enumerate(structured.steps[:steps])]
            return "\n".join(lines)

    # Path 3: complete fallback — empty string lets caller use its own default
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

class SkillDispatcher:
    """
    Executes a Plan, respecting `depends_on` ordering and guardrails gating.

    Each step is gated through `is_action_allowed()` from the guardrails
    module. Blocked steps record "BLOCKED" as their result. Steps whose
    dependencies didn't complete are marked "SKIPPED". Exceptions are
    caught and recorded as "ERROR: ..." — one bad step never kills the plan.

    Usage
    -----
        from raven_ai_agent.patterns.planner import Planner, SkillDispatcher

        dispatcher = SkillDispatcher(autonomy_level=2)
        dispatcher.register("lead_enricher", lead_enricher_instance)
        dispatcher.register("deal_coach", deal_coach_instance)

        plan = Planner().plan("Coach deal OPP-001", context={"opportunity": "OPP-001"})
        result = dispatcher.execute(plan)

        for step in result.steps:
            print(step.description, "→", step.result)

    Handler types
    -------------
    Two handler shapes are supported:

      1. A plain callable — invoked as `handler(**step.params)`.
      2. An object with method names matching step.action — invoked as
         `getattr(handler, step.action)(**step.params)`. This is the
         common case where one sub-agent class implements several actions.

    Thread safety
    -------------
    SkillDispatcher holds per-instance handler registry + autonomy state.
    Use one dispatcher per request / conversation; do not share across
    threads.
    """

    def __init__(self, autonomy_level: int = 1):
        self._registry: dict[str, Any] = {}
        self.autonomy_level: int = int(autonomy_level)

    def register(self, skill_name: str, callable_or_instance: Any) -> None:
        """Register a handler for a given skill name."""
        self._registry[skill_name] = callable_or_instance

    def execute(self, plan: Plan) -> Plan:
        """
        Execute steps in dependency order. Returns the same Plan with
        each step's `result` field populated.

        Algorithm: simple linear scan. Each step checks that all its
        `depends_on` indices are present in `completed_indices` before
        executing. This is O(N*D) where D = avg dependencies per step.
        For v0.1 plans with ≤5 steps this is fine; v0.3 will swap in
        a proper topological sort with asyncio parallelism.
        """
        # Lazy import to avoid circular import at module load time
        from raven_ai_agent.patterns.guardrails import is_action_allowed

        completed_indices: set[int] = set()

        for idx, step in enumerate(plan.steps):
            # 1. Verify dependencies completed
            if not all(d in completed_indices for d in step.depends_on):
                step.result = "SKIPPED (dependency not met)"
                # Don't add to completed_indices — downstream skips too
                continue

            # 2. Guardrails gate
            if step.skill and step.action:
                allowed = is_action_allowed(
                    skill=step.skill,
                    action=step.action,
                    autonomy_level=self.autonomy_level,
                    context={
                        "plan_goal": plan.goal,
                        "step_idx": idx,
                        "step_description": step.description,
                        **{k: v for k, v in step.params.items() if not callable(v)},
                    },
                )
                if not allowed:
                    step.result = "BLOCKED"
                    completed_indices.add(idx)
                    continue

            # 3. Look up handler
            handler = self._registry.get(step.skill)
            if handler is None:
                step.result = f"NO_HANDLER for skill={step.skill!r}"
                completed_indices.add(idx)
                continue

            # 4. Execute
            try:
                if callable(handler):
                    step.result = handler(**step.params)
                else:
                    method: Callable | None = getattr(handler, step.action, None)
                    if method is None:
                        step.result = (
                            f"NO_METHOD {step.action!r} on "
                            f"{type(handler).__name__}"
                        )
                    else:
                        step.result = method(**step.params)
            except Exception as exc:
                # Per-step error isolation. The exception message is
                # included verbatim so the audit log captures it.
                step.result = f"ERROR: {type(exc).__name__}: {exc}"

            completed_indices.add(idx)

        return plan
