"""Query the shared Pinecone passage index.

Each hit is a dict in the fusion layer's (text, score, source) shape plus provenance:
    {text, score, source='vector', passage_id, title, table_ids, table_count}
"""
import os

from pipeline import MODEL, QUERY_PREFIX, get_index, load_env, pick_device


class VectorRetriever:
    def __init__(self, device=None):
        from sentence_transformers import SentenceTransformer

        load_env()
        self.index = get_index()
        self.model = SentenceTransformer(MODEL, device=device or pick_device())

    def embed(self, queries):
        return self.model.encode([QUERY_PREFIX + q for q in queries], normalize_embeddings=True).tolist()

    def search(self, query, k=10, table_ids=None):
        """Top-k passages; pass table_ids to restrict to passages linked from those tables."""
        flt = {'table_ids': {'$in': list(table_ids)}} if table_ids else None
        res = self.index.query(vector=self.embed([query])[0], top_k=k, include_metadata=True, filter=flt)
        return [
            {
                'text': m.metadata['text'],
                'score': m.score,
                'source': 'vector',
                'passage_id': m.metadata['passage_id'],
                'title': m.metadata['title'],
                'table_ids': m.metadata['table_ids'],
                'table_count': int(m.metadata['table_count']),
            }
            for m in res.matches
        ]
