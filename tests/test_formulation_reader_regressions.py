"""
RAVEN-AB-001 regression tests — defects (a)/(b), F-C4c-1, and API/field-name pins.

Zero-DB by construction: conftest installs a mock `frappe` ModuleType (no site,
no connection). Attribute assignment on that module is visible to the reader
module because both share the same sys.modules['frappe'] object; a wrong API
name (e.g. frappe.get_al) raises a genuine AttributeError on a ModuleType,
which a MagicMock patch would silently auto-create — hence direct assignment,
not patch(), for the canary-style pins.
"""

import unittest
from unittest.mock import MagicMock, patch


class _row(dict):
    """frappe._dict lookalike: attribute access via dict.get (missing -> None)."""
    __getattr__ = dict.get


class TestFC4c1CoaLookup(unittest.TestCase):
    """F-C4c-1: get_batch_coa_parameters must query real columns, never lot_number."""

    def _install_frappe(self, coa_amb_rows, coa_amb2_rows, child_rows, batch_id='0612185231'):
        import frappe
        calls = []

        def get_all(doctype, *args, **kwargs):
            calls.append((doctype, kwargs))
            if doctype == 'COA AMB':
                return coa_amb_rows
            if doctype == 'COA AMB2':
                return coa_amb2_rows
            if doctype == 'COA Quality Test Parameter':
                return child_rows
            return []

        frappe.get_all = MagicMock(side_effect=get_all)
        frappe.db = MagicMock()
        frappe.db.get_value = MagicMock(return_value=batch_id)
        frappe.log_error = MagicMock()
        return frappe, calls

    def test_ab_01_no_lot_number_filter_anywhere(self):
        """AB-01: no COA lookup may filter on the phantom lot_number column."""
        frappe, calls = self._install_frappe([], [], [])
        from raven_ai_agent.skills.formulation_reader.reader import get_batch_coa_parameters
        get_batch_coa_parameters('LOTE040')
        for doctype, kwargs in calls:
            self.assertNotIn('lot_number', kwargs.get('filters', {}),
                             f"{doctype} still filters on lot_number")

    def test_ab_02_coa_amb_uses_golden_number_via_batch_id(self):
        """AB-02: COA AMB is keyed by custom_golden_number resolved from Batch.batch_id."""
        frappe, calls = self._install_frappe([_row(name='FOX-5176')], [], [])
        from raven_ai_agent.skills.formulation_reader.reader import get_batch_coa_parameters
        get_batch_coa_parameters('LOTE016')
        frappe.db.get_value.assert_called_once_with('Batch', 'LOTE016', 'batch_id')
        amb_calls = [kw for dt, kw in calls if dt == 'COA AMB']
        self.assertEqual(amb_calls[0]['filters'], {'custom_golden_number': '0612185231'})

    def test_ab_03_fallback_coa_amb2_uses_batch_reference(self):
        """AB-03: the COA AMB2 fallback filters on batch_reference with the raw docname."""
        child = [_row(specification='ASH', result='21.11', min_value=0, max_value=25,
                      status='PASS', numeric=1)]
        frappe, calls = self._install_frappe([], [_row(name='COA2-26-0011')], child)
        from raven_ai_agent.skills.formulation_reader.reader import get_batch_coa_parameters
        params = get_batch_coa_parameters('LOTE-26-28-0001')
        amb2_calls = [kw for dt, kw in calls if dt == 'COA AMB2']
        self.assertEqual(amb2_calls[0]['filters'], {'batch_reference': 'LOTE-26-28-0001'})
        self.assertIn('ASH', params)
        self.assertEqual(params['ASH']['source'], 'COA AMB2')
        self.assertAlmostEqual(params['ASH']['value'], 21.11)

    def test_ab_04_no_coa_returns_none_without_error(self):
        """AB-04: batches with no COA anywhere degrade to None, not an exception."""
        frappe, calls = self._install_frappe([], [], [], batch_id=None)
        from raven_ai_agent.skills.formulation_reader.reader import get_batch_coa_parameters
        self.assertIsNone(get_batch_coa_parameters('LOTE-NO-COA'))


class TestReaderApiAndFieldPins(unittest.TestCase):
    """Pins for the v1.6-flagged (and refuted) typos: get_all spelling + brix mapping."""

    def _batch_amb_frappe(self, rows):
        import frappe
        calls = []

        def get_all(doctype, *args, **kwargs):
            calls.append((doctype, kwargs))
            return rows if doctype == 'Batch AMB' else []

        frappe.get_all = MagicMock(side_effect=get_all)
        frappe.db = MagicMock()
        frappe.log_error = MagicMock()
        return frappe, calls

    def _sample_row(self, **over):
        base = dict(name='BAMB-001', product='0307', subproduct='', lot='L1',
                    sublot='S1', kilos=25, brix=13.5, total_solids=0.62,
                    manufacturing_date='2026-01-15', wwdyy_code='', warehouse='WH',
                    coa_amb2=None)
        base.update(over)
        return _row(base)

    def test_ab_05_get_batches_uses_get_all_and_no_swallowed_error(self):
        """AB-05: Batch AMB read goes through frappe.get_all; the broad except must
        stay silent (log_error untouched) — detects a future frappe.get_al typo,
        which the except at reader.py would otherwise swallow into an empty list."""
        frappe, calls = self._batch_amb_frappe([self._sample_row()])
        from raven_ai_agent.skills.formulation_reader.reader import (
            get_batches_for_item_and_warehouse,
        )
        batches = get_batches_for_item_and_warehouse('ITEM_0307001260', 'WH')
        self.assertEqual(len(batches), 1)
        self.assertEqual(calls[0][0], 'Batch AMB')
        frappe.log_error.assert_not_called()

    def test_ab_06_brix_value_survives_mapping(self):
        """AB-06: record.brix flows into the result (a .bri regression yields None)."""
        frappe, _ = self._batch_amb_frappe([self._sample_row()])
        from raven_ai_agent.skills.formulation_reader.reader import (
            get_batches_for_item_and_warehouse,
        )
        batches = get_batches_for_item_and_warehouse('ITEM_0307001260', 'WH')
        self.assertEqual(batches[0].brix, 13.5)
        self.assertEqual(batches[0].total_solids, 0.62)

    def test_ab_07_brix_none_row_maps_to_none(self):
        """AB-07: a row without brix maps to None without crashing."""
        frappe, _ = self._batch_amb_frappe([self._sample_row(brix=None)])
        from raven_ai_agent.skills.formulation_reader.reader import (
            get_batches_for_item_and_warehouse,
        )
        batches = get_batches_for_item_and_warehouse('ITEM_0307001260', 'WH')
        self.assertIsNone(batches[0].brix)


class TestDefectASelectorFallback(unittest.TestCase):
    """Defect (a): _select_batches falls back to payload product_code."""

    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.get_available_batches')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.parse_golden_number')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_ab_08_payload_product_code_drives_selection(self, mock_frappe, mock_parse,
                                                         mock_get_batches):
        """AB-08: non-golden item_code + payload product_code -> reader queried with it."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import BatchSelectorAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage

        mock_parse.return_value = None
        mock_get_batches.return_value = []
        agent = BatchSelectorAgent()
        message = AgentMessage(
            source_agent="orchestrator", target_agent="batch_selector",
            action="select_batches",
            payload={"item_code": None, "product_code": "0307", "quantity_required": 100},
        )
        response = agent.handle_message(message)
        self.assertTrue(response.success)
        self.assertEqual(mock_get_batches.call_args.kwargs.get('product_code'), '0307')
        self.assertEqual(response.result['selected_batches'], [])
        self.assertIn('0307', response.result['message'])

    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.get_available_batches')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.batch_selector.parse_golden_number')
    @patch('raven_ai_agent.skills.formulation_orchestrator.agents.base.frappe')
    def test_ab_09_golden_item_code_still_wins(self, mock_frappe, mock_parse,
                                               mock_get_batches):
        """AB-09: golden item_code behavior unchanged — parsed product outranks payload."""
        from raven_ai_agent.skills.formulation_orchestrator.agents import BatchSelectorAgent
        from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage

        mock_parse.return_value = {'product': '0617', 'folio': 27, 'year': 23,
                                   'fefo_key': 23027, 'full_year': 2023}
        mock_get_batches.return_value = []
        agent = BatchSelectorAgent()
        message = AgentMessage(
            source_agent="orchestrator", target_agent="batch_selector",
            action="select_batches",
            payload={"item_code": "ITEM_0617027231", "product_code": "9999"},
        )
        agent.handle_message(message)
        self.assertEqual(mock_get_batches.call_args.kwargs.get('product_code'), '0617')


class TestDefectBGoldenGate(unittest.TestCase):
    """Defect (b): get_available_batches fail-closed + plain-name admission."""

    def test_ab_10_no_product_returns_empty_without_query(self):
        """AB-10: product_code=None -> [] and the Bin table is never queried."""
        import frappe
        frappe.get_all = MagicMock()
        from raven_ai_agent.skills.formulation_reader.reader import get_available_batches
        self.assertEqual(get_available_batches(product_code=None), [])
        frappe.get_all.assert_not_called()

    def test_ab_11_plain_named_bin_admitted_for_its_own_code(self):
        """AB-11: a bin whose item_code IS the queried product is admitted."""
        import frappe

        def get_all(doctype, *args, **kwargs):
            if doctype == 'Bin':
                return [_row(item_code='0307', warehouse='FG', actual_qty=39)]
            return []

        frappe.get_all = MagicMock(side_effect=get_all)
        from raven_ai_agent.skills.formulation_reader.reader import get_available_batches
        out = get_available_batches(product_code='0307')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['item_code'], '0307')
        self.assertEqual(out[0]['product'], '0307')
        self.assertEqual(out[0]['fefo_key'], float('inf'))

    def test_ab_12_foreign_golden_bins_excluded(self):
        """AB-12: golden bins of OTHER products never leak into a scoped query."""
        import frappe

        def get_all(doctype, *args, **kwargs):
            if doctype == 'Bin':
                return [
                    _row(item_code='ITEM_0617027231', warehouse='FG', actual_qty=2908),
                    _row(item_code='0307', warehouse='FG', actual_qty=39),
                ]
            return []

        frappe.get_all = MagicMock(side_effect=get_all)
        from raven_ai_agent.skills.formulation_reader.reader import get_available_batches
        out = get_available_batches(product_code='0307')
        self.assertEqual([b['item_code'] for b in out], ['0307'])


if __name__ == '__main__':
    unittest.main()
