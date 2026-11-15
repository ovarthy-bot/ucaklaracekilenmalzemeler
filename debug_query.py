import time
import psycopg2

CONN_STR = 'postgresql://postgres.zygnvzcknzlwssuhvgpg:gVATBXfuwcmen7@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'
conn = psycopg2.connect(CONN_STR)
cur = conn.cursor()

print("Adding search_text column...")
cur.execute("""
    ALTER TABLE materials 
    ADD COLUMN IF NOT EXISTS search_text TEXT 
    GENERATED ALWAYS AS (
        coalesce(pn, '') || ' ' || 
        coalesce(pn_description, '') || ' ' || 
        coalesce(task_card, '') || ' ' || 
        coalesce(ac, '') || ' ' || 
        coalesce(emp_name, '')
    ) STORED;
""")
conn.commit()

print("Creating GIN trigram index on search_text...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_materials_search_trgm ON materials USING gin (search_text gin_trgm_ops);")
cur.execute("ANALYZE materials;")
conn.commit()
print("Search column & index created!")

# Benchmark search_text ILIKE '%threshol%'
t0 = time.time()
cur.execute("""
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT id, pn, pn_description, ac, task_card
    FROM materials
    WHERE search_text ILIKE '%threshol%'
    ORDER BY created_date DESC, id DESC
    LIMIT 25;
""")
for r in cur.fetchall():
    print(r[0])
print(f"Time: {(time.time() - t0)*1000:.1f} ms")

conn.close()
