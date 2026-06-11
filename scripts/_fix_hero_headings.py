"""
Fix "Bedste X" H1 headings in already-completed hero jobs.
Handles the raw CORRECTED_ARTICLE:```json{...}``` format stored by qa_review.
"""
import json, re, sqlite3

con = sqlite3.connect("trendly_local.db")


def extract_json_from_corrected(raw: str):
    """Extract the JSON dict from a CORRECTED_ARTICLE: ```json ... ``` blob."""
    m = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Fallback: try parsing the whole thing as JSON
    return json.loads(raw)


def repack_corrected(raw: str, d: dict) -> str:
    """Write modified dict back into the CORRECTED_ARTICLE: ```json...``` wrapper."""
    new_json = json.dumps(d, ensure_ascii=False, indent=2)
    return re.sub(
        r'(```json\s*)(\{.*?\})(\s*```)',
        lambda m: m.group(1) + new_json + m.group(3),
        raw,
        flags=re.DOTALL,
    )


# ── Fix H1 in 09821226 (roeremaskiner, complete) ─────────────────────────────
rows = con.execute(
    "SELECT id, output FROM steps "
    "WHERE job_id LIKE '09821226%' AND step_name='qa_review' AND status='complete' "
    "ORDER BY attempt DESC LIMIT 1"
).fetchall()

for step_id, raw in rows:
    d = extract_json_from_corrected(raw)
    article = d.get("article", "")
    old_h1 = article.split("\n")[0]

    new_article = re.sub(
        r'^# Bedste r[^\n]+',
        "# Røremaskine guide 2026: vores guide til at vælge rigtigt",
        article,
        flags=re.IGNORECASE,
    )

    seo = d.get("seo") or {}
    if isinstance(seo, dict):
        if seo.get("title"):
            seo["title"] = re.sub(r'(?i)bedste r[^\|"]+', "Røremaskine guide 2026", seo["title"])
        seo["focus_keyword"] = "røremaskine guide"
        if seo.get("slug"):
            seo["slug"] = re.sub(r'(?i)bedste-r\S*', "roeremaskine-guide-2026", seo["slug"])
        d["seo"] = seo

    d["article"] = new_article
    new_raw = repack_corrected(raw, d)

    con.execute("UPDATE steps SET output=? WHERE id=?", (new_raw, step_id))
    new_h1 = new_article.split("\n")[0]
    print("09821226 qa_review fixed:")
    print(f"  OLD: {old_h1}")
    print(f"  NEW: {new_h1}")
    if seo.get("title"):
        print(f"  SEO title: {seo['title']}")
    if seo.get("slug"):
        print(f"  SEO slug:  {seo['slug']}")

con.commit()
con.close()
print("\nDone.")
