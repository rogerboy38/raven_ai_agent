"""TASKS-342: the agent's kill switch (AI Agent Settings `enabled`) also covers the two scheduled jobs and the three
document hooks of the CRM agent. Zero-DB."""
import unittest
from unittest import mock

from raven_ai_agent.api import agent_guard as g
from raven_ai_agent.skills.crm_agent.agents import lead_enricher, meeting_capturer, opportunity_mover, pipeline_summarizer


class TestKillSwitchDoors(unittest.TestCase):
    def test_off_means_nothing_runs(self):
        with mock.patch.object(g, "agent_enabled", return_value=False), \
                mock.patch.object(opportunity_mover, "OpportunityMoverAgent") as om, \
                mock.patch.object(pipeline_summarizer, "PipelineSummarizerAgent") as ps, \
                mock.patch.object(lead_enricher.frappe, "enqueue") as enq:
            opportunity_mover.scan_stalled_opportunities()
            opportunity_mover.on_opportunity_update(mock.MagicMock(name="o"))
            pipeline_summarizer.run_daily_digest()
            lead_enricher.on_lead_after_insert(mock.MagicMock())
            meeting_capturer.on_communication_after_insert(mock.MagicMock())
            om.assert_not_called()
            ps.assert_not_called()
            enq.assert_not_called()

    def test_on_means_they_still_run(self):
        with mock.patch.object(g, "agent_enabled", return_value=True), \
                mock.patch.object(opportunity_mover, "OpportunityMoverAgent") as om, \
                mock.patch.object(pipeline_summarizer, "PipelineSummarizerAgent") as ps:
            opportunity_mover.scan_stalled_opportunities()
            pipeline_summarizer.run_daily_digest()
            om.assert_called_once()
            ps.assert_called_once()


if __name__ == "__main__":
    unittest.main()
