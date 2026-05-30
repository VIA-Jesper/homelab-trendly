"""
preview_server.py – Local WordPress-style article preview.

Renders generated articles from the pipeline SQLite DB in a classic 3-column
WP layout (left sidebar / article / right sidebar with SEO + QA info).

Handles both output formats:
  - New (JSON): step.output is a JSON blob with "article", "placements", "seo" fields.
    This is what generate_v1.txt / optimize_v1.txt now produce.
  - Legacy (markdown): step.output is plain markdown with META_DESCRIPTION: at the end.

Usage (from repo root):
    .venv\\Scripts\\python.exe scripts\\preview_server.py
    Open: http://localhost:8080
"""
import html as _html
import json
import os
import re
import sys
import uuid as _uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# config.py loads .env files relative to CWD. Switch to api/ so DATABASE_URL
# and API_KEY are found, regardless of where the script is launched from.
_API_DIR = Path(__file__).parent.parent / "api"
os.chdir(_API_DIR)
sys.path.insert(0, str(_API_DIR))

import models  # noqa: F401 – registers all ORM classes with Base
from database import AsyncSessionLocal
from models.job import Job
from models.site import Site
from models.step import Step
from services.brief_builder import ContentBrief
from services.widget_inserter import insert_anchored_placements

app = FastAPI(docs_url=None, redoc_url=None)

DANISH_MONTHS = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def _fmt_date(dt) -> str:
    if dt is None:
        return "–"
    return f"{dt.day}. {DANISH_MONTHS[dt.month - 1]} {dt.year}"


# ── Markdown renderer ────────────────────────────────────────────────────────

def _inline(t: str) -> str:
    t = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def _md(src: str) -> str:
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n{2,}", src.strip())
    out = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Raw HTML block (widget embeds, figure tags) — pass through unchanged
        if re.match(r"^<[a-zA-Z!/]", block):
            out.append(block)
            continue
        if re.match(r"^[-*_]{3,}$", block):
            out.append("<hr>")
            continue
        lines = block.split("\n")
        # Headings
        hm = re.match(r"^(#{1,6})\s+(.+)", lines[0])
        if hm and len(lines) == 1:
            lvl = len(hm.group(1))
            out.append(f"<h{lvl}>{_inline(hm.group(2))}</h{lvl}>")
            continue
        # Unordered list
        _ul_pat = r"^[-*+]\s+"
        if all(re.match(r"^[-*+]\s", l) for l in lines if l.strip()):
            items = "".join(
                "<li>" + _inline(re.sub(_ul_pat, "", l)) + "</li>"
                for l in lines if l.strip()
            )
            out.append(f"<ul>{items}</ul>")
            continue
        # Ordered list
        _ol_pat = r"^\d+\.\s+"
        if all(re.match(r"^\d+\.\s", l) for l in lines if l.strip()):
            items = "".join(
                "<li>" + _inline(re.sub(_ol_pat, "", l)) + "</li>"
                for l in lines if l.strip()
            )
            out.append(f"<ol>{items}</ol>")
            continue
        # Paragraph
        out.append(f"<p>{_inline(' '.join(lines))}</p>")
    return "\n".join(out)


def _render(
    raw: str,
    brief: ContentBrief | None = None,
    placements: list | None = None,
) -> tuple[str, str | None]:
    """Convert raw step output to (html, meta_description).

    New pipeline format: step.output is a JSON blob {"article": "...", "seo": {"description": ...}}.
    Legacy format: plain markdown with optional META_DESCRIPTION: line at the end.

    If brief and placements are provided, widgets are inserted into the article
    before rendering so the preview matches what will be published.
    """
    # New JSON format
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "article" in data:
            meta = data.get("seo", {}).get("description")
            article = data["article"]
            if brief and placements is not None:
                article, _ = insert_anchored_placements(article, brief, placements)
            return _md(article), meta
    except (json.JSONDecodeError, TypeError):
        pass

    # Legacy markdown format
    meta = None
    mo = re.search(r"\nMETA_DESCRIPTION:\s*(.+)$", raw, re.MULTILINE)
    if mo:
        meta = mo.group(1).strip()
        raw = raw[: mo.start()].strip()

    body = _md(raw)

    def _btn(m: re.Match) -> str:
        bid, txt = m.group(1), _html.escape(m.group(2))
        return (
            f'<div class="wp-cta">'
            f'<a class="btn-cta" href="#" data-id="{bid}">{txt} →</a>'
            f"</div>"
        )

    body = re.sub(
        r"<p>\s*\[affiliate_button\s+id=[\"']([^\"']+)[\"']\s+text=[\"']([^\"']+)[\"']\]\s*</p>",
        _btn, body,
    )
    body = re.sub(
        r"\[affiliate_button\s+id=[\"']([^\"']+)[\"']\s+text=[\"']([^\"']+)[\"']\]",
        _btn, body,
    )
    return body, meta


def _pop_h1(html: str) -> tuple[str, str | None]:
    """Extract first <h1> from rendered HTML, return (rest, title_text)."""
    m = re.match(r"<h1>(.+?)</h1>\n?", html, re.DOTALL)
    if m:
        return html[m.end() :].strip(), m.group(1)
    return html, None


def _article_stats(raw: str) -> dict:
    # New JSON format: article field contains the markdown
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "article" in data:
            article = data["article"]
            plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", article)
            plain = re.sub(r"[#*`>\[\]()_~]", " ", plain)
            words = len(plain.split())
            ctas = len(re.findall(r"\[[^\]]+\]\(https?://", article))
            return {"words": words, "ctas": ctas}
    except (json.JSONDecodeError, TypeError):
        pass

    # Legacy format
    plain = re.sub(r"\[affiliate_button[^\]]+\]", "", raw)
    plain = re.sub(r"META_DESCRIPTION:.+", "", plain)
    plain = re.sub(r"[#*`>\[\]()_~]", " ", plain)
    words = len(plain.split())
    ctas = len(re.findall(r"\[affiliate_button", raw))
    return {"words": words, "ctas": ctas}


# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#f0ede9;color:#333;font-size:16px;line-height:1.6}
a{color:#2a6496}

/* Preview banner */
#preview-banner{background:#1e2d3d;color:#8fb3cc;padding:7px 20px;
  font-size:12px;font-family:monospace;display:flex;align-items:center;gap:16px}
#preview-banner strong{color:#e0eaf2}
.pv-badge{background:#27ae60;color:#fff;padding:1px 8px;border-radius:10px;
  font-size:11px;font-weight:700}
.pv-badge.fail{background:#e74c3c}
.pv-badge.review{background:#e67e22}
.pv-badge.pending{background:#7f8c8d}

/* Header */
#masthead{background:#1c4966;color:#fff}
.header-inner{max-width:1220px;margin:0 auto;padding:26px 24px 18px}
.site-title{font-size:26px;font-weight:700;letter-spacing:-.4px}
.site-title a{color:#fff;text-decoration:none}
.site-description{font-size:13px;color:rgba(255,255,255,.6);
  font-weight:300;margin-top:3px;font-style:italic}

/* Nav */
#primary-nav{background:#2a6496;border-top:1px solid rgba(255,255,255,.1)}
.nav-inner{max-width:1220px;margin:0 auto;padding:0 24px;display:flex}
.nav-inner a{display:block;color:rgba(255,255,255,.85);text-decoration:none;
  padding:10px 14px;font-size:14px;font-weight:500}
.nav-inner a:hover{color:#fff;background:rgba(255,255,255,.1)}

/* Layout */
#wrapper{max-width:1220px;margin:24px auto 48px;padding:0 16px;
  display:grid;grid-template-columns:210px 1fr 270px;gap:20px;align-items:start}

/* Sidebar widgets */
.sidebar{display:flex;flex-direction:column;gap:14px}
.widget{background:#fff;border:1px solid #ddd;border-radius:2px}
.widget-title{background:#f7f7f7;border-bottom:1px solid #ddd;
  padding:9px 14px;font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;color:#555}
.widget-body{padding:12px 14px}
.widget-body ul{list-style:none}
.widget-body li{padding:4px 0;border-bottom:1px solid #f0f0f0;font-size:13px}
.widget-body li:last-child{border-bottom:none}
.widget-body li a{color:#2a6496;text-decoration:none}
.widget-body li a:hover{text-decoration:underline}

/* Article card */
#content-area{background:#fff;border:1px solid #ddd;border-radius:2px}
.entry-header{padding:28px 36px 18px;border-bottom:1px solid #eee}
.entry-title{font-family:Georgia,"Times New Roman",serif;font-size:27px;
  line-height:1.3;font-weight:normal;color:#1a1a1a;margin-bottom:9px}
.entry-meta{font-size:13px;color:#aaa}

.entry-content{padding:26px 36px 40px;
  font-family:Georgia,"Times New Roman",serif;font-size:17px;
  line-height:1.85;color:#2c2c2c}
.entry-content p{margin-bottom:1.15em}
.entry-content h2{font-size:21px;margin:1.8em 0 .6em;color:#1a1a1a;
  font-weight:normal;border-bottom:2px solid #ebebeb;padding-bottom:7px}
.entry-content h3{font-size:17px;margin:1.4em 0 .5em;color:#222;font-weight:700}
.entry-content h4{font-size:15px;margin:1.1em 0 .4em;font-weight:700;color:#333}
.entry-content ul,.entry-content ol{margin:.2em 0 1.1em 1.6em;line-height:1.75}
.entry-content li{margin-bottom:.3em}
.entry-content hr{border:none;border-top:1px solid #eee;margin:2em 0}
.entry-content code{font-family:monospace;background:#f4f4f4;
  padding:1px 5px;border-radius:3px;font-size:.88em}
.entry-content strong{color:#1a1a1a}

/* Affiliate CTA button */
.wp-cta{margin:1.6em 0;text-align:center}
.btn-cta{display:inline-block;
  background:linear-gradient(to bottom,#f7ca5b,#f0a900);
  color:#111 !important;text-decoration:none !important;
  padding:12px 30px;border-radius:3px;
  font-family:-apple-system,sans-serif;font-size:15px;font-weight:700;
  border:1px solid #d49600;box-shadow:0 1px 2px rgba(0,0,0,.15);
  cursor:pointer;letter-spacing:.2px}
.btn-cta:hover{background:linear-gradient(to bottom,#f9d270,#e09800)}

/* Right sidebar: info widgets */
.info-row{margin-bottom:9px;font-size:13px}
.info-label{font-size:11px;text-transform:uppercase;letter-spacing:.5px;
  color:#999;margin-bottom:2px}
.info-val{color:#333;font-weight:500}
.meta-preview{background:#f8f9fa;border:1px solid #dde;border-radius:3px;
  padding:8px 10px;font-size:13px;color:#444;line-height:1.5;
  margin-top:6px;font-family:sans-serif}
.char-count{font-size:11px;font-family:monospace;margin-top:4px}
.char-ok{color:#27ae60;font-weight:600}
.char-warn{color:#e74c3c;font-weight:600}
.qa-output{font-family:monospace;font-size:12px;color:#444;
  line-height:1.6;white-space:pre-wrap;max-height:320px;overflow-y:auto}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.stat-box{background:#f8f9fa;border:1px solid #eee;border-radius:3px;
  padding:8px 10px;text-align:center}
.stat-num{font-size:22px;font-weight:700;color:#1c4966;line-height:1}
.stat-lbl{font-size:11px;color:#888;margin-top:3px;text-transform:uppercase;
  letter-spacing:.5px}

/* Job list page */
.page-wrap{max-width:960px;margin:32px auto;padding:0 16px}
.page-title{font-size:22px;font-weight:600;margin-bottom:20px;color:#1c4966}
.jobs-table{width:100%;border-collapse:collapse;font-size:14px;background:#fff;
  border:1px solid #ddd}
.jobs-table th{background:#23282d;color:#eee;padding:10px 14px;
  text-align:left;font-weight:600;font-size:13px}
.jobs-table td{padding:10px 14px;border-bottom:1px solid #eee;vertical-align:top}
.jobs-table tr:hover td{background:#fafafa}
.kw{font-weight:600;color:#1a1a1a}
.status-badge{display:inline-block;padding:2px 9px;border-radius:10px;
  font-size:11px;font-weight:700}
.s-complete{background:#d5f5e3;color:#1e8449}
.s-in_progress{background:#fef9e7;color:#9a7d0a}
.s-queued{background:#eaf2f8;color:#1a5276}
.s-requires_review{background:#fdebd0;color:#935116}
.s-failed{background:#fadbd8;color:#922b21}
.btn-preview{background:#2a6496;color:#fff;padding:4px 12px;border-radius:3px;
  text-decoration:none;font-size:12px;font-weight:600}
.btn-preview:hover{background:#1c4966}
.no-preview{color:#bbb;font-size:12px}

/* Footer */
#colophon{background:#23282d;color:#777;text-align:center;
  padding:18px;font-size:13px;margin-top:0}
"""

# ── Page shell ───────────────────────────────────────────────────────────────

_CT = "text/html; charset=utf-8"


def _resp(html: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=html.encode("utf-8"),
        status_code=status_code,
        media_type=_CT,
    )


def _shell(title: str, body: str, site_name: str = "Preview", site_desc: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="{_CT}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} – {_html.escape(site_name)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<footer id="colophon">
  {_html.escape(site_name)} &mdash; Affiliate Pipeline Preview &nbsp;·&nbsp;
  <a href="/" style="color:#555">All jobs</a>
</footer>
</body>
</html>"""


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def list_jobs() -> HTMLResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .options(selectinload(Job.site))
            .order_by(Job.created_at.desc())
        )
        jobs = result.scalars().unique().all()

    rows = ""
    for j in jobs:
        brief_ctx = j.context.get("brief", {}) or {}
        products_ctx = brief_ctx.get("products", [])
        kw = (
            products_ctx[0].get("name") if products_ctx
            else j.context.get("target_keyword", "–")
        ) or "–"
        site_name = j.site.name if j.site else "?"
        status_cls = f"s-{j.status}"
        created = _fmt_date(j.created_at)

        has_content = any(
            s.step_name in ("write_draft", "optimize_seo") and s.status == "complete"
            for s in j.steps
        )
        preview_link = (
            f'<a class="btn-preview" href="/preview/{j.id}">Preview →</a>'
            if has_content
            else '<span class="no-preview">no content yet</span>'
        )

        rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:12px;color:#888">{str(j.id)[:8]}&hellip;</td>
          <td>{_html.escape(site_name)}</td>
          <td class="kw">{_html.escape(kw)}</td>
          <td><span class="status-badge {status_cls}">{j.status}</span></td>
          <td>{created}</td>
          <td>{preview_link}</td>
        </tr>"""

    body = f"""
<div class="page-wrap">
  <p class="page-title">Pipeline Jobs</p>
  <table class="jobs-table">
    <thead>
      <tr>
        <th>ID</th><th>Site</th><th>Keyword</th>
        <th>Status</th><th>Created</th><th></th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    return _resp(_shell("Jobs", body))


@app.get("/preview/{job_id}", response_class=HTMLResponse)
async def preview(job_id: str) -> HTMLResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .options(selectinload(Job.site))
            .where(Job.id == _uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()

    if job is None:
        return _resp("<h1>Job not found</h1>", status_code=404)

    site = job.site
    site_name = site.name if site else "Preview"
    site_domain = site.domain if site else ""
    site_desc = (site.seed or {}).get("niche", "") if site else ""
    brief_ctx = job.context.get("brief", {}) or {}
    products_ctx = brief_ctx.get("products", [])
    kw = (
        products_ctx[0].get("name") if products_ctx
        else job.context.get("target_keyword", "")
    ) or ""
    article_type = job.context.get("article_type", "")

    # Pick best content step
    steps_by_name = {s.step_name: s for s in job.steps if s.status == "complete"}
    content_step = steps_by_name.get("optimize_seo") or steps_by_name.get("write_draft")
    qa_step = steps_by_name.get("qa_review")

    if not content_step or not content_step.output:
        body = "<div style='padding:40px;font-size:18px;color:#888'>No article content yet.</div>"
        return _resp(_shell(kw or "Preview", body, site_name))

    raw = content_step.output

    # Parse JSON output if present (new pipeline format)
    output_data = None
    try:
        output_data = json.loads(raw)
        if not isinstance(output_data, dict) or "article" not in output_data:
            output_data = None
    except (json.JSONDecodeError, TypeError):
        pass

    seo_data = output_data.get("seo", {}) if output_data else {}
    placements = output_data.get("placements", []) if output_data else []

    # Reconstruct brief for widget insertion (graceful — widgets skipped if brief missing)
    brief_obj: ContentBrief | None = None
    brief_dict = job.context.get("brief")
    if brief_dict:
        try:
            brief_obj = ContentBrief.model_validate(brief_dict)
        except Exception:
            pass

    article_html, meta_desc = _render(raw, brief=brief_obj, placements=placements)
    content_body, h1_title = _pop_h1(article_html)
    title = h1_title or kw or "Artikel"
    stats = _article_stats(raw)

    # QA widget
    if qa_step and qa_step.output:
        qa_txt = qa_step.output.strip()
        qa_passed = "STATUS: PASS" in qa_txt.upper()
        qa_badge_cls = "pv-badge" if qa_passed else "pv-badge fail"
        qa_badge_lbl = "PASS" if qa_passed else "FAIL"
        qa_html = (
            f'<div class="widget-body">'
            f'<span class="{qa_badge_cls}">{qa_badge_lbl}</span>'
            f'<div class="qa-output" style="margin-top:10px">{_html.escape(qa_txt)}</div>'
            f"</div>"
        )
    else:
        qa_html = '<div class="widget-body"><span class="pv-badge pending">–</span></div>'
        qa_badge_lbl = "–"
        qa_badge_cls = "pv-badge pending"

    # Meta description widget
    if meta_desc:
        char_len = len(meta_desc)
        char_cls = "char-ok" if 120 <= char_len <= 160 else "char-warn"
        meta_widget = f"""
        <div class="widget">
          <div class="widget-title">SEO · Meta Description</div>
          <div class="widget-body">
            <div class="meta-preview">{_html.escape(meta_desc)}</div>
            <div class="char-count"><span class="{char_cls}">{char_len} tegn</span>
              &nbsp;(krav: 120–160)</div>
          </div>
        </div>"""
    else:
        meta_widget = ""

    # SEO fields widget (new format only)
    if seo_data:
        seo_rows = ""
        for label, key in [("Title", "title"), ("Keyword", "focus_keyword"), ("Slug", "slug")]:
            val = seo_data.get(key)
            if val:
                display = f"<code>{_html.escape(val)}</code>" if key == "slug" else _html.escape(val)
                seo_rows += (
                    f'<div class="info-row">'
                    f'<div class="info-label">{label}</div>'
                    f'<div class="info-val">{display}</div>'
                    f"</div>"
                )
        seo_widget = f"""
        <div class="widget">
          <div class="widget-title">SEO</div>
          <div class="widget-body">{seo_rows}</div>
        </div>"""
    else:
        seo_widget = ""

    # Placements widget (new format only)
    if placements:
        pl_items = "".join(
            f'<li><strong>{_html.escape(str(p.get("anchor", "?")))}</strong>'
            f' — {_html.escape(str(p.get("kind", "?")))}</li>'
            for p in placements
        )
        placements_widget = f"""
        <div class="widget">
          <div class="widget-title">Placements ({len(placements)})</div>
          <div class="widget-body"><ul>{pl_items}</ul></div>
        </div>"""
    else:
        placements_widget = ""

    # Token cost across all completed steps
    total_cost = 0.0
    cost_rows = ""
    for s in job.steps:
        if s.status == "complete" and s.input and isinstance(s.input, dict):
            u = s.input.get("usage", {})
            if u and u.get("cost_usd"):
                total_cost += u["cost_usd"]
                inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
                cost_rows += (
                    f'<div class="info-row">'
                    f'<div class="info-label">{_html.escape(s.step_name)}</div>'
                    f'<div class="info-val">{inp+out:,} tok · ${u["cost_usd"]:.4f}</div>'
                    f"</div>"
                )
    if cost_rows:
        cost_rows += (
            f'<div class="info-row" style="border-top:1px solid #eee;margin-top:6px;padding-top:6px">'
            f'<div class="info-label">Total</div>'
            f'<div class="info-val" style="font-weight:700">${total_cost:.4f}</div>'
            f"</div>"
        )
    cost_widget = (
        f'<div class="widget"><div class="widget-title">Token Cost</div>'
        f'<div class="widget-body">{cost_rows or "<span style=\'color:#aaa;font-size:12px\'>No usage data yet</span>"}</div></div>'
    )

    # Stats widget
    stats_widget = f"""
    <div class="widget">
      <div class="widget-title">Artikel Stats</div>
      <div class="widget-body">
        <div class="stat-grid">
          <div class="stat-box">
            <div class="stat-num">{stats["words"]}</div>
            <div class="stat-lbl">ord</div>
          </div>
          <div class="stat-box">
            <div class="stat-num">{stats["ctas"]}</div>
            <div class="stat-lbl">CTA&apos;er</div>
          </div>
        </div>
      </div>
    </div>"""

    # Context widget — skip large nested objects; show scalar values only
    ctx_rows = "".join(
        f'<div class="info-row"><div class="info-label">{_html.escape(k)}</div>'
        f'<div class="info-val">{_html.escape(str(v)[:120])}</div></div>'
        for k, v in job.context.items()
        if k not in ("brief", "affiliate_ids") and not isinstance(v, (dict, list))
    )

    # Job status badge for banner
    jstatus_badge = {
        "complete": "pv-badge",
        "in_progress": "pv-badge review",
        "requires_review": "pv-badge review",
        "failed": "pv-badge fail",
    }.get(job.status, "pv-badge pending")

    banner = f"""
    <div id="preview-banner">
      <strong>LOCAL PREVIEW</strong>
      <span>{_html.escape(site_domain)}</span>
      <span>{_html.escape(kw)}</span>
      <span class="{jstatus_badge}">{job.status}</span>
      <span style="margin-left:auto;color:#546e7a">
        Step: {content_step.step_name} · attempt {content_step.attempt}
      </span>
    </div>"""

    header = f"""
    <header id="masthead">
      <div class="header-inner">
        <div class="site-title"><a href="/">{_html.escape(site_name)}</a></div>
        <div class="site-description">{_html.escape(site_desc)}</div>
      </div>
    </header>
    <nav id="primary-nav">
      <div class="nav-inner">
        <a href="#">Forside</a>
        <a href="#">Guide</a>
        <a href="#">Test &amp; Anmeldelser</a>
        <a href="#">Om os</a>
      </div>
    </nav>"""

    left_sidebar = """
    <aside class="sidebar">
      <div class="widget">
        <div class="widget-title">Kategorier</div>
        <div class="widget-body">
          <ul>
            <li><a href="#">Støvsugere</a></li>
            <li><a href="#">Robotstøvsugere</a></li>
            <li><a href="#">Håndstøvsugere</a></li>
            <li><a href="#">Opvaskemaskiner</a></li>
            <li><a href="#">Vaskemaskiner</a></li>
          </ul>
        </div>
      </div>
      <div class="widget">
        <div class="widget-title">Seneste Artikler</div>
        <div class="widget-body">
          <ul>
            <li><a href="#">Bedste støvsuger til kæledyr</a></li>
            <li><a href="#">Guide: Vælg den rette opvaskemaskine</a></li>
            <li><a href="#">De 5 bedste boremaskiner 2026</a></li>
            <li><a href="#">Sådan vedligeholder du din vaskemaskine</a></li>
          </ul>
        </div>
      </div>
      <div class="widget">
        <div class="widget-title">Arkiv</div>
        <div class="widget-body">
          <ul>
            <li><a href="#">Maj 2026</a></li>
            <li><a href="#">April 2026</a></li>
            <li><a href="#">Marts 2026</a></li>
          </ul>
        </div>
      </div>
    </aside>"""

    right_sidebar = f"""
    <aside class="sidebar">
      <div class="widget">
        <div class="widget-title">Job Info</div>
        <div class="widget-body">
          {ctx_rows}
          <div class="info-row">
            <div class="info-label">Artikel type</div>
            <div class="info-val">{_html.escape(article_type)}</div>
          </div>
          <div class="info-row">
            <div class="info-label">Publiceret</div>
            <div class="info-val">{_fmt_date(job.created_at)}</div>
          </div>
        </div>
      </div>
      {stats_widget}
      {cost_widget}
      {seo_widget}
      {meta_widget}
      {placements_widget}
      <div class="widget">
        <div class="widget-title">QA Status</div>
        {qa_html}
      </div>
    </aside>"""

    main_article = f"""
    <main id="content-area">
      <header class="entry-header">
        <h1 class="entry-title">{title}</h1>
        <div class="entry-meta">
          {_fmt_date(job.created_at)} &nbsp;·&nbsp; Af Redaktionen
          &nbsp;·&nbsp; {_html.escape(article_type or "Artikel")}
        </div>
      </header>
      <div class="entry-content">
        {content_body}
      </div>
    </main>"""

    body = f"""
{banner}
{header}
<div id="wrapper">
  {left_sidebar}
  {main_article}
  {right_sidebar}
</div>"""

    return _resp(_shell(title, body, site_name, site_desc))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
