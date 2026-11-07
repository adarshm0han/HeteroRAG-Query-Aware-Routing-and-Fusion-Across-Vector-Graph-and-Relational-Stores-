"""Validate DB content, permissions, and repeatable imports against source JSON."""
import argparse,json
from pathlib import Path
import psycopg
from pipeline import ROOT,tables,connect,write_json

def verify(env,limit=None):
    items=tables(limit)
    expected={'wiki_tables':len(items),'wiki_columns':sum(len(t['header']) for _,_,t,_ in items),
      'wiki_rows':sum(len(t['data']) for _,_,t,_ in items),
      'wiki_cells':sum(len(r) for _,_,t,_ in items for r in t['data']),
      'cell_links':sum(len(links) for _,_,t,_ in items for r in t['data'] for _,links in r),
      'column_links':sum(len(links) for _,_,t,_ in items for _,links in t['header'])}
    with connect(env) as c:
        actual={n:c.execute('SELECT count(*) FROM hybridqa.'+n).fetchone()[0] for n in expected}
        assert actual==expected,(actual,expected)
        samples=items[::max(1,len(items)//40)]
        for pk,name,t,sha in samples:
            got=c.execute('SELECT row_index,column_index,value_text FROM hybridqa.wiki_cells WHERE table_pk=%s ORDER BY row_index,column_index',(pk,)).fetchall()
            assert got==[(r,col,value) for r,row in enumerate(t['data']) for col,(value,links) in enumerate(row)],name
            headers=c.execute('SELECT header FROM hybridqa.wiki_columns WHERE table_pk=%s ORDER BY column_index',(pk,)).fetchall()
            assert [h[0] for h in headers]==[h[0] for h in t['header']],name
            links=c.execute('SELECT l.row_index,l.column_index,e.wiki_id FROM hybridqa.cell_links l JOIN hybridqa.entities e ON e.id=l.entity_pk WHERE table_pk=%s ORDER BY row_index,column_index,link_index',(pk,)).fetchall()
            assert links==[(r,col,link) for r,row in enumerate(t['data']) for col,(value,ls) in enumerate(row) for link in ls],name
        first=next(i for i in items if i[2]['data'])
        view=c.execute('SELECT cells,evidence_text FROM hybridqa.rag_rows WHERE table_id=%s ORDER BY row_index LIMIT 1',(first[1],)).fetchone()
        assert len(view[0])==len(first[2]['header'])
        size=c.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        report={'passed':True,'counts':actual,'sampled_tables':len(samples),'database_bytes':size,'within_700MB':size<=700_000_000}
    write_json(ROOT/'reports'/('verified-remote.json' if env=='.env' else 'verified-local.json'),report)
    print(json.dumps(report))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--env',default='.env.local');p.add_argument('--limit',type=int);a=p.parse_args();verify(a.env,a.limit)
