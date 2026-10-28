import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RANK = Path(__file__).resolve().parent.parent / "skills" / "prod-findings" / "scripts" / "rank.py"
spec = importlib.util.spec_from_file_location("rank", RANK)
rank_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rank_mod)
rank = rank_mod.rank

def src(id="a", **kw):
    return {"id": id, **kw}


def row(sig="s", type="n_plus_one_sql", severity="warning", template="SELECT 1", per_trace=None,
        sources=None, acks=None, **kw):
    finding = {"type": type, "severity": severity, "service": "svc", "source_endpoint": "GET /x",
               "signature": sig, "suggestion": "fix it", "pattern": {"template": template},
               "code_location": None}
    if per_trace is not None:
        finding["green_impact"] = {"estimated_extra_io_ops": per_trace}
    r = {"finding": finding, "sources": sources if sources is not None else [src()], **kw}
    if acks is not None:
        r["acks"] = acks
    return r


def group(result, name):
    return next(g for g in result["groups"] if g["name"] == name)["findings"]


def sigs(result, name):
    return [f["signature"] for f in group(result, name)]


class RankTest(unittest.TestCase):
    def test_groups_in_spec_order(self):
        r = rank([row("a", "serialized_calls"), row("b", "slow_sql"), row("c", "redundant_sql")])
        self.assertEqual([g["name"] for g in r["groups"]], ["avoidable_io", "slow", "structural", "other"])
        self.assertEqual(sigs(r, "avoidable_io"), ["c"])
        self.assertEqual(sigs(r, "slow"), ["b"])
        self.assertEqual(sigs(r, "structural"), ["a"])

    def test_avoidable_io_sorted_by_volume(self):
        r = rank([row("red", "redundant_http", sources=[src(avoidable_io_ops=900, detections=10)]),
                  row("n1", "n_plus_one_sql", sources=[src(avoidable_io_ops=48200, detections=10)])])
        self.assertEqual(sigs(r, "avoidable_io"), ["n1", "red"])

    def test_unknown_volume_after_known_by_per_trace(self):
        r = rank([row("u3", per_trace=3), row("known", sources=[src(avoidable_io_ops=10, detections=1)]), row("u50", per_trace=50)])
        self.assertEqual(sigs(r, "avoidable_io"), ["known", "u50", "u3"])

    def test_sampling_extrapolated_per_source(self):
        r = rank([row(sources=[
            src("a", detections=100, detections_sampling_rate=0.1),
            src("b", detections=50, detections_sampling_rate=None)])])
        item = group(r, "avoidable_io")[0]
        self.assertEqual(item["detections"], 150)
        self.assertEqual(item["estimated_detections"], 1050)
        self.assertTrue(item["extrapolated"])
        self.assertEqual(item["min_sampling_rate"], 0.1)

    def test_zero_rate_is_not_divided(self):
        r = rank([row(sources=[src(detections=40, detections_sampling_rate=0)])])
        item = group(r, "avoidable_io")[0]
        self.assertEqual(item["estimated_detections"], 40)
        self.assertFalse(item["extrapolated"])
        self.assertIn("sampling", item["gaps"])

    def test_states(self):
        exact = rank([row(sources=[src(detections=5, detections_complete=True), src("b", detections=1, detections_complete=True)])])
        self.assertEqual(group(exact, "avoidable_io")[0]["state"], "exact")
        lower = rank([row(sources=[src(detections=5, detections_complete=False, detections_gaps=["restart"])])])
        item = group(lower, "avoidable_io")[0]
        self.assertEqual(item["state"], "lower_bound")
        self.assertIn("restart", item["gaps"])
        unknown = rank([row(sources=[src(detections=None), src("b")])])
        self.assertEqual(group(unknown, "avoidable_io")[0]["state"], "unknown")

    def test_mixed_sources_sum_known_and_name_unknown(self):
        r = rank([row(sources=[src("a", detections=None),
                               src("b", detections=20, detections_complete=False)])])
        item = group(r, "avoidable_io")[0]
        self.assertEqual(item["detections"], 20)
        self.assertEqual(item["state"], "lower_bound")
        self.assertIsNone(item["sources"][0]["detections"])
        self.assertEqual(item["sources"][0]["id"], "a")

    def test_acked_on_every_source_excluded(self):
        both = row("x", sources=[src("a"), src("b")], acks=[{"source_id": "a"}, {"source_id": "b"}])
        one = row("y", sources=[src("a"), src("b")], acks=[{"source_id": "a"}])
        r = rank([both, one])
        self.assertEqual(r["excluded_acked"], 1)
        self.assertEqual(sigs(r, "avoidable_io"), ["y"])

    def test_duplicate_signature_across_pages_is_kept_once(self):
        r = rank([row("d", sources=[src(avoidable_io_ops=1)]), row("d", sources=[src(avoidable_io_ops=2)])])
        items = group(r, "avoidable_io")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["avoidable_io_ops"], 1)

    def test_unknown_type_goes_to_other_group(self):
        r = rank([row("w", "blocking_wait")])
        self.assertEqual(sigs(r, "other"), ["w"])

    def test_slow_lock_risk_first(self):
        r = rank([row("sel", "slow_sql", "critical", "SELECT * FROM orders"),
                  row("upd", "slow_sql", "warning", "-- note\n  /* c */ UPDATE orders SET a = 1"),
                  row("http", "slow_http", "critical", "UPDATE x")])
        self.assertEqual(sigs(r, "slow"), ["upd", "http", "sel"])
        by = {f["signature"]: f for f in group(r, "slow")}
        self.assertTrue(by["upd"]["lock_risk"])
        self.assertFalse(by["http"]["lock_risk"])
        r = rank([row("fu", "slow_sql", template="SELECT * FROM t FOR UPDATE")])
        self.assertTrue(group(r, "slow")[0]["lock_risk"])

    def test_no_volume_fields_ranks_by_per_trace_impact(self):
        r = rank([row("low", per_trace=2), row("high", per_trace=9)])
        self.assertEqual(sigs(r, "avoidable_io"), ["high", "low"])
        self.assertTrue(all(f["state"] == "unknown" for f in group(r, "avoidable_io")))
        self.assertIsNone(r["window"])

    def test_window_from_first_row_carrying_both(self):
        r = rank([row("a"), row("b", detections_from="2026-10-01", detections_to="2026-10-08")])
        self.assertEqual(r["window"], {"from": "2026-10-01", "to": "2026-10-08"})

    def test_cli_rejects_non_array(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "page.json"
            bad.write_text("{}")
            p = subprocess.run([sys.executable, str(RANK), str(bad)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("page.json", p.stderr)

    def test_cli_concatenates_pages(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            a.write_text(json.dumps([row("a")]))
            b.write_text(json.dumps([row("b")]))
            p = subprocess.run([sys.executable, str(RANK), str(a), str(b)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(sorted(f["signature"] for f in json.loads(p.stdout)["groups"][0]["findings"]), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
