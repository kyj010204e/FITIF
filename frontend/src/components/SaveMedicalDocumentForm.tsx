import { useEffect, useRef, useState, type FormEvent } from "react";
import { documentRequest, documentTypeLabel, type DocumentSummary, type DocumentType, type PrescriptionInput } from "../api/medicalDocuments";
import type { OcrDocument } from "./OcrDocumentEditor";

type Props = {
  token: string;
  getDocument: () => OcrDocument;
  onPending: (pending: boolean) => void;
  onSaved: (documentId: string) => void;
};
type Row = { id: number };
type Saved = Pick<DocumentSummary, "document_id" | "encounter_id">;

export default function SaveMedicalDocumentForm({ token, getDocument, onPending, onSaved }: Props) {
  const [diagnoses, setDiagnoses] = useState<Row[]>([]);
  const [prescriptions, setPrescriptions] = useState<Row[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const documentId = useRef<string | null>(null);
  const rowSequence = useRef(0);

  useEffect(() => () => request.current?.abort(), []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (request.current || saved) return;

    const data = new FormData(event.currentTarget);
    const field = (key: string) => String(data.get(key) ?? "").trim();
    const prescriptionRows: PrescriptionInput[] = prescriptions.map(({ id }) => ({
      edi_code: field(`edi-${id}`),
      dose: field(`dose-${id}`),
      frequency: field(`frequency-${id}`),
      duration_days: Number(field(`days-${id}`)),
    }));
    documentId.current ??= crypto.randomUUID();
    const controller = new AbortController();
    request.current = controller;
    setSaving(true);
    onPending(true);
    setError("");

    try {
      const result = await documentRequest<Saved>(token, "", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: documentId.current,
          visit_date: field("visit-date"),
          document_type: field("document-type"),
          document: getDocument(),
          diagnoses: diagnoses.map(({ id }) => field(`diagnosis-${id}`).toUpperCase()),
          prescriptions: prescriptionRows,
        }),
      });
      setSaved(result);
      onSaved(result.document_id);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "저장하지 못했어요.");
    } finally {
      request.current = null;
      if (!controller.signal.aborted) {
        setSaving(false);
        onPending(false);
      }
    }
  }

  if (saved) return <p role="status">저장했어요. 아래 저장한 의료문서에서 다시 열 수 있어요.</p>;

  return (
    <form className="document-save" onSubmit={save} aria-busy={saving}>
      <fieldset disabled={saving}>
        <legend>저장할 의료기록</legend>
        <label>진료일<input name="visit-date" type="date" min="1900-01-01" required /></label>
        <label>
          문서 종류
          <select name="document-type" defaultValue="" required>
            <option value="" disabled>선택해 주세요</option>
            {(Object.keys(documentTypeLabel) as DocumentType[]).map((value) => (
              <option key={value} value={value}>{documentTypeLabel[value]}</option>
            ))}
          </select>
        </label>
        <p>원본에서 확인한 진단·처방을 아래에 추가하면 다른 기능에서도 사용할 수 있어요.</p>
        {diagnoses.map(({ id }, index) => (
          <div className="document-save__row" key={id}>
            <label>
              진단 {index + 1} · 질병분류코드 (ICD-10/KCD)
              <input name={`diagnosis-${id}`} placeholder="예: J10.1" pattern="[A-Za-z][0-9]{2}(\\.?[0-9A-Za-z]{1,4})?" maxLength={8} required />
            </label>
            <button type="button" onClick={() => setDiagnoses((rows) => rows.filter((row) => row.id !== id))}>
              진단 {index + 1} 제거
            </button>
          </div>
        ))}
        <button type="button" onClick={() => {
          const id = rowSequence.current++;
          setDiagnoses((rows) => [...rows, { id }]);
        }} disabled={diagnoses.length >= 100}>진단 추가</button>
        {prescriptions.map(({ id }, index) => (
          <div className="document-save__row" key={id}>
            <label>처방 {index + 1} · 약품 EDI 코드<input name={`edi-${id}`} inputMode="numeric" pattern="[0-9]{9}" maxLength={9} required /></label>
            <label>1회 용량<input name={`dose-${id}`} maxLength={50} required /></label>
            <label>복용 횟수<input name={`frequency-${id}`} maxLength={50} required /></label>
            <label>복용 일수<input name={`days-${id}`} type="number" min={1} max={32767} step={1} required /></label>
            <button type="button" onClick={() => setPrescriptions((rows) => rows.filter((row) => row.id !== id))}>
              처방 {index + 1} 제거
            </button>
          </div>
        ))}
        <button type="button" onClick={() => {
          const id = rowSequence.current++;
          setPrescriptions((rows) => [...rows, { id }]);
        }} disabled={prescriptions.length >= 100}>처방 추가</button>
        <label className="document-save__confirm"><input type="checkbox" required /> 원본과 대조해 내용을 확인했어요.</label>
        <button type="submit">{saving ? "저장 중…" : "저장하기"}</button>
        {error && <p role="alert" className="document-ocr__error">{error}</p>}
      </fieldset>
    </form>
  );
}
