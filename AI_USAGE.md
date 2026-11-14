# AI Usage Disclosure

## Tools used
Claude (claude.ai chat). No other AI tools.

## What I used them for
- Discussing the architecture: SQLite, an append-only events table, and
  deriving event-to-lead links at report time rather than storing them.
- A first draft of every module (normalize, schema, security, db, leads,
  events, reports, CLI) and of the unit tests.
- Choosing the PII approach: HMAC-SHA256 for phone matching and Fernet
  for encrypted fields.
- Step-by-step VS Code and Windows setup help.
- A first draft of this file and SUBMISSION.md, which I edited.

## What I wrote or decided myself
- [Write what is true. For example: I decided to keep unparsable
  timestamps as malformed events; I checked the schema JSONs and
  confirmed the reference fields are not PII; I added the equivalence
  test.]

## Where the AI was wrong or unhelpful
- It wrote code for the schema JSON and dispositions.csv formats before
  seeing the files. They happened to match, which I confirmed by opening
  the real files.
- Its first run instructions used a default schema path that only worked
  from the repo root, put --db/--schemas where they only worked before
  the subcommand, and left out pytest.ini so tests could not import the
  package. I hit these when following the steps and they were corrected.
- It told me to create files in a folder outside the starter repo; I had
  to move everything into the cloned repo's solution/ folder.
- [Add anything else you really hit.]

## How I verified AI-generated code
- Ran pytest (9 tests, including a test that drop_1 then drop_2 gives
  byte-identical reports to ingesting both at once, and that re-ingesting
  changes nothing).
- Ran the pipeline on the seed-42 small data and cross-checked totals:
  lead rows 2057 = sum of per-file rows; rejections 108 = sum of reasons;
  events 8745 = both drops; events table 8500 = 8745 - 8 malformed - 237
  duplicates.
- Re-ran ingest and saw every file skipped.
- Opened ledger.db and confirmed there are no plaintext phones or names.
- [Add: read each module line by line, only if you did.]