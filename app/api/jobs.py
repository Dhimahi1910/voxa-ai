from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_services
from app.container import Services
from app.core.security import require_api_key
from app.schemas.call import JobTriggerRequest
from app.scheduler import JOBS

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.post("/trigger")
async def trigger_job(body: JobTriggerRequest, sv: Services = Depends(get_services)):
    """Run a job now. Jobs are exclusive: if the same job is already running this returns {'skipped': 'already_running'}."""
    return {"job": body.job, "result": await JOBS[body.job](sv)}
