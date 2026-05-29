import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.site import Site

router = APIRouter(prefix="/sites", tags=["sites"])


class CreateSiteRequest(BaseModel):
    name: str
    domain: str
    seed: dict   # niche, audience, goals, cadence - extensible JSONB


class SiteResponse(BaseModel):
    site_id: str
    name: str
    domain: str
    seed: dict
    is_active: bool


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(
    request: CreateSiteRequest,
    db: AsyncSession = Depends(get_db),
) -> SiteResponse:
    site = Site(name=request.name, domain=request.domain, seed=request.seed)
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return SiteResponse(
        site_id=str(site.id),
        name=site.name,
        domain=site.domain,
        seed=site.seed,
        is_active=site.is_active,
    )


@router.get("/{site_id}/seed", response_model=dict)
async def get_seed(site_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Orchestrator reads this to understand the site's niche, goals, and context
    before deciding what article to commission next.
    """
    result = await db.execute(
        select(Site).where(Site.id == uuid.UUID(site_id), Site.is_active.is_(True))
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"site_id": str(site.id), "name": site.name, "domain": site.domain, **site.seed}


@router.get("", response_model=list[SiteResponse])
async def list_sites(db: AsyncSession = Depends(get_db)) -> list[SiteResponse]:
    result = await db.execute(select(Site).where(Site.is_active.is_(True)))
    sites = result.scalars().all()
    return [
        SiteResponse(
            site_id=str(s.id), name=s.name, domain=s.domain, seed=s.seed, is_active=s.is_active
        )
        for s in sites
    ]
