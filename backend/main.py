
"""
FITIF Health Data API

담당: A파트 (Health Data & Backend)

현재 제공하는 API:
    GET /                  서버 기본 정보
    GET /health            서버 실행 상태 확인
    GET /api/cgm/readings  사용자별 CGM 기록 조회

데이터 출처:
    PostgreSQL public.cgm_reading_old

주의:
    현재는 과거 CGM 데이터를 사용하는 개발용 API다.
    사용자 인증이 없으므로 외부에 공개해서는 안 된다.
"""

from datetime import datetime

import psycopg2
from fastapi import FastAPI, HTTPException, Query

# backend 패키지의 DB 연결 함수
from .database import get_connection


# ==============================================
# 1. FastAPI 애플리케이션 생성
# ==============================================

app = FastAPI(
    title="FITIF Health Data API",
    description="FITIF 건강정보 조회 및 분석 백엔드",
    version="0.1.0"
)


# ==============================================
# 2. 기본 API
# ==============================================

@app.get("/")
def root():
    """
    API 서버의 이름과 실행 상태를 반환한다.

    사용 예:
        GET /
    """
    return {
        "service": "FITIF",
        "message": "FastAPI server is running"
    }


@app.get("/health")
def health_check():
    """
    FastAPI 프로세스가 요청에 응답하는지 확인한다.

    주의:
        이 API는 데이터베이스 연결까지
        확인하는 것은 아니다.
    """
    return {"status": "ok"}


# ==============================================
# 3. 사용자별 CGM 데이터 조회 API
# ==============================================

@app.get("/api/cgm/readings")
def get_cgm_readings(
    member_id: int = Query(
        ...,
        ge=1,
        description="혈당 기록을 조회할 사용자 ID"
    ),
    start_at: datetime | None = Query(
        default=None,
        description="조회 시작 시각 (시간대 포함)"
    ),
    end_at: datetime | None = Query(
        default=None,
        description="조회 종료 시각 (시간대 포함)"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="최대 조회 건수 (1~500)"
    )
):
    """
    특정 사용자의 CGM 혈당 기록을 조회한다.

    매개변수:
        member_id:
            조회할 사용자 ID. 현재는 개발용으로 전달한다.

        start_at:
            조회 시작 시각. 해당 시각을 포함한다.

        end_at:
            조회 종료 시각. 해당 시각은 포함하지 않는다.

        limit:
            반환할 최대 기록 건수.

    반환값:
        member_id, 조회 기간, 조회 건수, 혈당 기록 목록.

    주의:
        count는 전체 기간의 데이터 수가 아니라
        이번 요청에서 반환된 레코드 수다.
    """

    # ------------------------------------------
    # 3-1. 날짜 입력 검증
    # ------------------------------------------

    # 시간대가 없는 날짜를 허용하면 UTC와 한국시간이
    # 혼동될 수 있으므로 반드시 시간대를 요구한다.
    for name, value in [
        ("start_at", start_at),
        ("end_at", end_at)
    ]:
        if value is not None and value.utcoffset() is None:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must include timezone"
            )

    # 시작 시간이 종료 시간보다 빠른지 확인한다.
    if (
        start_at is not None
        and end_at is not None
        and start_at >= end_at
    ):
        raise HTTPException(
            status_code=422,
            detail="start_at must be earlier than end_at"
        )

    # ------------------------------------------
    # 3-2. PostgreSQL에서 CGM 기록 조회
    # ------------------------------------------

    try:
        # 연결 종료 및 트랜잭션 관리를 명확히 하기 위해
        # DB 연결과 커서를 context manager로 관리한다.
        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cursor:

                    # %s는 SQL 파라미터 자리표시자이다.
                    # 사용자가 입력한 값을 SQL 문자열에
                    # 직접 연결하지 않아 SQL Injection을 방지한다.
                    cursor.execute(
                        """
                        SELECT
                            reading_id,
                            measured_at,
                            glucose_mg_dl,
                            device,
                            is_interpolated
                        FROM public.cgm_reading_old
                        WHERE member_id = %s

                          -- 시작 시각이 없으면 조건 생략
                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at >= %s::timestamptz
                          )

                          -- 종료 시각이 없으면 조건 생략
                          AND (
                              %s::timestamptz IS NULL
                              OR measured_at < %s::timestamptz
                          )

                        -- 최신 측정 기록부터 반환
                        ORDER BY measured_at DESC, reading_id DESC

                        -- 요청한 최대 건수만 조회
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

                    # SQL 실행 결과를 Python 리스트로 가져온다.
                    rows = cursor.fetchall()
        finally:
            # 오류 발생 여부와 관계없이 연결을 닫는다.
            conn.close()

    except psycopg2.Error as exc:
        # DB 내부 오류나 접속정보를 사용자에게 노출하지 않는다.
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable"
        ) from exc

    # ------------------------------------------
    # 3-3. DB 조회 결과를 JSON 형식으로 변환
    # ------------------------------------------

    readings = []

    for row in rows:
        readings.append({
            "reading_id": row[0],
            "measured_at": row[1],
            "glucose_mg_dl": row[2],
            "device": row[3],
            "is_interpolated": row[4]
        })

    # FastAPI가 datetime을 ISO 8601 문자열로 변환한다.
    return {
        "member_id": member_id,
        "start_at": start_at,
        "end_at": end_at,
        "count": len(readings),
        "limit": limit,
        "readings": readings
    }
