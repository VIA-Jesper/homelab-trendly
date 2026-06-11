import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.job import Job
from models.prompt import Prompt
from models.step import Step
from services.qa import qa_service

log = logging.getLogger(__name__)

# A worker must submit a result within this window or the step is reclaimed.
# 15 minutes covers even the slowest Claude invocations with margin.
STEP_LEASE_SECONDS = 900


class PipelineService:
    """
    Controls step sequencing, retry logic, and job state transitions.
    All structural pipeline decisions live here - not in the agent.
    """

    async def create_steps_for_job(self, job: Job, db: AsyncSession) -> None:
        """Create all pipeline steps for a new job based on config."""
        article_type = job.context.get("article_type", "single-product-review")
        type_key = article_type.replace("-", "_")

        for order, step_cfg in enumerate(settings.pipeline_steps):
            prompt_name = step_cfg["prompt_name"]
            # For write_draft, use the type-specific generate prompt when one exists
            if prompt_name == "generate_post":
                typed_name = f"generate_post_{type_key}"
                typed_prompt = await self._get_active_prompt(typed_name, db)
                prompt_name = typed_name if typed_prompt else "generate_post"

            prompt = await self._get_active_prompt(prompt_name, db)
            step = Step(
                job_id=job.id,
                step_name=step_cfg["name"],
                step_order=order,
                prompt_id=prompt.id if prompt else None,
                status="pending",
                attempt=1,
            )
            db.add(step)
        await db.commit()

    async def get_next_step(self, job: Job, db: AsyncSession) -> Step | None:
        """Return the next pending or in-progress step for this job, or None if done."""
        result = await db.execute(
            select(Step)
            .where(Step.job_id == job.id, Step.status.in_(["pending", "in_progress"]))
            .order_by(Step.step_order)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def build_step_input(self, step: Step, job: Job, db: AsyncSession) -> dict:
        """Assemble everything the agent needs for this step."""
        prompt_content = step.prompt.content if step.prompt else ""
        step_cfg = self._get_step_config(step.step_name)
        source_step_name = step_cfg.get("source_step") if step_cfg else None
        if source_step_name:
            # Prefer the QA-corrected article if one exists (produced by a qa_review retry)
            qa_corrected = job.context.get("qa_corrected")
            if qa_corrected and source_step_name == "optimize_seo":
                previous_output = json.dumps(qa_corrected, ensure_ascii=False)
            else:
                result = await db.execute(
                    select(Step)
                    .where(Step.job_id == job.id, Step.step_name == source_step_name, Step.status == "complete")
                    .order_by(Step.step_order.desc())
                    .limit(1)
                )
                src = result.scalar_one_or_none()
                previous_output = src.output if src else None
        else:
            previous_output = await self._get_previous_output(job, step.step_order, db)

        result_dict: dict = {
            "prompt": prompt_content,
            "context": job.context,
            "previous_output": previous_output,
            "step_name": step.step_name,
            "attempt": step.attempt,
        }
        # On qa_review retry: include previous QA feedback so the model can apply fixes
        qa_feedback = step.input.get("edits_needed") if step.input else None
        if qa_feedback:
            result_dict["qa_feedback"] = qa_feedback
        return result_dict

    async def handle_step_result(
        self, step: Step, output: str, job: Job, db: AsyncSession
    ) -> dict:
        """
        Process agent output. Advance step/job state.
        Returns updated job status.
        """
        step_cfg = self._get_step_config(step.step_name)
        step.completed_at = datetime.now(timezone.utc)

        if step_cfg and step_cfg.get("is_qa_step"):
            passed = "STATUS: PASS" in output
            # Extract any corrected article the LLM produced (present on retries).
            # Run Python QA against it (not the original optimize_seo output) so
            # retries are actually checked against the updated content.
            corrected = _extract_corrected_article(output)
            if passed:
                python_result = await self._run_python_qa(job, db, corrected_article=corrected)
                if not python_result["passed"]:
                    failures = "; ".join(
                        r["message"] for r in python_result["results"] if not r["passed"]
                    )
                    passed = False
                    output = f"STATUS: FAIL\n\nPython QA gate:\n{failures}\n\n---\n\n{output}"
            step.output = output
            if not passed and step.attempt < step_cfg.get("max_attempts", 3):
                # Retry: create new step record for next attempt, carrying forward QA feedback
                new_step = Step(
                    job_id=job.id,
                    step_name=step.step_name,
                    step_order=step.step_order,
                    prompt_id=step.prompt_id,
                    status="pending",
                    attempt=step.attempt + 1,
                    input={"edits_needed": output},
                )
                step.status = "failed"
                db.add(new_step)
            elif not passed:
                step.status = "failed"
                job.status = "requires_review"
            else:
                step.status = "complete"
                if corrected:
                    job.context = {**job.context, "qa_corrected": corrected}
        else:
            step.output = output
            step.status = "complete"

        # Advance job if all steps complete
        if step.status == "complete":
            remaining = await self.get_next_step(job, db)
            if not remaining:
                job.status = "complete"
            elif job.status == "queued":
                job.status = "in_progress"

        job.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"job_status": job.status, "step_status": step.status}

    async def expire_stale_steps(self, db: AsyncSession) -> int:
        """
        Reset in_progress steps whose lease has expired (worker died without submitting).
        Called at the start of every /work poll so stuck steps are reclaimed automatically.
        Each expiry counts as an attempt - when max_attempts is reached the job fails.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STEP_LEASE_SECONDS)
        result = await db.execute(
            select(Step).where(
                Step.status == "in_progress",
                Step.claimed_at.is_not(None),
                Step.claimed_at < cutoff,
            )
        )
        stale = result.scalars().all()
        for step in stale:
            step_cfg = self._get_step_config(step.step_name)
            max_attempts = step_cfg.get("max_attempts", 1) if step_cfg else 1
            step.status = "failed"
            step.error_message = "Lease expired - worker did not complete in time"
            log.warning(
                "Expired stale step %s (%s attempt %d/%d)",
                step.id, step.step_name, step.attempt, max_attempts,
            )
            if step.attempt < max_attempts:
                db.add(Step(
                    job_id=step.job_id,
                    step_name=step.step_name,
                    step_order=step.step_order,
                    prompt_id=step.prompt_id,
                    status="pending",
                    attempt=step.attempt + 1,
                ))
            else:
                job_r = await db.execute(select(Job).where(Job.id == step.job_id))
                job = job_r.scalar_one_or_none()
                if job and job.status not in ("complete", "requires_review", "failed"):
                    job.status = "failed"
                    job.updated_at = datetime.now(timezone.utc)
        if stale:
            await db.commit()
        return len(stale)

    async def fail_step(self, step: Step, error: str, job: Job, db: AsyncSession) -> dict:
        """
        Explicitly fail a step. Called by the worker when the agent errors out.
        Respects max_attempts: creates a new pending attempt if retries remain,
        otherwise marks the job failed.
        """
        step_cfg = self._get_step_config(step.step_name)
        max_attempts = step_cfg.get("max_attempts", 1) if step_cfg else 1
        step.status = "failed"
        step.error_message = (error or "Agent error")[:500]
        step.completed_at = datetime.now(timezone.utc)
        if step.attempt < max_attempts:
            db.add(Step(
                job_id=step.job_id,
                step_name=step.step_name,
                step_order=step.step_order,
                prompt_id=step.prompt_id,
                status="pending",
                attempt=step.attempt + 1,
            ))
            job_status = job.status
        else:
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc)
            job_status = "failed"
        await db.commit()
        return {"job_status": job_status, "step_status": "failed"}

    async def _run_python_qa(self, job: Job, db: AsyncSession, corrected_article: dict | None = None) -> dict:
        """Run hard Python QA checks against the article. Used as a gate after the LLM QA passes.

        Prefers corrected_article (from LLM retry output) over the stored optimize_seo output,
        so retries are checked against the content the LLM actually produced.
        """
        # Fetch optimize_seo output - needed for meta description regardless of which
        # article version we're checking (corrected or original).
        result = await db.execute(
            select(Step)
            .where(
                Step.job_id == job.id,
                Step.step_name == "optimize_seo",
                Step.status == "complete",
            )
            .order_by(Step.step_order.desc())
            .limit(1)
        )
        seo_step = result.scalar_one_or_none()
        seo_data: dict = {}
        seo_article = ""
        if seo_step and seo_step.output:
            try:
                seo_data = json.loads(seo_step.output)
                seo_article = seo_data.get("article", "")
            except (json.JSONDecodeError, ValueError):
                seo_article = seo_step.output

        if corrected_article:
            article = corrected_article.get("article", "")
            # Use meta description from the corrected output if available, else fall back to seo step
            meta_description = corrected_article.get("seo", {}).get("description", "") or seo_data.get("seo", {}).get("description", "")
        else:
            qa_corrected = job.context.get("qa_corrected")
            if qa_corrected:
                article = qa_corrected.get("article", "")
                meta_description = qa_corrected.get("seo", {}).get("description", "") or seo_data.get("seo", {}).get("description", "")
            else:
                article = seo_article
                meta_description = seo_data.get("seo", {}).get("description", "")

        qa_context = {**job.context, "meta_description": meta_description}
        # Thread min_words from brief.writing_rules so Python QA uses the same
        # threshold as the LLM prompt (which reads context.brief.writing_rules.min_words).
        brief_min_words = job.context.get("brief", {}).get("writing_rules", {}).get("min_words")
        if brief_min_words is not None:
            qa_context["min_words"] = brief_min_words
        return qa_service.run(article, qa_context)

    async def _get_active_prompt(self, name: str, db: AsyncSession) -> Prompt | None:
        result = await db.execute(
            select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_previous_output(self, job: Job, before_order: int, db: AsyncSession) -> str | None:
        result = await db.execute(
            select(Step)
            .where(Step.job_id == job.id, Step.step_order < before_order, Step.status == "complete")
            .order_by(Step.step_order.desc())
            .limit(1)
        )
        step = result.scalar_one_or_none()
        return step.output if step else None

    def _get_step_config(self, step_name: str) -> dict | None:
        return next((s for s in settings.pipeline_steps if s["name"] == step_name), None)


def _extract_corrected_article(output: str) -> dict | None:
    """Extract the corrected article JSON from a qa_review retry output."""
    m = re.search(r'CORRECTED_ARTICLE:\s*```json\s*(\{.*?\})\s*```', output, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


pipeline_service = PipelineService()
