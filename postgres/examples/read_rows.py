"""Read evidence from the shared database without logging credentials."""
import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--table-id', default='List_of_National_Football_League_rushing_yards_leaders_0')
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    url = os.environ.get('DATABASE_URL')
    if not url and args.env_file:
        for line in args.env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('DATABASE_URL='):
                url = line.split('=', 1)[1].strip().strip('"')
                break
    if not url:
        parser.error('Set DATABASE_URL or supply --env-file with the privately shared reader URL.')
    with psycopg.connect(url, connect_timeout=30, row_factory=dict_row) as conn:
        rows = conn.execute(
            'SELECT table_id, title, url, row_index, evidence_text, cells '
            'FROM hybridqa.rag_rows WHERE table_id = %s ORDER BY row_index LIMIT %s',
            (args.table_id, args.limit),
        ).fetchall()
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
