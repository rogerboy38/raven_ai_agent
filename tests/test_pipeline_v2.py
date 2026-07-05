"""Phase R1 tests: feature-flagged async Pipeline V2 dispatch."""
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def frappe_mock():
    import frappe
    if not hasattr(frappe, "logger"):
        frappe.logger = MagicMock(return_value=MagicMock())
    return frappe


def _mk_settings(frappe, flag=1, ack=1):
    def gsv(doctype, field):
        return {"agent_pipeline_v2_enabled": flag, "pipeline_ack_enabled": ack}.get(field)
    frappe.db.get_single_value = MagicMock(side_effect=gsv)


class TestIsEnabled:
    def test_flag_on(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        _mk_settings(frappe_mock, flag=1)
        assert pipeline_v2.is_enabled() is True

    def test_flag_off(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        _mk_settings(frappe_mock, flag=0)
        assert pipeline_v2.is_enabled() is False

    def test_flag_error_means_off(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        frappe_mock.db.get_single_value = MagicMock(side_effect=RuntimeError("db down"))
        assert pipeline_v2.is_enabled() is False


class TestDispatch:
    def test_ack_inserted_and_job_enqueued(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        _mk_settings(frappe_mock)
        bot = MagicMock(); bot.send_message.return_value = "ACK-1"
        ack_doc = MagicMock(); ack_doc.name = "ACK-1"

        def get_doc(*args):
            return bot if args and args[0] == "Raven Bot" else ack_doc
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.enqueue = MagicMock()

        pipeline_v2.dispatch("MSG-1", "channel-1", "diagnose SO-00752", "u@x.com")

        bot.send_message.assert_called_once()
        frappe_mock.enqueue.assert_called_once()
        kwargs = frappe_mock.enqueue.call_args.kwargs
        assert kwargs["queue"] == "short"
        assert kwargs["query"] == "diagnose SO-00752"
        assert kwargs["ack_name"] == "ACK-1"

    def test_ack_failure_still_enqueues(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        _mk_settings(frappe_mock)
        frappe_mock.get_doc = MagicMock(side_effect=RuntimeError("insert failed"))
        frappe_mock.enqueue = MagicMock()

        pipeline_v2.dispatch("MSG-1", "channel-1", "hello", "u@x.com")

        frappe_mock.enqueue.assert_called_once()
        assert frappe_mock.enqueue.call_args.kwargs["ack_name"] is None


class TestProcessCommand:
    def _run(self, frappe_mock, agent_result=None, agent_raises=None):
        from raven_ai_agent.api import pipeline_v2
        inserted = []

        def get_doc(payload):
            d = MagicMock(); d.payload = payload
            inserted.append(payload)
            return d
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.delete_doc = MagicMock()
        frappe_mock.db.commit = MagicMock()

        agent = MagicMock()
        if agent_raises:
            agent.process_query.side_effect = agent_raises
        else:
            agent.process_query.return_value = agent_result
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent):
            pipeline_v2.process_command(
                request_id="req123", message_name="MSG-1",
                channel_id="channel-1", query="diagnose", user="u@x.com",
                ack_name="ACK-1",
            )
        return inserted, frappe_mock

    def test_success_writes_reply_and_audit(self, frappe_mock):
        inserted, fm = self._run(
            frappe_mock,
            agent_result={"success": True, "response": "All good",
                          "skill_used": "coa_validator", "context_used": {}},
        )
        replies = [p for p in inserted if p.get("doctype") == "Raven Message"]
        audits = [p for p in inserted if p.get("doctype") == "AI Routing Audit Log"]
        assert replies and replies[0]["text"] == "All good"
        assert replies[0]["is_bot_message"] == 1
        assert audits and audits[0]["routing_status"] == "Routed"
        assert audits[0]["selected_skill"] == "coa_validator"
        assert audits[0]["request_id"] == "req123"
        fm.delete_doc.assert_called_once()  # ack removed

    def test_agent_exception_yields_apology_and_failed_audit(self, frappe_mock):
        inserted, fm = self._run(frappe_mock, agent_raises=RuntimeError("provider down"))
        replies = [p for p in inserted if p.get("doctype") == "Raven Message"]
        audits = [p for p in inserted if p.get("doctype") == "AI Routing Audit Log"]
        assert replies and "req123" in replies[0]["text"]
        assert audits and audits[0]["routing_status"] == "Failed"
        assert "RuntimeError" in audits[0]["error_text"]


class TestBotAttribution:
    def test_reply_sent_via_raven_bot_with_markdown(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        bot = MagicMock(); bot.name = "sales_order_bot"
        bot.send_message.return_value = "MSG-REPLY-1"
        calls = []

        def get_doc(*args):
            if args and args[0] == "Raven Bot":
                return bot
            calls.append(args)
            d = MagicMock(); d.name = "M-1"; return d
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.delete_doc = MagicMock()
        frappe_mock.db.commit = MagicMock()

        agent = MagicMock()
        agent.process_query.return_value = {"success": True, "response": "# ok", "context_used": {}}
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent):
            pipeline_v2.process_command(
                request_id="r", message_name="M", channel_id="c", query="q",
                user="u@x.com", ack_name=None,
            )
        bot.send_message.assert_called_once_with(channel_id="c", text="# ok", markdown=True)

    def test_reply_falls_back_to_raw_insert_without_bot(self, frappe_mock):
        from raven_ai_agent.api import pipeline_v2
        inserted = []

        def get_doc(*args):
            if args and args[0] == "Raven Bot":
                raise Exception("no bot")
            d = MagicMock(); d.name = "M-1"
            if isinstance(args[0], dict):
                inserted.append(args[0])
            return d
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.delete_doc = MagicMock()
        frappe_mock.db.commit = MagicMock()

        agent = MagicMock()
        agent.process_query.return_value = {"success": True, "response": "ok", "context_used": {}}
        with patch("raven_ai_agent.api.agent_v2.RaymondLucyAgentV2", return_value=agent):
            pipeline_v2.process_command(
                request_id="r", message_name="M", channel_id="c", query="q",
                user="u@x.com", ack_name=None,
            )
        replies = [p for p in inserted if p.get("doctype") == "Raven Message"]
        assert replies and replies[0]["is_bot_message"] == 1


class TestLazyProvider:
    def test_provider_failure_does_not_raise_and_help_still_works(self, frappe_mock):
        frappe_mock.get_single = MagicMock(return_value=MagicMock(
            max_tokens=2000, confidence_threshold=0.7,
            get_password=MagicMock(return_value=None),
        ))
        with patch("raven_ai_agent.api.agent_v2.get_provider", side_effect=ValueError("no key")), \
             patch("raven_ai_agent.api.agent_v2.CostMonitor"), \
             patch("raven_ai_agent.api.agent_v2.get_router") as router:
            router.return_value.get_skills_help.return_value = "skills!"
            router.return_value.route.return_value = None
            from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2
            agent = RaymondLucyAgentV2(user="u@x.com")
            assert agent.provider is None and agent._provider_error

            with patch("raven_ai_agent.api.agent.RaymondLucyAgent"), \
                 patch("raven_ai_agent.api.agent.SYSTEM_PROMPT", "sp", create=True), \
                 patch("raven_ai_agent.api.agent.CAPABILITIES_LIST", "caps", create=True):
                result = agent.process_query("help")
            assert result["success"] is True
            assert result["provider"] == "unavailable" or "caps" in result["response"]

    def test_llm_path_returns_actionable_message_without_provider(self, frappe_mock):
        frappe_mock.get_single = MagicMock(return_value=MagicMock(
            max_tokens=2000, confidence_threshold=0.7,
            get_password=MagicMock(return_value=None),
        ))
        with patch("raven_ai_agent.api.agent_v2.get_provider", side_effect=ValueError("no key")), \
             patch("raven_ai_agent.api.agent_v2.CostMonitor"), \
             patch("raven_ai_agent.api.agent_v2.get_router") as router:
            router.return_value.route.return_value = None
            from raven_ai_agent.api.agent_v2 import RaymondLucyAgentV2
            agent = RaymondLucyAgentV2(user="u@x.com")
            v1 = MagicMock(); v1.execute_workflow_command.return_value = None
            with patch("raven_ai_agent.api.agent.RaymondLucyAgent", return_value=v1):
                result = agent.process_query("what were my sales last month?")
            assert result["success"] is False
            assert "provider" in result and result["provider"] == "unavailable"
            assert "set-config" in result["response"]
