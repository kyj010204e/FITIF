"""로그인한 FITIF 사용자의 대화를 환경변수로 지정한 Gemma에 전달한다."""

import json
import os
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .auth import get_current_member

router = APIRouter(prefix="/api/chat", tags=["Gemma chat"])
ollama = build_opener(ProxyHandler({}))
SYSTEM_MESSAGE = (
    "너는 FITIF의 한국어 음성 대화 도우미야. 음성으로 듣기 쉽게 짧은 문장으로 답해. "
    "사용자의 의료기록에 접근했다고 주장하지 마. 진단하거나 약의 시작, 중단, 용량 변경을 지시하지 마."
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2500)]


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=11)]


def ollama_endpoint() -> str:
    base = os.environ.get("FITIF_OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        candidate = urlsplit(base)
        if (
            candidate.scheme == "http" and candidate.hostname in {"127.0.0.1", "localhost", "::1"}
            and not candidate.username and not candidate.password
            and candidate.path in {"", "/"} and not candidate.query and not candidate.fragment
            and candidate.port is not None
        ):
            return base.rstrip("/") + "/api/chat"
    except ValueError:
        pass
    raise HTTPException(503, "Gemma 연결 설정을 확인해 주세요.")


@router.post("", dependencies=[Depends(get_current_member)])
def chat(payload: ChatInput, response: Response) -> dict[str, str]:
    if payload.messages[-1].role != "user":
        raise HTTPException(422, "마지막 메시지는 질문이어야 해요.")
    model = os.environ.get("FITIF_GEMMA_MODEL", "").strip()
    if not model:
        raise HTTPException(503, "3060 백엔드에 Gemma 모델 이름을 설정해 주세요.")

    # 모델 서버는 로컬 주소 또는 루프백 SSH 터널로 연결한다.
    incoming = [{"role": "system", "content": SYSTEM_MESSAGE}]
    incoming.extend(message.model_dump() for message in payload.messages)
    body = {
        "model": model,
        "messages": incoming,
        "stream": False,
        "think": False,
        "keep_alive": 0,
        "options": {"num_ctx": 4096, "num_predict": 512},
    }
    request = Request(
        ollama_endpoint(),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with ollama.open(request, timeout=120) as result:
            data = json.load(result)
    except HTTPError as error:
        with error:
            if error.code == 404:
                raise HTTPException(503, "설정한 Gemma 모델을 Ollama에서 찾지 못했어요.") from None
        raise HTTPException(502, "Gemma가 답변을 생성하지 못했어요. Ollama 서버 로그를 확인해 주세요.") from None
    except TimeoutError:
        raise HTTPException(504, "Gemma 응답 시간이 초과됐어요.") from None
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise HTTPException(504, "Gemma 응답 시간이 초과됐어요.") from None
        raise HTTPException(503, "Gemma 서버에 연결할 수 없어요.") from None
    except OSError:
        raise HTTPException(503, "Gemma 서버에 연결할 수 없어요.") from None
    except ValueError:
        raise HTTPException(502, "Gemma 응답을 읽을 수 없어요.") from None

    message = data.get("message") if isinstance(data, dict) else None
    answer = message.get("content") if isinstance(message, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(502, "Gemma가 빈 답변을 보냈어요. 다시 시도해 주세요.")
    response.headers["Cache-Control"] = "no-store"
    return {"answer": answer.strip()}
