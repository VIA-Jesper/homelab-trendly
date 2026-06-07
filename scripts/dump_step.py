import sqlite3, sys
step_id = sys.argv[1].replace("-", "")
conn = sqlite3.connect("trendly_local.db")
row = conn.execute("SELECT output FROM steps WHERE id = ?", (step_id,)).fetchone()
if row:
    out = row[0] or ""
    print("LENGTH:", len(out))
    print("--- FIRST 800 ---")
    print(out[:800])
    print("--- LAST 300 ---")
    print(out[-300:])
conn.close()
