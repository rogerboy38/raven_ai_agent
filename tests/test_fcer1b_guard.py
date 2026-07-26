"""
F-CER-1b guard tests — migration-fixer degrades gracefully when the folio
custom fields are absent from Quotation (guard-first ruling; no schema change).
Zero-DB by construction (conftest mock frappe).
"""

import unittest
from unittest.mock import MagicMock


def _fixer(has_columns):
    import frappe
    frappe.conf = MagicMock()
    frappe.conf.get = MagicMock(return_value="/nonexistent")
    frappe.db = MagicMock()
    frappe.db.has_column = MagicMock(return_value=has_columns)
    frappe.get_all = MagicMock(return_value=[])
    frappe.log_error = MagicMock()
    from raven_ai_agent.skills.migration_fixer.fixer import MigrationFixer
    return MigrationFixer(json_source_path="/nonexistent"), frappe


class TestFCer1bGuard(unittest.TestCase):

    def test_g01_range_query_never_runs_without_fields(self):
        """No folio fields -> get_quotations_in_range returns [] and issues NO query."""
        mf, frappe = _fixer(has_columns=False)
        self.assertEqual(mf.get_quotations_in_range("01000", "01010"), [])
        frappe.get_all.assert_not_called()

    def test_g02_by_folio_skips_custom_query_without_fields(self):
        """No folio fields -> get_quotation_by_folio uses only the title fallback."""
        mf, frappe = _fixer(has_columns=False)
        mf.get_quotation_by_folio("01000")
        for call in frappe.get_all.call_args_list:
            self.assertNotIn("custom_invoice_folio", str(call),
                             "custom-field query ran despite missing columns")

    def test_g03_report_degrades_with_honest_note(self):
        mf, _ = _fixer(has_columns=False)
        out = mf.generate_report()
        self.assertIn("custom_invoice_folio", out)
        self.assertIn("F-CER-1b", out)
        self.assertNotIn("| Scanned |", out)

    def test_g04_fields_present_path_unchanged(self):
        """With the fields installed, the folio query runs exactly as before."""
        mf, frappe = _fixer(has_columns=True)
        mf.get_quotation_by_folio("01000")
        joined = " ".join(str(c) for c in frappe.get_all.call_args_list)
        self.assertIn("custom_invoice_folio", joined)

    def test_g05_check_is_cached(self):
        mf, frappe = _fixer(has_columns=False)
        mf.has_folio_fields()
        mf.has_folio_fields()
        self.assertLessEqual(frappe.db.has_column.call_count, 2,
                             "has_column should be probed once per field, then cached")


if __name__ == "__main__":
    unittest.main()
