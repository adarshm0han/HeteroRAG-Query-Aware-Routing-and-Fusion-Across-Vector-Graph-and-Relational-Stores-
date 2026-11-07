"""Reproducible HybridQA acquisition and PostgreSQL loader. No LLM dependency."""
import argparse, hashlib, io, json, os, re, sys, time, urllib.request, zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
REPOS={'questions':'wenhuchen/HybridQA','corpus':'wenhuchen/WikiTables-WithLinks'}
def digest(b): return hashlib.sha256(b).hexdigest()
def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def read_json(path): return json.loads(path.read_text(encoding='utf-8'))
def fetch(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HeteroRAG-dataset-loader'}),timeout=120) as r: return r.read()
        except Exception:
            if attempt==3: raise
            time.sleep(2**attempt)
def number(value):
    s=value.strip()
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',s): return None
    return Decimal(s.replace(',',''))
def download():
    DATA.mkdir(exist_ok=True)
    lockpath=DATA/'sources.json'
    pinned=ROOT/'sources.lock.json'
    locks=read_json(lockpath) if lockpath.exists() else (read_json(pinned) if pinned.exists() else {})
    write_json(lockpath,locks)
    for name,repo in REPOS.items():
        if name not in locks:
            commit=json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/master'))['sha']
            locks[name]={'repository':repo,'commit':commit}
            write_json(lockpath,locks)
        item=locks[name]; archive=DATA/(name+'.zip')
        if not archive.exists():
            print('Downloading',name,flush=True)
            payload=fetch(f'https://codeload.github.com/{repo}/zip/{item["commit"]}')
            archive.with_suffix('.partial').write_bytes(payload)
            archive.with_suffix('.partial').replace(archive)
        content=archive.read_bytes(); checksum=digest(content)
        if item.get('archive_sha256') and item['archive_sha256']!=checksum: raise ValueError('Archive checksum mismatch')
        item['archive_sha256']=checksum; write_json(lockpath,locks)
        manifest={}
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for entry in z.infolist():
                parts=entry.filename.split('/',1)
                if len(parts)<2: continue
                rel=parts[1]
                if name=='corpus' and rel.startswith(('tables_tok/','request_tok/')) and rel.endswith('.json'):
                    folder,table=rel.split('/',1); table=table[:-5]
                    dest=Path('raw')/folder/(digest(table.encode())+'.json')
                    payload=z.read(entry)
                    target=DATA/dest; target.parent.mkdir(parents=True,exist_ok=True)
                    if not target.exists() or digest(target.read_bytes())!=digest(payload): target.write_bytes(payload)
                    manifest[rel]={'path':dest.as_posix(),'sha256':digest(payload),'bytes':len(payload)}
                elif name=='questions' and rel.startswith('released_data/') and rel.endswith('.json'):
                    # Only direct JSON children; never extract archive-provided filesystem paths.
                    filename=rel.split('/')[-1]
                    if filename not in ['train.json','dev.json','test.json','train.traced.json','dev.traced.json','dev_reference.json']: continue
                    dest=DATA/'questions'/filename; dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes(z.read(entry))
            if name=='corpus': write_json(DATA/'manifest.json',manifest)
        print('Downloaded and verified',name,flush=True)
def tables(limit=None):
    manifest=read_json(DATA/'manifest.json')
    names=[p[len('tables_tok/'):-5] for p in manifest if p.startswith('tables_tok/')]
    # Fixed pseudo-random ordering, independent of Python hash seed and filesystem ordering.
    ordered=sorted(names,key=lambda n:digest(('heterorag-v1:'+n).encode()))
    selected=set(ordered[:limit] if limit else ordered)
    result=[]
    archive=zipfile.ZipFile(DATA/'corpus.zip')
    prefix=archive.namelist()[0].split('/')[0]+'/'
    for pk,name in enumerate(sorted(names),1):
        if name not in selected: continue
        entry=manifest[f'tables_tok/{name}.json']; raw=archive.read(prefix+f'tables_tok/{name}.json')
        if digest(raw)!=entry['sha256']: raise ValueError('Source checksum mismatch: '+name)
        result.append((pk,name,json.loads(raw),entry['sha256']))
    archive.close()
    return result
def validate_table(name,t):
    if not isinstance(t.get('header'),list) or not isinstance(t.get('data'),list): raise ValueError('Invalid table '+name)
    for row in [t['header']]+t['data']:
        if len(row)!=len(t['header']): raise ValueError('Ragged table '+name)
        for cell in row:
            if not (isinstance(cell,list) and len(cell)==2 and isinstance(cell[0],str) and isinstance(cell[1],list) and all(isinstance(x,str) for x in cell[1])): raise ValueError('Invalid cell '+name)
def inventory(limit=None):
    items=tables(limit); counts=Counter(); missing=[]; ids=set(); sizes=[]; manifest=read_json(DATA/'manifest.json')
    archive=zipfile.ZipFile(DATA/'corpus.zip'); prefix=archive.namelist()[0].split('/')[0]+'/'
    for pk,name,t,sha in items:
        validate_table(name,t); ids.add(name); counts['tables']+=1; counts['rows']+=len(t['data']); counts['cells']+=sum(map(len,t['data'])); sizes.append(len(t['data']))
        passage_bytes=archive.read(prefix+f'request_tok/{name}.json')
        if digest(passage_bytes)!=manifest[f'request_tok/{name}.json']['sha256']: raise ValueError('Passage checksum mismatch')
        passages=json.loads(passage_bytes)
        for row in [t['header']]+t['data']:
            for value,links in row:
                counts['links']+=len(links)
                for link in links:
                    if link not in passages: missing.append({'table_id':name,'wiki_id':link})
    archive.close()
    coverage={}
    for split in ['train','dev','test']:
        records=read_json(DATA/'questions'/(split+'.json')); kept=[r for r in records if r['table_id'] in ids]
        coverage[split]={'total_questions':len(records),'selected_questions':len(kept)}
        write_json(DATA/'selected'/(split+'.json'),kept)
    selection={'seed':'heterorag-v1','table_ids':sorted(ids),'count':len(ids),'coverage':coverage}
    write_json(DATA/'selection.json',selection)
    report={'counts':dict(counts),'question_coverage':coverage,'unresolved_links':missing,'row_count_distribution':{'min':min(sizes),'median':sorted(sizes)[len(sizes)//2],'max':max(sizes)},'sources':read_json(DATA/'sources.json')}
    write_json(ROOT/'reports'/'inventory.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['unresolved_links','sources']}),flush=True)
    print('Unresolved passage links:',len(missing),flush=True)
def connect(env):
    import psycopg
    # Values loaded without interpolation, expansion, or logging secrets.
    path=ROOT/env
    config={}
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k,v=line.split('=',1); config[k]=v.strip().strip('"')
    url=os.environ.get('DATABASE_URL_UNPOOLED') or config.get('DATABASE_URL_UNPOOLED')
    if not url: raise ValueError('DATABASE_URL_UNPOOLED missing from '+env)
    return psycopg.connect(url,connect_timeout=30)
def copy(cur,name,rows):
    if not rows: return
    with cur.copy('COPY hybridqa.'+name+' FROM STDIN') as c:
        for row in rows: c.write_row(row)
def seed(env,limit=None):
    from psycopg.types.json import Jsonb
    items=tables(limit)
    for _,name,t,_ in items: validate_table(name,t)
    entity_names=sorted({link for _,_,t,_ in items for row in [t['header']]+t['data'] for _,links in row for link in links})
    entities={name:i for i,name in enumerate(entity_names,1)}
    identity=digest(json.dumps([(name,sha) for _,name,_,sha in items]).encode())
    if env=='.env':
        measured=read_json(ROOT/'reports'/'local.json')
        if measured.get('selection_hash')!=identity or measured['database_bytes']>700_000_000:
            raise ValueError('Measure this exact selection locally below 700 MB before hosting it.')
    with connect(env) as conn:
        conn.execute('SELECT pg_advisory_lock(598,2026)')
        conn.execute((ROOT/'schema.sql').read_text())
        existing=conn.execute("SELECT value FROM hybridqa.source_info WHERE key='selection_hash'").fetchone()
        if existing and existing[0]!=identity: raise ValueError('Database belongs to a different selection; use a fresh database.')
        if not existing:
            conn.execute('INSERT INTO hybridqa.source_info VALUES (%s,%s)',('selection_hash',identity))
            conn.execute('INSERT INTO hybridqa.source_info VALUES (%s,%s)',('sources',json.dumps(read_json(DATA/'sources.json'))))
            copy(conn.cursor(),'entities',[(v,k) for k,v in entities.items()]); conn.commit()
        done=dict(conn.execute('SELECT table_id,source_hash FROM hybridqa.wiki_tables'))
        pending=[i for i in items if i[1] not in done]
        if any(done.get(name,sha)!=sha for _,name,_,sha in items): raise ValueError('Source drift')
        for offset in range(0,len(pending),200):
            batches={name:[] for name in ['wiki_tables','wiki_columns','wiki_rows','wiki_cells','cell_links','column_links']}
            for pk,name,t,sha in pending[offset:offset+200]:
                metadata={k:v for k,v in t.items() if k not in ['title','url','header','data']}
                batches['wiki_tables'].append((pk,name,t.get('title',''),t.get('url',''),Jsonb(metadata),sha))
                for col,(header,links) in enumerate(t['header']):
                    batches['wiki_columns'].append((pk,col,header))
                    for idx,link in enumerate(links): batches['column_links'].append((pk,col,idx,entities[link]))
                for row,cells in enumerate(t['data']):
                    batches['wiki_rows'].append((pk,row))
                    for col,(value,links) in enumerate(cells):
                        batches['wiki_cells'].append((pk,row,col,value,number(value)))
                        for idx,link in enumerate(links): batches['cell_links'].append((pk,row,col,idx,entities[link]))
            for name,rows in batches.items(): copy(conn.cursor(),name,rows)
            conn.commit()
            print('Committed tables',len(done)+min(offset+200,len(pending)),'/',len(items),flush=True)
        conn.execute('ANALYZE'); conn.commit()
        stats={'database_bytes':conn.execute('SELECT pg_database_size(current_database())').fetchone()[0],'selection_hash':identity}
        for name in ['wiki_tables','wiki_columns','wiki_rows','wiki_cells','entities','cell_links','column_links']:
            stats[name]=conn.execute('SELECT count(*) FROM hybridqa.'+name).fetchone()[0]
        write_json(ROOT/'reports'/('remote.json' if env=='.env' else 'local.json'),stats)
        print(json.dumps(stats),flush=True)
def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['download','inventory','seed']); p.add_argument('--env',default='.env.local'); p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.limit is not None and a.limit<1: p.error('limit must be positive')
    if a.command=='download': download()
    elif a.command=='inventory': inventory(a.limit)
    else: seed(a.env,a.limit)
if __name__=='__main__': main()
