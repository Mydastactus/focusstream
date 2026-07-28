from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.feedback import Feedback, FeedbackAction
from app.models.signal_card import SignalCard
from app.schemas.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def record_feedback(
    payload: FeedbackRequest, db: AsyncSession = Depends(get_db)
) -> FeedbackResponse:
    # `item_id` in the API spec resolves to a Signal Card here.
    card = await db.get(SignalCard, payload.item_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card_not_found")

    action = FeedbackAction(payload.action)
    db.add(Feedback(card_id=card.id, action=action, reason=payload.reason))

    # Fold obvious actions into the card's denormalized flags so the feed
    # reflects them immediately.
    if action == FeedbackAction.save:
        card.is_saved = True
    elif action in (FeedbackAction.downvote, FeedbackAction.dismiss):
        # Both hide the card from the feed; downvote additionally feeds
        # future re-ranking / threshold tuning via the recorded row above.
        card.is_dismissed = True

    await db.commit()
    return FeedbackResponse(status="recorded", item_id=payload.item_id, action=payload.action)
