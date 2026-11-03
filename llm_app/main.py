"""환자 질문 추론 API (FastAPI).

흐름
  1. Streamlit 등이 POST /chat 으로 member_id 와 질문을 보낸다.
  2. 이 서버가 Ollama(Gemma)에 질문과 툴 목록을 보낸다.
  3. 모델이 툴 호출을 요청하면 이 서버가 대신 실행하고 결과를 모델에 돌려준다.
  4. 모델이 최종 답을 쓰면 답만 돌려준다 (thinking 은 버린다).

설정은 환경변수로 바꾼다.
  OLLAMA_URL    기본 http://127.0.0.1:11435  (SSH 터널로 서버 Ollama에 연결)
  LLM_MODEL     기본 gemma4:12b  (부담되면 E4B 등으로 교체)
  LLM_NUM_CTX   기본 8192  (컨텍스트 길이. 크면 GPU 메모리를 많이 씀)
  LLM_THINK     기본 비움(모델 기본값). true / false 로 생각 모드를 켜고 끔
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD  PostgreSQL 접속 정보 (patient_tools.py 가 읽음)
실행 (llm_app 폴더에서)
  uvicorn main:app --port 8001
"""
import json
import os
import time
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from patient_tools import get_patient_record

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
MODEL = os.environ.get("LLM_MODEL", "gemma4:12b")
NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "8192"))
THINK = os.environ.get("LLM_THINK", "").strip().lower()  # "", "true", "false"
MAX_STEPS = 4      # 툴 호출 왕복 최대 횟수
TIMEOUT = 120      # Ollama 응답 대기(초)

SYSTEM_PROMPT = """너는 환자의 복약과 건강 기록을 읽고 질문에 답하는 도우미다.
지금 대화 중인 환자의 번호는 {member_id}번이다.

규칙
- 환자 기록이 필요하면 get_patient_record 툴로 조회한다. 기록에 없는 내용은 지어내지 말고 없다고 말한다.
- 약은 제품명, 주성분, 함량, 1회 투여량, 하루 횟수, 기간을 함께 말한다.
- 약 변화를 물으면 추가, 중단, 용량 변경을 말하고, 변화 없이 유지된 약이 몇 개인지(unchanged_count)도 함께 말한다.
- 혈당은 값과 함께 측정 시점을 "N분 전"으로 반드시 말한다(minutes_ago 값 사용). 예) "15분 전에 측정한 혈당은 142mg/dL입니다." freshness 가 old 이면 "45분 전 값이라 지금과 다를 수 있습니다"처럼 시점이 지났음을 덧붙인다. unavailable 이면 "최근 혈당 기록이 없습니다"라고만 말하고 숫자를 추측하지 않는다.
- 진단이나 처방 변경은 하지 않는다. 판단이 필요한 내용은 의사나 약사와 상담하라고 안내한다.
- 한국어로 알기 쉽게 답한다. 길게 늘이지 말되, 위 규칙에서 말하라고 한 정보는 빠뜨리지 않는다."""

# TOOLS 는 Ollama 모델이 호출할 수 있는 함수 목록(매뉴판같은)이다. 모델이 요청하면 run_tool()에서 실행한다.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_patient_record",
            "description": "환자의 진단, 처방(약), 약 변화, 최근 혈당을 한 번에 조회한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "integer", "description": "환자 번호"},
                }, #"parameters" 내용은 jsonschema 표준 형식
                "required": ["member_id"],
            },
        },
    },
]

app = FastAPI(title="FITIF LLM 추론 API")

#서버 API의 입구
class ChatRequest(BaseModel):
    member_id: int = Field(..., description="환자 번호")
    message: str = Field(..., min_length=1, description="사용자 질문")

#서버 API의 출구 돌아온 답변
class ChatResponse(BaseModel):
    answer: str
    tool_calls: list
    model: str
    elapsed_ms: int


def run_tool(name: str, member_id: int) -> dict:
    """모델이 요청한 툴을 실행한다.

    member_id 는 모델이 넘긴 값을 쓰지 않고 요청에 들어온 값으로 고정한다.
    모델이 다른 환자 번호를 넣어도 다른 사람 기록이 조회되지 않게 하려는 것이다.
    """
    if name == "get_patient_record":
        try:
            return get_patient_record(member_id)
        except ValueError as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": f"알 수 없는 툴: {name}"}


def call_ollama(client: httpx.Client, messages: list) -> dict:
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": messages,
        "tools": TOOLS,
        "options": {"num_ctx": NUM_CTX},
    }
    if THINK in ("true", "false"):
        payload["think"] = THINK == "true"
    try:
        r = client.post(f"{OLLAMA_URL}/api/chat", json=payload) #ollama가 정한 주소
        r.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(502, f"Ollama에 연결할 수 없음: {OLLAMA_URL} (SSH 터널과 서버 Ollama 확인)")
    except httpx.TimeoutException:
        raise HTTPException(504, "Ollama 응답 시간 초과")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Ollama 오류: {e.response.text[:300]}")
    return r.json()["message"]

# r.json()["message"] 의 모양 

# r.json() = {
#     "model": "gemma4:12b",
#     "message": {                                              ← call_ollama가 이 칸만 꺼내 돌려줌 (chat에서는 msg)
#         "role": "assistant",
#         "content": "",
#         "tool_calls": [                                        ← 이 목록이 requested
#             {"function": {"name": "get_patient_record",
#                           "arguments": {"member_id": 1}}}
#         ],
#     },
#     ... 그 밖의 칸들 (버전에 따라 다름)
# }
# Ollama의 /api/chat 응답에는 message 외에 
# 모델 이름, 생성 시각, 완료 여부, 걸린 시간, 처리한 토큰 수 같은 칸들이 보통 들어 있다. 
# 다만 정확한 칸 이름과 구성은 버전에 따라 다르다

@app.get("/health")     #우리 서버 /health 로 접속
def health():
    """서버와 Ollama 연결, 모델 존재 여부를 확인한다."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)  #ollama에게 직접 물어봄
        names = [m["name"] for m in r.json().get("models", [])] #예시 names = ["gemma4:12b", "다른모델:태그"]
    except httpx.HTTPError:
        return {"api": "ok", "ollama": "연결 안 됨", "ollama_url": OLLAMA_URL, "model": MODEL}
    return {
        "api": "ok",
        "ollama": "ok",
        "ollama_url": OLLAMA_URL,
        "model": MODEL,
        "model_available": MODEL in names,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.time()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(member_id=req.member_id)},
        {"role": "user", "content": req.message}, #req에는 ChatRequest 양식에 맞게 검사를 통과한 요청이 들어온다
    ]
    calls = []

    with httpx.Client(timeout=TIMEOUT) as client:
        for _ in range(MAX_STEPS):
            msg = call_ollama(client, messages)
            requested = msg.get("tool_calls") or []

            if not requested:
                return ChatResponse(
                    answer=(msg.get("content") or "").strip(),
                    tool_calls=calls,
                    model=MODEL,
                    elapsed_ms=int((time.time() - start) * 1000),
                )

            # 모델의 툴 요청을 대화에 남기고, 실행 결과를 tool 메시지로 돌려준다.
            # Ollama가 돌려주는 요청의 모양 (실제 응답은 print(requested)로 확인):
            #   requested = [{"function": {"name": "get_patient_record",
            #                              "arguments": {"member_id": 1}}}]          
            for tc in requested:
                fn = tc["function"]
                name = fn["name"]
                result = run_tool(name, req.member_id)
                calls.append({
                    "name": name,
                    "model_arguments": fn.get("arguments") or {},
                    "used_member_id": req.member_id,
                    "status": result.get("status"),
                })
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

    raise HTTPException(502, "툴 호출이 너무 많이 반복되어 중단함")
