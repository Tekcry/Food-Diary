#!/usr/bin/env python3
"""Builds au-foods.json: Australian products from Open Food Facts' daily export, trimmed to
what the Food Diary needs. Run by the monthly GitHub Action, or by hand:

    python tools/build_au_foods.py                 # downloads the export (about 1 GB, streamed)
    python tools/build_au_foods.py export.csv.gz   # from a file already downloaded

Each product is one row: [barcode, name, brand, serving size, kcal, protein, carbs, fat,
sugars, fibre, sat fat, trans fat, poly fat, mono fat, sodium g, cholesterol g], all per
100 g. Trailing empty values are dropped to keep the file small.
Data: Open Food Facts (openfoodfacts.org), Open Database Licence.
"""
import csv, datetime, gzip, json, sys, urllib.request

URL = 'https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz'
DETAIL = ['sugars', 'fiber', 'saturated-fat', 'trans-fat', 'polyunsaturated-fat',
          'monounsaturated-fat', 'sodium', 'cholesterol']      # the app's detail order

def num(row, key):
    try:
        v = float(row.get(key) or '')
    except ValueError:
        return None
    return v if v == v and v >= 0 else None

def kcal(row):
    k = num(row, 'energy-kcal_100g')
    if k is None:
        kj = num(row, 'energy-kj_100g')
        if kj is None:
            kj = num(row, 'energy_100g')                      # Open Food Facts' "energy" is kJ
        k = None if kj is None else kj / 4.184
    return k

def r(v, places=1):
    if not v:
        return 0
    v = round(v, places)
    return int(v) if v == int(v) else v

def rows(src):
    csv.field_size_limit(1 << 30)
    raw = open(src, 'rb') if not src.startswith('http') else urllib.request.urlopen(
        urllib.request.Request(src, headers={'User-Agent': 'FoodDiary/1.0 (personal food diary)'}))
    with gzip.open(raw, 'rt', encoding='utf-8', errors='replace', newline='') as f:
        yield from csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)

def build(src):
    out, seen, scanned = [], set(), 0
    for row in rows(src):
        scanned += 1
        if 'en:australia' not in (row.get('countries_tags') or ''):
            continue
        code = ''.join(ch for ch in (row.get('code') or '') if ch.isdigit())[:20]
        name = ' '.join((row.get('product_name') or '').split())[:80]
        k = kcal(row)
        if not code or not name or k is None or k > 900 or code in seen:
            continue
        p, c, fat = (num(row, x + '_100g') or 0 for x in ('proteins', 'carbohydrates', 'fat'))
        if p + c + fat > 105:                                  # not a believable label
            continue
        seen.add(code)
        brand = (row.get('brands') or '').split(',')[0].strip()[:40]
        serving = ' '.join((row.get('serving_size') or '').split())[:40]
        rec = [code, name, brand, serving, r(k, 0), r(p), r(c), r(fat)] + [r(num(row, d + '_100g'), 3) for d in DETAIL]
        while rec and rec[-1] in (0, ''):
            rec.pop()
        out.append(rec)
    return out, scanned

if __name__ == '__main__':
    data, scanned = build(sys.argv[1] if len(sys.argv) > 1 else URL)
    if len(data) < 100 and len(sys.argv) == 1:
        sys.exit('Only %d Australian products found - not replacing the list' % len(data))
    v = datetime.date.today().isoformat()
    with open('au-foods.json', 'w', encoding='utf-8') as f:
        json.dump({'v': v, 'n': len(data), 'd': data}, f, ensure_ascii=False, separators=(',', ':'))
    with open('au-foods.v.json', 'w') as f:                  # tiny, so phones can check for a new list cheaply
        json.dump({'v': v, 'n': len(data)}, f)
    print('%s: %d Australian products from %d scanned' % (v, len(data), scanned))
