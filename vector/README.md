# Vector component

Embeds HybridQA's hyperlinked Wikipedia passages locally and serves them from a shared Pinecone index. For querying the index that is already seeded, use [the teammate guide](../docs/vector-access.md); no reseeding is needed.

## Files

| File | Purpose |
|---|---|
| `pipeline.py` | `download`, `embed`, `upload` (resumable), `verify` commands |
| `retriever.py` | `VectorRetriever.search(question, k, table_ids=None)` for the RAG pipeline |
| `examples/query.py` | Runnable query example |
| `test_pipeline.py` | Offline parsing/id/metadata tests |

## Corpus and model

- Source: `WikiTables-WithLinks/request_tok` at revision `dc066e1a`, the passage text behind every `/wiki/...` link in the HybridQA tables.
- 512,670 table-to-passage links dedupe to **286,270 unique passages** (median 120 words, p99 411). One passage = one vector; no chunking, so record identity matches HybridQA's gold passage links.
- Embedding model: `BAAI/bge-small-en-v1.5` (384-d, cosine, run locally — free). Passages are embedded as `"{title}. {text}"`; queries get the bge query instruction (handled by `retriever.py`).
- Size: 286K × 384 × 4 B ≈ 440 MB of vectors plus ~190 MB of passage text.

## Pinecone index

`hybridqa-passages`, serverless AWS us-east-1 (Starter/free plan), dimension 384, cosine.

Record id: the `/wiki/...` link, percent-encoded because Pinecone ids must be ASCII (22K links are not, e.g. `/wiki/São_Paulo`). Metadata:

| Field | Meaning |
|---|---|
| `passage_id` | Original `/wiki/...` link; same identifier as `entity_ids` in `hybridqa.rag_rows` |
| `title`, `text` | Passage title and full text |
| `table_ids` | HybridQA tables linking to this passage, capped at 300 (Pinecone's 40 KB metadata limit) |
| `table_count` | True number of linking tables; the complete link map is in PostgreSQL |

## Free-plan budget

Starter allows 2 GB storage, 2M write units and 1M read units per month. A query costs 1 RU per GB of namespace (this index ≈ 0.65 GB), regardless of `top_k`, so ~1.5M queries/month. Upserts cost 1 WU per KB: a full seed uses roughly 0.7–1.3M WU, so **only seed once per month**. `upload` checkpoints to `data/upload_checkpoint.json` and resumes instead of re-sending records.

## Rebuild as the index maintainer

Requires Python 3.10–3.12. Run from this `vector/` directory.

```bash
python -m pip install -r requirements.txt
cp .env.example .env            # add the Pinecone API key; never commit it
python pipeline.py download
python pipeline.py embed        # ~286K passages; uses CUDA/MPS when available
python pipeline.py upload
python pipeline.py verify
```

`data/embeddings.npy` + `data/passages.parquet` (row i ↔ vector i) can also back a local FAISS index for offline experiments.
