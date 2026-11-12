import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, XAxis } from "recharts";
import { useAuth } from "../auth/AuthProvider";

type Point = {
  timestamp: number;
  glucose: number;
};

type PreviewState =
  | { status: "ready"; points: Point[] }
  | { status: "error" };

const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

function parsePoints(data: unknown): Point[] {
  const body = data as Record<string, unknown> | null;
  const rows = Array.isArray(data)
    ? data
    : body?.readings ?? body?.items ?? body?.data ?? body?.results;

  if (!Array.isArray(rows)) {
    throw new Error("혈당 기록 응답 형식을 확인해 주세요.");
  }

  return rows.flatMap((row) => {
    if (
      typeof row?.measured_at !== "string" ||
      !["number", "string"].includes(typeof row?.glucose_mg_dl)
    ) {
      return [];
    }

    const timestamp = Date.parse(row.measured_at);
    const glucose = Number(row.glucose_mg_dl);
    return Number.isFinite(timestamp) && Number.isFinite(glucose) && glucose > 0
      ? [{ timestamp, glucose }]
      : [];
  });
}

export default function RecentGlucosePreview() {
  const { token } = useAuth();
  const [result, setResult] = useState<{
    token: typeof token;
    preview: PreviewState;
  } | null>(null);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();

    async function fetchPoints(path: string) {
      const response = await fetch(path, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`혈당 조회 실패 (${response.status})`);
      }

      return parsePoints(await response.json());
    }

    // 두 API에서 최신 기록을 받아 합친 뒤, 표시할 20건을 시간순으로 정렬한다.
    Promise.all([
      fetchPoints("/api/glucose/readings?limit=20"),
      fetchPoints("/api/cgm/readings?limit=20"),
    ])
      .then(([manual, cgm]) => {
        if (controller.signal.aborted) return;
        const points = [...manual, ...cgm]
          .sort((a, b) => a.timestamp - b.timestamp)
          .slice(-20);

        setResult({ token, preview: { status: "ready", points } });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResult({ token, preview: { status: "error" } });
        }
      });

    return () => controller.abort();
  }, [token]);

  const preview = result?.token === token ? result?.preview : null;

  if (!preview) {
    return <p role="status">혈당 기록을 불러오는 중이에요.</p>;
  }

  if (preview.status === "error") {
    return <p role="status">혈당 기록을 불러오지 못했어요.</p>;
  }

  const { points } = preview;
  if (points.length === 0) {
    return <p>아직 기록된 혈당이 없어요.</p>;
  }

  const first = points[0];
  const latest = points[points.length - 1];
  const startDate = dateFormat.format(first.timestamp);
  const endDate = dateFormat.format(latest.timestamp);

  return (
    <div style={{ margin: "16px 0" }}>
      <strong>최근 측정 {latest.glucose} mg/dL</strong>

      {points.length > 1 && (
        <div aria-hidden="true" style={{ width: "100%", height: 76 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 6, right: 4, bottom: 6, left: 4 }}>
              <XAxis dataKey="timestamp" type="number" domain={["dataMin", "dataMax"]} hide />
              <Line
                dataKey="glucose"
                type="linear"
                stroke="#127663"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <small>
        {startDate === endDate ? endDate : `${startDate} ~ ${endDate}`}
        {" · "}{points.length}건
      </small>
    </div>
  );
}