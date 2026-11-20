"""로그인한 사용자의 이미지 OCR 요청을 5090 서버로 전달한다."""

import os
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request as UpstreamRequest, build_opener

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from .auth import get_current_member
from .document_records import router as document_records_router

router = APIRouter(prefix="/api/documents", tags=["Document OCR"])
router.include_router(document_records_router)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
OCR_SERVICE_URL = "http://127.0.0.1:18501/ocr"
ocr_client = build_opener(ProxyHandler({}))


def request_ocr(image: bytes, content_type: str, token: str) -> Response:
    upstream = UpstreamRequest(
        OCR_SERVICE_URL,
        data=image,
        headers={
            "Content-Type": content_type,
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with ocr_client.open(upstream, timeout=155) as result:
            return Response(
                result.read(),
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )
    except HTTPError as error:
        with error:
            # 사용자에게 조치 가능한 오류만 전달한다.
            if error.code in {413, 415, 422, 429, 504}:
                return Response(
                    error.read(), status_code=error.code, media_type="application/json"
                )
        raise HTTPException(502, "OCR 서버에서 인식에 실패했어요.") from error
    except TimeoutError as error:
        raise HTTPException(504, "OCR 응답 시간이 초과됐어요.") from error
    except (URLError, OSError) as error:
        raise HTTPException(503, "OCR 서버에 연결할 수 없어요.") from error


@router.post("/ocr", dependencies=[Depends(get_current_member)])
async def recognize_document(request: Request) -> Response:
    token = os.getenv("FITIF_OCR_SERVICE_TOKEN")
    if not token:
        raise HTTPException(503, "OCR 서버 연결이 설정되지 않았어요.")

    content_type = request.headers.get("content-type", "")
    if content_type not in IMAGE_TYPES:
        raise HTTPException(415, "JPG, PNG, WebP 이미지를 선택해 주세요.")

    image = bytearray()
    async for chunk in request.stream():
        if len(image) + len(chunk) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "10MB 이하의 이미지를 선택해 주세요.")
        image.extend(chunk)
    if not image:
        raise HTTPException(422, "이미지 파일이 비어 있어요.")

    # SSH 터널을 통한 동기 HTTP 호출은 이벤트 루프 밖에서 실행한다.
    return await run_in_threadpool(request_ocr, bytes(image), content_type, token)
