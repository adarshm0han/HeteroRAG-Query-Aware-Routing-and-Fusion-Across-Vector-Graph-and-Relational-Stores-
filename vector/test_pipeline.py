import json

from pipeline import MAX_TABLE_IDS, load_passages, record_id, to_metadata


def test_load_passages_dedupes_and_tracks_tables(tmp_path):
    (tmp_path / 'Table_A_0.json').write_text(json.dumps({'/wiki/X': 'X is a thing .', '/wiki/Y': ' '}))
    (tmp_path / 'Table_B_0.json').write_text(json.dumps({'/wiki/X': 'X is a thing .'}))
    passages = load_passages(tmp_path)
    assert [p['passage_id'] for p in passages] == ['/wiki/X']
    assert passages[0]['title'] == 'X'
    assert sorted(passages[0]['table_ids']) == ['Table_A_0', 'Table_B_0']


def test_record_id_is_ascii_and_stable():
    rid = record_id('/wiki/São_Paulo')
    assert rid.isascii() and rid == record_id('/wiki/São_Paulo')
    assert record_id("/wiki/D.C._United") == "/wiki/D.C._United"


def test_metadata_caps_table_ids():
    meta = to_metadata({'passage_id': '/wiki/U', 'title': 'U', 'text': 't', 'table_ids': [str(i) for i in range(900)]})
    assert len(meta['table_ids']) == MAX_TABLE_IDS and meta['table_count'] == 900
