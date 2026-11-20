export const summaryPeriods = [
  { days: 1, label: "오늘" },
  { days: 7, label: "일주일" },
  { days: 14, label: "2주" },
  { days: 30, label: "한달" },
] as const;

type SummaryDays = (typeof summaryPeriods)[number]["days"];

export type SummaryPeriod = {
  days: SummaryDays;
  start: number;
  end: number;
};

export function getSummaryPeriod(days: SummaryDays, now = Date.now()): SummaryPeriod {
  const day = 24 * 60 * 60 * 1000;
  const koreaOffset = 9 * 60 * 60 * 1000;
  // 한국시간 자정을 기준으로 오늘을 포함한 N일을 조회한다.
  const todayStart = Math.floor((now + koreaOffset) / day) * day - koreaOffset;

  return { days, start: todayStart - (days - 1) * day, end: now + 1 };
}
