from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user
from app.core.supabase_client import get_supabase

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("")
async def list_candidates(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, le=100),
):
    """Returns all parsed candidates in the recruiter's talent pool."""
    db = get_supabase()
    res = db.table("candidates").select("*").eq("user_id", current_user["id"]).limit(limit).execute()
    return res.data
