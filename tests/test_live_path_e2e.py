"""R3: end-to-end tests for the LIVE message path.

Covers the previously untested chain:
  Raven Message (after_insert) -> handle_raven_message -> flag check
  -> ack + enqueue -> process_command -> dispatcher -> reply + audit.
"""
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


def _settings(frappe, flag=1, ack=1):
    def gsv(doctype, field):
        return {"agent_pipeline_v2_enabled": flag, "pipeline_ack_enabled": ack}.get(field)
    frappe.db.get_single_value = MagicMock(side_effect=gsv)


def _raven_doc(text="<p>@ai help</p>"):
    doc = MagicMock()
    doc.name = "MSG-0001"
    doc.text = text
    doc.is_bot_message = 0
    doc.channel_id = "general"
    doc.owner = "hugh@x.com"
    return doc


class TestHookDiversion:
    def test_flag_on_acks_and_enqueues_without_legacy_path(self, frappe_mock):
        from raven_ai_agent.api import agent as agent_mod
        _settings(frappe_mock, flag=1)
        bot = MagicMock(); bot.send_message.return_value = "ACK-1"
        ack_doc = MagicMock(); ack_doc.name = "ACK-1"

        def get_doc(*args):
            return bot if args and args[0] == "Raven Bot" else ack_doc
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.enqueue = MagicMock()

        agent_mod.handle_raven_message(_raven_doc(), "after_insert")

        frappe_mock.enqueue.assert_called_once()
        kwargs = frappe_mock.enqueue.call_args.kwargs
        assert kwargs["query"] == "help"
        assert kwargs["channel_id"] == "general"
        assert kwargs["user"] == "hugh@x.com"

    def test_flag_off_skips_v2_entirely(self, frappe_mock):
        from raven_ai_agent.api import agent as agent_mod
        _settings(frappe_mock, flag=0)
        frappe_mock.enqueue = MagicMock()
        frappe_mock.get_doc = MagicMock(return_value=MagicMock())
        with patch("raven_ai_agent.api.pipeline_v2.dispatch") as dispatch:
            try:
                agent_mod.handle_raven_message(_raven_doc("<p>hello no trigger</p>"), "after_insert")
            except Exception:
                pass  # legacy path may fail in mock env; V2 must not be touched
            dispatch.assert_not_called()

    def test_bot_messages_ignored(self, frappe_mock):
        from raven_ai_agent.api import agent as agent_mod
        _settings(frappe_mock, flag=1)
        frappe_mock.enqueue = MagicMock()
        doc = _raven_doc(); doc.is_bot_message = 1
        agent_mod.handle_raven_message(doc, "after_insert")
        frappe_mock.enqueue.assert_not_called()


class TestFullChain:
    def test_enqueue_to_reply_and_audit(self, frappe_mock):
        """Run the captured job inline: dispatcher result must land as a
        bot reply and an audit row carrying the dispatcher stage."""
        from raven_ai_agent.api import agent as agent_mod, pipeline_v2
        _settings(frappe_mock, flag=1)
        inserted = []
        bot = MagicMock(); bot.send_message.return_value = "ACK-1"

        def get_doc(*args):
            if args and args[0] == "Raven Bot":
                return bot
            d = MagicMock(); d.name = "M-X"
            if args and isinstance(args[0], dict):
                inserted.append(args[0])
            return d
        frappe_mock.get_doc = MagicMock(side_effect=get_doc)
        frappe_mock.delete_doc = MagicMock()
        frappe_mock.db.commit = MagicMock()
        frappe_mock.enqueue = MagicMock()

        agent_mod.handle_raven_message(_raven_doc("<p>@ai validate COA-26-0010</p>"), "after_insert")
        job = frappe_mock.enqueue.call_args
        job_kwargs = {k: v for k, v in job.kwargs.items() if k not in ("queue", "timeout")}

        with patch("raven_ai_agent.api.dispatcher.route", return_value={
            "success": True, "response": "COA ok", "skill_used": "coa_validator",
            "stage": "skill_exact", "context_used": {},
        }):
            pipeline_v2.process_command(**job_kwargs)

        audits = [p for p in inserted if p.get("doctype") == "AI Routing Audit Log"]
        assert audits and audits[0]["resolved_intent"] == "skill_exact"
        assert audits[0]["selected_skill"] == "coa_validator"
        assert audits[0]["routing_status"] == "Routed"
        bot.send_message.assert_any_call(channel_id="general", text="COA ok", markdown=True)
