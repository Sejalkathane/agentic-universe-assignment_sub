import csv, json
from collections import Counter
from .normalize import parse_value


def evaluate_row(schema, colmap, cells):
    """Returns (reject_reason | None, values, warnings). Walks fields in schema order."""
    values, warnings = {}, 0
    ident = schema.identity_phone
    for f in schema.fields:
        i = colmap.get(f.name)
        raw = cells[i].strip() if i is not None and i < len(cells) else ""
        if raw == "":
            ok, val, present = False, None, False
        else:
            ok, val = parse_value(f.type, raw, f.values)
            present = True
        if f is ident:
            if not present:
                return f"missing_required:{f.name}", values, 0
            if not ok:
                return "invalid_phone", values, 0
        elif not ok:
            if f.required:
                return f"missing_required:{f.name}", values, 0
            if present:
                warnings += 1
        values[f.name] = val if ok else None
    return None, values, warnings


def ingest_lead_file(conn, pii, schema, path, batch_id) -> dict:
    stats = Counter()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return dict(stats)
        colmap = schema.map_headers(header)
        row_number = 0
        for cells in reader:
            if all(not c.strip() for c in cells):
                continue
            row_number += 1
            stats["lead_rows_total"] += 1
            reason, values, warns = evaluate_row(schema, colmap, cells)
            if reason:
                conn.execute("INSERT INTO rejections VALUES (?,?,?,?)",
                             (schema.workflow_id, batch_id, row_number, reason))
                continue
            stats["field_warnings"] += warns
            if _upsert(conn, pii, schema, batch_id, values):
                stats["duplicate_lead_rows_merged"] += 1
    return dict(stats)


def _upsert(conn, pii, schema, batch_id, values) -> bool:
    """Returns True if merged into an existing lead (a duplicate)."""
    ident = schema.identity_phone
    phone = values[ident.name]
    phash = pii.hash_phone(phone)
    row = conn.execute("SELECT lead_id, fields_json, pii_enc FROM leads "
                       "WHERE workflow_id=? AND phone_hash=?",
                       (schema.workflow_id, phash)).fetchone()
    public = json.loads(row["fields_json"]) if row else {}
    secret = pii.decrypt(row["pii_enc"]) if row else {}

    for f in schema.fields:  # last non-null write wins
        v = values.get(f.name)
        if v is None:
            continue
        target = secret if (f.pii or f is ident) else public
        target[f.name] = v
    for f in schema.fields:  # defaults after merging
        target = secret if f.pii else public
        if f.default is not None and target.get(f.name) is None:
            target[f.name] = f.default

    ref = schema.reference_field
    ext = (public.get(ref.name) or secret.get(ref.name)) if ref else None
    if row:
        conn.execute("UPDATE leads SET fields_json=?, pii_enc=?, external_ref=? "
                     "WHERE lead_id=?",
                     (json.dumps(public), pii.encrypt(secret), ext, row["lead_id"]))
        return True
    conn.execute("INSERT INTO leads(workflow_id, phone_hash, phone_last4, batch_id, "
                 "external_ref, fields_json, pii_enc) VALUES (?,?,?,?,?,?,?)",
                 (schema.workflow_id, phash, phone[-4:], batch_id, ext,
                  json.dumps(public), pii.encrypt(secret)))
    return False