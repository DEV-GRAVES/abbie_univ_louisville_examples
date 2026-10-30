"""Unit tests for fill_rate_analyzer.py  (added v1.1.1, extended v2.1.0)."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import fill_rate_analyzer as fra  # noqa: E402


class KpiBucketTests(unittest.TestCase):
    def test_empty_bucket_returns_zero(self):          # CHG-091 regression
        self.assertEqual(fra.KpiBucket().fill_rate, 0.0)
        self.assertEqual(fra.KpiBucket().on_time_rate, 0.0)

    def test_fill_rate(self):
        b = fra.KpiBucket()
        b.add(fra.OrderLine(date(2026, 10, 1), "S", "F", 100, 90, True))
        b.add(fra.OrderLine(date(2026, 10, 1), "S", "F", 100, 100, False))
        self.assertAlmostEqual(b.fill_rate, 0.95)
        self.assertAlmostEqual(b.on_time_rate, 0.5)


class LoadTests(unittest.TestCase):
    def test_clamp_and_skip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"
            p.write_text("order_date,site,sku_family,ordered_qty,shipped_qty,shipped_on_time\n"
                         "2026-10-01,A,F,10,15,1\n"     # clamped to 10
                         "2026-10-01,A,F,-1,0,1\n"      # skipped
                         "bad,A,F,1,1,1\n")              # skipped
            lines = fra.load_orders(p)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].shipped_qty, 10)


class ChangelogTests(unittest.TestCase):
    def test_parses_repo_changelog(self):
        rel = fra.parse_changelog(fra.CHANGELOG_PATH)
        self.assertEqual(rel[0]["version"], fra.__version__)   # version kept in sync
        self.assertTrue(any(i["type"] == "Fixed" for r in rel for i in r["items"]))


class CommsTests(unittest.TestCase):
    def test_text_is_escaped(self):
        msgs = fra.load_team_comms(fra.TEAM_COMMS_PATH)
        self.assertTrue(msgs)
        self.assertFalse(any("<b>" in m["text"] for m in msgs))


if __name__ == "__main__":
    unittest.main()
