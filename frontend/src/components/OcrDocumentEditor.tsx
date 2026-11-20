import { useRef, useState, type FormEvent } from "react";
import SaveMedicalDocumentForm from "./SaveMedicalDocumentForm";

type OcrCell = { text: string; colspan: number; rowspan: number; header?: boolean };
type OcrContent = { type: "table"; rows: OcrCell[][] } | { type: "text"; text: string };

export type OcrDocument = {
  pages: { page: number; contents: OcrContent[] }[];
};

type EditorProps = {
  document: OcrDocument;
  originalImage?: string | null;
  saving?: { token: string; onPending: (pending: boolean) => void; onSaved: (documentId: string) => void };
};

export default function OcrDocumentEditor({ document, originalImage, saving }: EditorProps) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [editTarget, setEditTarget] = useState("");
  const [draft, setDraft] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const [locked, setLocked] = useState(false);
  const [pending, setPending] = useState(false);

  function editText(id: string, original: string) {
    setEditTarget(id);
    setDraft(edits[id] ?? original);
    dialog.current?.showModal();
  }

  function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEdits((previous) => ({ ...previous, [editTarget]: draft }));
    dialog.current?.close();
  }

  function editableText(id: string, original: string, label: string) {
    const text = edits[id] ?? original;
    if (!saving || locked) return <span className="document-editor__saved-text">{text}</span>;
    return (
      <button
        type="button"
        className="document-editor__text"
        disabled={pending}
        aria-label={text ? `${label} 수정, ${text}` : `빈 ${label} 수정`}
        onClick={() => editText(id, original)}
      >
        {text || "내용 입력"}
      </button>
    );
  }

  function captureDocument(): OcrDocument {
    return {
      pages: document.pages.map((page, pageIndex) => ({
        ...page,
        contents: page.contents.map((content, contentIndex) => {
          const contentId = `${pageIndex}:${contentIndex}`;
          if (content.type === "text") {
            return { ...content, text: edits[contentId] ?? content.text };
          }
          return {
            ...content,
            rows: content.rows.map((row, rowIndex) => row.map((cell, cellIndex) => ({
              ...cell,
              text: edits[`${contentId}:${rowIndex}:${cellIndex}`] ?? cell.text,
            }))),
          };
        }),
      })),
    };
  }

  if (!document.pages.some((page) => page.contents.length > 0)) {
    return <p>읽을 수 있는 글자가 없어요. 문서를 밝은 곳에서 다시 찍어 주세요.</p>;
  }

  return (
    <>
      {saving && !locked && <p>원본과 비교하고 수정할 문단이나 표의 셀을 눌러 주세요.</p>}
      {originalImage && (
        <details>
          <summary>원본 이미지 보기</summary>
          <img className="document-editor__original" src={originalImage} alt="업로드한 원본 의료문서" />
        </details>
      )}
      <div className="document-editor">
        {document.pages.map((page, pageIndex) => (
          <article className="document-editor__paper" key={pageIndex} aria-label={`${page.page}페이지`}>
            <h3>{page.page}페이지</h3>
            {page.contents.map((content, contentIndex) => {
              const contentId = `${pageIndex}:${contentIndex}`;
              if (content.type === "text") {
                return <p key={contentId}>{editableText(contentId, content.text, "문단")}</p>;
              }
              return (
                <div className="document-editor__table-wrap" key={contentId}>
                  <table aria-label={`${page.page}페이지 표`}>
                    <tbody>
                      {content.rows.map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {row.map((cell, cellIndex) => {
                            const Cell = cell.header ? "th" : "td";
                            const cellId = `${contentId}:${rowIndex}:${cellIndex}`;
                            return (
                              <Cell key={cellId} colSpan={cell.colspan} rowSpan={cell.rowspan}>
                                {editableText(cellId, cell.text, "표 셀")}
                              </Cell>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </article>
        ))}
      </div>
      {saving && (
        <SaveMedicalDocumentForm token={saving.token} getDocument={captureDocument} onPending={(status) => {
          setPending(status);
          saving.onPending(status);
        }} onSaved={(id) => {
          setLocked(true);
          saving.onSaved(id);
        }} />
      )}
      <dialog className="document-editor__dialog" ref={dialog} aria-labelledby="document-edit-label">
        <form onSubmit={saveEdit}>
          <label id="document-edit-label" htmlFor="document-edit-text">인식 내용 수정</label>
          <textarea id="document-edit-text" rows={5} autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} />
          <div className="document-editor__actions">
            <button type="button" onClick={() => dialog.current?.close()}>취소</button>
            <button type="submit">수정 적용</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
