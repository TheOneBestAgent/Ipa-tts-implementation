from typing import Any, Dict

from fastapi import APIRouter

from core.jobs import get_job_manager


router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/status")
def get_status() -> Dict[str, Any]:
    job_manager = get_job_manager()
    return job_manager.status_snapshot()
