import sqlite3
from pathlib import Path

root = Path(__file__).parent.parent
dbs = [
    root / "trendly_local.db",
    root / "api" / "trendly_local.db",
    root / "data" / "trendly.db",
]

for db in dbs:
    print(f"\n=== {db} ===")
    if not db.exists():
        print("  (not found)")
        continue
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    for table in ("sites", "prompts", "jobs", "steps"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count}")
        except Exception as e:
            print(f"  {table}: error ({e})")
    try:
        cur.execute("SELECT id, status, created_at FROM jobs ORDER BY created_at")
        for r in cur.fetchall():
            print(f"    job {r[0][:8]}... {r[1]} {r[2][:10] if r[2] else '?'}")
    except Exception as e:
        print(f"  jobs detail error: {e}")
    con.close()
