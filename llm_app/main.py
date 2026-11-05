
"""
FITIF C파트 - Gemma 4 Tool Calling API

역할:
    사용자 질문을 Gemma 4에 전달하고,
    모델이 요청한 도구를 Python에서 실행한 뒤,
    조회 결과를 자연어로 설명하도록 한다.

전체 처리 흐름:
    1. 사용자가 POST /chat으로 질문 전송
    2. Ollama의 Gemma 4 모델에 질문 전달
    3. Gemma가 필요한 Tool 선택
    4. Python에서 해당 Tool 실행
    5. Tool 실행 결과를 Gemma에 전달
    6. Gemma가 최종 한국어 답변 생성
    7. FastAPI가 결과 반환

현재 지원하는 도구:
    get_patient_record:
        기존 C파트 PostgreSQL 환자정보 조회

    get_glucose_readings:
        A파트 FastAPI를 이용한 과거 CGM 혈당 조회

실행 환경:
    5090 GPU 서버 (fitif@server301)

실행 명령:
    cd ~/FITIF-integration/llm_app
    uvicorn main:app --host 127.0.0.1 --port 18002

주의:
    현재는 내부 통합 테스트용 API이다.
    사용자 인증 및 접근 권한 확인이 구현되지 않았으므로
    외부에 공개해서는 안 된다.
"""

import json
import logging
import os
import time

import httpx

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 기존 C파트 환자정보 조회 함수
from patient_tools import get_patient_record

# A파트 FastAPI 연동 함수
from glucose_api import fetch_glucose_from_api


# =========================================================
# 1. 환경설정
# =========================================================

# Ollama API 주소
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://127.0.0.1:11435"
).rstrip("/")

# 사용할 Gemma 모델
MODEL = os.environ.get(
    "LLM_MODEL",
    "gemma4:12b"
)

# 모델이 사용할 최대 컨텍스트 길이
NUM_CTX = int(
    os.environ.get("LLM_NUM_CTX", "8192")
)

# Gemma Thinking 모드
# true / false / 미설정
THINK = os.environ.get(
    "LLM_THINK",
    ""
).strip().lower()

# Tool Calling 최대 왕복 횟수
MAX_STEPS = 4

# Ollama HTTP 요청 제한 시간(초)
TIMEOUT = 120

# 진단·처방 조회 과정의 직접 DB 접근을 허용할지 결정한다.
# 현재는 기존 기능을 보존하기 위해 기본적으로 허용한다.
ENABLE_PATIENT_RECORD_TOOL = True


# =========================================================
# 2. 로그 설정
# =========================================================

# 로그에는 Tool 이름과 실행 성공 여부만 남긴다.
# 환자 개인정보와 혈당 데이터는 출력하지 않는다.
logger = logging.getLogger("fitif.llm")


# =========================================================
# 3. Gemma 시스템 프롬프트
# =========================================================

SYSTEM_PROMPT = """
너는 FITIF 헬스케어 서비스의 건강정보 안내 도우미다.

현재 대화 중인 사용자 번호는 {member_id}번이다.

[기본 규칙]
- 사용자에게 한국어로 알기 쉽게 설명한다.
- 조회하지 않은 의료정보를 추측해서 답변하지 않는다.
- 의료진의 진단이나 처방을 임의로 변경하지 않는다.
- 필요한 경우 의사 또는 약사와 상담하도록 안내한다.

[혈당 조회 규칙]
- 사용자가 혈당 기록을 질문하면 get_glucose_readings 도구를 사용한다.
- 혈당 기록 조회를 위해 get_patient_record를 사용하지 않는다.
- 혈당 결과에는 실제 측정 날짜와 시간, 혈당값을 포함한다.
- 혈당 기록의 measured_at_kst 필드가 한국시간으로 변환된 정확한 시각이다.
- 혈당 측정 시각을 직접 계산하거나 임의로 변경하지 않는다.
- 각 혈당값과 해당 기록의 measured_at_kst를 정확히 일대일로 대응하여 설명한다.
- 혈당 기록은 최신 측정 시각부터 순서대로 설명한다.
- 과거 기록을 현재 혈당이라고 설명하지 않는다.
- 오래된 기록을 '방금', '15분 전'처럼 표현하지 않는다.
- 조회 결과가 없거나 오류가 발생하면 숫자를 추측하지 않는다.
- 도구에서 반환된 값만 사용한다.

[진단 및 처방 조회 규칙]
- 진단, 처방, 약물 변경에 관한 질문에는 get_patient_record를 사용한다.
- 약물 정보를 설명할 때는 확인 가능한 제품명, 성분명,
  함량, 1회 복용량, 하루 횟수, 기간을 전달한다.
- 약물 변경 질문에는 추가, 중단, 용량 변경을 구분한다.
- 확인되지 않은 정보는 임의로 생성하지 않는다.

[답변 작성 규칙]
- 도구 실행 결과가 제공되면 이를 바탕으로 최종 답변을 작성한다.
- 질문과 관련된 정보만 간결하게 전달한다.
- 과거 데이터는 반드시 과거 기록임을 명시한다.
"""


# =========================================================
# 4. Tool 정의
# =========================================================

# Gemma가 사용할 수 있는 함수 목록이다.
#
# 여기서 도구를 정의하는 것만으로
# 실제 Python 함수가 실행되는 것은 아니다.
#
# 모델이 도구 호출을 요청하면
# 아래 run_tool()에서 실제 실행한다.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_glucose_readings",
            "description": (
                "A파트 FastAPI를 통해 사용자의 "
                "과거 CGM 혈당 측정 기록 3건을 조회한다. "
                "혈당값과 정확한 측정 시각을 반환한다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {
                        "type": "integer",
                        "description": "조회할 사용자 번호"
                    }
                },
                "required": ["member_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_patient_record",
            "description": (
                "환자의 진단, 처방 약물, "
                "약물 변경 정보를 조회한다. "
                "혈당 기록만 묻는 질문에는 사용하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {
                        "type": "integer",
                        "description": "조회할 사용자 번호"
                    }
                },
                "required": ["member_id"]
            }
        }
    }
]


# =========================================================
# 5. FastAPI 애플리케이션
# =========================================================

app = FastAPI(
    title="FITIF LLM 추론 API",
    description="Gemma 4 기반 의료정보 Tool Calling API",
    version="0.2.0"
)


# =========================================================
# 6. 요청 및 응답 데이터 형식
# =========================================================

class ChatRequest(BaseModel):
    """
    사용자가 /chat에 전달하는 요청 형식.

    member_id:
        조회할 사용자 번호.

    message:
        사용자의 자연어 질문.
    """

    member_id: int = Field(
        ...,
        ge=1,
        description="환자 번호"
    )

    message: str = Field(
        ...,
        min_length=1,
        description="사용자 질문"
    )


class ChatResponse(BaseModel):
    """
    /chat API 응답 형식.

    answer:
        Gemma의 자연어 답변.

    tool_calls:
        실행한 Tool의 이름 및 상태 기록.

    model:
        사용한 LLM 모델.

    elapsed_ms:
        전체 처리 시간(ms).
    """

    answer: str
    tool_calls: list
    model: str
    elapsed_ms: int


# =========================================================
# 7. 실제 Tool 실행 함수
# =========================================================

def run_tool(name: str, member_id: int) -> dict:
    """
    Gemma가 요청한 도구를 실제 실행한다.

    매개변수:
        name:
            실행할 도구 이름.

        member_id:
            요청에서 받은 사용자 번호.

    보안:
        LLM이 만들어 낸 member_id를 사용하지 않는다.

        단, 현재 ChatRequest의 member_id 자체는
        인증된 사용자 ID가 아니므로,
        운영 환경에서는 인증·인가가 반드시 필요하다.
    """

    # ---------------------------------------------
    # A파트 FastAPI 혈당 조회
    # ---------------------------------------------

    if name == "get_glucose_readings":

        try:
            # 별도 작성된 glucose_api.py 호출
            # 5090 → SSH 터널 → 3060 FastAPI
            result = fetch_glucose_from_api(
                member_id=member_id,
                limit=3
            )

            return result

        except (ValueError, RuntimeError):
            logger.warning(
                "glucose API tool failed"
            )

            return {
                "status": "error",
                "message": "혈당 조회 서비스에 연결할 수 없습니다."
            }

    # ---------------------------------------------
    # 기존 C파트 환자정보 조회
    # ---------------------------------------------

    if name == "get_patient_record":

        if not ENABLE_PATIENT_RECORD_TOOL:
            return {
                "status": "error",
                "message": "환자정보 조회 기능을 사용할 수 없습니다."
            }

        try:
            return get_patient_record(member_id)

        except ValueError:
            logger.warning(
                "patient record tool failed"
            )

            return {
                "status": "error",
                "message": "환자정보 조회에 실패했습니다."
            }

    # ---------------------------------------------
    # 알 수 없는 도구
    # ---------------------------------------------

    return {
        "status": "error",
        "message": "지원하지 않는 도구입니다."
    }


# =========================================================
# 8. Ollama API 호출 함수
# =========================================================

def call_ollama(
    client: httpx.Client,
    messages: list,
    enable_tools: bool = True
) -> dict:
    """
    Ollama의 Gemma 모델에 대화 내용을 전달한다.

    매개변수:
        client:
            HTTP 연결을 관리하는 httpx 객체.

        messages:
            시스템 프롬프트, 사용자 질문,
            Tool 호출 기록 등이 들어 있는 대화 목록.

        enable_tools:
            True:
                Gemma에게 Tool 목록을 전달한다.

            False:
                Tool 목록을 전달하지 않는다.
                조회가 끝났으므로 최종 답변 작성을 요청한다.

    반환값:
        Ollama 응답의 message 딕셔너리.
    """

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": messages,
        "options": {
            "num_ctx": NUM_CTX
        }
    }

    # 초기 질문 단계에서만 Tool 정의를 전달한다.
    if enable_tools:
        payload["tools"] = TOOLS

    # Thinking 설정이 명시된 경우 적용한다.
    if THINK in ("true", "false"):
        payload["think"] = THINK == "true"

    try:
        response = client.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload
        )

        response.raise_for_status()

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Gemma 모델 응답 시간이 초과되었습니다."
        ) from exc

    except httpx.HTTPError as exc:
        logger.warning(
            "Ollama HTTP request failed: %s",
            type(exc).__name__
        )

        raise HTTPException(
            status_code=502,
            detail="Gemma 모델 서버와 통신하지 못했습니다."
        ) from exc

    # Ollama 응답을 JSON으로 변환한다.
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Ollama 응답이 올바른 JSON 형식이 아닙니다."
        ) from exc

    message = data.get("message")

    if not isinstance(message, dict):
        raise HTTPException(
            status_code=502,
            detail="Ollama 응답에 message가 없습니다."
        )

    return message


# =========================================================
# 9. 서버 상태 확인 API
# =========================================================

@app.get("/health")
def health():
    """
    C파트 FastAPI와 Ollama 연결 상태를 확인한다.

    주의:
        Gemma 모델 존재 여부까지 확인하지만
        A파트 DB 접근까지 검증하는 API는 아니다.
    """

    try:
        response = httpx.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )

        response.raise_for_status()

        data = response.json()

        names = [
            item.get("name")
            for item in data.get("models", [])
        ]

    except (httpx.HTTPError, ValueError):
        return {
            "api": "ok",
            "ollama": "연결 안 됨",
            "ollama_url": OLLAMA_URL,
            "model": MODEL
        }

    return {
        "api": "ok",
        "ollama": "ok",
        "ollama_url": OLLAMA_URL,
        "model": MODEL,
        "model_available": MODEL in names
    }


# =========================================================
# 10. 사용자 질문 처리 API
# =========================================================

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    사용자 질문을 Gemma에 전달하고 최종 답변을 반환한다.

    처리 순서:
        1. 질문과 시스템 프롬프트 생성
        2. Gemma에 Tool 목록을 전달
        3. 모델이 Tool을 선택하면 Python이 실행
        4. Tool 결과를 대화 기록에 추가
        5. 도구 목록 없이 Gemma에 최종 답변 요청
        6. 자연어 답변 반환

    이번 통합 테스트에서는 Tool을 한 번 선택한 뒤
    그 결과로 최종 답변을 생성하도록 구성한다.
    """

    # 요청 시작 시간 기록
    start = time.monotonic()

    # ---------------------------------------------
    # 10-1. 대화 기록 초기화
    # ---------------------------------------------

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                member_id=req.member_id
            )
        },
        {
            "role": "user",
            "content": req.message
        }
    ]

    # 실제 호출한 Tool의 메타데이터
    calls = []

    # HTTP 연결을 하나의 요청 처리 과정에서 재사용한다.
    with httpx.Client(timeout=TIMEOUT) as client:

        # -----------------------------------------
        # 10-2. Gemma에게 Tool 선택 요청
        # -----------------------------------------

        msg = call_ollama(
            client=client,
            messages=messages,
            enable_tools=True
        )

        requested = msg.get("tool_calls") or []

        # -----------------------------------------
        # 10-3. 모델이 Tool을 요청하지 않은 경우
        # -----------------------------------------

        if not requested:

            answer = (
                msg.get("content") or ""
            ).strip()

            return ChatResponse(
                answer=answer,
                tool_calls=[],
                model=MODEL,
                elapsed_ms=int(
                    (time.monotonic() - start) * 1000
                )
            )

        # -----------------------------------------
        # 10-4. Tool 호출 요청을 대화 기록에 저장
        # -----------------------------------------

        # 이 부분이 기존 코드에서 누락되었던 부분이다.
        #
        # Gemma가 도구를 호출한 사실을 저장해야
        # 다음 응답에서 Tool 결과를 이해할 수 있다.

        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": requested
        })

        # -----------------------------------------
        # 10-5. Gemma가 선택한 Tool 실행
        # -----------------------------------------

        # 여러 Tool을 요청했다면 순서대로 처리한다.
        # 다만 동일한 Tool을 반복 요청했을 때
        # 불필요한 DB 조회가 발생하지 않도록 한다.

        executed_names = set()

        for tc in requested:

            fn = tc.get("function") or {}

            name = fn.get("name")

            # Tool 이름이 없으면 실행하지 않는다.
            if not isinstance(name, str) or not name:
                raise HTTPException(
                    status_code=502,
                    detail="모델이 잘못된 Tool 호출을 생성했습니다."
                )

            # 동일한 도구가 한 번의 응답에서
            # 중복 요청되면 기존 결과를 재사용한다.
            if name in executed_names:
                result = next(
                    item["result"]
                    for item in executed_results
                    if item["name"] == name
                )
            else:
                result = run_tool(
                    name=name,
                    member_id=req.member_id
                )

                executed_names.add(name)

                # 처음 실행한 결과만 저장한다.
                if "executed_results" not in locals():
                    executed_results = []

                executed_results.append({
                    "name": name,
                    "result": result
                })

            # 개인정보는 출력하지 않고
            # 도구명 및 결과 상태만 로그에 남긴다.
            logger.info(
                "Tool executed: %s, status=%s",
                name,
                result.get("status", "unknown")
            )

            # 실제 Tool 실행 이력
            calls.append({
                "name": name,
                "model_arguments": fn.get("arguments") or {},
                "used_member_id": req.member_id,
                "status": result.get("status")
            })

            # Ollama Tool 응답 형식으로 추가
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(
                    result,
                    ensure_ascii=False,
                    default=str
                )
            })

        # -----------------------------------------
        # 10-6. Gemma에 최종 답변 생성 요청
        # -----------------------------------------

        # 앞선 단계에서 필요한 정보를 조회했으므로
        # 이번 요청에는 Tool 목록을 전달하지 않는다.
        #
        # 이를 통해 모델이 같은 Tool을 반복 호출하는
        # 문제를 방지한다.
        #
        # 주의:
        # 이는 단일 Tool 호출 중심의 MVP 설계이며,
        # 여러 단계의 연쇄 Tool Calling은 추후 구현한다.

        final_msg = call_ollama(
            client=client,
            messages=messages,
            enable_tools=False
        )

        # -----------------------------------------
        # 10-7. 최종 답변 검증
        # -----------------------------------------

        answer = (
            final_msg.get("content") or ""
        ).strip()

        # Ollama가 최종 단계에서도 Tool을 요청하거나
        # 빈 응답을 반환하면 정상 완료로 처리하지 않는다.
        if final_msg.get("tool_calls") or not answer:
            raise HTTPException(
                status_code=502,
                detail="Gemma가 최종 답변을 생성하지 못했습니다."
            )

        # -----------------------------------------
        # 10-8. 최종 응답 반환
        # -----------------------------------------

        return ChatResponse(
            answer=answer,
            tool_calls=calls,
            model=MODEL,
            elapsed_ms=int(
                (time.monotonic() - start) * 1000
            )
        )
