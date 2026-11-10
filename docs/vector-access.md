# Querying the shared Pinecone passage index

The index `hybridqa-passages` is already seeded with all 286,270 HybridQA passages. You only need the API key, shared privately by the index owner (Vaibav). Put it in `vector/.env` (ignored by Git), using `vector/.env.example` as the template. Never post the key in issues, logs, screenshots, or pull requests.

```bash
cd vector
python -m pip install -r requirements.txt
python examples/query.py "Which stadium is home to D.C. United?" -k 5
python examples/query.py "Who coached the team?" --table-id List_of_National_Football_League_rushing_yards_leaders_0
```

In code:

```python
from retriever import VectorRetriever

retriever = VectorRetriever()                     # loads the bge-small query encoder (~130 MB, first run downloads it)
hits = retriever.search(question, k=10)           # whole corpus
hits = retriever.search(question, k=10, table_ids=[table_id])  # passages linked from the question's table
```

Queries must be embedded with the same model (`BAAI/bge-small-en-v1.5` plus its query instruction); `VectorRetriever` does this. Do not query the index with vectors from another model.

## Evidence contract

Each hit is a dict:

- `text`, `score` (cosine similarity), `source='vector'` — the fusion tuple.
- `passage_id`: original `/wiki/...` link. Joins to `cells[].entity_ids` in `hybridqa.rag_rows` and to Neo4j entity ids.
- `title`: passage title.
- `table_ids`: HybridQA tables linking to the passage (first 300); `table_count` is the true total. Use PostgreSQL for the complete link map of very common entities (e.g. `/wiki/United_States`, 831 tables).

## Budget etiquette

The free plan includes 1M read units per month, about 1.5M queries for this index — enough for evaluation, but cache retrieval results for repeated experiment runs rather than re-querying. Only the owner runs `upload`; writes are capped at 2M units per month and a full seed uses about half.
