"""검수한 의료문서와 진단·처방을 로그인한 회원의 기록으로 저장한다."""

import json
import logging
from contextlib import closing
from datetime import date, datetime
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ..database import get_connection, get_write_connection
from .auth import get_current_member

router = APIRouter(prefix="/records", tags=["Reviewed medical documents"])
logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

CellText = Annotated[str, StringConstraints(max_length=20000)]
DosingText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Span = Annotated[int, Field(ge=1, le=1000)]


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cell(RecordInput):
    text: CellText
    colspan: Span = 1
    rowspan: Span = 1
    header: bool = False


class TextBlock(RecordInput):
    type: Literal["text"]
    text: CellText


class TableBlock(RecordInput):
    type: Literal["table"]
    rows: Annotated[list[Annotated[list[Cell], Field(max_length=250)]], Field(max_length=500)]


class Page(RecordInput):
    page: Annotated[int, Field(ge=1)]
    contents: Annotated[list[Annotated[TextBlock | TableBlock, Field(discriminator="type")]], Field(max_length=500)]


class ReviewedDocument(RecordInput):
    pages: Annotated[list[Page], Field(min_length=1, max_length=25)]


class DrugInput(RecordInput):
    edi_code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{9}$")]
    dose: DosingText
    frequency: DosingText
    duration_days: Annotated[int, Field(strict=True, gt=0, le=32767)]


class SaveDocument(RecordInput):
    document_id: UUID
    visit_date: date
    document_type: Literal["prescription", "diagnosis_certificate"]
    document: ReviewedDocument
    diagnoses: Annotated[list[Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{2}(?:\.?[0-9A-Z]{1,4})?$")]], Field(max_length=100)]
    prescriptions: Annotated[list[DrugInput], Field(max_length=100)]

    @field_validator("visit_date")
    @classmethod
    def check_visit_date(cls, value: date) -> date:
        if not date(1900, 1, 1) <= value <= datetime.now(KST).date():
            raise ValueError("진료일을 확인해 주세요.")
        return value


def get_catalog_id(cur, kind: str, code: str, visit_date: date) -> int:
    # 확정된 분류 코드만 연결한다. 이름이 비슷한 약품을 추측해 연결하지 않는다.
    if kind == "diagnosis":
        cur.execute(
            """
            SELECT disease_id FROM public.disease
            WHERE upper(replace(icd_code, '.', '')) = %s
            LIMIT 2
            """,
            (code.replace(".", ""),),
        )
    else:
        cur.execute(
            """
            SELECT drug_id FROM public.drug
            WHERE edi_code = %s
              AND (valid_from IS NULL OR valid_from <= %s)
              AND (valid_to IS NULL OR valid_to >= %s)
            LIMIT 2
            """,
            (code, visit_date, visit_date),
        )
    rows = cur.fetchall()
    if len(rows) != 1:
        label = "진단 코드" if kind == "diagnosis" else "약품 EDI 코드"
        reason = "등록된 항목이 없어요" if not rows else "일치하는 항목이 여러 개예요"
        raise HTTPException(422, f"{label} {code}에 {reason}. 코드와 진료일을 확인해 주세요.")
    return rows[0][0]


def store_document(cur, member_id: int, payload: SaveDocument) -> dict:
    data = payload.model_dump(mode="json")
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > 1024 * 1024:
        raise HTTPException(413, "저장할 전자문서가 너무 커요.")
    request_hash = sha256(serialized.encode("utf-8")).hexdigest()
    document_id = str(payload.document_id)
    cur.execute(
        """
        INSERT INTO public.ocr_reviewed_document
            (member_id, document_id, visit_date, document_type, document, request_sha256)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (member_id, document_id) DO NOTHING
        RETURNING document_id
        """,
        (member_id, document_id, payload.visit_date, payload.document_type, Json(data["document"]), request_hash),
    )
    if cur.fetchone() is None:
        # 같은 요청을 다시 보내도 진료·진단·처방이 중복 생성되지 않는다.
        cur.execute(
            """
            SELECT request_sha256, encounter_id FROM public.ocr_reviewed_document
            WHERE member_id = %s AND document_id = %s
            """,
            (member_id, document_id),
        )
        saved_hash, encounter_id = cur.fetchone()
        if saved_hash != request_hash:
            raise HTTPException(409, "이 문서 ID로 이미 다른 내용이 저장됐어요. 저장된 문서를 확인해 주세요.")
        return {"document_id": document_id, "encounter_id": encounter_id}

    # 문서만 저장하는 경우, AI의 최신 진료 조회에 빈 방문을 생성하지 않는다.
    if not payload.diagnoses and not payload.prescriptions:
        return {"document_id": document_id, "encounter_id": None}

    diagnosis_ids = {
        get_catalog_id(cur, "diagnosis", code, payload.visit_date)
        for code in dict.fromkeys(code.replace(".", "") for code in payload.diagnoses)
    }
    prescriptions = [
        (get_catalog_id(cur, "drug", item.edi_code, payload.visit_date), item)
        for item in payload.prescriptions
    ]
    cur.execute(
        """
        INSERT INTO public.encounter (member_id, visit_date, source_type)
        VALUES (%s, %s, 'uploaded_document') RETURNING encounter_id
        """,
        (member_id, payload.visit_date),
    )
    encounter_id = cur.fetchone()[0]
    for disease_id in sorted(diagnosis_ids):
        cur.execute(
            "INSERT INTO public.diagnosis (encounter_id, disease_id, diagnosed_date) VALUES (%s, %s, %s)",
            (encounter_id, disease_id, payload.visit_date),
        )
    for drug_id, item in prescriptions:
        cur.execute(
            """
            INSERT INTO public.prescription (encounter_id, drug_id, dose, frequency, duration_days)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (encounter_id, drug_id, item.dose, item.frequency, item.duration_days),
        )
    cur.execute(
        """
        UPDATE public.ocr_reviewed_document SET encounter_id = %s
        WHERE member_id = %s AND document_id = %s
        """,
        (encounter_id, member_id, document_id),
    )
    return {"document_id": document_id, "encounter_id": encounter_id}


def database_error(error):
    # DB 오류 메시지에는 의료정보가 있을 수 있어 상태 코드만 기록한다.
    logger.error("Reviewed document database operation failed (SQLSTATE %s)", error.pgcode)
    return HTTPException(503, "의료문서 DB에 접근할 수 없어요. 잠시 후 다시 시도해 주세요.")


@router.post("", status_code=201)
def save_document(
    payload: SaveDocument, response: Response, member: dict = Depends(get_current_member)
):
    response.headers["Cache-Control"] = "no-store"
    try:
        with closing(get_write_connection()) as conn, conn, conn.cursor() as cur:
            return store_document(cur, member["member_id"], payload)
    except psycopg2.Error as error:
        raise database_error(error) from None


@router.get("")
def list_documents(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    member: dict = Depends(get_current_member),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        with closing(get_connection()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT document_id::text, visit_date, document_type, encounter_id
                FROM public.ocr_reviewed_document WHERE member_id = %s
                ORDER BY visit_date DESC, created_at DESC, document_id DESC
                LIMIT %s OFFSET %s
                """,
                (member["member_id"], limit + 1, offset),
            )
            rows = cur.fetchall()
            return {"items": rows[:limit], "has_more": len(rows) > limit}
    except psycopg2.Error as error:
        raise database_error(error) from None


@router.get("/{document_id}")
def read_document(document_id: UUID, response: Response, member: dict = Depends(get_current_member)):
    response.headers["Cache-Control"] = "no-store"
    try:
        with closing(get_connection()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT document_id::text, visit_date, document_type, document, encounter_id
                FROM public.ocr_reviewed_document WHERE member_id = %s AND document_id = %s
                """,
                (member["member_id"], str(document_id)),
            )
            record = cur.fetchone()
            if record is None:
                raise HTTPException(404, "저장된 의료문서를 찾을 수 없어요.")
            record.update(diagnoses=[], prescriptions=[])
            if record["encounter_id"] is None:
                return record
            cur.execute(
                """
                SELECT d.icd_code, COALESCE(d.disease_name_ko, d.disease_name) AS name
                FROM public.diagnosis a JOIN public.disease d ON a.disease_id = d.disease_id
                WHERE a.encounter_id = %s ORDER BY a.diagnosis_id
                """,
                (record["encounter_id"],),
            )
            record["diagnoses"] = cur.fetchall()
            cur.execute(
                """
                SELECT d.edi_code, d.drug_name, p.dose, p.frequency, p.duration_days
                FROM public.prescription p JOIN public.drug d ON p.drug_id = d.drug_id
                WHERE p.encounter_id = %s ORDER BY p.prescription_id
                """,
                (record["encounter_id"],),
            )
            record["prescriptions"] = cur.fetchall()
            return record
    except psycopg2.Error as error:
        raise database_error(error) from None
