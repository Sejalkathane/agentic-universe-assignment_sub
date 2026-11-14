import shutil
from pathlib import Path

import pytest

from pipeline.__main__ import DEFAULT_SCHEMAS, ingest_drop
from pipeline.db import connect
from pipeline.reports import write_reports
from pipeline.schema import Catalogue, load_schemas
from pipeline.security import PII

DATA = Path(__file__).resolve().parents[2] / "data"
FILES = ["batch_summary.csv", "daily_overview.csv", "lead_report.csv",
         "rejections.csv", "data_quality.json"]

pytestmark = pytest.mark.skipif(not (DATA / "drop_1").exists(),
                                reason="generate data first")


def run(db_path, drops, out):
    conn = connect(str(db_path))
    schemas = load_schemas(DEFAULT_SCHEMAS)
    for d in drops:
        ingest_drop(conn, PII("test-secret"), schemas, d)
    write_reports(conn, schemas, Catalogue(DEFAULT_SCHEMAS / "dispositions.csv"), out)
    conn.close()
    return {f: (Path(out) / f).read_bytes() for f in FILES}


def test_incremental_equals_all_at_once(tmp_path):
    a = run(tmp_path / "a.db", [DATA / "drop_1", DATA / "drop_2"], tmp_path / "ra")

    combined = tmp_path / "combined"
    for d in ("drop_1", "drop_2"):
        shutil.copytree(DATA / d, combined, dirs_exist_ok=True)
    b = run(tmp_path / "b.db", [combined], tmp_path / "rb")

    assert a == b


def test_reingest_changes_nothing(tmp_path):
    drops = [DATA / "drop_1", DATA / "drop_2"]
    first = run(tmp_path / "c.db", drops, tmp_path / "r1")
    second = run(tmp_path / "c.db", drops, tmp_path / "r2")
    assert first == second