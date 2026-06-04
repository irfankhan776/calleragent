from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from database import get_session
from models import Call

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("")
def get_stats(session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
    
    # 1. Total calls
    total_calls = session.exec(select(func.count(Call.id))).one() or 0
    
    # 2. Today's calls
    today_calls = session.exec(select(func.count(Call.id)).where(Call.called_at >= today_start)).one() or 0
    
    # 3. Outcomes count
    outcomes = {"Interested": 0, "Callback": 0, "Pitched": 0, "Not interested": 0}
    outcome_rows = session.exec(
        select(Call.outcome, func.count(Call.id)).group_by(Call.outcome)
    ).all()
    for outcome, count in outcome_rows:
        if outcome in outcomes:
            outcomes[outcome] = count
            
    # 4. Avg duration
    avg_duration = session.exec(select(func.avg(Call.duration_seconds))).one()
    avg_duration_seconds = round(avg_duration) if avg_duration is not None else 0
    
    # 5. Recordings saved (count how many database entries have non-empty recording_path)
    recordings_saved = session.exec(
        select(func.count(Call.id)).where(Call.recording_path != "")
    ).one() or 0
    
    # 6. Sentiment breakdown
    sentiment_breakdown = {"Positive": 0, "Neutral": 0, "Negative": 0}
    sentiment_rows = session.exec(
        select(Call.sentiment, func.count(Call.id)).group_by(Call.sentiment)
    ).all()
    for sentiment, count in sentiment_rows:
        if sentiment in sentiment_breakdown:
            sentiment_breakdown[sentiment] = count
            
    # 7. Calls by hour (last 24 hours)
    # Get all calls in the last 24 hours
    twenty_four_hours_ago = now - timedelta(hours=24)
    recent_calls = session.exec(
        select(Call.called_at).where(Call.called_at >= twenty_four_hours_ago)
    ).all()
    
    # Generate the list of 24 hourly slots in chronological order
    # Format: "HH:00"
    hour_slots = []
    hour_counts = {}
    for i in range(24):
        slot_time = now - timedelta(hours=23 - i)
        slot_str = slot_time.strftime("%H:00")
        hour_slots.append(slot_str)
        hour_counts[slot_str] = 0
        
    # Populate counts
    for called_at in recent_calls:
        # Convert to local time or keep UTC? Keeping UTC or converting to local depends on display.
        # Let's group by UTC hour for simplicity, or local hour if timezone info is available.
        # The frontend will display whatever is returned.
        # Let's align slot_time and called_at formatting.
        called_at_str = called_at.strftime("%H:00")
        if called_at_str in hour_counts:
            hour_counts[called_at_str] += 1
            
    calls_by_hour = [{"hour": hr, "count": hour_counts[hr]} for hr in hour_slots]
    
    return {
        "total_calls": total_calls,
        "today_calls": today_calls,
        "outcomes": outcomes,
        "avg_duration_seconds": avg_duration_seconds,
        "recordings_saved": recordings_saved,
        "sentiment_breakdown": sentiment_breakdown,
        "calls_by_hour": calls_by_hour
    }
