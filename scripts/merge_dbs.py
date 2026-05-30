"""
Merge api/trendly_local.db (old jobs) into trendly_local.db (current).
Skips rows that already exist. Maps site IDs if they differ.
"""
import sqlite3
import json
from pathlib import Path

root = Path(__file__).parent.parent
target_path = root / "trendly_local.db"
source_path = root / "api" / "trendly_local.db"

target = sqlite3.connect(str(target_path))
source = sqlite3.connect(str(source_path))
target.row_factory = sqlite3.Row
source.row_factory = sqlite3.Row

tc = target.cursor()
sc = source.cursor()

# ── Sites ─────────────────────────────────────────────────────────────────────
# Get site IDs from both DBs (assume single site each)
tc.execute("SELECT id, domain FROM sites")
target_sites = {r["domain"]: r["id"] for r in tc.fetchall()}

sc.execute("SELECT id, domain, name, seed, is_active, created_at FROM sites")
source_sites = sc.fetchall()

site_id_map = {}  # source_id → target_id
for s in source_sites:
    if s["domain"] in target_sites:
        site_id_map[s["id"]] = target_sites[s["domain"]]
        print(f"  site {s['domain']}: already exists, mapping {s['id'][:8]} -> {target_sites[s['domain']][:8]}")
    else:
        tc.execute(
            "INSERT OR IGNORE INTO sites (id, domain, name, seed, is_active, created_at) VALUES (?,?,?,?,?,?)",
            (s["id"], s["domain"], s["name"], s["seed"], s["is_active"], s["created_at"]),
        )
        site_id_map[s["id"]] = s["id"]
        print(f"  site {s['domain']}: inserted")

# ── Jobs ──────────────────────────────────────────────────────────────────────
sc.execute("SELECT * FROM jobs")
jobs = sc.fetchall()
jobs_inserted = 0
for j in jobs:
    mapped_site_id = site_id_map.get(j["site_id"], j["site_id"])
    tc.execute("SELECT id FROM jobs WHERE id=?", (j["id"],))
    if tc.fetchone():
        print(f"  job {j['id'][:8]}: already exists, skip")
        continue
    tc.execute(
        "INSERT INTO jobs (id, site_id, status, context, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (j["id"], mapped_site_id, j["status"], j["context"], j["created_at"], j["updated_at"]),
    )
    jobs_inserted += 1
    print(f"  job {j['id'][:8]}: inserted ({j['status']})")

# ── Steps ─────────────────────────────────────────────────────────────────────
sc.execute("SELECT * FROM steps")
steps = sc.fetchall()
steps_inserted = 0
for s in steps:
    tc.execute("SELECT id FROM steps WHERE id=?", (s["id"],))
    if tc.fetchone():
        continue
    cols = [k for k in s.keys()]
    placeholders = ",".join("?" * len(cols))
    tc.execute(
        f"INSERT INTO steps ({','.join(cols)}) VALUES ({placeholders})",
        tuple(s[k] for k in cols),
    )
    steps_inserted += 1

print(f"\nDone. Jobs inserted: {jobs_inserted}, Steps inserted: {steps_inserted}")
target.commit()
target.close()
source.close()
