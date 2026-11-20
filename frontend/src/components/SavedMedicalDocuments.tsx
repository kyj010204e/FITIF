import { useEffect, useState } from "react";
import { documentRequest, documentTypeLabel, type DocumentSummary, type SavedDocument } from "../api/medicalDocuments";
import OcrDocumentEditor from "./OcrDocumentEditor";

const pageSize = 20;
type Listing = { items: DocumentSummary[]; has_more: boolean };

export default function SavedMedicalDocuments({ token, newestId }: { token: string; newestId: string | null }) {
  const [page, setPage] = useState(0);
  const [list, setList] = useState<Listing | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [readBack, setReadBack] = useState<SavedDocument | null>(null);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    documentRequest<Listing>(token, `?limit=${pageSize}&offset=${page * pageSize}`, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setListError("");
        setList(result);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setListError(error.message);
      });
    return () => controller.abort();
  }, [newestId, page, token]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    documentRequest<SavedDocument>(token, `/${encodeURIComponent(selectedId)}`, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setDetailError("");
        setReadBack(result);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setDetailError(error.message);
      });
    return () => controller.abort();
  }, [selectedId, token]);

  function open(id: string) {
    if (selectedId === id) {
      setSelectedId(null);
      return;
    }
    setDetailError("");
    setReadBack(null);
    setSelectedId(id);
  }

  return (
    <section className="document-ocr__panel document-ocr__result" aria-labelledby="saved-document-title">
      <h2 id="saved-document-title">저장한 의료문서</h2>
      {listError && <p role="alert" className="document-ocr__error">{listError}</p>}
      {!list && !listError && <p role="status">저장한 의료문서를 불러오는 중이에요.</p>}
      {list && !list.items.length && <p>저장한 의료문서가 없어요.</p>}
      {newestId && list && !list.items.some(({ document_id }) => document_id === newestId) && (
        <button type="button" onClick={() => open(newestId)}>방금 저장한 문서 열기</button>
      )}
      {list?.items.map((item) => (
        <button type="button" key={item.document_id} onClick={() => open(item.document_id)} aria-expanded={selectedId === item.document_id}>
          {item.visit_date} {documentTypeLabel[item.document_type]} {selectedId === item.document_id ? "닫기" : "열기"}
        </button>
      ))}
      {(page > 0 || list?.has_more) && (
        <div className="document-editor__actions">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>이전</button>
          <button type="button" disabled={!list?.has_more} onClick={() => setPage(page + 1)}>다음</button>
        </div>
      )}
      {selectedId && detailError && <p role="alert" className="document-ocr__error">{detailError}</p>}
      {selectedId && !readBack && !detailError && <p role="status">의료문서를 불러오는 중이에요.</p>}
      {selectedId && readBack && (
        <>
          <h2>{readBack.visit_date} {documentTypeLabel[readBack.document_type]}</h2>
          <OcrDocumentEditor document={readBack.document} />
          {readBack.diagnoses.length > 0 && (
            <ul aria-label="저장한 진단">
              {readBack.diagnoses.map((item) => <li key={item.icd_code}>{item.icd_code} {item.name}</li>)}
            </ul>
          )}
          {readBack.prescriptions.length > 0 && (
            <ul aria-label="저장한 처방">
              {readBack.prescriptions.map((item, index) => (
                <li key={index}>{item.drug_name} · {item.dose} · {item.frequency} · {item.duration_days}일</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
