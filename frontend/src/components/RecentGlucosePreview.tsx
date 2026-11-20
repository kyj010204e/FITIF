import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, XAxis } from "recharts";
import { useAuth } from "../auth/AuthProvider";
import type { SummaryPeriod } from "../pages/homeSummaryPeriod";

type Point = {
  timestamp: number;
  glucose: number;
};

type PreviewState =
  | { status: "ready"; points: Point[] }
  | { status: "error" };

type PeriodResult = { manual: Point[]; cgm: Point[] };

const MAX_READINGS = 500;

const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  timeZone: "Asia/Seoul",
});

function parsePoints(data: unknown) {
  const body = data as Record<string, unknown> | null;
  const rows = Array.isArray(data)
    ? data
    : body?.readings ?? body?.items ?? body?.data ?? body?.results;

  if (!Array.isArray(rows)) {
    throw new Error("혈당 기록 응답 형식을 확인해 주세요.");
  }

  const points = rows.flatMap((row) => {
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
  return { points, count: rows.length };
}

type FetchPoints = (path: string) => Promise<ReturnType<typeof parsePoints>>;

async function fetchPeriodPoints(fetchPoints: FetchPoints, path: string, start: number, end: number): Promise<Point[]> {
  const params = new URLSearchParams({
    start_at: new Date(start).toISOString(),
    end_at: new Date(end).toISOString(),
    limit: String(MAX_READINGS),
  });
  const { points, count } = await fetchPoints(`${path}?${params}`);
  const inRange = points.filter(({ timestamp }) => timestamp >= start && timestamp < end);

  if (count < MAX_READINGS) return inRange;

  // API 응답이 조회 한도까지 차면 해당 구간을 나눠 기간 평균 누락을 막는다.
  const middle = start + Math.floor((end - start) / 2);
  if (middle === start || inRange.length !== points.length) {
    throw new Error("혈당 기록을 지정한 기간으로 모두 가져올 수 없어요.");
  }
  const earlier = await fetchPeriodPoints(fetchPoints, path, start, middle);
  const later = await fetchPeriodPoints(fetchPoints, path, middle, end);
  return [...earlier, ...later];
}

function GlucoseTrend({ points, period }: { points: Point[]; period: SummaryPeriod }) {
  // 오늘은 시간대별, 장기 조회는 날짜별 평균으로 작은 추이선을 그린다.
  const bucketSize = (period.days === 1 ? 1 : 24) * 3_600_000;
  const buckets = new Map<number, { sum: number; count: number }>();
  for (const { timestamp, glucose } of points) {
    const index = Math.floor((timestamp - period.start) / bucketSize);
    const bucket = buckets.get(index) ?? { sum: 0, count: 0 };
    bucket.sum += glucose;
    bucket.count++;
    buckets.set(index, bucket);
  }
  const values = [...buckets].sort(([a], [b]) => a - b)
    .map(([index, { sum, count }]) => ({ index, avg: sum / count }));
  if (values.length < 2) return null;

  const min = Math.min(...values.map(({ avg }) => avg));
  const max = Math.max(...values.map(({ avg }) => avg));
  const last = values[values.length - 1].index;
  const first = values[0].index;
  const line = values.map(({ index, avg }) => {
    const x = 2 + 96 * (index - first) / (last - first);
    const y = max === min ? 13 : 24 - 22 * (avg - min) / (max - min);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg className="home-glucose-trend" viewBox="0 0 100 26" aria-hidden="true">
      <polyline points={line} />
    </svg>
  );
}

export default function RecentGlucosePreview(
  { compact = false, period }: { compact?: boolean; period?: SummaryPeriod },
) {
  const { token } = useAuth();
  const [result, setResult] = useState<{
    token: typeof token;
    period?: SummaryPeriod;
    preview: PreviewState;
    sources?: PeriodResult;
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

    const paths = ["/api/glucose/readings", "/api/cgm/readings"] as const;
    const request = (path: string) => period
      ? fetchPeriodPoints(fetchPoints, path, period.start, period.end)
      : fetchPoints(`${path}?limit=20`).then(({ points }) => points);

    Promise.all(paths.map(request))
      .then(([manual, cgm]) => {
        if (controller.signal.aborted) return;
        const points = [...manual, ...cgm]
          .sort((a, b) => a.timestamp - b.timestamp)
          .slice(period ? -1 : -20);
        setResult({
          token, period, preview: { status: "ready", points }, sources: { manual, cgm },
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResult({ token, period, preview: { status: "error" } });
        }
      });

    return () => controller.abort();
  }, [token, period]);

  const current = result?.token === token && result?.period === period ? result : null;
  const preview = current?.preview;

  if (period && preview?.status === "ready" && current?.sources && preview.points.length) {
    const { manual, cgm } = current.sources;
    const trendPoints = cgm.length ? cgm : manual;
    if (period.days === 1) {
      const latest = preview.points[0];
      return (
        <>
          <strong>{latest.glucose}</strong>
          <small>mg/dL · 최근 측정</small>
          <GlucoseTrend points={trendPoints} period={period} />
        </>
      );
    }

    const sum = trendPoints.reduce((total, { glucose }) => total + glucose, 0);
    return (
      <>
        <strong>{Math.round(sum / trendPoints.length)}</strong>
        <small>mg/dL · {cgm.length ? "연속측정" : "직접기록"} 평균</small>
        <GlucoseTrend points={trendPoints} period={period} />
      </>
    );
  }

  if (compact || period) {
    const latest = preview?.status === "ready" ? preview.points.at(-1) : undefined;
    if (latest) {
      return (
        <>
          <strong>{latest.glucose}</strong>
          <small>mg/dL · {dateFormat.format(latest.timestamp)}</small>
        </>
      );
    }

    const message = !preview
      ? "불러오는 중"
      : preview.status === "error" ? "조회 실패" : "기록 없음";
    return <span role="status" className="home-card-status">{message}</span>;
  }

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