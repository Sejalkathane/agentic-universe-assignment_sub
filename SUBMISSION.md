# Submission

## Candidate
- **Name:** Sejal Kathane
- **Assignment chosen:** A (Data)
- **Time spent (honest estimate):** 6

## How to run
Windows PowerShell, from the repo root:
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r solution/requirements.txt
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data

cd solution
pytest
python -m pipeline ingest ../data/drop_1
python -m pipeline ingest ../data/drop_2
python -m pipeline report --out ../reports
```
Optional flags: `--db` (default `ledger.db`) and `--schemas` (default: the repo's `assignment-a-data/schemas`).
Set `AU_PII_SECRET` to your own secret. If it isn't set, the code falls back to a dev secret and prints a warning.
Dependencies: `cryptography` and `pytest`. Everything else is the standard library.

## Design
I used SQLite. There are four tables:

- `ingest_files`: one row per ingested file, with its drop name, path, SHA-256 and the counts from that file. This is what makes re-ingest safe.
- `leads`: one row per (workflow_id, phone). It holds `phone_hash`, `phone_last4`, `batch_id`, `external_ref`, a JSON blob of the non-PII fields, and an encrypted blob of the PII fields.
- `rejections`: keyed by (workflow_id, batch_id, row_number), with the reason and no PII.
- `events`: the ledger. The event_id is the primary key, and triggers block UPDATE and DELETE, so it really is append-only.

The main decision is that I don't store which lead an event belongs to. Reports work it out when they run, by joining events to leads on (workflow_id, phone_hash). Overrides join through call_id instead, because they have no phone. This has two effects:

- An event that was an orphan after drop_1 links itself once its lead shows up in drop_2. Nothing has to be updated.
- Reports depend only on what is in the tables, not on the order drops arrived. A test checks that drop_1 then drop_2 gives byte-identical reports to ingesting both together.

Ingest does the validation, normalisation and merging. The report step reads the tables, builds calls per lead in Python, and writes the five files. Each lead's bucket and each call's effective disposition are computed in small pure functions (`bucket`, `effective_code`), so they're easy to unit test.

**PII.** `customer_name` and `phone` are marked pii in the schemas. They only exist inside a Fernet-encrypted blob (`leads.pii_enc`). To match events to leads I store an HMAC-SHA256 of the canonical phone, keyed with a secret. I didn't use a plain SHA-256 because there are only about 4 billion possible Indian mobile numbers, so an unkeyed hash can be brute-forced quickly. I also keep the last 4 digits, only so the report can print the masked phone. Raw phones from events are never stored.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| Don't store event→lead links; derive them at report time | Late-arriving leads work automatically, and the ledger never needs an UPDATE | Store `lead_id` on events and back-fill it after each lead ingest. More code, and it breaks "append-only" |
| A required field that is present but invalid (e.g. bad date) is rejected as `missing_required:<field>` | The spec only gives two rejection reasons | Add a third reason such as `invalid_<field>`, but that would change the contract |
| An event line with a missing or unparsable `occurred_at` counts as malformed | I can't place it in time, so it's useless to the ledger | Keep it and treat it as an orphan |
| Ties on `occurred_at` are broken by `event_id` | The spec is silent, and I wanted deterministic output | Ingestion order, which would depend on drop boundaries |
| If a call has several `call.initiated` events, use the earliest | The spec is silent | The latest |
| An event with no phone, or an invalid one, and no override link is an orphan | It can't be linked to a lead | A separate category |
| Orphan is checked before unknown disposition, and the lead's workflow is used for the catalogue lookup | Follows the order of the rules in the spec | |
| `rejections_by_reason` lists every required field, even with zero counts | Keeps the keys stable across seeds | Only list reasons that occurred |
| Only the first phone-type field is the lead identity | Both provided schemas have exactly one | |
| `external_ref` is stored in plaintext | It's needed in `lead_report.csv`, and it's not marked pii in either schema | Encrypt it. I'd have to if a schema ever marked the reference field as pii |
| Drops must be ingested in order | First valid row creates the lead and sets its `batch_id`, so order matters by the spec | |

## Failure modes considered
- **Re-running a drop.** Each file is logged with its SHA-256 in the same transaction as its data, so a re-run skips it. I checked this by hand and in a test.
- **A file changing after ingest.** The run stops with an error instead of silently ingesting different data.
- **Crash halfway through a file.** The whole file is one transaction, so it either fully lands or not at all.
- **Duplicate events**, in one file or across drops. The primary key on event_id catches them, and they're counted.
- **Malformed JSON lines and missing event_id.** Counted and skipped.
- **Events before their lead.** Handled by deriving links at report time.
- **Messy lead files.** Renamed or reordered columns, extra columns, blank rows, mixed date and currency formats, and six phone formats are all handled by the header mapping and the validators.

Not handled, or only partly:
- No locking, so two ingest processes at once on the same database isn't safe.
- If drop_2 is ingested before drop_1, `batch_id` and the merge winners change. I treat that as caller error.
- Unknown field types in a schema raise an error and stop the run.
- The report step loads all leads and events into memory.
- I couldn't compare my output with the company's expected output, so I can't claim the numbers are exact.

## Testing
9 tests pass.
- Unit tests for phone normalisation, the date and currency parsers, header normalisation, timestamp handling (UTC, offset, naive-as-IST), effective disposition (override beats set, latest wins) and bucket logic.
- Two integration tests on the generated seed-42 data. One checks that drop_1 then drop_2 produces byte-identical report files to ingesting both together. The other checks that re-ingesting everything changes nothing.

What I didn't test: a different seed beyond a manual run [only keep this if you did it], malformed CSV edge cases such as a file with no header, and any very large input.

## Results
On `--scale small` (seed 42):
- 2,057 lead rows read, 108 rejected (42 invalid phone, 66 missing required fields), 57 merged duplicates, 122 field warnings.
- 8,745 event lines read, 8 malformed, 237 duplicates dropped, 18 unknown dispositions, 462 orphans.
- I cross-checked the totals against each other. Per-file lead rows add up to 2,057, the rejection reasons add up to 108, and the `events` table has 8,500 rows, which is 8,745 minus 8 minus 237.
- Both workflows show in `batch_summary.csv` for batches 001 to 003.
- The full test run, including four ingests and four report runs, takes about 3 seconds on this data.

I didn't run `--scale large`, so I have no timings for it.

## If I had another day
1. Run on `--scale large` and measure it. I'd expect to move the per-lead aggregation into SQL.
2. Test on more seeds, and read the orphan and unknown-disposition counts closely, since those depend on subtle ordering rules.
3. Make the report step incremental, instead of recomputing from all events every time.
4. Add a lock around ingest so two runs can't overlap.
5. For 100k leads/day: use Postgres, run ingest on a schedule per drop, retry failed files, backfill by replaying drops in order, and keep the PII key in a secrets manager with a rotation plan.