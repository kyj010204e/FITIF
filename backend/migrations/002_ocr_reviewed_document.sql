BEGIN;

-- AI 조회와 OCR 적재 코드가 사용하는 현재 진단·처방 스키마인지 먼저 확인한다.
SELECT encounter_id, member_id, visit_date, source_type FROM public.encounter LIMIT 0;
SELECT diagnosis_id, encounter_id, disease_id, diagnosed_date FROM public.diagnosis LIMIT 0;
SELECT prescription_id, encounter_id, drug_id, dose, frequency, duration_days FROM public.prescription LIMIT 0;
SELECT disease_id, icd_code, disease_name_ko, disease_name FROM public.disease LIMIT 0;
SELECT drug_id, edi_code, drug_name, valid_from, valid_to FROM public.drug LIMIT 0;

-- OCR 편집 문서와 기존 진료 기록을 연결한다. 원본 이미지 대신 검수한 문서 구조를 보관한다.
CREATE TABLE IF NOT EXISTS public.ocr_reviewed_document (
    member_id BIGINT NOT NULL REFERENCES public.member(member_id),
    document_id UUID NOT NULL,
    visit_date DATE NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('prescription', 'diagnosis_certificate')),
    document JSONB NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    request_sha256 CHAR(64) NOT NULL,
    encounter_id BIGINT UNIQUE REFERENCES public.encounter(encounter_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (member_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_ocr_reviewed_member_date
    ON public.ocr_reviewed_document (member_id, visit_date DESC, created_at DESC, document_id DESC);

COMMIT;
