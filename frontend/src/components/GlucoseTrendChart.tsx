import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import "./GlucoseTrendChart.css";

type GlucoseReading = {
  reading_id: number;
  glucose_mg_dl: number | string;
  measured_at: string;
};

type Props = {
  readings: GlucoseReading[];
  loadCgmReadings: (
    start: number,
    end: number,
    signal: AbortSignal,
  ) => Promise<GlucoseReading[]>;
};

type Period = 1 | 3 | 7 | "custom";

const DAY_MS = 24 * 60 * 60 * 1000;

// 날짜 입력에 사용할 로컬 날짜 문자열
function localDateString(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;

  return new Date(date.getTime() - offset)
    .toISOString()
    .slice(0, 10);
}

function formatAxisDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
  });
}

function formatTooltipDate(timestamp: number): string {
  return new Date(timestamp).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function GlucoseTrendChart({
  readings,
  loadCgmReadings,
}: Props) {
  // 기본 기간: 최근 3일
  const [period, setPeriod] = useState<Period>(3);

  // 직접 기간 설정 기본값: 최근 7일의 달력 날짜
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 6);
    return localDateString(date);
  });

  const [endDate, setEndDate] = useState(() =>
    localDateString(new Date()),
  );

  const today = localDateString(new Date());

  const [appliedDates, setAppliedDates] = useState<{
    startDate: string;
    endDate: string;
  } | null>(null);

  const canApplyDates = Boolean(
    startDate && endDate && startDate <= endDate && endDate <= today,
  );

  // ============================================
  // 1. 조회 기간 계산
  // ============================================

  const dateRange = useMemo(() => {
    const now = Date.now();

    // 직접 선택한 날짜 범위
    if (period === "custom") {
      if (!appliedDates) {
        return null;
      }

      const start = new Date(
        `${appliedDates.startDate}T00:00:00`,
      ).getTime();

      // 선택한 종료일 전체를 포함하도록 다음 날 자정을 경계로 사용한다.
      const endExclusive = new Date(
        `${appliedDates.endDate}T00:00:00`,
      );

      endExclusive.setDate(
        endExclusive.getDate() + 1,
      );

      const end = Math.min(
        endExclusive.getTime(),
        now + 1,
      );

      if (
        !Number.isFinite(start) ||
        !Number.isFinite(end) ||
        start >= end
      ) {
        return null;
      }

      return {
        start,
        end,
      };
    }

    // 최근 1일, 3일, 7일
    return {
      start: now - period * DAY_MS,
      end: now,
    };
  }, [period, appliedDates]);

  const [cgmResult, setCgmResult] = useState<{
    range: typeof dateRange;
    loader: typeof loadCgmReadings;
    readings: GlucoseReading[];
    error: string;
  } | null>(null);

  useEffect(() => {
    if (!dateRange) return;

    const controller = new AbortController();
    loadCgmReadings(dateRange.start, dateRange.end, controller.signal)
      .then((records) => {
        if (controller.signal.aborted) return;
        setCgmResult({
          range: dateRange,
          loader: loadCgmReadings,
          readings: records,
          error: "",
        });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setCgmResult({
          range: dateRange,
          loader: loadCgmReadings,
          readings: [],
          error: err instanceof Error ? err.message : "CGM 조회 중 오류가 발생했습니다.",
        });
      });

    return () => controller.abort();
  }, [dateRange, loadCgmReadings]);

  const currentCgmResult =
    cgmResult?.range === dateRange && cgmResult.loader === loadCgmReadings
      ? cgmResult
      : null;

  // ============================================
  // 2. 선택 기간에 해당하는 데이터
  // ============================================

  const chartData = useMemo(() => {
    if (!dateRange) {
      return [];
    }

    return [...readings, ...(currentCgmResult?.readings ?? [])]
      .map((item) => ({
        reading_id: item.reading_id,
        timestamp: new Date(
          item.measured_at,
        ).getTime(),
        glucose: Number(item.glucose_mg_dl),
      }))
      .filter(
        (item) =>
          Number.isFinite(item.timestamp) &&
          Number.isFinite(item.glucose) &&
          item.glucose > 0 &&
          item.timestamp >= dateRange.start &&
          item.timestamp < dateRange.end,
      )
      .sort(
        (a, b) => a.timestamp - b.timestamp,
      );
  }, [readings, dateRange, currentCgmResult]);

  // ============================================
  // 3. 선택 기간 통계
  // ============================================

  const stats = useMemo(() => {
    if (chartData.length === 0) {
      return null;
    }

    const values = chartData.map(
      (item) => item.glucose,
    );

    const total = values.reduce(
      (sum, value) => sum + value,
      0,
    );

    return {
      average:
        Math.round(
          (total / values.length) * 10,
        ) / 10,
      min: Math.min(...values),
      max: Math.max(...values),
      count: values.length,
    };
  }, [chartData]);

  // ============================================
  // 4. 그래프 축 범위
  // ============================================

  const yDomain = useMemo<[number, number]>(() => {
    if (!stats) {
      return [0, 200];
    }

    const padding = Math.max(
      15,
      (stats.max - stats.min) * 0.2,
    );

    const lower = Math.max(
      0,
      Math.floor(
        (stats.min - padding) / 10,
      ) * 10,
    );

    const upper =
      Math.ceil(
        (stats.max + padding) / 10,
      ) * 10;

    return [
      lower,
      Math.max(lower + 20, upper),
    ];
  }, [stats]);

  const xDomain = useMemo<[number, number]>(() => {
    if (chartData.length === 0) {
      const now = Date.now();
      return [now - DAY_MS, now];
    }

    const first = chartData[0].timestamp;
    const last =
      chartData[chartData.length - 1].timestamp;

    if (first === last) {
      return [
        first - DAY_MS / 2,
        last + DAY_MS / 2,
      ];
    }

    const padding = Math.max(
      60 * 60 * 1000,
      (last - first) * 0.05,
    );

    return [
      first - padding,
      last + padding,
    ];
  }, [chartData]);

  return (
    <section className="glucose-panel glucose-trend-panel">
      <div className="glucose-trend-header">
        <div className="glucose-trend-heading">
          <h2>혈당 추이</h2>
          <p>기간별 혈당 변화 확인</p>
        </div>

        {/* 빠른 기간 선택 */}
        <div
          className="glucose-period-selector"
          role="group"
          aria-label="혈당 조회 기간"
        >
          {([1, 3, 7] as const).map((days) => (
            <button
              key={days}
              type="button"
              className={
                period === days
                  ? "glucose-period-button active"
                  : "glucose-period-button"
              }
              onClick={() => setPeriod(days)}
              aria-pressed={period === days}
            >
              {days}일
            </button>
          ))}

          <button
            type="button"
            className={
              period === "custom"
                ? "glucose-period-button active"
                : "glucose-period-button"
            }
            onClick={() => setPeriod("custom")}
            aria-pressed={period === "custom"}
          >
            직접
          </button>
        </div>
      </div>

      {/* 직접 기간 설정 */}
      {period === "custom" && (
        <div className="glucose-custom-range">
          <div className="glucose-custom-field">
            <label htmlFor="glucose-start-date">
              시작일
            </label>

            <input
              id="glucose-start-date"
              type="date"
              value={startDate}
              max={endDate || today}
              onChange={(event) =>
                setStartDate(event.target.value)
              }
            />
          </div>

          <span
            className="glucose-custom-separator"
            aria-hidden="true"
          >
            ~
          </span>

          <div className="glucose-custom-field">
            <label htmlFor="glucose-end-date">
              종료일
            </label>

            <input
              id="glucose-end-date"
              type="date"
              value={endDate}
              min={startDate}
              max={today}
              onChange={(event) =>
                setEndDate(event.target.value)
              }
            />
          </div>
          <button
            type="button"
            className="glucose-period-button active"
            disabled={!canApplyDates}
            onClick={() => setAppliedDates({ startDate, endDate })}
          >
            조회
          </button>
        </div>
      )}

      {currentCgmResult?.error && (
        <p role="alert">{currentCgmResult.error}</p>
      )}

      {dateRange === null ? (
        <div className="glucose-trend-empty">
          <strong>시작일과 종료일을 선택하고 조회를 눌러 주세요.</strong>
        </div>
      ) : chartData.length === 0 ? (
        <div className="glucose-trend-empty">
          <span className="glucose-trend-empty-icon">
            ◇
          </span>
          <strong>
            표시할 혈당 기록이 없어요
          </strong>
          <p>
            선택한 기간에 등록된 측정값이 없습니다.
          </p>
        </div>
      ) : (
        <>
          {/* 선택 기간 통계 */}
          <div className="glucose-trend-stats">
            <div className="glucose-trend-stat">
              <span className="glucose-trend-stat-label">
                평균 혈당
              </span>
              <div className="glucose-trend-stat-value">
                {stats?.average}
                <small>mg/dL</small>
              </div>
            </div>

            <div className="glucose-trend-stat">
              <span className="glucose-trend-stat-label">
                최저 혈당
              </span>
              <div className="glucose-trend-stat-value">
                {stats?.min}
                <small>mg/dL</small>
              </div>
            </div>

            <div className="glucose-trend-stat">
              <span className="glucose-trend-stat-label">
                최고 혈당
              </span>
              <div className="glucose-trend-stat-value">
                {stats?.max}
                <small>mg/dL</small>
              </div>
            </div>

            <div className="glucose-trend-stat">
              <span className="glucose-trend-stat-label">
                측정 횟수
              </span>
              <div className="glucose-trend-stat-value">
                {stats?.count}
                <small>건</small>
              </div>
            </div>
          </div>

          {/* 시계열 그래프 */}
          <div className="glucose-trend-chart">
            <ResponsiveContainer
              width="100%"
              height="100%"
            >
              <LineChart
                data={chartData}
                margin={{
                  top: 16,
                  right: 12,
                  bottom: 4,
                  left: -12,
                }}
              >
                <CartesianGrid
                  stroke="#e4ebe8"
                  strokeDasharray="4 4"
                  vertical={false}
                />

                <XAxis
                  dataKey="timestamp"
                  type="number"
                  scale="time"
                  domain={xDomain}
                  tickCount={4}
                  tickFormatter={formatAxisDate}
                  tickLine={false}
                  axisLine={false}
                  tick={{
                    fill: "#758780",
                    fontSize: 11,
                  }}
                  minTickGap={20}
                  dy={9}
                />

                <YAxis
                  type="number"
                  domain={yDomain}
                  width={46}
                  tickLine={false}
                  axisLine={false}
                  tick={{
                    fill: "#758780",
                    fontSize: 11,
                  }}
                />

                <Tooltip
                  labelFormatter={(value) =>
                    formatTooltipDate(Number(value))
                  }
                  formatter={(value) => [
                    `${Number(value)} mg/dL`,
                    "혈당",
                  ]}
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #e0ebe6",
                    backgroundColor: "#ffffff",
                    fontSize: 12,
                  }}
                />

                <Line
                  type="linear"
                  dataKey="glucose"
                  name="혈당"
                  stroke="#168a73"
                  strokeWidth={2.5}
                  dot={
                    chartData.length <= 80
                      ? {
                          r: 4,
                          stroke: "#168a73",
                          strokeWidth: 2,
                          fill: "#ffffff",
                        }
                      : false
                  }
                  activeDot={{
                    r: 6,
                    stroke: "#168a73",
                    strokeWidth: 2,
                    fill: "#ffffff",
                  }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p className="glucose-trend-note">
            통계는 선택한 기간에 등록된 측정값의
            산술평균을 사용합니다. 측정하지 않은
            시간의 혈당은 추정하지 않습니다.
          </p>
        </>
      )}
    </section>
  );
}
