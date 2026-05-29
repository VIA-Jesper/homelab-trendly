import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.job import Job
from models.prompt import Prompt
from models.step import Step


class PipelineService:
    """
    Controls step sequencing, retry logic, and job state transitions.
    All structural pipeline decisions live here - not in the agent.
    """

    async def create_steps_for_job(self, job: Job, db: AsyncSession) -> None:
        """Create all pipeline steps for a new job based on config."""
        for order, step_cfg in enumerate(settings.pipeline_steps):
            prompt = await self._get_active_prompt(step_cfg["prompt_name"], db)
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
        previous_output = await self._get_previous_output(job, step.step_order, db)
        return {
            "prompt": prompt_content,
            "context": job.context,
            "previous_output": previous_output,
            "step_name": step.step_name,
            "attempt": step.attempt,
        }

    async def handle_step_result(
        self, step: Step, output: str, job: Job, db: AsyncSession
    ) -> dict:
        """
        Process agent output. Advance step/job state.
        Returns updated job status.
        """
        step_cfg = self._get_step_config(step.step_name)
        step.output = output
        step.completed_at = datetime.now(timezone.utc)

        if step_cfg and step_cfg.get("is_qa_step"):
            passed = "PASS" in output.upper()
            if not passed and step.attempt < step_cfg.get("max_attempts", 3):
                # Retry: create new step record for next attempt
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
        else:
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


pipeline_service = PipelineService()
