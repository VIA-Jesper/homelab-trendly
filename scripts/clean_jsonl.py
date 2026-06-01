"""One-off: remove global-run entries from hot-products.jsonl."""
import json
from pathlib import Path

VALID_CATS = {
    "cl1595","cl119","cl1611","cl120","cl335","cl638","cl1290","cl541","cl1388",
    "cl499","cl348","cl345","cl1258","cl1260","cl1613","cl19","cl13","cl14",
    "cl17","cl101","cl105","cl106","t14",
}

src = Path(__file__).parent.parent / "data" / "hot-products.jsonl"
tmp = src.with_suffix(".jsonl.tmp")

kept = dropped = 0
with src.open(encoding="utf-8") as fin, tmp.open("w", encoding="utf-8") as fout:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            dropped += 1
            continue
        ff = p.get("fetched_for", "UNKNOWN")
        if ff is None:
            dropped += 1  # explicit null = global run
        elif ff == "UNKNOWN":
            if p.get("category_id") in VALID_CATS:  # old entry, valid category
                fout.write(line + "\n")
                kept += 1
            else:
                dropped += 1
        else:
            fout.write(line + "\n")  # has fetched_for = site-only, keep
            kept += 1

tmp.replace(src)
print(f"Done. Kept: {kept}  Dropped: {dropped}")
