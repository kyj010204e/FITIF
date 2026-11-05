
"""
FITIF A파트 혈당 조회 API 연동 모듈

담당:
    C파트와 A파트 간 혈당 데이터 통신

역할:
    1. A파트 FastAPI에 사용자 혈당 기록 요청
    2. JSON 응답 수신
    3. 혈당 측정 시각을 UTC에서 한국시간으로 변환
    4. Gemma가 활용할 수 있도록 구조화된 데이터 반환

서버 구성:
    5090 GPU 서버 → SSH 터널(18001)
    → 3060 FastAPI(8001) → PostgreSQL

주의:
    과거 기록을 현재 혈당으로 해석해서는 안 된다.
"""

import json
import os

from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo


# 한국 표준시: UTC+9
KST = ZoneInfo("Asia/Seoul")

# 5090 서버에서 접근하는 A파트 FastAPI 주소
HEALTH_API_URL = os.environ.get(
    "HEALTH_API_URL",
    "http://127.0.0.1:18001"
).rstrip("/")


def convert_to_kst(iso_datetime: str) -> str:
    """
    ISO 8601 측정 시각을 한국시간으로 변환한다.

    매개변수:
        iso_datetime:
            시간대가 포함된 ISO 8601 문자열.

    예시 입력:
        2021-03-04T20:58:00+00:00

    예시 반환:
        2021-03-05T05:58:00+09:00

    주의:
        시간대가 없는 시각은 UTC인지 한국시간인지
        판단할 수 없으므로 변환하지 않고 오류를 발생시킨다.
    """

    # ISO 8601 문자열을 datetime 객체로 변환한다.
    # Z 표기도 UTC(+00:00)로 해석한다.
    measured_at = datetime.fromisoformat(
        iso_datetime.replace("Z", "+00:00")
    )

    # 시간대 정보가 없으면 변환하지 않는다.
    if measured_at.utcoffset() is None:
        raise ValueError(
            "측정 시각에 시간대 정보가 없습니다."
        )

    # astimezone()은 실제 측정 순간을 유지하면서
    # 표시되는 날짜와 시간을 한국시간으로 바꾼다.
    return measured_at.astimezone(KST).isoformat()


def fetch_glucose_from_api(
    member_id: int,
    limit: int = 3
) -> dict:
    """
    A파트 FastAPI에서 CGM 혈당 기록을 조회한다.

    매개변수:
        member_id:
            조회할 사용자 번호.

        limit:
            최대 조회 건수. 기본값 3건.

    반환값:
        다음 정보를 포함한 dict.

        status:
            API 조회 성공 여부.

        source:
            데이터 출처.

        latest:
            최신 혈당과 측정 시각.

        readings:
            실제 측정값 목록.
            원본 UTC 및 한국시간을 모두 포함한다.

    보안:
        member_id는 호출자가 전달한 값을 사용한다.
        실제 운영에서는 로그인한 사용자의 ID를
        서버가 검증하여 전달해야 한다.
    """

    # ---------------------------------------------
    # 1. 요청 파라미터 검증
    # ---------------------------------------------

    if (
        isinstance(member_id, bool)
        or not isinstance(member_id, int)
        or member_id < 1
    ):
        raise ValueError(
            "member_id는 1 이상의 정수여야 합니다."
        )

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 500
    ):
        raise ValueError(
            "limit는 1~500 사이의 정수여야 합니다."
        )

    # ---------------------------------------------
    # 2. A파트 FastAPI 요청 URL 생성
    # ---------------------------------------------

    params = urlencode({
        "member_id": member_id,
        "limit": limit
    })

    url = (
        f"{HEALTH_API_URL}/api/cgm/readings?{params}"
    )

    # ---------------------------------------------
    # 3. HTTP 요청 및 JSON 응답 수신
    # ---------------------------------------------

    try:
        with urlopen(url, timeout=10) as response:
            data = json.load(response)

    except (HTTPError, URLError, TimeoutError) as exc:
        # 원본 접속정보 및 내부 오류를 모델에 전달하지 않는다.
        raise RuntimeError(
            "A파트 혈당 API 호출에 실패했습니다."
        ) from exc

    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            "혈당 API 응답을 해석하지 못했습니다."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "혈당 API 응답이 객체 형식이 아닙니다."
        )

    readings = data.get("readings")

    if not isinstance(readings, list):
        raise RuntimeError(
            "혈당 API 응답에 readings가 없습니다."
        )

    # ---------------------------------------------
    # 4. 측정 시각을 한국시간으로 변환
    # ---------------------------------------------

    converted_readings = []

    for reading in readings:

        try:
            # 원본 데이터의 측정 시각
            original_time = reading["measured_at"]

            # Python에서 한국시간 변환
            korean_time = convert_to_kst(original_time)

            # 원본의 혈당값
            glucose_value = reading["glucose_mg_dl"]

            if (
                isinstance(glucose_value, bool)
                or not isinstance(glucose_value, (int, float))
                or not 0 < glucose_value < float("inf")
            ):
                raise ValueError("혈당값이 올바르지 않습니다.")

            # 기존 응답 필드를 유지하면서
            # 한국시간 필드를 추가한다.
            converted_readings.append({
                **reading,
                "measured_at_kst": korean_time
            })

        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "혈당 API 응답의 측정 데이터가 잘못되었습니다."
            ) from exc

    # ---------------------------------------------
    # 5. 혈당 기록이 없는 경우
    # ---------------------------------------------

    if not converted_readings:
        return {
            "status": "ok",
            "source": "fitif_health_api",
            "member_id": member_id,
            "record_count": 0,
            "latest": None,
            "readings": []
        }

    # ---------------------------------------------
    # 6. 최종 조회 결과 구성
    # ---------------------------------------------

    # A파트 API가 최신 측정 시각순으로
    # 반환한다는 계약을 따른다.
    latest = converted_readings[0]

    return {
        "status": "ok",
        "source": "fitif_health_api",
        "member_id": member_id,
        "record_count": len(converted_readings),

        "latest": {
            "value": latest["glucose_mg_dl"],
            "measured_at": latest["measured_at"],
            "measured_at_kst": latest["measured_at_kst"]
        },

        # Gemma가 변환된 시각을 읽을 수 있도록
        # 모든 측정 기록에 한국시간 필드를 포함한다.
        "readings": converted_readings
    }
