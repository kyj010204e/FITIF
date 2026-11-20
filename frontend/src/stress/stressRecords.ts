export const stressOptions = [
  { score: 1, label: "아주 나빠", emoji: "😣" },
  { score: 2, label: "별로야", emoji: "😕" },
  { score: 3, label: "보통이야", emoji: "😐" },
  { score: 4, label: "괜찮아", emoji: "🙂" },
  { score: 5, label: "아주 좋아", emoji: "😄" },
] as const;

export type StressOption = (typeof stressOptions)[number];
type StressRecord = { recorded_on: string; score: StressOption["score"] };

export async function getStressRecords(token: string, start: number, end: number, signal: AbortSignal) {
  const koreanDate = (time: number) => new Date(time + 9 * 3_600_000).toISOString().slice(0, 10);
  const query = new URLSearchParams({ start: koreanDate(start), end: koreanDate(end - 1) });
  const response = await fetch(`/api/stress/readings?${query}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  if (!response.ok) throw new Error("스트레스 기록을 불러오지 못했어요.");
  return await response.json() as StressRecord[];
}

export async function saveStressScore(token: string, score: StressOption["score"], signal: AbortSignal) {
  const response = await fetch("/api/stress/today", {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ score }),
    signal,
  });
  if (!response.ok) throw new Error("저장하지 못했어요. 다시 시도해 주세요.");
}
