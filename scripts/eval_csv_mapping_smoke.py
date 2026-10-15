"""Smoke test only: mapping rows are used as both input and expected result!
Do not publish these numbers as blind/independent accuracy.
"""
from __future__ import annotations
import argparse,csv,json,random,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from nomenclature_matcher.csv_mapping import CsvMappingIndex


def run(data_dir, n=200):
    index=CsvMappingIndex(data_dir)
    report={'warning':'IN_SAMPLE_SMOKE_ONLY: same CSV rows are both the search index and expected LD mappings', 'rows_by_file':index.rows_by_file,'groups':{}}
    randomizer=random.Random(53)
    for fn in CsvMappingIndex.FILES:
        expectations=defaultdict(set)
        with (Path(data_dir)/fn).open('r',encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f,delimiter=';' if fn.startswith('butterfly') else ','):
                if fn.startswith('competitor'):
                    query,article=r['competitor_article'],r['ld_article']
                elif fn.startswith('butterfly'):
                    query,article=r['steel_marking'],r['ld_marking']
                else:
                    query,article=r['steel_name'],r['ld_article']
                if query and article:
                    expectations[query].add(article)
        samples=randomizer.sample(sorted(expectations),min(n,len(expectations)))
        found=0;hit_top1=0;hit_top10=0;neg_dn=0
        missing=[]
        for q in samples:
            actual=index.search(q)
            if actual:found+=1
            if actual and actual[0]['ld_article'] in expectations[q]:hit_top1+=1
            if any(x['ld_article'] in expectations[q] for x in actual):hit_top10+=1
            # Impossible DN constraint should never match known source.
            if not index.search(q+' DN9999'):neg_dn+=1
            if not actual:missing.append(q)
        report['groups'][fn]={'sampled':len(samples),'identity_found':found,'top1_in_source_mapping':hit_top1,'top10_in_source_mapping':hit_top10,'reject_dn9999':neg_dn,'unresolved_examples':missing[:4]}
    return report
if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('--mapping-dir',default='data/csv_mappings');pa.add_argument('--sample',type=int,default=200)
    args=pa.parse_args();print(json.dumps(run(args.mapping_dir,args.sample),ensure_ascii=False,indent=2))
