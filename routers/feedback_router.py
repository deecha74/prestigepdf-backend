"""
routers/feedback_router.py — PrestigePDF User Feedback API

Allows visitors to submit genuine 1-click reviews and ratings.
Persists feedback in SQLite blogs.db and returns live summary metrics.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from database import insert_feedback, get_feedback_summary, get_all_feedback

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


class FeedbackSubmission(BaseModel):
    tool_id: str = Field(default="general", max_length=100)
    rating: int = Field(ge=1, le=5, description="Star rating from 1 to 5")
    tags: Optional[List[str]] = Field(default_factory=list)
    comment: Optional[str] = Field(default="", max_length=500)


@router.post("", summary="Submit User Feedback")
async def submit_feedback(payload: FeedbackSubmission):
    """
    Submits user review / rating.
    Stores into SQLite and returns the updated summary.
    """
    try:
        feedback_id = insert_feedback(
            tool_id=payload.tool_id,
            rating=payload.rating,
            tags=payload.tags,
            comment=payload.comment,
        )
        summary = get_feedback_summary(payload.tool_id)
        return {
            "status": "success",
            "message": "Thank you for your feedback!",
            "id": feedback_id,
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.get("/summary", summary="Get Feedback Summary")
async def get_summary(tool_id: Optional[str] = Query(default=None)):
    """
    Returns aggregated rating count and average score.
    """
    try:
        summary = get_feedback_summary(tool_id)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/list", summary="Get Recent Feedback")
async def list_feedback(limit: int = Query(default=50, ge=1, le=200)):
    """
    Returns recent feedback submissions.
    """
    try:
        items = get_all_feedback(limit)
        return {"total": len(items), "feedback": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list feedback: {str(e)}")
