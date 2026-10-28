#!/usr/bin/env python3
"""Rank Hub findings by avoidable I/O. Usage: rank.py PAGE.json [PAGE.json ...]

Each file is the JSON array `perf-sentinel hub findings --format json` prints.
Writes one JSON object to stdout. Exit 2 when a file is not a JSON array.
"""
import json
import re
import sys

GROUPS = ["avoidable_io", "slow", "structural", "other"]
GROUP_OF = {
    "n_plus_one_sql": "avoidable_io", "n_plus_one_http": "avoidable_io", "n_plus_one_messaging": "avoidable_io",
    "redundant_sql": "avoidable_io", "redundant_http": "avoidable_io",
    "slow_sql": "slow", "slow_http": "slow", "slow_messaging": "slow",
    "excessive_fanout": "structural", "chatty_service": "structural",
    "pool_saturation": "structural", "serialized_calls": "structural",
}
SEVERITY = {"critical": 0, "warning": 1, "info": 2}
LEADING_NOISE = re.compile(r"\A(?:\s+|--[^\n]*|/\*.*?\*/)*", re.DOTALL)
# A write, alone or after a leading WITH ... CTE.
LOCK_WRITE = re.compile(r"(?:WITH\b.*\)\s*)?(?:INSERT|UPDATE|DELETE|MERGE|UPSERT|REPLACE)\b", re.DOTALL)
LOCK_CLAUSE = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|(?:KEY\s+)?SHARE)\b")


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def lock_risk(finding):
    if finding.get("type") != "slow_sql":
        return False
    sql = ((finding.get("pattern") or {}).get("template") or "").upper()
    return bool(LOCK_WRITE.match(LEADING_NOISE.sub("", sql)) or LOCK_CLAUSE.search(sql))


def acked(row):
    sources = row.get("sources") or []
    acked_ids = {a.get("source_id") for a in row.get("acks") or []}
    return bool(sources) and all(s.get("id") in acked_ids for s in sources)


def scale(value, rate):
    return None if value is None else round(value / rate) if rate else value


def source_entry(s, gaps):
    rate = s.get("detections_sampling_rate")
    if is_number(rate) and rate <= 0:
        gaps.add("sampling")
    has_counts = s.get("detections") is not None or s.get("avoidable_io_ops") is not None
    usable = rate if has_counts and is_number(rate) and 0 < rate < 1 else None
    gaps.update(s.get("detections_gaps") or [])
    return {
        "id": s.get("id"), "detections": s.get("detections"), "complete": s.get("detections_complete"),
        "rate": rate, "estimated": scale(s.get("detections"), usable),
        "_io": s.get("avoidable_io_ops"), "_est_io": scale(s.get("avoidable_io_ops"), usable), "_usable": usable,
    }


def total(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def item(row):
    f = row.get("finding") or {}
    gaps = set()
    entries = [source_entry(s, gaps) for s in row.get("sources") or []]
    known = [e for e in entries if e["detections"] is not None or e["_io"] is not None]
    if not known:
        state = "unknown"
    elif len(known) == len(entries) and all(e["complete"] is True for e in entries):
        state = "exact"
    else:
        state = "lower_bound"
    rates = [e["_usable"] for e in entries if e["_usable"] is not None]
    # Hub contract: a counted source without avoidable I/O makes the finding total unknown, not partial.
    io_partial = any(e["detections"] is not None and e["_io"] is None for e in entries)
    return {
        "signature": f.get("signature"), "type": f.get("type"), "severity": f.get("severity"),
        "service": f.get("service"), "endpoint": f.get("source_endpoint"),
        "code_location": f.get("code_location"), "suggestion": f.get("suggestion"),
        "template": (f.get("pattern") or {}).get("template"),
        "sources": [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries],
        "detections": total(e["detections"] for e in entries),
        "avoidable_io_ops": None if io_partial else total(e["_io"] for e in entries),
        "estimated_detections": total(e["estimated"] for e in entries),
        "estimated_avoidable_io_ops": None if io_partial else total(e["_est_io"] for e in entries),
        "state": state, "gaps": sorted(gaps), "extrapolated": bool(rates),
        "min_sampling_rate": min(rates) if rates else None,
        "per_trace_extra_io": (f.get("green_impact") or {}).get("estimated_extra_io_ops"),
        "lock_risk": lock_risk(f),
    }


def desc_null_last(v):
    return (v is None, -(v or 0))


def sort_key(group):
    sev = lambda i: SEVERITY.get(i["severity"], len(SEVERITY))  # noqa: E731
    if group == "avoidable_io":
        return lambda i: (i["estimated_avoidable_io_ops"] is None,
                          desc_null_last(i["estimated_avoidable_io_ops"] if i["estimated_avoidable_io_ops"] is not None
                                         else i["per_trace_extra_io"]), i["signature"])
    if group == "slow":
        return lambda i: (not i["lock_risk"], sev(i), desc_null_last(i["estimated_detections"]), i["signature"])
    return lambda i: (sev(i), desc_null_last(i["estimated_detections"]), i["signature"])


def rank(rows):
    seen, excluded, dropped, buckets, window = set(), 0, 0, {g: [] for g in GROUPS}, None
    for row in rows:
        sig = (row.get("finding") or {}).get("signature")
        if sig in seen:
            dropped += 1
            continue
        seen.add(sig)
        if acked(row):
            excluded += 1
            continue
        if window is None and row.get("detections_from") and row.get("detections_to"):
            window = {"from": row["detections_from"], "to": row["detections_to"]}
        it = item(row)
        buckets[GROUP_OF.get(it["type"], "other")].append(it)
    return {"window": window, "excluded_acked": excluded, "duplicates_dropped": dropped,
            "groups": [{"name": g, "findings": sorted(buckets[g], key=sort_key(g))} for g in GROUPS]}


def main(argv):
    rows, inputs = [], []
    for path in argv:
        try:
            with open(path) as fh:
                page = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"{path}: cannot read JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(page, list):
            print(f"{path}: not a JSON array", file=sys.stderr)
            return 2
        rows.extend(page)
        inputs.append({"file": path, "rows": len(page)})
    print(json.dumps({"inputs": inputs, **rank(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
