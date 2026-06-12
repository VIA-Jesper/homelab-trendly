"""
Publish route - inserts widgets and posts to WordPress for a completed job.

The job must have a complete optimize_seo (or at minimum write_draft) step.
Publishing to ?status=publish requires qa_review to have passed.

Flow:
  1. Load job, find best content step output
  2. Parse JSON → article markdown + placements + seo dict
  3. insert_anchored_placements() → markdown with widget HTML blocks
  4. markdown_to_html() → full HTML
  5. POST to WP REST API
  6. Store wp_post_id / wp_post_url in job.context
"""

import json
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.job import Job
from services.brief_builder import ContentBrief, get_site_config
from services.coverage import related_articles, set_coverage_slug
from services.internal_links import build_related_section
from services.widget_inserter import insert_anchored_placements
from services.wp_publisher import markdown_to_html, publish_to_wordpress

router = APIRouter(prefix="/jobs", tags=["publish"])


@router.post("/{job_id}/publish")
async def publish_job(
    job_id: str,
    status: str = Query("draft", pattern="^(draft|publish|future)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Insert widgets and publish the article to WordPress.

    ?status=draft    - saves as WP draft (default, always allowed)
    ?status=future   - schedules 24h from now; blocked if qa_review has not passed
    ?status=publish  - publishes live immediately; blocked if qa_review has not passed
    """
    result = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    steps_by_name = {s.step_name: s for s in job.steps if s.status == "complete"}

    if status in ("publish", "future"):
        qa_step = steps_by_name.get("qa_review")
        if not qa_step or "PASS" not in (qa_step.output or "").upper():
            raise HTTPException(
                status_code=422,
                detail="Cannot publish: qa_review has not passed. Use ?status=draft to save as draft.",
            )

    # Prefer the QA-corrected article if the qa_review retry produced one
    qa_corrected = job.context.get("qa_corrected")
    if qa_corrected:
        output = qa_corrected
    else:
        content_step = steps_by_name.get("optimize_seo") or steps_by_name.get("write_draft")
        if not content_step or not content_step.output:
            raise HTTPException(status_code=422, detail="No content ready to publish.")

        raw = (content_step.output or "").strip()
        if raw.startswith("```"):
            _lines = raw.splitlines()
            _end = len(_lines) - 1 if _lines[-1].strip() == "```" else len(_lines)
            raw = "\n".join(_lines[1:_end]).strip()
        try:
            output = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=422, detail="Content step output is not valid JSON.")

    article_md = output.get("article", "")
    placements = output.get("placements", [])
    seo = output.get("seo", {})

    # WP theme renders the post title - strip leading H1 to avoid duplication
    _lines = article_md.splitlines()
    if _lines and _lines[0].startswith("# "):
        article_md = "\n".join(_lines[1:]).lstrip("\n")

    if not article_md:
        raise HTTPException(status_code=422, detail="No article text in step output.")

    brief_dict = job.context.get("brief")
    if not brief_dict:
        raise HTTPException(status_code=422, detail="No brief in job context.")
    brief = ContentBrief.model_validate(brief_dict)

    # Internal-link cluster: append links to other published articles in the same
    # category on this site (topical authority). Empty on a fresh site - no-op then.
    try:
        candidates = await related_articles(db, job.site_id, brief.category_slug, job.id)
        related_md = build_related_section(candidates, get_site_config(brief.site_key).domain)
        if related_md:
            article_md += related_md
    except (ValueError, KeyError):
        pass  # never block a publish on the related-links cluster

    article_with_widgets, widget_errors = insert_anchored_placements(article_md, brief, placements)
    article_html = markdown_to_html(article_with_widgets)

    try:
        wp_result = await publish_to_wordpress(article_html, brief, seo, wp_status=status)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    job.context = {
        **job.context,
        "wp_post_id": wp_result["post_id"],
        "wp_post_url": wp_result["post_url"],
        "wp_status": wp_result["wp_status"],
    }
    # Record the published slug on the coverage row (best-effort, for slug-collision checks).
    _path = urlparse(wp_result.get("post_url") or "").path.strip("/")
    await set_coverage_slug(db, job.id, _path.rsplit("/", 1)[-1] if _path else None)
    await db.commit()

    return {
        "job_id": job_id,
        "post_id": wp_result["post_id"],
        "post_url": wp_result["post_url"],
        "wp_status": wp_result["wp_status"],
        "widget_errors": widget_errors,
    }
