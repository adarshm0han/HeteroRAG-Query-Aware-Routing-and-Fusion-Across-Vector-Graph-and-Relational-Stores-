"""Print database storage use without revealing connection credentials."""
import argparse,json
from pipeline import connect
p=argparse.ArgumentParser();p.add_argument('--env',default='.env');a=p.parse_args()
with connect(a.env) as c:
    total=c.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    relations=c.execute("SELECT relname,pg_total_relation_size(relid) FROM pg_catalog.pg_statio_user_tables WHERE schemaname='hybridqa' ORDER BY pg_total_relation_size(relid) DESC").fetchall()
    print(json.dumps({'database_bytes':total,'target_bytes':700_000_000,'within_target':total<=700_000_000,'relations_including_indexes':dict(relations)},indent=2))
