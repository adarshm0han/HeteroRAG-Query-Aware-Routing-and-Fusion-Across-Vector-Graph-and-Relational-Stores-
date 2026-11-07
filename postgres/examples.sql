-- Provide table IDs as values, never interpolate user text as SQL identifiers.
SELECT table_id,title FROM hybridqa.wiki_tables ORDER BY table_id LIMIT 20;

SELECT table_id,row_index,evidence_text,cells FROM hybridqa.rag_rows
WHERE table_id='List_of_National_Football_League_rushing_yards_leaders_0'
ORDER BY row_index LIMIT 20;

-- Numeric ranking: cell text remains available alongside parsed numbers.
SELECT r.row_index,r.evidence_text,c.numeric_value AS yards
FROM hybridqa.wiki_tables t
JOIN hybridqa.wiki_cells c ON c.table_pk=t.id
JOIN hybridqa.wiki_columns h ON (h.table_pk,h.column_index)=(c.table_pk,c.column_index)
JOIN hybridqa.rag_rows r ON r.table_id=t.table_id AND r.row_index=c.row_index
WHERE t.table_id='List_of_National_Football_League_rushing_yards_leaders_0'
AND h.header='Yards' AND c.numeric_value IS NOT NULL
ORDER BY c.numeric_value DESC LIMIT 2;

SELECT t.table_id,l.row_index,l.column_index,e.wiki_id
FROM hybridqa.entities e JOIN hybridqa.cell_links l ON l.entity_pk=e.id
JOIN hybridqa.wiki_tables t ON t.id=l.table_pk
WHERE e.wiki_id='/wiki/Walter_Payton' LIMIT 20;

SELECT t.table_id,COUNT(*) AS rows
FROM hybridqa.wiki_tables t JOIN hybridqa.wiki_rows r ON r.table_pk=t.id
GROUP BY t.table_id ORDER BY rows DESC LIMIT 10;
