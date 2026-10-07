from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.gate import GateCountResponse
from services.gate_service import GateService

router = APIRouter(prefix="/api/gate", tags=["Gate"])


@router.get("/counts/daily", response_model=GateCountResponse)
def get_daily_gate_count(
    date: date | None = Query(None, description="Day to query in Asia/Bangkok"),
    db: Session = Depends(get_db),
):
    return GateService(db).get_daily_count(date)


@router.get("/counts/hourly")
def get_hourly_gate_count(
    date: date | None = Query(None, description="Day to query in Asia/Bangkok"),
    db: Session = Depends(get_db),
):
    return {
        "date": date or datetime.now(ZoneInfo("Asia/Bangkok")).date(),
        "hours": GateService(db).get_hourly_counts(date),
    }



@router.get("/counts/weekly")
def get_weekly_gate_count(
    week_start: date | None = Query(
        None, description="Any day in the week to query; weeks start on Monday"
    ),
    db: Session = Depends(get_db),
):
    return GateService(db).get_weekly_summary(week_start)
