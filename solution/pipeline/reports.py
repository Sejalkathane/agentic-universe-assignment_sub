import csv, json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from .normalize import IST


@dataclass
class Call:
    lead_id: int
    initiated: datetime | None = None
    connected: bool = False
    failed: bool = False
    sets: list = field(default_factory=list)
    overrides: list = field(default_factory=list)


def effective_code(call):
    """Latest override, else latest set, else None (lists are chronological)."""
    if call.overrides:
        return call.overrides[-1]
    return call.sets[-1] if call.sets else None


def bucket(calls, is_terminal):
    if not calls:
        return "yet_to_reach_out"
    for c in calls:
        code = effective_code(c)
        if code is not None and is_terminal(code):
            return "completed"
    if all(c.failed for c in calls):
        return "in_progress_telephony_failed"
    return "in_progress_dialed"


def derive(conn, cat):
    leads, by_phone = {}, {}
    for r in conn.execute("SELECT * FROM leads"):
        leads[r["lead_id"]] = r
        by_phone[(r["workflow_id"], r["phone_hash"])] = r["lead_id"]

    rows = conn.execute("SELECT event_id, event_type, workflow_id, call_id, "
                        "occurred_at_utc, phone_hash, payload_json FROM events "
                        "ORDER BY occurred_at_utc, event_id").fetchall()
    orphans = unknown = 0
    call_lead, linked, overrides = {}, [], []

    for r in rows:  # pass 1: link via phone
        if r["event_type"] == "disposition.override":
            overrides.append(r)
            continue
        lid = by_phone.get((r["workflow_id"], r["phone_hash"])) if r["phone_hash"] else None
        if lid is None:
            orphans += 1
            continue
        if r["call_id"]:
            call_lead.setdefault(r["call_id"], lid)
        linked.append((lid, r))
    for r in overrides:  # pass 2: link via call_id
        lid = call_lead.get(r["call_id"])
        if lid is None:
            orphans += 1
        else:
            linked.append((lid, r))
    linked.sort(key=lambda x: (x[1]["occurred_at_utc"], x[1]["event_id"]))

    calls = {}
    for lid, r in linked:
        wf, t = leads[lid]["workflow_id"], r["event_type"]
        code = None
        if t in ("disposition.set", "disposition.override"):
            code = json.loads(r["payload_json"]).get("disposition_code")
            if cat.get(wf, code) is None:
                unknown += 1
                continue
        if not r["call_id"]:
            continue
        c = calls.setdefault(r["call_id"], Call(lid))
        if t == "call.initiated":
            if c.initiated is None:
                c.initiated = datetime.fromisoformat(r["occurred_at_utc"])
        elif t == "call.connected":
            c.connected = True
        elif t == "call.telephony_failed":
            c.failed = True
        elif t == "disposition.set":
            c.sets.append(code)
        elif t == "disposition.override":
            c.overrides.append(code)

    per_lead = {}
    for c in calls.values():
        if c.initiated is not None:
            per_lead.setdefault(c.lead_id, []).append(c)
    return leads, per_lead, orphans, unknown


def _w(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def write_reports(conn, schemas, cat, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    leads, per_lead, orphans, unknown = derive(conn, cat)

    lead_rows, batch, daily = [], {}, {}
    for lid, L in leads.items():
        wf = L["workflow_id"]
        cs = sorted(per_lead.get(lid, []), key=lambda c: c.initiated)
        b = bucket(cs, lambda code: cat.is_terminal(wf, code))
        bk = batch.setdefault((wf, L["batch_id"]), dict.fromkeys(
            ["total", "yet_to_reach_out", "in_progress_telephony_failed",
             "in_progress_dialed", "completed"], 0))
        bk["total"] += 1
        bk[b] += 1

        cur = next((effective_code(c) for c in reversed(cs)
                    if effective_code(c) is not None), "")
        ever = False
        for c in cs:
            code = effective_code(c)
            d = daily.setdefault((wf, c.initiated.astimezone(IST).date().isoformat()),
                                 [0, 0, set()])
            d[0] += 1
            d[1] += c.connected
            if code is not None and cat.is_success(wf, code):
                ever = True
                d[2].add(lid)
        last = cs[-1].initiated.astimezone(IST).isoformat(timespec="seconds") if cs else ""
        lead_rows.append((wf, L["external_ref"] or "", L["batch_id"],
                          "+91******" + L["phone_last4"], b, len(cs),
                          sum(c.connected for c in cs), last, cur,
                          "true" if ever else "false"))

    _w(out / "batch_summary.csv",
       ["workflow_id", "batch_id", "total_leads", "yet_to_reach_out",
        "in_progress_telephony_failed", "in_progress_dialed", "completed"],
       [(wf, bid, v["total"], v["yet_to_reach_out"], v["in_progress_telephony_failed"],
         v["in_progress_dialed"], v["completed"]) for (wf, bid), v in sorted(batch.items())])
    _w(out / "daily_overview.csv",
       ["workflow_id", "date", "total_calls", "connected_calls",
        "connectivity_rate", "success_leads"],
       [(wf, d, t, c, f"{c / t:.4f}", len(s)) for (wf, d), (t, c, s) in sorted(daily.items())])
    _w(out / "lead_report.csv",
       ["workflow_id", "external_ref", "batch_id", "phone_masked", "bucket",
        "total_calls", "connected_calls", "last_call_at", "current_disposition",
        "ever_success"], sorted(lead_rows, key=lambda r: (r[0], r[1])))

    rej = conn.execute("SELECT workflow_id, batch_id, row_number, reason FROM rejections "
                       "ORDER BY workflow_id, batch_id, row_number").fetchall()
    _w(out / "rejections.csv", ["workflow_id", "batch_id", "row_number", "reason"],
       [tuple(r) for r in rej])

    totals = {k: 0 for k in ["lead_rows_total", "field_warnings",
              "duplicate_lead_rows_merged", "events_total", "malformed_events",
              "duplicate_events_dropped"]}
    for (s,) in conn.execute("SELECT stats_json FROM ingest_files"):
        for k, v in json.loads(s).items():
            totals[k] = totals.get(k, 0) + v
    reasons = {"invalid_phone": 0}
    for sc in schemas.values():
        for f in sc.fields:
            if f.required:
                reasons[f"missing_required:{f.name}"] = 0
    for r in rej:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    dq = {"lead_rows_total": totals["lead_rows_total"], "lead_rows_rejected": len(rej),
          "rejections_by_reason": dict(sorted(reasons.items())),
          "duplicate_lead_rows_merged": totals["duplicate_lead_rows_merged"],
          "field_warnings": totals["field_warnings"],
          "events_total": totals["events_total"],
          "malformed_events": totals["malformed_events"],
          "duplicate_events_dropped": totals["duplicate_events_dropped"],
          "orphan_events": orphans, "unknown_disposition_events": unknown}
    (out / "data_quality.json").write_text(json.dumps(dq, indent=2) + "\n",
                                           encoding="utf-8")