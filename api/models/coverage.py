"""
Coverage ledger models - the de-dup spine.

Two tables, both written when a job is created and read by the API gate (to
block collisions) and the planner (to find unfilled slots):

  job_products  - one row per (job, product). A roundup has several, a single
                  review has one. Answers "which products are already covered on
                  this site?" without scanning every job's JSON context.
  job_coverage  - one row per job: its slot identity (category, format, subject).
                  Two live jobs must never share a slot_key on the same site.

site_id is denormalised from the parent job so the hot per-site lookups need no
join. The JSON `context` on Job stays the source of truth for content; these
tables are a fast, queryable index over it (rebuildable via backfill).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class JobProduct(Base):
    __tablename__ = "job_products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    article_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_job_products_site_key", "site_id", "product_key"),
        Index("idx_job_products_job", "job_id"),
    )


class JobCoverage(Base):
    __tablename__ = "job_coverage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    slot_key: Mapped[str] = mapped_column(String(512), nullable=False)
    category_slug: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    article_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Filled progressively: derived keyword now, final WP slug at publish.
    primary_keyword: Mapped[str | None] = mapped_column(String(512), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_job_coverage_site_slot", "site_id", "slot_key"),
        Index("idx_job_coverage_job", "job_id"),
    )
