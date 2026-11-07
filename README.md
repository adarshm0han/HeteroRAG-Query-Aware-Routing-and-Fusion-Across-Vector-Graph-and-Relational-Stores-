# HeteroRAG

Query-aware routing and evidence fusion across vector, graph, and relational stores, using HybridQA.

## Repository structure

```text
postgres/              PostgreSQL schema, dataset loader, verification, SQL examples
  examples/            Minimal connection example for RAG integration
  reports/             Sanitized results from the initial verified deployment
  sources.lock.json    Exact upstream dataset revisions and archive checksums
docs/                  Team onboarding and integration contracts
```

The current implementation is the relational component. Vector retrieval, Neo4j, routing, and fusion can be added as separate components when implemented.

## For teammates

The shared PostgreSQL database is already seeded. You do **not** need to download the dataset or seed another database to query it.

1. Follow [the connection guide](docs/database-access.md).
2. Obtain the read-only `DATABASE_URL` privately from the project owner.
3. Use [the Python connection example](postgres/examples/read_rows.py) and [SQL examples](postgres/examples.sql).

The full corpus contains 15,316 source tables, 241,435 rows, and 1,081,904 cells. The verified deployment used approximately 265 MB including indexes. Snapshot reports are under `postgres/reports/`; current usage must be checked against the live database.

For rebuilding or maintaining the database, see [PostgreSQL setup](postgres/README.md). Keep data downloads, passwords, local databases, and model artifacts out of Git.

## Development

Use a branch for each component or feature and open a pull request into `main`. Keep component dependencies and tests together. Changes to shared evidence identifiers or formats should update [the SQL contract](docs/database-access.md#evidence-contract).

```bash
cd postgres
python -m pip install -r requirements.txt
python -m pytest -q
```

## Sources

- [HybridQA](https://github.com/wenhuchen/HybridQA)
- [WikiTables-WithLinks](https://github.com/wenhuchen/WikiTables-WithLinks)
- [HybridQA paper](https://aclanthology.org/2020.findings-emnlp.91/)
- [Dataset site and CC BY 4.0 attribution](https://hybridqa.github.io/)

Dataset content is downloaded from upstream; it is not redistributed here. Preserve upstream attribution when sharing it.
