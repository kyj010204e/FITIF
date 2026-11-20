import type { OcrDocument } from "../components/OcrDocumentEditor";

export type DocumentType = "prescription" | "diagnosis_certificate";
export type PrescriptionInput = {
  edi_code: string;
  dose: string;
  frequency: string;
  duration_days: number;
};

export type DocumentSummary = {
  document_id: string;
  visit_date: string;
  document_type: DocumentType;
  encounter_id: number | null;
};

export type SavedDocument = DocumentSummary & {
  document: OcrDocument;
  diagnoses: { icd_code: string; name: string | null }[];
  prescriptions: (PrescriptionInput & { drug_name: string })[];
};

export const documentTypeLabel: Record<DocumentType, string> = {
  prescription: "처방전",
  diagnosis_certificate: "진단서",
};

export async function documentRequest<T>(token: string, path = "", options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api/documents/records${path}`, { ...options, headers });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? "다시 로그인해 주세요."
        : typeof data?.detail === "string"
          ? data.detail
          : "의료문서 요청을 처리하지 못했어요. 입력값을 확인하거나 잠시 후 다시 시도해 주세요.",
    );
  }
  if (data === null) throw new Error("의료문서 응답을 읽을 수 없어요.");
  return data;
}
