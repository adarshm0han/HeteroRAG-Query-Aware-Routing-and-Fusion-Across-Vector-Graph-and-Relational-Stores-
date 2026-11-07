# Connecting to the shared PostgreSQL database

## What the owner shares privately

Share a complete `DATABASE_URL` for a **reader** login. The connection string contains the hostname, database, username, password, and TLS settings. Do not share the owner URL or commit any real connection string.

- `rag_reader`: application and notebook queries.
- `team_reader`: manual exploration and development.

Both accounts can SELECT from the `hybridqa` schema, including `rag_rows`, but cannot modify source data. They use a 30-second statement timeout. These are shared service credentials; if a teammate needs individually revocable access, the owner should create a separate login in the `heterorag_readonly` group.

The project owner already has the private connection files `.env.rag_reader` and `.env.team_reader` in the original local database workspace. Send the appropriate file through a private channel. Teammates should place it inside their clone's `postgres/` directory. The repository's ignore rules exclude these files.

For the RAG application, copy the **value after `DATABASE_URL=`** into its environment or secret manager. Do not include the variable name in the URL value. A typical URL has this form:

```dotenv
DATABASE_URL=postgresql://rag_reader:REPLACE_WITH_PRIVATE_PASSWORD@REPLACE_WITH_POOLED_HOST:5432/heterorag?sslmode=require&channel_binding=require
```

| Setting | Value |
|---|---|
| Host | Pooled hostname from the privately shared URL |
| Port | `5432` |
| Database | `heterorag` |
| Schema | `hybridqa` |
| RAG user | `rag_reader` |
| Manual browsing user | `team_reader` |
| Password | Supplied privately |
| TLS | Required; retain URL TLS parameters |

Teammates do not need a Neon account for direct SQL access. Access to the Neon dashboard is a separate project permission and is not needed by the RAG code. The database runs remotely; the owner's laptop does not need to stay on. Internet access to the database is required. The free compute may sleep when idle, so allow a connection timeout of at least 30 seconds.

## Run the Python example

From the repository root:

```bash
cd postgres
python -m pip install -r requirements.txt
python examples/read_rows.py --env-file .env.rag_reader
```

Alternatively, set `DATABASE_URL` in your application's environment and omit `--env-file`. Environment configuration takes precedence over the optional file. The example prints evidence rows, never the connection URL.

The core query for your RAG pipeline is:

```python
import os
import psycopg
from psycopg.rows import dict_row

with psycopg.connect(os.environ['DATABASE_URL'],
                     connect_timeout=30, row_factory=dict_row) as conn:
    evidence = conn.execute(
        '''SELECT table_id, title, url, row_index, evidence_text, cells
           FROM hybridqa.rag_rows
           WHERE table_id = %s
           ORDER BY row_index
           LIMIT %s''',
        ('List_of_National_Football_League_rushing_yards_leaders_0', 5),
    ).fetchall()
```

Use parameter binding rather than formatting questions into SQL. For a long-running service, reuse a bounded connection pool instead of opening a new connection for every retrieved row. The example is a connection demonstration, not a complete question-to-SQL retriever.

## Evidence contract

`hybridqa.rag_rows` exposes:

- `table_id`: original HybridQA table identifier; use this across all three stores.
- `title`, `url`: source provenance.
- `row_index`: original zero-based row position.
- `evidence_text`: human-readable headers and values for the row.
- `cells`: ordered JSON array with `column_index`, `header`, `value`, optional `numeric_value`, and linked `/wiki/...` entity identifiers in `entity_ids`.

Internal integer database keys are implementation details. Preserve `(table_id, row_index, column_index)` and Wikipedia identifiers when building graph/vector integrations. Relevance scores are assigned by the retriever/fusion layer; SQL matches do not supply a semantic similarity score.

Question files, reference answers, and full passage text are outside this SQL evidence database. The original benchmark provides the associated table for a question; searching the entire table corpus is additional retrieval work.

## Troubleshooting

- Authentication failure: check that the URL and password were copied intact; do not use the example placeholders.
- Relation not found: select database `heterorag` and qualify tables with `hybridqa.`.
- Connection failure: retain TLS settings and check your runtime/network permits outbound PostgreSQL connections.
- Empty results: verify the exact source `table_id`.
- Permission denied on INSERT/UPDATE/DDL: expected for reader accounts; schema changes belong to the owner.
- Never post a full URL/password in issues, logs, screenshots, or pull requests.
