from pathlib import Path
import csv
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from nomenclature_matcher.csv_mapping import CsvMappingIndex

ROOT=Path(__file__).parents[1]

def test_fixture_data(tmp_path):
    data = [
        ("competitor_ld_mapping.csv", ['competitor_article','ld_article','c_name','c_dn','c_pn','c_thread_type','name','dn','pn','url'],
         [['ST-200-80','LD-BR-80','Кран Stout Ду80 Ру16 ВР/НР','80','16','Внутренняя/Наружная','Кран LD Ду80 Ру25','80','25','']]),
        ("butterfly_mapping_results.csv", ['ld_marking','ld_dn','ld_pn','ld_connection','steel_marking','steel_dn','steel_pn','steel_connection'],
         [['LD-6','100','16','Фланцевое','PALUR-100','100','16','Фланцевое']]),
        ("mapping_results.csv", ['ld_name','ld_article','ld_url','ld_dn','ld_pn_mpa','ld_connection','steel_name','steel_article','steel_dn','steel_pn_bar','steel_connection','steel_medium','steel_control','steel_body_material'],
         [['Кран LD DN80 PN25','LD-80','https://x/products/123--a','80','25','фланцевое','Кран MARSHAL Ду80 Ру16 фланцевый','MAR-80','80','16','фланцевое','жидкость','ручное','сталь 20']])
    ]
    for fn, cols, rows in data:
        with (tmp_path/fn).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f,delimiter=';' if fn.startswith('butterfly') else ','); w.writerow(cols);w.writerows(rows)
    i=CsvMappingIndex(tmp_path)
    assert i.search('MAR-80 DN80 PN16')[0]['ld_article']=='LD-80'
    assert i.search('MAR-80 DN81 PN16')==[]
    assert i.search('MAR-80 DN80 PN40')==[]
    assert i.search('MAR-80 DN80 PN16 газ')==[]
    assert i.search('PALUR-100')[0]['ld_article']=='LD-6'
    assert i.search('ST-200-80 DN80 PN16')[0]['ld_article']=='LD-BR-80'
    assert i.search('ST-200-80 DN40 PN16')==[]
    assert i.search('unknown article XYZ-123456')==[]
    assert i.search('кран шаровой ду80 ру16')==[]  # no fuzzy-only automatic acceptance
    assert i.search('Кран MARSHAL Ду80 Ру16 фланцевый')[0]['ld_article']=='LD-80'
