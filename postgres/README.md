# PostgreSQL component

This component downloads HybridQA, normalizes Wikipedia tables into PostgreSQL, and verifies the import. For access to the already running database, use [the teammate guide](../docs/database-access.md); no reseeding is needed.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Initial schema, indexes, and row-evidence view |
| `pipeline.py` | Download, inventory, and resumable seeding commands |
| `sources.lock.json` | Dataset revisions used for the deployed corpus |
| `verify.py` | Source-count and sampled-content validation |
| `status.py` | Database and relation sizes |
| `provision_readers.py` | Owner-only reader creation and permission checks |
| `examples.sql` | Lookup, numeric ranking, aggregation, and entity joins |
| `examples/read_rows.py` | Runnable read-only RAG connection example |
| `test_pipeline.py` | Offline parsing/shape tests |
| `reports/` | Sanitized initial deployment evidence |

## Rebuild as the database maintainer

Requires Python 3.11+, PostgreSQL 17, and a newly created target database. Run commands from this `postgres/` directory. The loader does not create the PostgreSQL server or database.

1. Create a virtual environment and install `requirements.txt`.
2. Download and inspect the pinned dataset:

```bash
python pipeline.py download
python pipeline.py inventory
```

3. Put a direct local staging URL under `DATABASE_URL_UNPOOLED` in `.env.local`. Put the hosted owner URL under the same key in `.env`. Use `.env.example` as the template; no real password belongs in Git.
4. Load and validate locally, then seed the hosted database:

```bash
python pipeline.py seed --env .env.local
python verify.py --env .env.local
python pipeline.py seed --env .env
python verify.py --env .env
python provision_readers.py
python status.py --env .env
```

The hosted import requires a matching local measurement below 700,000,000 bytes, leaving room under the free storage quota. The initial full deployment was 264,552,448 bytes. Check current free-plan compute and storage allowances in the Neon console. No paid upgrade is performed by these scripts.

Imports commit complete tables in batches of 200 and resume from completed batches. Identical reruns leave counts unchanged. Source revisions and selection hashes must match; switching selections requires a fresh database. Use a direct connection for migrations/imports and pooled connections for RAG queries.

For a smaller corpus, pass the same `--limit N` to inventory, seed, and verify. Selection uses SHA-256 ordering with seed `heterorag-v1`, retains complete tables, and exports matching questions in their original splits. Measure a fresh staging database for each selection.

Raw archives and hashed Windows-safe JSON files are stored in ignored `data/`. The loader verifies table and passage bytes against the manifest. Questions, answers, and full passages stay outside PostgreSQL. The selected question splits intentionally may share source tables; traced answers are weak labels, and the test split has no reference answers.

## Schema

The `hybridqa` schema contains `wiki_tables`, `wiki_columns`, `wiki_rows`, `wiki_cells`, `entities`, `cell_links`, `column_links`, `source_info`, and view `rag_rows`. It preserves original text, column/header ordering, duplicate headers, metadata, and hyperlink order. Numeric parsing handles strict integers/decimals and valid thousands separators; ambiguous dates, ranges, and percentages remain text.

See [the evidence contract](../docs/database-access.md#evidence-contract) for RAG integration. The scripts are maintenance tools, not a web service or an LLM retriever.
