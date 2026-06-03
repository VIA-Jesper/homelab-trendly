"""
preview_server.py – Local WordPress-style article preview.

Renders generated articles from the pipeline SQLite DB in a classic 3-column
WP layout (left sidebar / article / right sidebar with SEO + QA info).

Handles both output formats:
  - New (JSON): step.output is a JSON blob with "article", "placements", "seo" fields.
    This is what generate_v1.txt / optimize_v1.txt now produce.
  - Legacy (markdown): step.output is plain markdown with META_DESCRIPTION: at the end.

Routes:
  GET  /                              — Job list (all jobs, newest first)
  GET  /preview/{job_id}              — Final article in 3-column WP layout
  GET  /preview/{job_id}/history      — Full pipeline iteration timeline (all step
                                        attempts in order: drafts → QA bubbles →
                                        SEO pass → scores). Use to spot token waste
                                        and identify prompts to tune.
  POST /archive/{job_id}              — Mark job as archived

Usage (from repo root):
    .venv\\Scripts\\python.exe scripts\\preview_server.py
    Open: http://localhost:8080
"""
import difflib
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

_API_DIR = Path(__file__).parent.parent / "api"
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


def _fmt_datetime(dt) -> str:
    if dt is None:
        return "–"
    return f"{dt.day}. {DANISH_MONTHS[dt.month - 1]} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


# ── Markdown renderer ────────────────────────────────────────────────────────

def _inline(t: str) -> str:
    t = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
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
    # Strip markdown code fences if stored output was wrapped (e.g. ```json ... ```)
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        stripped = "\n".join(lines[1:end]).strip()
    else:
        stripped = raw

    # New JSON format
    try:
        data = json.loads(stripped)
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


# ── History view helpers ─────────────────────────────────────────────────────

def _strip_corrected_article(qa_text: str) -> str:
    """Remove CORRECTED_ARTICLE: ```json...``` block from QA output."""
    return re.sub(r'CORRECTED_ARTICLE:\s*```json.*?```\s*', '', qa_text, flags=re.DOTALL).strip()


def _parse_step_output(raw: str) -> dict | None:
    """Strip markdown fences and JSON-parse step output. Returns dict or None."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        stripped = "\n".join(lines[1:end]).strip()
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _step_cost_str(step) -> str:
    """Return 'N tok · $X.XXXX' from step.input usage metadata, or empty string."""
    if not step.input or not isinstance(step.input, dict):
        return ""
    u = step.input.get("usage", {})
    cost = u.get("cost_usd")
    if not cost:
        return ""
    tok = u.get("input_tokens", 0) + u.get("output_tokens", 0)
    return f"{tok:,} tok · ${cost:.4f}"


def _word_delta_badge(prev: int | None, cur: int) -> str:
    """HTML badge showing word count change vs previous content step."""
    if prev is None:
        return ""
    diff = cur - prev
    if diff > 0:
        return f'<span class="ht-delta pos">+{diff} ord</span>'
    if diff < 0:
        return f'<span class="ht-delta neg">{diff} ord</span>'
    return '<span class="ht-delta zero">±0 ord</span>'


def _auto_refresh_snippet(job_status: str, interval: int = 8) -> str:
    """Return a JS auto-refresh block if the job is still running, else empty string."""
    if job_status not in ("in_progress", "queued"):
        return ""
    return f"""<script>
(function(){{
  var secs = {interval};
  var el = document.getElementById('auto-refresh-msg');
  if (!el) return;
  var t = setInterval(function(){{
    secs--;
    el.textContent = 'Auto-refresh in ' + secs + 's';
    if (secs <= 0) {{ clearInterval(t); location.reload(); }}
  }}, 1000);
  el.textContent = 'Auto-refresh in ' + secs + 's';
}})();
</script>
<div id="auto-refresh-msg" style="text-align:center;font-size:11px;color:#8fb3cc;
  font-family:monospace;padding:4px 0;background:#1e2d3d"></div>"""



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
.s-archived{background:#ecf0f1;color:#95a5a6}
.wp-published{background:#1e8449;color:#fff;display:inline-block;padding:2px 9px;
  border-radius:10px;font-size:11px;font-weight:700}
.wp-draft{background:#e67e22;color:#fff;display:inline-block;padding:2px 9px;
  border-radius:10px;font-size:11px;font-weight:700}
.btn-preview{background:#2a6496;color:#fff;padding:4px 12px;border-radius:3px;
  text-decoration:none;font-size:12px;font-weight:600;white-space:nowrap}
.btn-preview:hover{background:#1c4966}
.no-preview{color:#bbb;font-size:12px}
.btn-archive{background:none;border:1px solid #ddd;color:#aaa;padding:3px 9px;
  border-radius:3px;font-size:11px;cursor:pointer}
.btn-archive:hover{border-color:#e74c3c;color:#e74c3c}
.archived-row{display:none}
.archived-row td{opacity:0.5}

/* Footer */
#colophon{background:#23282d;color:#777;text-align:center;
  padding:18px;font-size:13px;margin-top:0}

/* ── History / pipeline iteration view ─────────────────────────────────── */
.ht-wrap{max-width:820px;margin:28px auto 60px;padding:0 16px}
.ht-pass{display:flex;align-items:center;gap:12px;margin:28px 0 0}
.ht-pass-line{flex:1;height:1px;background:#ddd}
.ht-pass-label{font-size:12px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;color:#555;white-space:nowrap;padding:0 6px}
.ht-connector{width:2px;height:28px;background:#ddd;margin:0 auto}
.ht-article-card{background:#fff;border:1px solid #ddd;border-radius:3px;
  margin-top:10px;overflow:hidden}
.ht-article-card summary{list-style:none;cursor:pointer;padding:11px 16px;
  display:flex;align-items:center;gap:10px;background:#f7f7f7;
  border-bottom:1px solid #eee;font-size:13px;font-weight:600;color:#1c4966;
  user-select:none}
.ht-article-card summary::-webkit-details-marker{display:none}
.ht-article-card summary::before{content:"▶";font-size:10px;color:#aaa;
  transition:transform .15s;flex-shrink:0}
.ht-article-card[open] summary::before{transform:rotate(90deg)}
.ht-card-meta{display:flex;gap:14px;margin-left:auto;font-size:12px;
  color:#888;font-weight:400;flex-wrap:wrap}
.ht-card-meta span{white-space:nowrap}
.ht-article-body{padding:20px 28px 28px;font-family:Georgia,"Times New Roman",serif;
  font-size:16px;line-height:1.8;color:#2c2c2c;max-height:600px;overflow-y:auto}
.ht-article-body p{margin-bottom:1em}
.ht-article-body h2{font-size:19px;margin:1.6em 0 .5em;color:#1a1a1a;
  font-weight:normal;border-bottom:2px solid #ebebeb;padding-bottom:6px}
.ht-article-body h3{font-size:16px;margin:1.2em 0 .4em;font-weight:700}
.ht-article-body ul,.ht-article-body ol{margin:.2em 0 1em 1.4em}
.ht-status-card{background:#fff;border:1px solid #ddd;border-radius:3px;
  padding:11px 16px;margin-top:10px;font-size:13px;color:#888;
  display:flex;align-items:center;gap:10px}
.ht-bubble{background:#f8f9fa;border:1px solid #e0e0e0;border-radius:6px;
  margin-top:10px;overflow:hidden}
.ht-bubble-header{padding:9px 14px;font-size:12px;font-weight:700;
  display:flex;align-items:center;gap:8px;background:#f0f0f0;
  border-bottom:1px solid #e0e0e0;text-transform:uppercase;letter-spacing:.6px}
.ht-bubble-body{padding:10px 14px}
.ht-bubble.qa-pass .ht-bubble-header{background:#eafaf1;border-color:#c3e6cb;color:#1e6b3a}
.ht-bubble.qa-fail .ht-bubble-header{background:#fdf2f2;border-color:#f5c6cb;color:#922b21}
.ht-score-card{background:#fff;border:1px solid #ddd;border-radius:3px;margin-top:10px}
.ht-score-header{padding:9px 14px;background:#1c4966;color:#fff;font-size:13px;
  font-weight:700;display:flex;align-items:center;gap:10px}
.ht-score-dims{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #eee}
.ht-score-dim{text-align:center;padding:12px 8px;border-right:1px solid #eee}
.ht-score-dim:last-child{border-right:none}
.ht-score-dim .sd-num{font-size:22px;font-weight:700;color:#1c4966;line-height:1}
.ht-score-dim .sd-lbl{font-size:11px;color:#888;margin-top:3px;
  text-transform:uppercase;letter-spacing:.5px}
.ht-score-notes{padding:10px 14px;font-size:12px;color:#555;line-height:1.55}
.ht-score-notes p{margin-bottom:5px}
.ht-total-cost{margin:28px 0 0;padding:12px 16px;background:#1c4966;color:#e0eaf2;
  border-radius:3px;font-size:14px;font-weight:700;text-align:center;letter-spacing:.3px}
.ht-delta{font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;margin-left:4px}
.ht-delta.pos{background:#d5f5e3;color:#1e8449}
.ht-delta.neg{background:#fadbd8;color:#922b21}
.ht-delta.zero{background:#eee;color:#888}
.ht-seo-row{font-size:12px;margin-bottom:7px;line-height:1.4}
.ht-seo-key{font-weight:700;color:#555;margin-right:5px;text-transform:uppercase;
  font-size:11px;letter-spacing:.4px}
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

from fastapi.responses import JSONResponse


@app.post("/archive/{job_id}")
async def archive_job(job_id: str) -> JSONResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == _uuid.UUID(job_id)))
        job = result.scalar_one_or_none()
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        job.status = "archived"
        await db.commit()
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def list_jobs() -> HTMLResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .options(selectinload(Job.site), selectinload(Job.steps))
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
        created = _fmt_datetime(j.created_at)

        total_cost = sum(
            s.input.get("usage", {}).get("cost_usd", 0.0)
            for s in j.steps
            if s.status == "complete" and isinstance(s.input, dict)
        )
        cost_str = f"${total_cost:.4f}" if total_cost else "–"

        has_content = any(
            s.step_name in ("write_draft", "optimize_seo") and s.status == "complete"
            for s in j.steps
        )
        preview_link = (
            f'<a class="btn-preview" href="/preview/{j.id}">Preview →</a>'
            if has_content
            else '<span class="no-preview">no content yet</span>'
        )

        wp_post_url = j.context.get("wp_post_url", "")
        wp_status = j.context.get("wp_status", "")
        if wp_post_url and wp_status == "publish":
            wp_cell = f'<a href="{_html.escape(wp_post_url)}" target="_blank"><span class="wp-published">Published</span></a>'
        elif wp_post_url and wp_status == "draft":
            wp_cell = f'<a href="{_html.escape(wp_post_url)}" target="_blank"><span class="wp-draft">Draft</span></a>'
        else:
            wp_cell = '<span style="color:#ccc;font-size:12px">—</span>'

        is_archived = j.status == "archived"
        row_cls = "archived-row" if is_archived else ""
        archive_btn = (
            f'<button class="btn-archive" onclick="archiveJob(\'{j.id}\', this)">Archive</button>'
            if not is_archived else
            '<span style="color:#bbb;font-size:11px">archived</span>'
        )

        rows += f"""
        <tr class="{row_cls}" id="row-{j.id}">
          <td style="font-family:monospace;font-size:12px;color:#888">{str(j.id)[:8]}&hellip;</td>
          <td>{_html.escape(site_name)}</td>
          <td class="kw">{_html.escape(kw)}</td>
          <td><span class="status-badge {status_cls}">{j.status}</span></td>
          <td>{wp_cell}</td>
          <td>{created}</td>
          <td style="font-family:monospace;font-size:12px;color:#666">{cost_str}</td>
          <td style="display:flex;gap:6px;align-items:center">{preview_link} {archive_btn}</td>
        </tr>"""

    body = f"""
<div class="page-wrap">
  <div style="display:flex;align-items:baseline;gap:16px;margin-bottom:20px">
    <p class="page-title" style="margin-bottom:0">Pipeline Jobs</p>
    <label style="font-size:13px;color:#888;cursor:pointer">
      <input type="checkbox" id="show-archived" onchange="toggleArchived(this.checked)" style="margin-right:4px">
      Show archived
    </label>
  </div>
  <table class="jobs-table">
    <thead>
      <tr>
        <th>ID</th><th>Site</th><th>Keyword</th>
        <th>Status</th><th>WordPress</th><th>Created</th><th>Cost</th><th></th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<script>
function toggleArchived(show) {{
  document.querySelectorAll('.archived-row').forEach(r => r.style.display = show ? 'table-row' : 'none');
}}
async function archiveJob(jobId, btn) {{
  if (!confirm('Archive this job?')) return;
  const r = await fetch('/archive/' + jobId, {{method: 'POST'}});
  if (r.ok) {{
    const row = document.getElementById('row-' + jobId);
    row.classList.add('archived-row');
    row.style.display = 'none';
    btn.replaceWith(document.createTextNode('archived'));
  }}
}}
</script>"""

    return _resp(_shell("Jobs", body))


@app.get("/preview/{job_id}", response_class=HTMLResponse)
async def preview(job_id: str) -> HTMLResponse:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .options(selectinload(Job.site), selectinload(Job.steps))
            .where(Job.id == _uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()

        recent_result = await db.execute(
            select(Job)
            .options(selectinload(Job.steps))
            .order_by(Job.created_at.desc())
            .limit(6)
        )
        recent_jobs = recent_result.scalars().unique().all()

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

    # Pick best content step — prefer QA-corrected article if one was produced
    steps_by_name = {s.step_name: s for s in job.steps if s.status == "complete"}
    content_step = steps_by_name.get("optimize_seo") or steps_by_name.get("write_draft")
    qa_step = steps_by_name.get("qa_review")

    if not content_step or not content_step.output:
        body = "<div style='padding:40px;font-size:18px;color:#888'>No article content yet.</div>"
        return _resp(_shell(kw or "Preview", body, site_name))

    qa_corrected = job.context.get("qa_corrected")
    if qa_corrected:
        raw = json.dumps(qa_corrected, ensure_ascii=False)
    else:
        raw = content_step.output

    # Strip markdown code fences if the model wrapped output in ```json ... ```
    _raw = raw.strip()
    if _raw.startswith("```"):
        _lines = _raw.splitlines()
        _end = len(_lines) - 1 if _lines[-1].strip() == "```" else len(_lines)
        raw = "\n".join(_lines[1:_end]).strip()

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
        # Strip CORRECTED_ARTICLE block (article JSON from retry) — not QA feedback
        qa_display = _strip_corrected_article(qa_txt)
        qa_badge_cls = "pv-badge" if qa_passed else "pv-badge fail"
        qa_badge_lbl = "PASS" if qa_passed else "FAIL"
        qa_html = (
            f'<div class="widget-body">'
            f'<span class="{qa_badge_cls}">{qa_badge_lbl}</span>'
            f'<div class="qa-output" style="margin-top:10px">{_html.escape(qa_display)}</div>'
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

    # Article scores
    score_step = steps_by_name.get("score_article")
    scores: dict = {}
    if score_step and score_step.output:
        try:
            _raw_score = score_step.output.strip()
            if _raw_score.startswith("```"):
                _sl = _raw_score.splitlines()
                _se = len(_sl) - 1 if _sl[-1].strip() == "```" else len(_sl)
                _raw_score = "\n".join(_sl[1:_se]).strip()
            scores = json.loads(_raw_score)
        except (json.JSONDecodeError, TypeError):
            pass

    # Token cost across all completed steps
    total_cost = 0.0
    total_tokens = 0
    cost_rows = ""
    for s in job.steps:
        if s.status == "complete" and s.input and isinstance(s.input, dict):
            u = s.input.get("usage", {})
            if u and u.get("cost_usd"):
                total_cost += u["cost_usd"]
                inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
                total_tokens += inp + out
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
            f'<div class="info-val" style="font-weight:700">{total_tokens:,} tok · ${total_cost:.4f}</div>'
            f"</div>"
        )
    _no_cost = '<span style="color:#aaa;font-size:12px">No usage data yet</span>'
    cost_widget = (
        f'<div class="widget"><div class="widget-title">Token Cost</div>'
        f'<div class="widget-body">{cost_rows or _no_cost}</div></div>'
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

    qa_passed = qa_step and "PASS" in (qa_step.output or "").upper()
    wp_post_url = job.context.get("wp_post_url", "")
    wp_status = job.context.get("wp_status", "")

    if wp_post_url:
        _wp_indicator = (
            f'<span class="pv-badge" style="background:#27ae60">Published</span>'
            if wp_status == "publish"
            else f'<span class="pv-badge" style="background:#e67e22">Draft in WP</span>'
        )
        _wp_link = f'<a href="{_html.escape(wp_post_url)}" target="_blank" style="color:#8fb3cc;font-size:12px">View in WP →</a>'
    else:
        _wp_indicator = ""
        _wp_link = ""

    _btn_style = "cursor:pointer;border:none;border-radius:3px;padding:4px 12px;font-size:12px;font-weight:600;"
    _draft_btn = f'<button style="{_btn_style}background:#546e7a;color:#fff" onclick="publishJob(\'{job_id}\',\'draft\')">Push as Draft</button>'
    _publish_btn = (
        f'<button style="{_btn_style}background:#27ae60;color:#fff" onclick="publishJob(\'{job_id}\',\'publish\')">Publish Live</button>'
        if qa_passed else
        f'<button style="{_btn_style}background:#444;color:#888;cursor:not-allowed" title="QA must pass before publishing" disabled>Publish Live</button>'
    )

    banner = f"""
    <div id="preview-banner">
      <strong>LOCAL PREVIEW</strong>
      <span>{_html.escape(site_domain)}</span>
      <span>{_html.escape(kw)}</span>
      <span class="{jstatus_badge}">{job.status}</span>
      {_wp_indicator}
      {_wp_link}
      <span style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <span id="publish-msg" style="font-size:12px;color:#8fb3cc"></span>
        <a href="#pipeline-history" style="{_btn_style}background:#37474f;color:#cfd8dc;text-decoration:none;display:inline-block">↓ Pipeline</a>
        {_draft_btn}
        {_publish_btn}
      </span>
    </div>
    <script>
    async function publishJob(jobId, status) {{
      const msg = document.getElementById('publish-msg');
      msg.textContent = 'Publishing…';
      try {{
        const r = await fetch('http://localhost:8000/api/v1/jobs/' + jobId + '/publish?status=' + status, {{
          method: 'POST',
          headers: {{'X-API-Key': 'changeme'}}
        }});
        const data = await r.json();
        if (!r.ok) {{
          msg.style.color = '#e74c3c';
          msg.textContent = 'Error: ' + (data.detail || r.status);
        }} else {{
          msg.style.color = '#27ae60';
          msg.textContent = status === 'publish' ? 'Published! ' : 'Saved as draft! ';
          if (data.post_url) {{
            const a = document.createElement('a');
            a.href = data.post_url; a.target = '_blank';
            a.style.color = '#27ae60'; a.textContent = 'View →';
            msg.appendChild(a);
          }}
        }}
      }} catch(e) {{
        msg.style.color = '#e74c3c';
        msg.textContent = 'Request failed: ' + e.message;
      }}
    }}
    </script>
    {_auto_refresh_snippet(job.status)}"""

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

    article_category = brief_ctx.get("category", "")
    category_items = (
        f'<li>{_html.escape(article_category)}</li>' if article_category else ""
    )

    recent_items = ""
    for rj in recent_jobs:
        if str(rj.id) == job_id:
            continue
        rj_brief = rj.context.get("brief", {}) or {}
        rj_products = rj_brief.get("products", [])
        rj_name = (rj_products[0].get("name") if rj_products else None) or "–"
        has_content = any(
            s.step_name in ("write_draft", "optimize_seo") and s.status == "complete"
            for s in rj.steps
        )
        if has_content:
            recent_items += f'<li><a href="/preview/{rj.id}">{_html.escape(rj_name)}</a></li>'

    left_sidebar = f"""
    <aside class="sidebar">
      <div class="widget">
        <div class="widget-title">Kategorier</div>
        <div class="widget-body"><ul>{category_items}</ul></div>
      </div>
      <div class="widget">
        <div class="widget-title">Seneste Artikler</div>
        <div class="widget-body"><ul>{recent_items or '<li style="color:#bbb;font-size:12px">Ingen endnu</li>'}</ul></div>
      </div>
    </aside>"""

    _score_dims = [("seo", "SEO"), ("cro", "CRO"), ("readability", "Readability"), ("overall", "Overall")]
    _score_boxes = "".join(
        f'<div class="stat-box">'
        f'<div class="stat-num" style="font-size:16px;color:{"#1c4966" if scores.get(k) is not None else "#aaa"}">'
        f'{scores.get(k, "–")}</div>'
        f'<div class="stat-lbl">{label}</div></div>'
        for k, label in _score_dims
    )
    _score_notes = ""
    if scores.get("notes"):
        _note_rows = "".join(
            f'<p style="margin-bottom:4px"><strong>{label}:</strong> {_html.escape(str(scores["notes"].get(k, "")))}</p>'
            for k, label in [("seo", "SEO"), ("cro", "CRO"), ("readability", "Readability")]
        )
        _score_notes = f'<div style="margin-top:10px;font-size:12px;color:#555;line-height:1.5">{_note_rows}</div>'
    score_widget = (
        f'<div class="widget"><div class="widget-title">Article Scores</div>'
        f'<div class="widget-body"><div class="stat-grid">{_score_boxes}</div>{_score_notes}</div></div>'
    )

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
      {score_widget}
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

    # ── Reversed pipeline history (below the main article) ──────────────────
    history_nodes: list[str] = []
    prev_words: int | None = None
    pass_counter_h = 0
    history_cost = 0.0
    all_steps_sorted = sorted(job.steps, key=lambda s: (s.step_order, s.attempt))

    for s in all_steps_sorted:
        if s.status == "complete" and isinstance(s.input, dict):
            history_cost += s.input.get("usage", {}).get("cost_usd", 0.0)

    # Build nodes in forward order, then reverse
    prev_article_text: str | None = None
    for s in all_steps_sorted:
        if s.step_name in ("write_draft", "optimize_seo"):
            pass_counter_h += 1
            history_nodes.append(_ht_pass_divider(pass_counter_h, s))
            if s.output:
                st = _article_stats(s.output)
                seo_h = (_parse_step_output(s.output) or {}).get("seo", {})
                cur_text = _extract_article_text(s.output)
                if prev_article_text and cur_text:
                    history_nodes.append(_ht_diff_card(f"Ændringer vs. forrige", prev_article_text, cur_text))
                    history_nodes.append(_ht_connector())
                history_nodes.append(_ht_article_card(s, st, seo_h, _step_cost_str(s),
                                                      _word_delta_badge(prev_words, st["words"]),
                                                      brief_obj, open_=True))
                prev_words = st["words"]
                if cur_text:
                    prev_article_text = cur_text
                if s.step_name == "optimize_seo" and seo_h:
                    history_nodes.append(_ht_connector())
                    history_nodes.append(_ht_seo_bubble(seo_h))
            else:
                history_nodes.append(_ht_status_card(s))
        elif s.step_name == "qa_review":
            history_nodes.append(_ht_qa_bubble(s) if s.output else _ht_status_card(s))
            # Show corrected article + diff if QA rewrote it
            if s.output:
                corrected = _extract_corrected_article(s.output)
                if corrected:
                    if prev_article_text:
                        history_nodes.append(_ht_connector())
                        history_nodes.append(_ht_diff_card("QA korrektioner", prev_article_text, corrected))
                    fake_stats = {"words": len(corrected.split()), "ctas": corrected.count("](http")}
                    history_nodes.append(_ht_connector())
                    history_nodes.append(
                        f'<details class="ht-article-card">'
                        f'<summary>✏️ QA Korrigeret artikel (forsøg {s.attempt})'
                        f'<span class="ht-card-meta"><span>{fake_stats["words"]} ord</span></span></summary>'
                        f'<div class="ht-article-body">{_md(corrected)}</div>'
                        f'</details>'
                    )
                    prev_article_text = corrected
        elif s.step_name == "score_article":
            history_nodes.append(_ht_score_card(s) if s.output else _ht_status_card(s))
        else:
            history_nodes.append(_ht_status_card(s))
        history_nodes.append(_ht_connector())

    if history_nodes and history_nodes[-1] == _ht_connector():
        history_nodes.pop()

    # Add brief at the end (bottom = origin)
    brief_card = _ht_brief_card(brief_ctx)
    if brief_card:
        history_nodes.append(_ht_connector())
        history_nodes.append(brief_card)

    history_nodes.reverse()
    if history_cost:
        history_nodes.insert(0, _ht_total_cost(history_cost))

    history_section = (
        f'<div id="pipeline-history" style="max-width:1220px;margin:0 auto 48px;padding:0 16px">'
        f'<div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;'
        f'color:#888;margin-bottom:16px;padding-top:8px;border-top:2px solid #ddd">Pipeline History</div>'
        f'<div class="ht-wrap" style="max-width:100%;margin:0">{"".join(history_nodes)}</div>'
        f'</div>'
    )

    body = f"""
{banner}
{header}
<div id="wrapper">
  {left_sidebar}
  {main_article}
  {right_sidebar}
</div>
{history_section}"""

    return _resp(_shell(title, body, site_name, site_desc))


# ── History view HTML builders ────────────────────────────────────────────────
# Each _ht_* function returns a self-contained HTML fragment for one timeline node.
# To add a new step type: add a branch in preview_history's iteration loop and a
# matching _ht_* builder here.

def _ht_connector() -> str:
    return '<div class="ht-connector"></div>'


def _ht_pass_divider(n: int, step) -> str:
    attempt_str = f" (forsøg {step.attempt})" if step.attempt > 1 else ""
    status_cls = {"complete": "pv-badge", "failed": "pv-badge fail"}.get(step.status, "pv-badge pending")
    badge = f'<span class="{status_cls}">{step.status}</span>'
    return (
        f'<div class="ht-pass">'
        f'<div class="ht-pass-line"></div>'
        f'<span class="ht-pass-label">Pass {n}: {step.step_name}{attempt_str}</span>'
        f'{badge}'
        f'<div class="ht-pass-line"></div>'
        f'</div>'
    )


def _ht_article_card(step, stats: dict, seo: dict, cost_str: str, delta_badge: str,
                     brief_obj, open_: bool = True) -> str:
    open_attr = " open" if open_ else ""
    seo_title = _html.escape(seo.get("title", "")[:70]) if seo else ""
    title_part = f'<span style="color:#555;font-weight:400;font-size:12px">{seo_title}</span>' if seo_title else ""
    cost_part = f'<span>{_html.escape(cost_str)}</span>' if cost_str else ""
    if step.status != "complete":
        status_cls = {"failed": "pv-badge fail", "in_progress": "pv-badge review"}.get(step.status, "pv-badge pending")
        title_part = f'<span class="{status_cls}" style="margin-left:4px">{step.status}</span>' + title_part
    try:
        article_html, _ = _render(step.output, brief=brief_obj)
    except Exception as exc:
        article_html = f'<pre style="color:#c0392b;font-size:12px">{_html.escape(str(exc))}</pre>'
    return (
        f'<details class="ht-article-card"{open_attr}>'
        f'<summary>'
        f'{_html.escape(step.step_name)}'
        f'{delta_badge}'
        f'<span class="ht-card-meta">'
        f'<span>{stats["words"]} ord</span>'
        f'<span>{stats["ctas"]} CTA</span>'
        f'{cost_part}'
        f'{title_part}'
        f'</span>'
        f'</summary>'
        f'<div class="ht-article-body">{article_html}</div>'
        f'</details>'
    )


def _ht_status_card(step) -> str:
    status_cls = {"complete": "pv-badge", "failed": "pv-badge fail",
                  "in_progress": "pv-badge review"}.get(step.status, "pv-badge pending")
    err = f' — <span style="color:#c0392b;font-size:12px">{_html.escape(step.error_message[:120])}</span>' if step.error_message else ""
    return (
        f'<div class="ht-status-card">'
        f'<span class="{status_cls}">{step.status}</span>'
        f'<span style="font-size:12px">{_html.escape(step.step_name)}{err}</span>'
        f'</div>'
    )


def _ht_qa_bubble(step) -> str:
    qa_txt = _strip_corrected_article(step.output.strip())
    passed = "STATUS: PASS" in qa_txt.upper()
    cls = "ht-bubble qa-pass" if passed else "ht-bubble qa-fail"
    badge = f'<span class="pv-badge{"" if passed else " fail"}">{"PASS" if passed else "FAIL"}</span>'
    attempt_str = f" · forsøg {step.attempt}" if step.attempt > 1 else ""
    return (
        f'<div class="{cls}">'
        f'<div class="ht-bubble-header">💬 QA Review{attempt_str} {badge}</div>'
        f'<div class="ht-bubble-body">'
        f'<div class="qa-output" style="max-height:200px">{_html.escape(qa_txt)}</div>'
        f'</div>'
        f'</div>'
    )


def _ht_seo_bubble(seo: dict) -> str:
    if not seo:
        return ""
    rows = ""
    for key, label in [("title", "Title"), ("focus_keyword", "Keyword"),
                        ("slug", "Slug"), ("description", "Description")]:
        val = seo.get(key)
        if not val:
            continue
        display = f"<code>{_html.escape(str(val))}</code>" if key == "slug" else _html.escape(str(val))
        rows += f'<div class="ht-seo-row"><span class="ht-seo-key">{label}</span>{display}</div>'
    if not rows:
        return ""
    return (
        f'<div class="ht-bubble">'
        f'<div class="ht-bubble-header">✏️ SEO Optimization</div>'
        f'<div class="ht-bubble-body">{rows}</div>'
        f'</div>'
    )


def _ht_score_card(step) -> str:
    scores = _parse_step_output(step.output) or {}
    dims = [("seo", "SEO"), ("cro", "CRO"), ("readability", "Readability"), ("overall", "Overall")]
    dim_cells = "".join(
        f'<div class="ht-score-dim">'
        f'<div class="sd-num">{scores.get(k, "–")}</div>'
        f'<div class="sd-lbl">{label}</div>'
        f'</div>'
        for k, label in dims
    )
    overall = scores.get("overall", "–")
    notes_html = ""
    if scores.get("notes"):
        note_rows = "".join(
            f'<p><strong>{label}:</strong> {_html.escape(str(scores["notes"].get(k, "")))}</p>'
            for k, label in [("seo", "SEO"), ("cro", "CRO"), ("readability", "Readability")]
        )
        notes_html = f'<div class="ht-score-notes">{note_rows}</div>'
    return (
        f'<div class="ht-score-card">'
        f'<div class="ht-score-header">📊 Score: {overall}/100</div>'
        f'<div class="ht-score-dims">{dim_cells}</div>'
        f'{notes_html}'
        f'</div>'
    )


def _ht_total_cost(total: float) -> str:
    return f'<div class="ht-total-cost">TOTAL COST: ${total:.4f}</div>'


def _ht_brief_card(brief_ctx: dict) -> str:
    if not brief_ctx:
        return ""
    products = brief_ctx.get("products", [])
    hook = brief_ctx.get("article_hook", "")
    rules = brief_ctx.get("writing_rules", {})
    rows = ""
    if hook:
        rows += f'<div class="ht-seo-row"><span class="ht-seo-key">Hook</span>{_html.escape(hook)}</div>'
    rows += f'<div class="ht-seo-row"><span class="ht-seo-key">Type</span>{_html.escape(brief_ctx.get("article_type",""))}</div>'
    rows += f'<div class="ht-seo-row"><span class="ht-seo-key">Kategori</span>{_html.escape(brief_ctx.get("category",""))}</div>'
    if rules:
        rules_str = f'{rules.get("tone","")} · {rules.get("min_words",0)}–{rules.get("max_words",0)} ord'
        rows += f'<div class="ht-seo-row"><span class="ht-seo-key">Regler</span>{_html.escape(rules_str)}</div>'
    for p in products[:1]:
        spec_parts = [f'{k}: {v}' for k, v in (p.get("specs") or {}).items()]
        rows += (
            f'<div class="ht-seo-row" style="margin-top:8px">'
            f'<span class="ht-seo-key">Produkt</span>'
            f'<strong>{_html.escape(p.get("name",""))}</strong> — {p.get("price_kr",0):.0f} kr'
            f'</div>'
        )
        if spec_parts:
            rows += f'<div class="ht-seo-row" style="color:#888;font-size:11px">{_html.escape(" · ".join(spec_parts[:5]))}</div>'
    return (
        f'<div class="ht-bubble">'
        f'<div class="ht-bubble-header">📋 Brief — startpunktet</div>'
        f'<div class="ht-bubble-body">{rows}</div>'
        f'</div>'
    )


def _extract_article_text(raw: str) -> str | None:
    """Pull plain article markdown out of a step output (JSON or legacy)."""
    if not raw:
        return None
    data = _parse_step_output(raw)
    if data and "article" in data:
        return data["article"]
    m = re.search(r'CORRECTED_ARTICLE:\s*```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        data = _parse_step_output(m.group(1))
        if data and "article" in data:
            return data["article"]
    return None


def _extract_corrected_article(qa_output: str) -> str | None:
    """Extract the CORRECTED_ARTICLE JSON block from a qa_review output."""
    m = re.search(r'CORRECTED_ARTICLE:\s*```json\s*(\{.*?\})\s*```', qa_output, re.DOTALL)
    if not m:
        return None
    data = _parse_step_output(m.group(1))
    return data.get("article") if data else None


def _ht_diff_card(label: str, text_a: str, text_b: str) -> str:
    """Render a collapsible diff card comparing two article versions."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = list(difflib.unified_diff(lines_a, lines_b, lineterm="", n=2))
    if not diff:
        return '<div class="ht-bubble" style="opacity:.5"><div class="ht-bubble-header">≈ Ingen ændringer</div></div>'
    rows = []
    for line in diff[2:]:  # skip --- +++ header lines
        escaped = _html.escape(line.rstrip("\n"))
        if line.startswith("+"):
            rows.append(f'<div style="background:#eafaf1;color:#1e6b3a;padding:1px 6px;white-space:pre-wrap;font-size:12px;font-family:monospace">{escaped}</div>')
        elif line.startswith("-"):
            rows.append(f'<div style="background:#fdf2f2;color:#922b21;padding:1px 6px;white-space:pre-wrap;font-size:12px;font-family:monospace">{escaped}</div>')
        else:
            rows.append(f'<div style="color:#aaa;padding:1px 6px;white-space:pre-wrap;font-size:12px;font-family:monospace">{escaped}</div>')
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    summary = f'+{added} / -{removed} linjer'
    return (
        f'<details class="ht-article-card">'
        f'<summary>🔀 {_html.escape(label)}'
        f'<span class="ht-card-meta"><span style="color:#1e8449">+{added}</span>'
        f' <span style="color:#922b21">-{removed}</span></span></summary>'
        f'<div style="max-height:400px;overflow-y:auto">{"".join(rows)}</div>'
        f'</details>'
    )


# ── Routes (/preview/{job_id}/history) ───────────────────────────────────────

@app.get("/preview/{job_id}/history", response_class=HTMLResponse)
async def preview_history(job_id: str) -> HTMLResponse:
    """
    Pipeline iteration history view.

    WHY THIS EXISTS
      The main /preview/{job_id} route shows only the final article. This view
      shows the full evolution from first write_draft through every QA retry to
      the final scored output. Use it to:
        - Spot where the model wastes tokens or regresses between passes
        - See exactly what QA blockers triggered retries and how the article changed
        - Identify which prompts to tune to reduce pass count or improve quality

    LAYOUT (top → bottom)
      Content steps (write_draft, optimize_seo) → collapsible article card
      QA review steps                           → comment bubble (PASS/FAIL)
      SEO optimizer (after optimize_seo)        → SEO fields bubble
      score_article                             → 4-dimension score card
      Vertical connector lines between nodes
      Total cost footer bar

    EXTENDING
      To add a new step type to the timeline: add a branch in the iteration loop
      below and a matching _ht_* builder function above.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .options(selectinload(Job.site), selectinload(Job.steps))
            .where(Job.id == _uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()

    if job is None:
        return _resp("<h1>Job not found</h1>", status_code=404)

    site = job.site
    site_name = site.name if site else "Preview"
    site_desc = (site.seed or {}).get("niche", "") if site else ""
    brief_ctx = job.context.get("brief", {}) or {}
    products_ctx = brief_ctx.get("products", [])
    kw = (products_ctx[0].get("name") if products_ctx else job.context.get("target_keyword", "")) or ""

    brief_obj: ContentBrief | None = None
    brief_dict = job.context.get("brief")
    if brief_dict:
        try:
            brief_obj = ContentBrief.model_validate(brief_dict)
        except Exception:
            pass

    jstatus_badge = {
        "complete": "pv-badge", "in_progress": "pv-badge review",
        "requires_review": "pv-badge review", "failed": "pv-badge fail",
    }.get(job.status, "pv-badge pending")

    banner = (
        f'<div id="preview-banner">'
        f'<strong>PIPELINE HISTORY</strong>'
        f'<a href="/preview/{job_id}" style="color:#8fb3cc">← Preview</a>'
        f'<span>{_html.escape(kw)}</span>'
        f'<span class="{jstatus_badge}">{job.status}</span>'
        f'</div>'
    )

    steps = sorted(job.steps, key=lambda s: (s.step_order, s.attempt))

    if not steps:
        body = f'{banner}<div class="ht-wrap"><p style="color:#aaa;padding:40px 0">Ingen pipeline-trin endnu.</p></div>'
        return _resp(_shell(f"History: {kw}", body, site_name, site_desc))

    nodes: list[str] = []
    pass_counter = 0
    prev_content_words: int | None = None
    total_cost = 0.0

    for step in steps:
        # Accumulate cost
        if step.status == "complete" and isinstance(step.input, dict):
            u = step.input.get("usage", {})
            total_cost += u.get("cost_usd", 0.0)

        if step.step_name in ("write_draft", "optimize_seo"):
            pass_counter += 1
            nodes.append(_ht_pass_divider(pass_counter, step))

            if step.output:
                stats = _article_stats(step.output)
                seo = (_parse_step_output(step.output) or {}).get("seo", {})
                cost_str = _step_cost_str(step)
                delta = _word_delta_badge(prev_content_words, stats["words"])
                nodes.append(_ht_article_card(step, stats, seo, cost_str, delta, brief_obj, open_=True))
                prev_content_words = stats["words"]

                # SEO bubble after optimize_seo
                if step.step_name == "optimize_seo" and seo:
                    nodes.append(_ht_connector())
                    nodes.append(_ht_seo_bubble(seo))
            else:
                nodes.append(_ht_status_card(step))

        elif step.step_name == "qa_review":
            if step.output:
                nodes.append(_ht_qa_bubble(step))
            else:
                nodes.append(_ht_status_card(step))

        elif step.step_name == "score_article":
            if step.output:
                nodes.append(_ht_score_card(step))
            else:
                nodes.append(_ht_status_card(step))

        else:
            # Unknown step type — show generic status card
            nodes.append(_ht_status_card(step))

        nodes.append(_ht_connector())

    # Remove trailing connector
    if nodes and nodes[-1] == _ht_connector():
        nodes.pop()

    if total_cost:
        nodes.append(_ht_total_cost(total_cost))

    timeline_html = "\n".join(nodes)
    body = f'{banner}{_auto_refresh_snippet(job.status)}<div class="ht-wrap">{timeline_html}</div>'
    return _resp(_shell(f"History: {kw}", body, site_name, site_desc))


if __name__ == "__main__":
    print("Preview server: http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
