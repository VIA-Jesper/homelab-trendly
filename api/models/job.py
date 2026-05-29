import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sites.id"), nullable=False)
    # status: queued | in_progress | complete | failed | requires_review
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    # context is JSON - holds article_type, keyword, product info, etc.
    # extend here (add product_id, seo_data, links) without schema changes
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship("Site", back_populates="jobs")  # noqa: F821
    steps: Mapped[list["Step"]] = relationship("Step", back_populates="job", order_by="Step.step_order", lazy="selectin")  # noqa: F821
