
"""
FITIF 수동 혈당 기록 수정·삭제 API

PUT    /api/glucose/readings/{reading_id}
DELETE /api/glucose/readings/{reading_id}

보안:
- JWT 인증 필수
- 로그인 회원 본인의 기록만 수정 및 삭제
- 클라이언트가 전달한 member_id는 신뢰하지 않음
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import psycopg2

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from ..database import get_write_connection
from .auth import get_current_member


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/glucose",
    tags=["Glucose Management"],
)


# ==========================================
# 1. 혈당 수정 요청 모델
# ==========================================

class GlucoseUpdate(BaseModel):
    # 수정 화면에서는 모든 측정 정보를 전달한다.
    # 회원 ID와 기록 ID는 요청 본문에서 받지 않는다.

    glucose_mg_dl: Decimal = Field(
        gt=0,
        le=1000,
        max_digits=5,
        decimal_places=1,
    )

    measured_at: datetime

    measurement_context: Literal[
        "fasting",
        "before_meal",
        "after_meal",
        "bedtime",
        "other",
        "unknown",
    ]

    measurement_method: Literal[
        "fingerstick",
        "other",
        "unknown",
    ]

    note: str | None = Field(default=None, max_length=500)

    model_config = {"extra": "forbid"}

    @field_validator("measured_at")
    @classmethod
    def validate_measured_at(cls, value: datetime):
        # 시간대가 없는 날짜는 서버에서 해석이 달라질 수 있다.
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("측정 시각에 시간대 정보가 필요합니다.")

        if value > datetime.now(timezone.utc):
            raise ValueError("미래 시각은 입력할 수 없습니다.")

        return value


# ==========================================
# 2. 혈당 기록 수정 (Update)
# ==========================================

@router.put("/readings/{reading_id}")
def update_glucose(
    reading_id: int,
    data: GlucoseUpdate,
    member: dict = Depends(get_current_member),
):
    """
    자신의 혈당 기록만 수정한다.

    WHERE 조건에 reading_id와 member_id를 함께 사용한다.
    해당 회원의 기록이 아니면 404를 반환한다.
    """

    if reading_id < 1:
        raise HTTPException(
            status_code=422,
            detail="올바른 기록 ID가 아닙니다.",
        )

    member_id = member["member_id"]

    try:
        conn = get_write_connection()

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.glucose_reading_manual
                        SET
                            glucose_mg_dl = %s,
                            measured_at = %s,
                            measurement_context = %s,
                            measurement_method = %s,
                            note = %s
                        WHERE reading_id = %s
                          AND member_id = %s
                        RETURNING
                            reading_id,
                            member_id,
                            glucose_mg_dl,
                            measured_at,
                            measurement_context,
                            measurement_method,
                            input_method,
                            recorded_at,
                            note
                        """,
                        (
                            data.glucose_mg_dl,
                            data.measured_at,
                            data.measurement_context,
                            data.measurement_method,
                            data.note,
                            reading_id,
                            member_id,
                        ),
                    )

                    row = cur.fetchone()

                    if row is None:
                        raise HTTPException(
                            status_code=404,
                            detail="수정할 혈당 기록을 찾을 수 없습니다.",
                        )

                    # 반환할 데이터를 컬럼명과 매칭한다.
                    columns = [
                        column.name
                        for column in cur.description
                    ]

                    result = dict(zip(columns, row))

        finally:
            conn.close()

    except psycopg2.Error as exc:
        logger.error(
            "Glucose update DB error: SQLSTATE=%s",
            exc.pgcode,
        )

        raise HTTPException(
            status_code=503,
            detail="혈당 기록 수정 중 DB 오류가 발생했습니다.",
        ) from exc

    return result


# ==========================================
# 3. 혈당 기록 삭제 (Delete)
# ==========================================

@router.delete(
    "/readings/{reading_id}",
    status_code=204,
)
def delete_glucose(
    reading_id: int,
    member: dict = Depends(get_current_member),
):
    """
    자신의 혈당 기록만 삭제한다.

    잘못된 기록 ID나 타인 기록의 경우
    동일하게 404를 반환한다.

    삭제는 실제 DB에서 행을 제거하는 방식이다.
    """

    if reading_id < 1:
        raise HTTPException(
            status_code=422,
            detail="올바른 기록 ID가 아닙니다.",
        )

    member_id = member["member_id"]

    try:
        conn = get_write_connection()

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM public.glucose_reading_manual
                        WHERE reading_id = %s
                          AND member_id = %s
                        """,
                        (reading_id, member_id),
                    )

                    if cur.rowcount == 0:
                        raise HTTPException(
                            status_code=404,
                            detail="삭제할 혈당 기록을 찾을 수 없습니다.",
                        )

        finally:
            conn.close()

    except psycopg2.Error as exc:
        logger.error(
            "Glucose delete DB error: SQLSTATE=%s",
            exc.pgcode,
        )

        raise HTTPException(
            status_code=503,
            detail="혈당 기록 삭제 중 DB 오류가 발생했습니다.",
        ) from exc

    return Response(status_code=204)
