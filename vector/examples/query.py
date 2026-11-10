"""Query the shared Pinecone passage index without logging credentials."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retriever import VectorRetriever  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', nargs='?', default='Which stadium is home to D.C. United?')
    parser.add_argument('-k', type=int, default=5)
    parser.add_argument('--table-id', action='append', help='restrict to passages linked from this table')
    args = parser.parse_args()
    hits = VectorRetriever().search(args.question, k=args.k, table_ids=args.table_id)
    for hit in hits:
        hit['text'] = hit['text'][:300]
        hit['table_ids'] = hit['table_ids'][:5]
    print(json.dumps(hits, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
