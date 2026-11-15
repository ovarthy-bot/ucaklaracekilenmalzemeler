"""
Excel -> Supabase 'materials' tablosu aktarimi (mukerrer kayitlar atlanir).

Kullanim:
  python scripts/import_materials.py "dosya.xlsx"            # kuru calistirma (yazmaz, sadece raporlar)
  python scripts/import_materials.py "dosya.xlsx" --write    # gercekten ekler

Mukerrer tanimi: Excel satirindaki 30 alanin (id ve search_text haric) tamami
veritabanindaki bir satirla birebir ayniysa o satir zaten var kabul edilir.
Coklu kopya destekli: Excel'de ayni satir 2 kez, DB'de 1 kez varsa, 1 kez eklenir.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error

import openpyxl

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zygnvzcknzlwssuhvgpg.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_Tyfa1EqEkSNcFjZLmZAVQA_igjZ2XKL")
TABLE = "materials"
BATCH = 200

# Excel basligi -> veritabani kolonu (Excel sirasiyla)
COLUMN_MAP = [
    ("PN", "pn"), ("Category", "category"), ("PN Description", "pn_description"),
    ("Owner", "owner"), ("AC", "ac"), ("AC Location", "ac_location"), ("WO", "wo"),
    ("WO Description", "wo_description"), ("WO Status", "wo_status"), ("Location", "location"),
    ("Task Card", "task_card"), ("Task Card Status", "task_card_status"),
    ("Task Card Desc", "task_card_desc"), ("Source Code", "source_code"),
    ("Schedule Task Card", "schedule_task_card"), ("Addition Work", "addition_work"),
    ("Transaction Type", "transaction_type"), ("GL Company", "gl_company"),
    ("Issue To Employee", "issue_to_employee"), ("Emp Name", "emp_name"),
    ("Director", "director"), ("Manager", "manager"), ("Chief", "chief"),
    ("Created Date", "created_date"), ("Qty", "qty"), ("Quotation No", "quotation_no"),
    ("Stock UOM", "stock_uom"), ("Catalog List Price", "catalog_list_price"),
    ("Total Catalog List Price", "total_catalog_list_price"),
    ("Last PO Price", "last_po_price"), ("Total Last PO Price", "total_last_po_price"),
]
DB_COLS = [db for _, db in COLUMN_MAP]
NUMERIC = {"qty", "catalog_list_price", "total_catalog_list_price", "last_po_price", "total_last_po_price"}


def norm_value(col, v):
    """Excel degeri ve DB degeri ayni sekilde karsilastirilabilsin diye normalize eder."""
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if col in NUMERIC:
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return str(v)
    if isinstance(v, str):
        return v.strip()
    return v


def row_key(d):
    canon = json.dumps([d.get(c) for c in DB_COLS], ensure_ascii=False, sort_keys=False, default=str)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


def http(method, url, body=None, extra_headers=None):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
               "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def fetch_existing_counts():
    """Veritabanindaki tum satirlarin anahtar sayilarini, id'ye gore sayfalayarak ceker."""
    counts = collections.Counter()
    last_id = 0
    total = 0
    cols = ",".join(["id"] + DB_COLS)
    while True:
        url = (f"{SUPABASE_URL}/rest/v1/{TABLE}?select={cols}&id=gt.{last_id}"
               f"&order=id.asc&limit=1000")
        rows = http("GET", url)
        if not rows:
            break
        for r in rows:
            d = {c: norm_value(c, r.get(c)) for c in DB_COLS}
            counts[row_key(d)] += 1
        last_id = rows[-1]["id"]
        total += len(rows)
        print(f"  DB okunuyor: {total} satir", end="\r")
    print(f"  DB okundu: {total} satir               ")
    return counts


def read_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    idx = {}
    for excel_name, db in COLUMN_MAP:
        if excel_name not in header:
            sys.exit(f"Excel'de kolon yok: {excel_name!r}")
        idx[db] = header.index(excel_name)
    for r in rows:
        if r is None or all(v is None for v in r):
            continue
        d = {db: norm_value(db, r[i]) for db, i in idx.items()}
        yield d


def insert_rows(rows):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        http("POST", url, body=chunk, extra_headers={"Prefer": "return=minimal"})
        print(f"  eklendi: {min(i + BATCH, len(rows))}/{len(rows)}", end="\r")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--write", action="store_true", help="Kuru calistirma yerine gercekten ekle")
    args = ap.parse_args()

    print("1) Veritabani okunuyor...")
    db_counts = fetch_existing_counts()

    print("2) Excel okunuyor ve karsilastiriliyor...")
    remaining = collections.Counter(db_counts)
    to_insert = []
    total_x = skipped = 0
    for d in read_excel(args.xlsx):
        total_x += 1
        k = row_key(d)
        if remaining[k] > 0:
            remaining[k] -= 1
            skipped += 1
        else:
            to_insert.append(d)

    print(f"\nExcel satiri      : {total_x}")
    print(f"Mukerrer (atlanan): {skipped}")
    print(f"Eklenecek yeni    : {len(to_insert)}")

    if not args.write:
        print("\nKuru calistirma: hicbir sey yazilmadi. Eklemek icin --write ile calistirin.")
        return
    if not to_insert:
        print("Eklenecek yeni kayit yok.")
        return
    print("\n3) Ekleniyor...")
    insert_rows(to_insert)
    print("Tamamlandi.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP hata {e.code}: {e.read().decode('utf-8', 'replace')}")
