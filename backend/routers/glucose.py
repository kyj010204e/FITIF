
"""
FITIF 사용자 혈당 기록 API

POST /api/glucose/readings
    JWT 인증된 사용자의 혈당 기록 저장

GET /api/glucose/readings
    JWT 인증된 사용자의 혈당 기록 조회

데이터베이스:
    public.glucose_reading_manual

보안:
    member_id는 클라이언트 입력을 사용하지 않는다.
    JWT 검증 후 DB에서 확인한 사용자 ID를 사용한다.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

import psycopg2

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from ..database import (
    get_connection,
    get_write_connection,
)

from .auth import get_current_member


# ==========================================
# 1. API 라우터 설정
# ==========================================

router = APIRouter(
    prefix="/api/glucose",
    tags=["Manual Glucose"],
)


# ==========================================
# 2. 혈당 입력 데이터 검증
# ==========================================

class GlucoseCreate(BaseModel):
    """
    사용자가 입력한 혈당 데이터.

    member_id는 입력받지 않는다.
    로그인한 사용자 정보에서 가져온다.
    """

    # 사용자로부터 임의의 member_id가 전달되면
    # 무시하지 않고 검증 오류를 반환한다.
    model_config = {"extra": "forbid"}

    glucose_mg_dl: Decimal = Field(
        ...,
        gt=0,
        le=1000,
        allow_inf_nan=False,
        max_digits=6,
        decimal_places=1,
        description="혈당값 (mg/dL)",
    )

    measured_at: datetime | None = Field(
        default=None,
        description="혈당 측정 시각 (시간대 필수)",
    )

    measurement_context: Literal[
        "fasting",
        "before_meal",
        "after_meal",
        "bedtime",
        "other",
        "unknown",
    ] = "unknown"

    measurement_method: Literal[
        "fingerstick",
        "other",
        "unknown",
    ] = "unknown"

    input_method: Literal[
        "voice",
        "manual",
    ]

    note: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("measured_at")
    @classmethod
    def validate_measured_at(cls, value):
        """
        측정 시각이 있다면 UTC 또는 KST 등
        시간대 정보가 포함되어야 한다.
        """

        if value is not None and value.utcoffset() is None:
            raise ValueError(
                "measured_at에는 시간대가 필요합니다."
            )

        return value


# ==========================================
# 3. 혈당 기록 저장 API
# ==========================================

@router.post(
    "/readings",
    status_code=status.HTTP_201_CREATED,
)
def create_glucose_reading(
    data: GlucoseCreate,
    member: dict = Depends(get_current_member),
):
    """
    로그인한 사용자의 혈당 기록을 저장한다.

    처리 순서:
        1. JWT 인증
        2. 입력값 검증
        3. 인증된 member_id 확인
        4. PostgreSQL INSERT
        5. 저장 결과 반환
    """

    # JWT를 검증한 뒤 DB에서 확인된 사용자 ID
    member_id = member["member_id"]

    # --------------------------------------
    # 3-1. PostgreSQL 저장
    # --------------------------------------

    try:
        conn = get_write_connection()

        try:
            # 정상 종료 시 COMMIT
            # SQL 오류 발생 시 ROLLBACK
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO
                            public.glucose_reading_manual
                        (
                            member_id,
                            glucose_mg_dl,
                            measured_at,
                            measurement_context,
                            measurement_method,
                            input_method,
                            note
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s
                        )
                        RETURNING
                            reading_id,
                            recorded_at
                        """,
                        (
                            member_id,
                            data.glucose_mg_dl,
                            data.measured_at,
                            data.measurement_context,
                            data.measurement_method,
                            data.input_method,
                            data.note,
                        ),
                    )

                    row = cursor.fetchone()

        finally:
            conn.close()

    # --------------------------------------
    # 3-2. PostgreSQL 오류 처리
    # --------------------------------------

    except psycopg2.errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=422,
            detail="존재하지 않는 사용자 ID입니다.",
        ) from exc

    except psycopg2.errors.CheckViolation as exc:
        raise HTTPException(
            status_code=422,
            detail="혈당 입력값이 DB 제약조건에 맞지 않습니다.",
        ) from exc

    except psycopg2.Error as exc:
        # 사용자에게 SQL이나 DB 내부 정보를 노출하지 않는다.
        raise HTTPException(
            status_code=503,
            detail="Database write unavailable",
        ) from exc

    # --------------------------------------
    # 3-3. 저장 성공 응답
    # --------------------------------------

    return {
        "status": "created",
        "reading_id": row[0],
        "member_id": member_id,
        "glucose_mg_dl": float(data.glucose_mg_dl),
        "measured_at": data.measured_at,
        "measurement_context": data.measurement_context,
        "measurement_method": data.measurement_method,
        "input_method": data.input_method,
        "recorded_at": row[1],
    }


# ==========================================
# 4. 혈당 기록 조회 API
# ==========================================

@router.get("/readings")
def get_manual_glucose_readings(
    member: dict = Depends(get_current_member),
    start_at: datetime | None = Query(
        default=None,
        description="조회 시작 시각 (시간대 필수, 포함)",
    ),
    end_at: datetime | None = Query(
        default=None,
        description="조회 종료 시각 (시간대 필수, 미포함)",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="최대 조회 건수 (1~500)",
    ),
):
    """
    로그인한 사용자의 혈당 기록만 조회한다.

    요청 예:
        GET /api/glucose/readings?limit=10

    클라이언트에서 member_id를 전달할 필요가 없다.

    조회 대상:
        public.glucose_reading_manual
    """

    member_id = member["member_id"]

    # --------------------------------------
    # 4-1. 조회 날짜 검증
    # --------------------------------------

    # 시간대가 없는 시각은 허용하지 않는다.
    for name, value in (
        ("start_at", start_at),
        ("end_at", end_at),
    ):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must include timezone",
            )

    # 시작 시각은 종료 시각보다 빨라야 한다.
    if (
        start_at is not None
        and end_at is not None
        and start_at >= end_at
    ):
        raise HTTPException(
            status_code=422,
            detail="start_at must be earlier than end_at",
        )

    # --------------------------------------
    # 4-2. PostgreSQL 조회
    # --------------------------------------

    try:
        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            reading_id,
                            member_id,
                            glucose_mg_dl,
                            measured_at,
                            measurement_context,
                            measurement_method,
                            input_method,
                            recorded_at,
                            note
                        FROM public.glucose_reading_manual

                        -- JWT 인증된 사용자만 조회
                        WHERE member_id = %s

                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at >= %s::timestamptz
                          )

                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at < %s::timestamptz
                          )

                        ORDER BY
                            measured_at DESC NULLS LAST,
                            recorded_at DESC,
                            reading_id DESC

                        LIMIT %s
                        """,
                        (
                            member_id,
                            start_at,
                            start_at,
                            end_at,
                            end_at,
                            limit,
                        ),
                    )

                    rows = cursor.fetchall()

        finally:
            conn.close()

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from exc

    # --------------------------------------
    # 4-3. 조회 결과 JSON 변환
    # --------------------------------------

    readings = []

    for row in rows:
        readings.append({
            "reading_id": row[0],
            "member_id": row[1],
            "glucose_mg_dl": float(row[2]),
            "measured_at": row[3],
            "measurement_context": row[4],
            "measurement_method": row[5],
            "input_method": row[6],
            "recorded_at": row[7],
            "note": row[8],
        })

    # --------------------------------------
    # 4-4. 조회 응답
    # --------------------------------------

    return {
        "member_id": member_id,
        "source": "manual_glucose",
        "start_at": start_at,
        "end_at": end_at,
        "count": len(readings),
        "limit": limit,
        "readings": readings,
    }
