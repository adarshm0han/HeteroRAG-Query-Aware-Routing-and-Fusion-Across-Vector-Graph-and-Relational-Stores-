"""Embed HybridQA passages locally and seed the shared Pinecone index.

Commands (run from this vector/ directory):
    python pipeline.py download            sparse-clone the passage files into data/
    python pipeline.py embed [--limit N]   write data/embeddings.npy + data/passages.parquet
    python pipeline.py upload              resumable upsert into Pinecone
    python pipeline.py verify              index stats and a sample query
"""
import argparse
import glob
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
PASSAGE_REPO = 'https://github.com/wenhuchen/WikiTables-WithLinks.git'
PASSAGE_REVISION = 'dc066e1a6d5281511d8b73a6107d5ad2824cc2b2'
REQUEST_TOK = DATA / 'WikiTables-WithLinks' / 'request_tok'
EMBEDDINGS = DATA / 'embeddings.npy'
PASSAGES = DATA / 'passages.parquet'
CHECKPOINT = DATA / 'upload_checkpoint.json'
CHUNKS = DATA / 'embedding_chunks'
EMBED_CHUNK = 8192

MODEL = 'BAAI/bge-small-en-v1.5'
DIM = 384
# bge expects this instruction on queries only, never on passages.
QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '
# Pinecone caps metadata at 40 KB per record; /wiki/United_States alone links 831 tables.
MAX_TABLE_IDS = 300
UPSERT_BATCH = 100


def load_env(path=HERE / '.env'):
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def record_id(passage_id):
    """Pinecone ids must be ASCII; 22K HybridQA links are not (e.g. /wiki/São_Paulo)."""
    return quote(passage_id, safe="/_-.,()'!:")


def pick_device():
    import torch
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def empty_device_cache(device):
    import torch
    if device == 'mps':
        torch.mps.empty_cache()
    elif device == 'cuda':
        torch.cuda.empty_cache()


def load_passages(request_tok_dir=REQUEST_TOK):
    """Each request_tok file is one table's {"/wiki/X": text} map; dedupe by link."""
    passages = {}
    files = sorted(glob.glob(str(Path(request_tok_dir) / '*.json')))
    if not files:
        raise SystemExit(f'no passage files in {request_tok_dir}; run `python pipeline.py download`')
    for path in tqdm(files, desc='reading passages'):
        table_id = Path(path).stem
        for link, text in json.loads(Path(path).read_text(encoding='utf-8')).items():
            text = text.strip()
            if not text:
                continue
            if link in passages:
                passages[link]['table_ids'].append(table_id)
            else:
                title = link.removeprefix('/wiki/').replace('_', ' ')
                passages[link] = {'passage_id': link, 'title': title, 'text': text, 'table_ids': [table_id]}
    return sorted(passages.values(), key=lambda p: p['passage_id'])


def to_metadata(passage):
    table_ids = passage['table_ids']
    return {
        'passage_id': passage['passage_id'],
        'title': passage['title'],
        'text': passage['text'],
        'table_ids': table_ids[:MAX_TABLE_IDS],
        'table_count': len(table_ids),
    }


def cmd_download(_args):
    target = DATA / 'WikiTables-WithLinks'
    if not target.exists():
        DATA.mkdir(exist_ok=True)
        subprocess.run(['git', 'clone', '--filter=blob:none', '--sparse', '--no-checkout', PASSAGE_REPO, str(target)], check=True)
    subprocess.run(['git', '-C', str(target), 'sparse-checkout', 'set', 'request_tok'], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', '-q', PASSAGE_REVISION], check=True)
    print(f'{len(list(REQUEST_TOK.glob("*.json")))} passage files at {PASSAGE_REVISION[:12]}')


def cmd_embed(args):
    from sentence_transformers import SentenceTransformer

    passages = load_passages()
    if args.limit:
        passages = passages[:args.limit]
    device = args.device or pick_device()
    print(f'{len(passages)} unique passages; embedding with {MODEL} on {device}')
    model = SentenceTransformer(MODEL, device=device)
    # Title is prepended so short passages still carry the entity name.
    docs = [f"{p['title']}. {p['text']}" for p in passages]
    # Encode in chunks saved to disk: bounds GPU memory (MPS otherwise OOMs on the
    # full corpus) and lets a crashed run resume.
    CHUNKS.mkdir(exist_ok=True)
    chunks = []
    for start in tqdm(range(0, len(docs), EMBED_CHUNK), desc='chunks'):
        path = CHUNKS / f'{start:07d}_{min(start + EMBED_CHUNK, len(docs)):07d}.npy'
        if not path.exists():
            emb = model.encode(docs[start:start + EMBED_CHUNK], batch_size=args.batch_size,
                               normalize_embeddings=True, convert_to_numpy=True)
            np.save(path, emb.astype(np.float32))
            empty_device_cache(device)
        chunks.append(np.load(path))
    emb = np.concatenate(chunks)
    np.save(EMBEDDINGS, emb)
    pq.write_table(pa.Table.from_pylist(passages), PASSAGES)
    print(f'wrote {emb.shape} to {EMBEDDINGS.name} and {PASSAGES.name}')


def get_index(create=False):
    from pinecone import Pinecone, ServerlessSpec

    load_env()
    pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
    name = os.environ.get('PINECONE_INDEX', 'hybridqa-passages')
    if create and not pc.has_index(name):
        # The Starter plan only offers AWS us-east-1.
        pc.create_index(name, dimension=DIM, metric='cosine', spec=ServerlessSpec(cloud='aws', region='us-east-1'))
    return pc.Index(name)


def cmd_upload(args):
    emb = np.load(EMBEDDINGS)
    passages = pq.read_table(PASSAGES).to_pylist()
    assert len(emb) == len(passages)
    end = min(len(passages), args.limit or len(passages))
    # Resume from the checkpoint: re-upserting existing records costs extra write units.
    done = json.loads(CHECKPOINT.read_text())['next'] if CHECKPOINT.exists() else 0
    index = get_index(create=True)
    for start in tqdm(range(done, end, UPSERT_BATCH), desc='upserting', initial=done // UPSERT_BATCH,
                      total=-(-end // UPSERT_BATCH)):
        batch = range(start, min(start + UPSERT_BATCH, end))
        index.upsert(vectors=[
            {'id': record_id(passages[i]['passage_id']), 'values': emb[i].tolist(), 'metadata': to_metadata(passages[i])}
            for i in batch
        ])
        CHECKPOINT.write_text(json.dumps({'next': batch.stop}))
    print(f'upserted through row {end} of {len(passages)}')


def cmd_verify(_args):
    from retriever import VectorRetriever

    index = get_index()
    stats = index.describe_index_stats()
    print(f"vectors: {stats['total_vector_count']}  dimension: {stats['dimension']}")
    if PASSAGES.exists():
        print(f'local passages: {pq.read_metadata(PASSAGES).num_rows}')
    for ev in VectorRetriever().search('Which stadium is home to D.C. United?', k=3):
        print(f"{ev['score']:.3f}  {ev['passage_id']}  {ev['text'][:80]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('download').set_defaults(func=cmd_download)
    embed = sub.add_parser('embed')
    embed.add_argument('--limit', type=int)
    embed.add_argument('--batch-size', type=int, default=64)
    embed.add_argument('--device', help='cuda / mps / cpu (auto if omitted)')
    embed.set_defaults(func=cmd_embed)
    upload = sub.add_parser('upload')
    upload.add_argument('--limit', type=int, help='stop after this many rows (for a trial upload)')
    upload.set_defaults(func=cmd_upload)
    sub.add_parser('verify').set_defaults(func=cmd_verify)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
