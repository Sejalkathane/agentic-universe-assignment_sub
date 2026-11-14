import json
from collections import Counter
from .normalize import normalise_phone, parse_timestamp


def ingest_event_file(conn, pii, path, ingest_seq) -> dict:
    stats = Counter()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            stats["events_total"] += 1
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict) or not obj.get("event_id"):
                    raise ValueError
                ts = parse_timestamp(str(obj["occurred_at"]))
            except (ValueError, KeyError, TypeError):
                stats["malformed_events"] += 1
                continue
            phone = normalise_phone(str(obj.get("phone") or ""))
            cur = conn.execute(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)",
                (str(obj["event_id"]), str(obj.get("event_type") or ""),
                 obj.get("workflow_id"), obj.get("call_id"),
                 ts.isoformat(timespec="microseconds"),
                 pii.hash_phone(phone) if phone else None,
                 json.dumps(obj.get("payload") or {}), ingest_seq))
            if cur.rowcount == 0:
                stats["duplicate_events_dropped"] += 1
    return dict(stats)