"""Every `app_include_js` / `app_include_css` entry of this app is a served URL, in the working form, for a file that exists.

The three stale entries were written `raven_ai_agent/public/js/<x>.js` (no leading slash, no /assets/): the browser asks
for `/raven_ai_agent/public/js/<x>.js` and gets a 404 on every Desk page; and `sales_order_upload.js` is in no commit.
DB-free: hooks.py is parsed with `ast`, never imported.   python -m unittest raven_ai_agent.api.tests.test_hooks_includes
"""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PKG = os.path.join(ROOT, "raven_ai_agent")
PREFIX = "/assets/raven_ai_agent/"


def includes(*names):
    tree = ast.parse(open(os.path.join(PKG, "hooks.py"), encoding="utf8").read())
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) in names:
            out += ast.literal_eval(node.value)
    return out


class TestAppIncludes(unittest.TestCase):
    def test_the_hooks_declare_at_least_the_working_include(self):
        self.assertIn(PREFIX + "js/raven_ai_agent.js", includes("app_include_js"))

    def test_every_app_include_js_is_in_the_working_form(self):
        bad = [p for p in includes("app_include_js", "app_include_css") if not p.startswith(PREFIX)]
        self.assertEqual(bad, [], "not served under /assets/raven_ai_agent/: %s" % bad)

    def test_every_app_include_has_a_file_under_public(self):
        missing = [p for p in includes("app_include_js", "app_include_css")
                   if not os.path.isfile(os.path.join(PKG, "public", p[len(PREFIX):]))]
        self.assertEqual(missing, [], "no file under public/: %s" % missing)

    def test_the_stale_entries_are_gone(self):
        inc = includes("app_include_js")
        for name in ("sales_order_upload.js", "sales_invoice_upload.js", "documents_panel.js"):
            self.assertFalse([p for p in inc if p.endswith(name)], name)

    def test_the_two_existing_scripts_are_kept_on_disk_and_not_registered(self):
        for name in ("sales_invoice_upload.js", "documents_panel.js"):
            self.assertTrue(os.path.isfile(os.path.join(PKG, "public", "js", name)), name)
        self.assertEqual(includes("app_include_js"), [PREFIX + "js/raven_ai_agent.js"])


if __name__ == "__main__":
    unittest.main()
