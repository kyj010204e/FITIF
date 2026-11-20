import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { saveStressScore, stressOptions, type StressOption } from "../stress/stressRecords";
import "./StressPage.css";

export default function StressPage() {
  const { token } = useAuth();
  const { state } = useLocation();
  const [selected, setSelected] = useState<StressOption>();
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const pending = useRef<AbortController | null>(null);
  const fromChat = state?.fromChat === true;

  useEffect(() => () => pending.current?.abort(), []);

  async function save() {
    if (!token || !selected || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setStatus("saving");
    try {
      await saveStressScore(token, selected.score, controller.signal);
      if (!controller.signal.aborted) setStatus("saved");
    } catch {
      if (!controller.signal.aborted) setStatus("error");
    } finally {
      pending.current = null;
    }
  }

  return (
    <section className="stress-page" aria-labelledby="stress-title">
      <Link className="stress-back" to={fromChat ? "/chat" : "/home"}>
        {fromChat ? "← 대화로 돌아가기" : "← 홈으로 돌아가기"}
      </Link>
      <h1 id="stress-title">스트레스 기록</h1>
      <div className="stress-card">
        <h2>오늘 스트레스는 어땠어요?</h2>
        <p>오늘 하루가 어땠는지 골라 주세요.</p>
        <div className="stress-options" role="group" aria-label="오늘 스트레스 상태">
          {stressOptions.map((option) => (
            <button
              key={option.score}
              type="button"
              aria-pressed={selected?.score === option.score}
              disabled={status === "saving"}
              onClick={() => {
                setSelected(option);
                setStatus("idle");
              }}
            >
              <strong>{option.score}</strong>
              <span>{option.label}</span>
            </button>
          ))}
        </div>
        <div className="stress-feedback" aria-live="polite">
          {selected && (
            <div key={selected.score} className="stress-reaction">
              <span className="stress-emoji" aria-hidden="true">{selected.emoji}</span>
              <strong>{selected.label}</strong>
            </div>
          )}
        </div>
        <button className="primary-button" type="button" disabled={!selected || status === "saving" || status === "saved"} onClick={() => void save()}>
          {status === "saving" ? "저장 중…" : "저장"}
        </button>
        {status === "saved" && <p role="status">오늘 기록을 저장했어요.</p>}
        {status === "error" && <p role="alert">저장하지 못했어요. 다시 시도해 주세요.</p>}
      </div>
    </section>
  );
}
