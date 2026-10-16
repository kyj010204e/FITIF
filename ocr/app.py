from scripts.export_final_db_json import build_final_payload
import copy
import hashlib
import json
import subprocess
import sys
import uuid
from io import BytesIO
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

from scripts.image_quality_v3 import analyze_bytes as analyze_iqa
from scripts.extract_visit_date import extract_date_candidates
from scripts.iqa_preview import create_iqa_preview

from scripts.document_renderer import (
    parse_ocr_document,
    export_confirmed,
)

ROOT = Path(__file__).resolve().parent

INPUT_DIR = ROOT / "inputs/real"
JSON_DIR = ROOT / "outputs/json"
CONFIRMED_DIR = ROOT / "outputs/confirmed"
FRONTEND_DIR = ROOT / "frontend/document_editor"

for directory in (INPUT_DIR, JSON_DIR, CONFIRMED_DIR):
    directory.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="FITIF OCR",
    page_icon="📄",
    layout="wide",
)

# HTML/JS 편집 컴포넌트 등록
document_editor = components.declare_component(
    "fitif_document_editor",
    path=str(FRONTEND_DIR),
)


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_ocr(image_bytes, timeout):
    job_id = uuid.uuid4().hex[:12]
    input_path = INPUT_DIR / f"{job_id}.png"
    input_path.write_bytes(image_bytes)

    command = [
        sys.executable,
        str(ROOT / "scripts/process_image.py"),
        "--input", str(input_path),
        "--device", "gpu:0",
        "--timeout", str(int(timeout)),
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=int(timeout) + 90,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"OCR 실행 실패 (종료 코드: {result.returncode}). "
            "서버의 OCR 실행 기록을 확인해 주세요."
        )

    raw_path = JSON_DIR / f"{job_id}.json"

    if not raw_path.exists():
        raise RuntimeError("OCR 결과 JSON이 생성되지 않았습니다.")

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    document = parse_ocr_document(raw)

    return job_id, document


st.title("FITIF OCR")
st.caption("이미지 업로드 → 전자문서 재구성 → 직접 수정 → JSON 확정")

uploaded = st.file_uploader(
    "문서 이미지 업로드",
    type=["png", "jpg", "jpeg", "webp"],
)

if uploaded is None:
    st.info("이미지를 업로드해 주세요.")
    st.stop()

uploaded_bytes = uploaded.getvalue()
file_hash = hashlib.sha256(uploaded_bytes).hexdigest()

if st.session_state.get("file_hash") != file_hash:
    st.session_state["file_hash"] = file_hash

    for key in ("job_id", "document", "confirmed"):
        st.session_state.pop(key, None)

try:
    with Image.open(BytesIO(uploaded_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
except Exception:
    st.error("유효하지 않은 이미지입니다.")
    st.stop()


# FITIF_IQA_V3_BEGIN

@st.cache_data(show_spinner=False, max_entries=16)
def evaluate_quality(data: bytes):
    return analyze_iqa(data)


if "document" not in st.session_state:
    st.subheader("이미지 품질 검사")

    try:
        quality_result = evaluate_quality(uploaded_bytes)

        labels = {
            "LOW_RESOLUTION": "이미지 해상도가 낮습니다.",
            "EXTREMELY_LOW_RESOLUTION": "이미지 크기가 지나치게 작습니다.",
            "POSSIBLE_BLUR": "이미지가 흐릴 가능성이 있습니다.",
            "POSSIBLE_LOCAL_BLUR": "일부 영역이 흐릴 가능성이 있습니다.",
            "TOO_DARK": "이미지가 어둡습니다.",
            "LOW_CONTRAST": "명암 대비가 부족합니다.",
            "UNEVEN_ILLUMINATION": "조명이 고르지 않거나 그림자가 있을 수 있습니다.",
            "POSSIBLE_OVEREXPOSURE": "빛이 강해 글자가 희미할 수 있습니다.",
        }

        if quality_result["status"] == "PASS":
            st.success("이미지 품질 검사 통과")

        else:
            st.warning(
                "이미지 품질을 확인해 주세요. "
                "인식 정확도가 떨어질 수 있습니다."
            )

            for reason in quality_result["reasons"]:
                st.write("• " + labels.get(reason, reason))

        blur = quality_result.get("local_blur_v3", {})

        if blur.get("detected"):
            with st.expander(
                "부분 흐림 의심 영역 확인",
                expanded=True,
            ):
                preview = create_iqa_preview(
                    uploaded_bytes,
                    quality_result,
                )

                st.image(
                    preview,
                    caption="빨간색은 부분 흐림 의심 영역입니다.",
                    width=460,
                )

        with st.expander("품질 분석 수치"):
            st.json(quality_result["metrics"])

        st.caption(
            "품질 검사는 실험 단계입니다. "
            "WARNING이어도 OCR을 진행할 수 있습니다."
        )

    except Exception as exc:
        st.warning("품질 검사를 완료하지 못했습니다.")
        print(
            f"[IQA ERROR] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

# FITIF_IQA_V3_END


if "document" not in st.session_state:
    st.image(
        image,
        caption="업로드 문서",
        width=420,
    )

    timeout = st.number_input(
        "OCR 실행 제한 시간",
        min_value=30,
        max_value=600,
        value=120,
        step=30,
    )

    if st.button("OCR 실행", type="primary"):
        try:
            buffer = BytesIO()
            image.save(buffer, format="PNG")

            with st.spinner("문서 인식 중..."):
                job_id, document = run_ocr(
                    buffer.getvalue(),
                    int(timeout),
                )

            st.session_state["job_id"] = job_id
            st.session_state["document"] = document
            st.rerun()

        except Exception as exc:
            st.error(str(exc))

    st.stop()


job_id = st.session_state["job_id"]

if "confirmed" in st.session_state:
    st.success("문서 내용 확인이 완료됐습니다.")

    confirmed = st.session_state["confirmed"]

    st.download_button(
        "확정 JSON 다운로드",
        data=json.dumps(
            confirmed,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
        file_name=f"{job_id}_confirmed.json",
        mime="application/json",
        use_container_width=True,
    )


    st.divider()
    st.subheader("진료일 확인")

    candidates = extract_date_candidates(confirmed)
    dates = [item["date"] for item in candidates]

    if dates:
        st.info("문서에서 날짜 후보를 발견했습니다. 진료일을 확인해 주세요.")
        options = ["직접 입력"] + dates
        selection = st.selectbox(
            "진료일 후보",
            options,
            index=1,
        )
        default_date = selection if selection != "직접 입력" else None
    else:
        st.warning(
            "문서에서 진료일을 찾지 못했습니다. "
            "진료일을 직접 입력해 주세요."
        )
        default_date = None

    from datetime import date as Date

    visit_date = st.date_input(
        "진료일",
        value=Date.fromisoformat(default_date) if default_date else None,
        min_value=Date(1900, 1, 1),
        max_value=Date.today(),
        format="YYYY-MM-DD",
    )

    if st.button("진료일 확정", type="primary"):
        if visit_date is None:
            st.error("진료일을 입력해 주세요.")
        else:
            st.session_state["visit_date_confirmed"] = (
                visit_date.isoformat()
            )
            st.success("진료일 확정 완료")

    if st.session_state.get("visit_date_confirmed"):
        st.write(
            "확정 진료일:",
            st.session_state["visit_date_confirmed"],
        )


    # FITIF_FINAL_DB_JSON_BEGIN
    st.divider()
    st.subheader("최종 DB 저장용 JSON")

    visit_date = st.session_state.get("visit_date_confirmed")

    if visit_date:
        try:
            final_payload = build_final_payload(
                job_id=job_id,
                visit_date=visit_date,
            )

            final_json = json.dumps(
                final_payload,
                ensure_ascii=False,
                indent=2,
            )

            st.success("DB 저장용 JSON 생성 완료")

            st.download_button(
                "최종 DB JSON 다운로드",
                data=final_json,
                file_name=f"{job_id}_final.json",
                mime="application/json",
                use_container_width=True,
            )

            with st.expander("최종 DB JSON 미리보기"):
                st.json(final_payload)

        except Exception as exc:
            st.error(f"DB JSON 생성 실패: {exc}")

    else:
        st.info("진료일을 먼저 확정해 주세요.")
    # FITIF_FINAL_DB_JSON_END

    with st.expander("확정 JSON 미리보기"):
        st.json(confirmed)

else:
    with st.expander("원본 이미지 비교하기"):
        st.image(image, use_container_width=True)

    st.info(
        "아래 문서는 OCR 결과로 재구성됐습니다. "
        "잘못된 글자나 셀을 클릭해서 수정한 다음 확인해 주세요."
    )

    response = document_editor(
        document=st.session_state["document"],
        job_id=job_id,
        key=f"editor_{job_id}",
        default=None,
    )

    if isinstance(response, dict) and response.get("confirmed"):
        edited_document = response.get("document")

        # 반환 데이터의 기본 구조 확인
        if not (
            isinstance(edited_document, dict)
            and isinstance(edited_document.get("pages"), list)
        ):
            st.error("편집 결과 구조가 올바르지 않습니다.")
            st.stop()

        # 문서 내용이 실제로 반영되도록
        # 브라우저에서 반환한 편집 데이터를 사용
        final = export_confirmed(
            copy.deepcopy(edited_document)
        )

        save_json(
            CONFIRMED_DIR / f"{job_id}.json",
            final,
        )

        st.session_state["confirmed"] = final
        st.rerun()

    st.caption(
        "빨간색 표시는 규칙 기반 검토 권장 항목이며 "
        "실제 OCR 신뢰도 점수는 아닙니다. "
        "확정 JSON은 서버에 저장되고, DB 연동은 추후 진행합니다."
    )
