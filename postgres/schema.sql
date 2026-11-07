BEGIN;
CREATE SCHEMA IF NOT EXISTS hybridqa;
CREATE TABLE IF NOT EXISTS hybridqa.source_info (key text PRIMARY KEY, value text NOT NULL);
CREATE TABLE IF NOT EXISTS hybridqa.wiki_tables (
 id integer PRIMARY KEY, table_id text UNIQUE NOT NULL, title text NOT NULL,
 url text NOT NULL, metadata jsonb NOT NULL, source_hash text NOT NULL
);
CREATE TABLE IF NOT EXISTS hybridqa.wiki_columns (
 table_pk integer REFERENCES hybridqa.wiki_tables(id), column_index integer CHECK(column_index>=0),
 header text NOT NULL, PRIMARY KEY(table_pk,column_index)
);
CREATE TABLE IF NOT EXISTS hybridqa.wiki_rows (
 table_pk integer REFERENCES hybridqa.wiki_tables(id), row_index integer CHECK(row_index>=0),
 PRIMARY KEY(table_pk,row_index)
);
CREATE TABLE IF NOT EXISTS hybridqa.wiki_cells (
 table_pk integer NOT NULL, row_index integer NOT NULL, column_index integer NOT NULL,
 value_text text NOT NULL, numeric_value numeric,
 PRIMARY KEY(table_pk,row_index,column_index),
 FOREIGN KEY(table_pk,row_index) REFERENCES hybridqa.wiki_rows,
 FOREIGN KEY(table_pk,column_index) REFERENCES hybridqa.wiki_columns
);
CREATE TABLE IF NOT EXISTS hybridqa.entities (id integer PRIMARY KEY, wiki_id text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS hybridqa.cell_links (
 table_pk integer NOT NULL, row_index integer NOT NULL, column_index integer NOT NULL,
 link_index integer NOT NULL, entity_pk integer REFERENCES hybridqa.entities,
 PRIMARY KEY(table_pk,row_index,column_index,link_index),
 FOREIGN KEY(table_pk,row_index,column_index) REFERENCES hybridqa.wiki_cells
);
CREATE TABLE IF NOT EXISTS hybridqa.column_links (
 table_pk integer NOT NULL, column_index integer NOT NULL, link_index integer NOT NULL,
 entity_pk integer REFERENCES hybridqa.entities,
 PRIMARY KEY(table_pk,column_index,link_index),
 FOREIGN KEY(table_pk,column_index) REFERENCES hybridqa.wiki_columns
);
CREATE INDEX IF NOT EXISTS cell_numeric ON hybridqa.wiki_cells(table_pk,column_index,numeric_value) WHERE numeric_value IS NOT NULL;
CREATE INDEX IF NOT EXISTS entity_cells ON hybridqa.cell_links(entity_pk);
CREATE OR REPLACE VIEW hybridqa.rag_rows AS
 SELECT t.table_id,t.title,t.url,r.row_index,
 jsonb_agg(jsonb_build_object('column_index',c.column_index,'header',h.header,'value',c.value_text,
 'numeric_value',c.numeric_value,'entity_ids',COALESCE(l.ids,'[]'::jsonb)) ORDER BY c.column_index) AS cells,
 string_agg(h.header || ': ' || c.value_text, ' | ' ORDER BY c.column_index) AS evidence_text
 FROM hybridqa.wiki_rows r JOIN hybridqa.wiki_tables t ON t.id=r.table_pk
 JOIN hybridqa.wiki_cells c USING(table_pk,row_index)
 JOIN hybridqa.wiki_columns h USING(table_pk,column_index)
 LEFT JOIN LATERAL (SELECT jsonb_agg(e.wiki_id ORDER BY x.link_index) ids
 FROM hybridqa.cell_links x JOIN hybridqa.entities e ON e.id=x.entity_pk
 WHERE (x.table_pk,x.row_index,x.column_index)=(c.table_pk,c.row_index,c.column_index)) l ON true
 GROUP BY t.table_id,t.title,t.url,r.row_index;
COMMIT;
