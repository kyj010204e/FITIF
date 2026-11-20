import {
  Activity, Droplet, Footprints, Heart, Utensils, Zap,
  type LucideIcon,
} from "lucide-react";
import type { ComponentType } from "react";
import RecentGlucosePreview from "../components/RecentGlucosePreview";
import StressPreview from "../stress/StressPreview";
import type { SummaryPeriod } from "./homeSummaryPeriod";

type HealthMetric = {
  id: string;
  label: string;
  Preview?: ComponentType<{ period: SummaryPeriod }>;
};

export type HealthSummaryCard = {
  id: string;
  title: string;
  icon: LucideIcon;
  metrics: readonly HealthMetric[];
  href?: string;
};

const metrics = {
  stress: { id: "stress", label: "스트레스", Preview: StressPreview },
  condition: { id: "condition", label: "컨디션" },
  pressure: { id: "pressure", label: "혈압" },
  glucose: { id: "glucose", label: "혈당", Preview: RecentGlucosePreview },
  diet: { id: "diet", label: "식이" },
  activity: { id: "activity", label: "운동" },
} satisfies Record<string, HealthMetric>;

// 배열 순서대로 왼쪽·오른쪽에 배치한다. 지표를 합치려면 카드 하나의
// metrics에 [metrics.stress, metrics.condition]처럼 함께 넣으면 된다.
export const homeHealthCards: readonly HealthSummaryCard[] = [
  { id: "stress", title: "스트레스", icon: Zap, metrics: [metrics.stress], href: "/records/stress" },
  { id: "condition", title: "컨디션", icon: Heart, metrics: [metrics.condition] },
  { id: "pressure", title: "혈압", icon: Activity, metrics: [metrics.pressure] },
  {
    id: "glucose",
    title: "혈당",
    icon: Droplet,
    metrics: [metrics.glucose],
    href: "/records/glucose",
  },
  { id: "diet", title: "식이", icon: Utensils, metrics: [metrics.diet] },
  { id: "activity", title: "운동", icon: Footprints, metrics: [metrics.activity] },
];
