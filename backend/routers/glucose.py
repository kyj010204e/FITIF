
"""
FITIF 사용자 수동 혈당 기록 저장 API

POST /api/glucose/readings

기능:
    사용자가 직접 입력하거나 음성으로 전달한
    혈당 정보를 PostgreSQL에 저장한다.

저장 대상:
    public.glucose_reading_manual

주의:
    현재는 개발 및 테스트 전용이다.
    실제 사용자 인증 및 권한 검증은 아직 구현되지 않았다.
"""

import os
from datetime import datetime
from decimal import Decimal
from typing import Literal

import psycopg2

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Query,
    status
)

from pydantic import BaseModel, Field, field_validator

from ..database import get_connection, get_write_connection


# API 주소의 공통 앞부분
router = APIRouter(
    prefix="/api/glucose",
    tags=["Manual Glucose"]
)


# ==========================================
# 1. 요청 데이터 검증
# ==========================================

class GlucoseCreate(BaseModel):
    """
    사용자가 새로 저장할 혈당 기록.

    FastAPI가 요청 JSON을 자동 검증한다.
    """

    member_id: int = Field(
        ...,
        ge=1,
        description="사용자 번호"
    )

    glucose_mg_dl: Decimal = Field(
        ...,
        gt=0,
        le=1000,
        allow_inf_nan=False,
        max_digits=6,
        decimal_places=1,
        description="혈당 측정값 (mg/dL)"
    )

    measured_at: datetime | None = Field(
        default=None,
        description="실제 측정 시각, 시간대 필수"
    )

    measurement_context: Literal[
        "fasting",
        "before_meal",
        "after_meal",
        "bedtime",
        "other",
        "unknown"
    ] = "unknown"

    measurement_method: Literal[
        "fingerstick",
        "other",
        "unknown"
    ] = "unknown"

    input_method: Literal[
        "voice",
        "manual"
    ]

    note: str | None = Field(
        default=None,
        max_length=500
    )

    @field_validator("measured_at")
    @classmethod
    def validate_measured_at(cls, value):
        """
        시각이 입력되었다면
        UTC 또는 KST 등의 시간대 정보가 반드시 필요하다.
        """

        if value is not None:
            if value.utcoffset() is None:
                raise ValueError(
                    "measured_at에는 시간대가 필요합니다."
                )

        return value


# ==========================================
# 2. 수동 혈당 기록 저장
# ==========================================

@router.post(
    "/readings",
    status_code=status.HTTP_201_CREATED
)
def create_glucose_reading(
    data: GlucoseCreate,
    request: Request
):
    """
    검증된 혈당 정보를 DB에 저장한다.

    처리 흐름:
        JSON 수신
        → 데이터 검증
        → PostgreSQL INSERT
        → 저장 결과 반환

    중요:
        현재는 인증 기능이 없는 개발용 API다.
        로컬 요청과 명시적인 개발 플래그가 있는
        경우에만 사용할 수 있도록 제한한다.

        운영 환경에서는 로그인 사용자 권한 확인과
        사용자 저장 동의 처리가 필요하다.
    """

    # --------------------------------------
    # 2-1. 개발용 API 접근 제한
    # --------------------------------------

    enabled = (
        os.getenv("ENABLE_DEV_GLUCOSE_WRITE")
        == "1"
    )

    client_host = (
        request.client.host
        if request.client is not None
        else None
    )

    if not enabled or client_host not in (
        "127.0.0.1",
        "::1"
    ):
        raise HTTPException(
            status_code=403,
            detail="Development write API is disabled"
        )

    # --------------------------------------
    # 2-2. PostgreSQL INSERT
    # --------------------------------------

    try:
        conn = get_write_connection()

        try:
            # with conn은 정상 종료 시 COMMIT,
            # SQL 오류 발생 시 ROLLBACK을 처리한다.
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
                            data.member_id,
                            data.glucose_mg_dl,
                            data.measured_at,
                            data.measurement_context,
                            data.measurement_method,
                            data.input_method,
                            data.note
                        )
                    )

                    row = cursor.fetchone()

        finally:
            # 오류가 발생하더라도 연결은 종료한다.
            conn.close()

    except psycopg2.errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=422,
            detail="존재하지 않는 사용자 ID입니다."
        ) from exc

    except psycopg2.errors.CheckViolation as exc:
        raise HTTPException(
            status_code=422,
            detail="혈당 입력값이 DB 제약조건에 맞지 않습니다."
        ) from exc

    except psycopg2.Error as exc:
        # DB 내부 오류와 비밀번호를 외부에 노출하지 않는다.
        raise HTTPException(
            status_code=503,
            detail="Database write unavailable"
        ) from exc

    # --------------------------------------
    # 2-3. 저장 성공 응답
    # --------------------------------------

    return {
        "status": "created",
        "reading_id": row[0],
        "member_id": data.member_id,
        "glucose_mg_dl": float(data.glucose_mg_dl),
        "measured_at": data.measured_at,
        "measurement_context": data.measurement_context,
        "measurement_method": data.measurement_method,
        "input_method": data.input_method,
        "recorded_at": row[1]
    }


# ==========================================
# 3. 사용자 수동 혈당 기록 조회 API
# ==========================================

@router.get("/readings")
def get_manual_glucose_readings(
    member_id: int = Query(
        ...,
        ge=1,
        description="혈당 기록을 조회할 사용자 ID"
    ),

    start_at: datetime | None = Query(
        default=None,
        description="조회 시작 시각 (시간대 필수, 포함)"
    ),

    end_at: datetime | None = Query(
        default=None,
        description="조회 종료 시각 (시간대 필수, 미포함)"
    ),

    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="최대 조회 건수 (1~500)"
    )
):
    """
    사용자가 수동으로 입력한 혈당 기록을 조회한다.

    요청 예:
        GET /api/glucose/readings?member_id=28&limit=3

    조회 대상:
        public.glucose_reading_manual

    기존 CGM 조회 API와의 차이:
        /api/cgm/readings
            과거 CGM 장치 측정값 조회

        /api/glucose/readings
            사용자 직접·음성 입력 기록 조회

    처리 순서:
        1. 입력 파라미터 검증
        2. PostgreSQL 읽기 전용 연결
        3. member_id 조건으로 데이터 조회
        4. 최신 기록순 정렬
        5. JSON 응답 생성

    주의:
        개발용 API이므로 사용자 인증 및 인가가 없다.
        외부 네트워크에 공개하면 안 된다.
    """

    # --------------------------------------
    # 3-1. 날짜 입력 검증
    # --------------------------------------

    # 조회 기간의 날짜에 시간대가 없다면
    # UTC와 한국시간을 구분할 수 없다.
    for name, value in (
        ("start_at", start_at),
        ("end_at", end_at)
    ):
        if (
            value is not None
            and value.utcoffset() is None
        ):
            raise HTTPException(
                status_code=422,
                detail=f"{name} must include timezone"
            )

    # 조회 시작일은 종료일보다 빨라야 한다.
    if (
        start_at is not None
        and end_at is not None
        and start_at >= end_at
    ):
        raise HTTPException(
            status_code=422,
            detail="start_at must be earlier than end_at"
        )

    # --------------------------------------
    # 3-2. PostgreSQL 조회
    # --------------------------------------

    try:
        # 기존 CGM API와 동일한 읽기 전용 연결을 사용한다.
        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cursor:

                    # SQL Injection 방지를 위해
                    # 사용자의 입력을 %s 파라미터로 전달한다.
                    #
                    # measured_at이 NULL인 기록도 보존한다.
                    # 단, 기간 필터가 적용되면 NULL 기록은
                    # 해당 기간에 속하는지 판단할 수 없어
                    # 조회 결과에서 제외된다.
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
                        WHERE member_id = %s

                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at >= %s::timestamptz
                          )

                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at < %s::timestamptz
                          )

                        -- 측정 시각이 있는 기록을 우선 배치한다.
                        -- 측정 시각이 없는 기록은 마지막에 배치한다.
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
                            limit
                        )
                    )

                    rows = cursor.fetchall()

        finally:
            # 요청이 종료되면 연결을 반드시 닫는다.
            conn.close()

    except psycopg2.Error as exc:
        # SQL 및 DB 내부 오류는 사용자에게 노출하지 않는다.
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable"
        ) from exc

    # --------------------------------------
    # 3-3. DB 결과 → JSON
    # --------------------------------------

    readings = []

    for row in rows:

        readings.append({
            "reading_id": row[0],
            "member_id": row[1],

            # PostgreSQL NUMERIC은 Decimal로 반환된다.
            # 응답에서 JSON 숫자로 표시하기 위해 변환한다.
            "glucose_mg_dl": float(row[2]),

            # datetime은 FastAPI가 ISO 8601로 변환한다.
            "measured_at": row[3],

            "measurement_context": row[4],
            "measurement_method": row[5],
            "input_method": row[6],
            "recorded_at": row[7],
            "note": row[8]
        })

    # --------------------------------------
    # 3-4. 최종 응답
    # --------------------------------------

    return {
        "member_id": member_id,
        "source": "manual_glucose",
        "start_at": start_at,
        "end_at": end_at,

        # 전체 DB 기록 수가 아니라 반환된 기록 수
        "count": len(readings),

        "limit": limit,
        "readings": readings
    }
