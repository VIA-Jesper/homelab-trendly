import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("prompts.id"), nullable=True)
    # input is JSON - holds everything the agent needs (prompt text + content)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    # status: pending | in_progress | complete | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # claimed_at: set when a worker takes this step. Used for lease expiry -
    # if the worker dies before submitting, the step is reset after STEP_LEASE_SECONDS.
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="steps")  # noqa: F821
    prompt: Mapped["Prompt | None"] = relationship("Prompt", lazy="selectin")  # noqa: F821
