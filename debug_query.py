import time
import psycopg2

CONN_STR = 'postgresql://postgres.zygnvzcknzlwssuhvgpg:gVATBXfuwcmen7@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'
conn = psycopg2.connect(CONN_STR)
cur = conn.cursor()

print("Creating GIN trigram indexes for pn, task_card, ac, emp_name...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_materials_pn_trgm ON materials USING gin (pn gin_trgm_ops);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_materials_tc_trgm ON materials USING gin (task_card gin_trgm_ops);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_materials_emp_trgm ON materials USING gin (emp_name gin_trgm_ops);")
conn.commit()
print("Indexes created!")

# Test query with threshol
t0 = time.time()
cur.execute("""
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT id, pn, pn_description, ac, task_card
    FROM materials
    WHERE (
        pn ILIKE '%threshol%' OR
        pn_description ILIKE '%threshol%' OR
        task_card ILIKE '%threshol%'
    )
    LIMIT 25;
""")
for r in cur.fetchall():
    print(r[0])
print(f"Time: {(time.time() - t0)*1000:.1f} ms")

conn.close()
