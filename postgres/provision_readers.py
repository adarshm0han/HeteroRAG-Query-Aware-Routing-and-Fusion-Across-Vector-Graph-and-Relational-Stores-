"""Create restricted logins and save credentials locally without printing them."""
import secrets
from urllib.parse import urlsplit,urlunsplit,quote
import psycopg
from psycopg import sql
from pipeline import ROOT,connect,write_json

with connect('.env') as c:
    if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='heterorag_readonly'").fetchone():
        c.execute('CREATE ROLE heterorag_readonly NOLOGIN')
    c.execute('GRANT CONNECT ON DATABASE heterorag TO heterorag_readonly')
    c.execute('GRANT USAGE ON SCHEMA hybridqa TO heterorag_readonly')
    c.execute('GRANT SELECT ON ALL TABLES IN SCHEMA hybridqa TO heterorag_readonly')
    c.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA hybridqa GRANT SELECT ON TABLES TO heterorag_readonly')
    owner=c.info.dsn
    # Source URL is used only to construct encrypted, independently authenticated clients.
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    base=conninfo_to_dict(owner)
    for role in ['rag_reader','team_reader']:
        dest=ROOT/('.env.'+role)
        if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
            if not dest.exists(): raise RuntimeError('Existing role has no local credential file: '+role)
            continue
        password=secrets.token_urlsafe(32)
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION').format(sql.Identifier(role),sql.Literal(password)))
        c.execute(sql.SQL('GRANT heterorag_readonly TO {}').format(sql.Identifier(role)))
        c.execute(sql.SQL("ALTER ROLE {} SET statement_timeout='30s'").format(sql.Identifier(role)))
        host=base['host']; pooled=host if '-pooler.' in host else host.replace('.', '-pooler.',1)
        url='postgresql://'+role+':'+quote(password,safe='')+'@'+pooled+'/'+base['dbname']+'?sslmode=require&channel_binding=require'
        # Save before commit: rerun can recover after an interrupted commit.
        dest.write_text('DATABASE_URL='+url+'\n',encoding='utf-8')
        c.commit()
    c.commit()

results={}
for role in ['rag_reader','team_reader']:
    url=(ROOT/('.env.'+role)).read_text().strip().split('=',1)[1]
    with psycopg.connect(url,connect_timeout=30) as c:
        count=c.execute('SELECT count(*) FROM hybridqa.wiki_tables').fetchone()[0]
        # Neon terminates client TLS at its proxy; pg_stat_ssl describes the
        # proxy-to-backend hop. Check the actual client socket through libpq.
        assert c.pgconn.ssl_in_use
        blocked=False
        try: c.execute("INSERT INTO hybridqa.source_info VALUES ('permission_probe','must_not_write')")
        except psycopg.errors.InsufficientPrivilege: c.rollback();blocked=True
        else: c.rollback()
        assert blocked
        results[role]={'remote_select':True,'tls':True,'writes_denied':True,'tables':count}
write_json(ROOT/'reports'/'access.json',results)
print('Verified encrypted remote SELECT and denied INSERT for both reader roles.')
