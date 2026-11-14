import argparse, hashlib, json
from pathlib import Path
from .db import connect
from .events import ingest_event_file
from .leads import ingest_lead_file
from .reports import write_reports
from .schema import Catalogue, load_schemas
from .security import PII

# solution/pipeline/__main__.py -> repo root is two levels above "pipeline"
DEFAULT_SCHEMAS = Path(__file__).resolve().parents[2] / "assignment-a-data" / "schemas"


def ingest_drop(conn, pii, schemas, drop: Path):
    drop_name = drop.name
    jobs = []
    for wf_dir in sorted((drop / "leads").glob("*")):
        jobs += [("leads", wf_dir.name, p) for p in sorted(wf_dir.glob("*.csv"))]
    jobs += [("events", None, p) for p in sorted((drop / "events").glob("*.jsonl"))]

    for kind, wf, path in jobs:
        rel = path.relative_to(drop).as_posix()
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        prev = conn.execute("SELECT sha256 FROM ingest_files WHERE drop_name=? AND "
                            "rel_path=?", (drop_name, rel)).fetchone()
        if prev:
            if prev["sha256"] != sha:
                raise SystemExit(f"{drop_name}/{rel} changed since it was ingested")
            print(f"skip   {drop_name}/{rel}")
            continue
        with conn:  # one transaction per file: data + log commit together
            seq = conn.execute("INSERT INTO ingest_files(drop_name, rel_path, kind, "
                               "sha256, stats_json) VALUES (?,?,?,?,'{}')",
                               (drop_name, rel, kind, sha)).lastrowid
            if kind == "leads":
                stats = ingest_lead_file(conn, pii, schemas[wf], path, path.stem)
            else:
                stats = ingest_event_file(conn, pii, path, seq)
            conn.execute("UPDATE ingest_files SET stats_json=? WHERE seq=?",
                         (json.dumps(stats), seq))
        print(f"ingest {drop_name}/{rel}  {stats}")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="ledger.db")
    common.add_argument("--schemas", default=str(DEFAULT_SCHEMAS))

    ap = argparse.ArgumentParser(prog="pipeline", parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest", parents=[common])
    s.add_argument("drop")
    r = sub.add_parser("report", parents=[common])
    r.add_argument("--out", required=True)
    a = ap.parse_args()

    conn, schemas = connect(a.db), load_schemas(a.schemas)
    if a.cmd == "ingest":
        ingest_drop(conn, PII(), schemas, Path(a.drop))
    else:
        write_reports(conn, schemas, Catalogue(Path(a.schemas) / "dispositions.csv"),
                      a.out)


if __name__ == "__main__":
    main()