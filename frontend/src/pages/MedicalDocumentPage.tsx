import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import OcrDocumentEditor, { type OcrDocument } from "../components/OcrDocumentEditor";
import SavedMedicalDocuments from "../components/SavedMedicalDocuments";
import { HEALTH_RECORDS_PATH } from "./HealthRecordsPage";
import "./HealthRecordsPage.css";

const imageTypes = new Map([
  ["jpg", "image/jpeg"],
  ["jpeg", "image/jpeg"],
  ["png", "image/png"],
  ["webp", "image/webp"],
]);
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const qualityReasons: Record<string, string> = {
  LOW_RESOLUTION: "이미지 해상도가 낮아요.",
  EXTREMELY_LOW_RESOLUTION: "이미지 크기가 너무 작아요.",
  POSSIBLE_BLUR: "이미지가 흐릴 수 있어요.",
  POSSIBLE_LOCAL_BLUR: "일부 글자가 흐릴 수 있어요.",
  TOO_DARK: "이미지가 어두워요.",
  LOW_CONTRAST: "글자와 배경의 색 차이가 작아요.",
  UNEVEN_ILLUMINATION: "그림자가 있거나 조명이 고르지 않아요.",
  POSSIBLE_OVEREXPOSURE: "빛이 강해 글자가 희미할 수 있어요.",
};

type OCRResult = {
  quality: { status: string; reasons: string[] };
  document: OcrDocument;
  legacyText: boolean;
};

export default function MedicalDocumentPage() {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [originalImage, setOriginalImage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [newestId, setNewestId] = useState<string | null>(null);
  const [result, setResult] = useState<OCRResult | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => () => {
    if (originalImage) URL.revokeObjectURL(originalImage);
  }, [originalImage]);

  async function recognize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || activeRequest.current || saving) return;

    setError("");
    setResult(null);
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    const contentType = imageTypes.get(extension);
    if (!contentType) {
      setError("JPG, PNG, WebP 이미지를 선택해 주세요.");
      return;
    }
    if (file.size === 0 || file.size > MAX_IMAGE_BYTES) {
      setError("비어 있지 않은 10MB 이하 이미지를 선택해 주세요.");
      return;
    }
    if (!token) {
      setError("다시 로그인해 주세요.");
      return;
    }

    const controller = new AbortController();
    activeRequest.current = controller;
    setBusy(true);
    try {
      const response = await fetch("/api/documents/ocr", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": contentType },
        body: file,
        signal: controller.signal,
      });

      if (response.status === 401) throw new Error("다시 로그인해 주세요.");
      if (response.status === 404) throw new Error("OCR 기능이 백엔드에 아직 연결되지 않았어요.");

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "문서를 인식하지 못했어요. 잠시 후 다시 시도해 주세요.",
        );
      }
      if (!data?.quality) throw new Error("인식 결과를 읽을 수 없어요.");

      if (Array.isArray(data.document?.pages)) {
        setResult({ quality: data.quality, document: data.document, legacyText: false });
      } else if (Array.isArray(data.blocks)) {
        // 구버전 5090 API가 응답해도 추출 문단을 검수할 수 있게 한다.
        const contents = data.blocks.map((text: string) => ({ type: "text" as const, text }));
        setResult({ quality: data.quality, document: { pages: [{ page: 1, contents }] }, legacyText: true });
      } else {
        throw new Error("인식 결과를 읽을 수 없어요.");
      }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "문서를 인식하지 못했어요.");
      }
    } finally {
      activeRequest.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="health-records" aria-labelledby="medical-document-title">
      <Link to={HEALTH_RECORDS_PATH} className="health-records__back">
        <ArrowLeft size={18} aria-hidden="true" />
        건강기록
      </Link>
      <h1 id="medical-document-title">의료문서 등록</h1>
      <form className="document-ocr__panel" onSubmit={recognize} aria-busy={busy}>
        <label htmlFor="medical-document-file">처방전 또는 진단서 사진</label>
        <p id="medical-document-formats">JPG, PNG, WebP · 최대 10MB</p>
        <input
          id="medical-document-file"
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          aria-describedby="medical-document-formats"
          disabled={busy || saving}
          onChange={(event) => {
            const selected = event.target.files?.[0] ?? null;
            setFile(selected);
            setOriginalImage(selected ? URL.createObjectURL(selected) : null);
            setError("");
            setResult(null);
          }}
        />
        <button type="submit" disabled={!file || busy || saving}>
          {busy ? "인식 중…" : "문서 인식하기"}
        </button>
      </form>

      {busy && <p role="status">사진에서 글자를 읽고 있어요. 최대 2분 정도 걸릴 수 있어요.</p>}
      {error && <p role="alert" className="document-ocr__error">{error}</p>}
      {result && (
        <section className="document-ocr__panel document-ocr__result" aria-labelledby="ocr-result-title">
          <h2 id="ocr-result-title">인식 결과</h2>
          {result.quality.status === "WARNING" && (
            <div>
              <strong>사진 품질을 확인해 주세요.</strong>
              <ul>
                {result.quality.reasons.map((reason) => (
                  <li key={reason}>{qualityReasons[reason] ?? reason}</li>
                ))}
              </ul>
            </div>
          )}
          {result.legacyText && <p role="status">OCR 서버가 텍스트만 반환했어요. 표와 셀을 보려면 OCR 서버를 업데이트해 주세요.</p>}
          <OcrDocumentEditor
            document={result.document}
            originalImage={originalImage}
            saving={token ? { token, onPending: setSaving, onSaved: setNewestId } : undefined}
          />
        </section>
      )}
      {token && <SavedMedicalDocuments token={token} newestId={newestId} />}
    </section>
  );
}
