from contextlib import closing
from datetime import date
import logging

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_write_connection
from .auth import get_current_member


router = APIRouter(prefix="/api/stress", tags=["Stress"])
logger = logging.getLogger(__name__)


class StressScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(strict=True, ge=1, le=5)


def record_from_row(row):
    return {"recorded_on": row[0], "score": row[1], "recorded_at": row[2]}


@router.put("/today")
def save_today(data: StressScore, member: dict = Depends(get_current_member)):
    # 회원 번호는 인증 결과에서만 가져온다. 한국시간 하루에 한 건을 기록한다.
    try:
        with closing(get_write_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.stress_checkin (member_id, recorded_on, score)
                VALUES (%s, (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date, %s)
                ON CONFLICT (member_id, recorded_on) DO UPDATE
                    SET score = EXCLUDED.score,
                        recorded_at = CASE
                            WHEN stress_checkin.score = EXCLUDED.score
                            THEN stress_checkin.recorded_at
                            ELSE EXCLUDED.recorded_at
                        END
                RETURNING recorded_on, score, recorded_at
                """,
                (member["member_id"], data.score),
            )
            record = record_from_row(cursor.fetchone())
    except (psycopg2.Error, RuntimeError):
        logger.warning("Could not save stress check-in")
        raise HTTPException(503, "스트레스 기록을 저장하지 못했어요.") from None
    return record


@router.get("/readings")
def list_readings(start: date, end: date, member: dict = Depends(get_current_member)):
    if not 0 <= (end - start).days < 30:
        raise HTTPException(422, "조회 기간은 최대 30일이에요.")

    try:
        with closing(get_write_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT recorded_on, score, recorded_at
                FROM public.stress_checkin
                WHERE member_id = %s AND recorded_on BETWEEN %s AND %s
                ORDER BY recorded_on DESC
                """,
                (member["member_id"], start, end),
            )
            return [record_from_row(row) for row in cursor.fetchall()]
    except (psycopg2.Error, RuntimeError):
        logger.warning("Could not load stress check-ins")
        raise HTTPException(503, "스트레스 기록을 불러오지 못했어요.") from None
