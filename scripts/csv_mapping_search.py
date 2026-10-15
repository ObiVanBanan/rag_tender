"""Inspect up to ten mapping candidates without Postgres/Qdrant/network."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nomenclature_matcher.csv_mapping import CsvMappingIndex

parser = argparse.ArgumentParser()
parser.add_argument('query', help='Competitor name or exact source article')
parser.add_argument('--mapping-dir', default=str(ROOT / 'data/csv_mappings'))
parser.add_argument('--limit', type=int, default=10)
args = parser.parse_args()

index = CsvMappingIndex(args.mapping_dir)
hits = index.search(args.query, args.limit)
print(json.dumps({
    'query': args.query,
    'status': 'CANDIDATES' if hits else 'NOT_FOUND',
    'candidate_count': len(hits),
    'warning': 'CSV-derived candidates are not independently verified equivalents',
    'candidates': [
        {
            'ld_article': item['ld_article'],
            'ld_name': item['ld_name'],
            'evidence': item['evidence'],
            'source_file': item['source_file'],
            'source_article': item['source_article'],
            'ld_url': item['ld_url'],
        }
        for item in hits
    ],
}, ensure_ascii=False, indent=2))
