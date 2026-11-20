import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import type { SummaryPeriod } from "../pages/homeSummaryPeriod";
import { getStressRecords, stressOptions, type StressOption } from "./stressRecords";

export default function StressPreview({ period }: { period: SummaryPeriod }) {
  const { token } = useAuth();
  const [result, setResult] = useState<{
    period: SummaryPeriod;
    token: string;
    score?: StressOption["score"];
    days?: number;
    error?: boolean;
  }>();

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    getStressRecords(token, period.start, period.end, controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) {
          setResult({ period, token, score: records[0]?.score, days: records.length });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ period, token, error: true });
      });
    return () => controller.abort();
  }, [token, period]);

  const current = result?.period === period && result.token === token ? result : undefined;
  const option = stressOptions.find(({ score }) => score === current?.score);
  if (option) {
    return (
      <>
        <span><span aria-hidden="true">{option.emoji}</span> {option.label}</span>
        {period.days > 1 && <small>최근 기록 · {current?.days}일</small>}
      </>
    );
  }
  const status = !current ? "불러오는 중" : current.error ? "조회 실패" : "기록 없음";
  return <span className="home-card-status" role="status">{status}</span>;
}
