#!/usr/bin/env python3
"""Builds au-foods.json: Australian products from Open Food Facts' daily export, plus the
generic foods (fruit, veg, meat, cooked dishes) of the Australian Food Composition Database,
trimmed to what the Food Diary needs. Run by the monthly GitHub Action, or by hand:

    python tools/build_au_foods.py                              # downloads both
    python tools/build_au_foods.py export.csv.gz                # Open Food Facts from a file
    python tools/build_au_foods.py export.csv.gz profiles.xlsx  # and the AFCD from a file

Each product is one row: [barcode, name, brand, serving size, kcal, protein, carbs, fat,
sugars, fibre, sat fat, trans fat, poly fat, mono fat, sodium g, cholesterol g], all per
100 g. Trailing empty values are dropped to keep the file small.
AFCD foods use the key "afcd-<Public Food Key>" in place of a barcode and have no brand.
Data: Open Food Facts (openfoodfacts.org), Open Database Licence; Australian Food Composition
Database, Food Standards Australia New Zealand, CC BY 4.0.
"""
import csv, datetime, gzip, io, json, re, sys, urllib.request

URL = 'https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz'
AFCD_PAGE = 'https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files'
AFCD_FILE = ('https://www.foodstandards.gov.au/sites/default/files/2025-12/'
             'AFCD%20Release%203%20-%20Nutrient%20profiles.xlsx')      # Release 3, if the page can't be read
UA = {'User-Agent': 'FoodDiary/1.0 (personal food diary)'}
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

# ---------- Australian Food Composition Database ----------
# Its "Nutrient profiles" workbook has a per 100 g sheet with a heading row of names such as
# "Protein (g)" and "Sodium (Na) (mg)". Columns are found by their names and units rather
# than their positions, so a new release with columns moved still reads correctly.
AFCD_COLS = [   # (field, pattern the heading must match, preferred wording if several match)
    ('key', r'public food key|food key|food id', None),
    ('name', r'food name', None),
    ('kj', r'energy', r'with dietary fibre'),
    ('p', r'^protein', None),
    ('f', r'^fat,? total|^total fat', None),
    ('c', r'available carbohydrate|^carbohydrate', r'with sugar alcohols'),
    ('sugars', r'total sugars|^sugars', None),
    ('fiber', r'dietary fibre', None),
    ('saturated-fat', r'total saturated', None),
    ('trans-fat', r'total trans', None),
    ('polyunsaturated-fat', r'total polyunsaturated', None),
    ('monounsaturated-fat', r'total monounsaturated', None),
    ('sodium', r'^sodium', None),
    ('cholesterol', r'^cholesterol', None),
]
TO_G = {'g': 1, 'mg': 1e-3, 'ug': 1e-6, '\u00b5g': 1e-6, 'kj': 1}

def unit(head):
    m = re.findall(r'\(([^()]*)\)', head)
    return m[-1].strip().lower() if m else ''

def afcd_columns(head):
    heads = [str(h or '').strip() for h in head]
    low = [h.lower() for h in heads]
    cols = {}
    for field, pat, prefer in AFCD_COLS:
        hits = [i for i, h in enumerate(low) if re.search(pat, h)]
        if field not in ('key', 'name'):              # a number column needs a unit it can use
            want = ('kj',) if field == 'kj' else ('g', 'mg', 'ug', '\u00b5g')
            hits = [i for i in hits if unit(low[i]) in want]
        if prefer:
            hits = [i for i in hits if re.search(prefer, low[i])] or hits
        if hits:
            cols[field] = hits[0]
    return cols

def afcd_rows(src):
    import openpyxl
    data = open(src, 'rb').read() if not src.startswith('http') else urllib.request.urlopen(
        urllib.request.Request(src, headers=UA), timeout=120).read()
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = next((ws for ws in book.worksheets if '100 g' in ws.title.lower() or '100g' in ws.title.lower()), book.worksheets[0])
    rows = sheet.iter_rows(values_only=True)
    for _ in range(30):                                # the heading row sits under a title or two
        head = next(rows, None)
        if head is None:
            raise ValueError('no heading row with "Food Name" on sheet ' + sheet.title)
        cols = afcd_columns(head)
        if 'name' in cols and 'kj' in cols:
            break
    else:
        raise ValueError('no heading row with "Food Name" on sheet ' + sheet.title)
    missing = [f for f, _, _ in AFCD_COLS if f not in cols]
    if missing:
        print('AFCD: columns not found, left empty: ' + ', '.join(missing))
    units = {f: TO_G.get(unit(str(head[i]).lower()), 1) for f, i in cols.items() if f not in ('key', 'name')}
    def get(row, f):
        i = cols.get(f)
        try:
            v = float(row[i]) if i is not None and i < len(row) and row[i] not in (None, '') else None
        except (TypeError, ValueError):
            return None
        return None if v is None or v < 0 else v * units.get(f, 1)
    for row in rows:
        name = ' '.join(str(row[cols['name']] or '').split())[:80] if cols['name'] < len(row) else ''
        vals = {f: get(row, f) for f in cols if f not in ('key', 'name')}
        if not name or vals.get('kj') is None:
            continue
        key = ''.join(ch for ch in str(row[cols['key']] if 'key' in cols else name) if ch.isalnum())[:20]
        yield key, name, vals

def afcd_url():
    """The current release's Nutrient profiles file, as linked from the FSANZ download page."""
    try:
        page = urllib.request.urlopen(urllib.request.Request(AFCD_PAGE, headers=UA), timeout=60).read().decode('utf-8', 'replace')
        m = re.search(r'href="([^"]*nutrient(?:%20|\s|-|_)profiles[^"]*\.xlsx)"', page, re.I)
        if m:
            u = m.group(1)
            return u if u.startswith('http') else 'https://www.foodstandards.gov.au' + u
    except Exception as e:
        print('AFCD: download page unreadable (%s), trying Release 3 directly' % e)
    return AFCD_FILE

def build_afcd(src):
    """AFCD foods as rows in the same shape as the Open Food Facts ones, per 100 g, no serving."""
    out, seen = [], set()
    for key, name, v in afcd_rows(src):
        k = v['kj'] / 4.184
        p, c, fat = (v.get(x) or 0 for x in ('p', 'c', 'f'))
        if k > 900 or p + c + fat > 105 or key in seen:
            continue
        seen.add(key)
        rec = ['afcd-' + key, name, '', '', r(k, 0), r(p), r(c), r(fat)] + [r(v.get(d), 3) for d in DETAIL]
        while rec and rec[-1] in (0, ''):
            rec.pop()
        out.append(rec)
    return out

if __name__ == '__main__':
    data, scanned = build(sys.argv[1] if len(sys.argv) > 1 else URL)
    if len(data) < 100 and len(sys.argv) == 1:
        sys.exit('Only %d Australian products found - not replacing the list' % len(data))
    try:                                              # the AFCD adds to the list; if it fails the list still publishes
        afcd = build_afcd(sys.argv[2] if len(sys.argv) > 2 else afcd_url())
        print('AFCD: %d generic foods' % len(afcd))
    except Exception as e:
        afcd = []
        print('::warning::AFCD not added this time: %s' % e)
    data += afcd
    v = datetime.date.today().isoformat()
    with open('au-foods.json', 'w', encoding='utf-8') as f:
        json.dump({'v': v, 'n': len(data), 'd': data}, f, ensure_ascii=False, separators=(',', ':'))
    with open('au-foods.v.json', 'w') as f:                  # tiny, so phones can check for a new list cheaply
        json.dump({'v': v, 'n': len(data), 'afcd': len(afcd)}, f)
    print('%s: %d foods - %d Australian products from %d scanned, %d from the AFCD' % (v, len(data), len(data) - len(afcd), scanned, len(afcd)))
