from routes.jobs import router as jobs_router
from routes.sites import router as sites_router
from routes.work import router as work_router

__all__ = ["work_router", "jobs_router", "sites_router"]
