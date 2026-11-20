import { ChevronRight, Info, Mic, Send } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { homeHealthCards, type HealthSummaryCard } from "./homeHealthCards";
import { getSummaryPeriod, summaryPeriods } from "./homeSummaryPeriod";
import "./HomePage.css";

function SummaryMetric({
  metric,
  showLabel,
}: {
  metric: HealthSummaryCard["metrics"][number];
  showLabel: boolean;
}) {
  const { label, Preview } = metric;
  const [period, setPeriod] = useState(() => getSummaryPeriod(1));

  return (
    <div className="home-card-metric">
      {showLabel && <span className="home-card-label">{label}</span>}
      <div className="home-card-periods" role="group" aria-label={`${label} 조회 기간`}>
        {summaryPeriods.map(({ days, label: periodLabel }) => (
          <button
            key={days}
            type="button"
            aria-pressed={period.days === days}
            onClick={() => setPeriod(getSummaryPeriod(days))}
          >
            {periodLabel}
          </button>
        ))}
      </div>
      {Preview ? <Preview period={period} /> : <span className="home-card-status">연동 전</span>}
    </div>
  );
}

function SummaryCard({ card }: { card: HealthSummaryCard }) {
  const { icon: Icon, title, metrics, href } = card;
  const titleContent = (
    <>
      <span className="home-card-icon"><Icon size={18} aria-hidden="true" /></span>
      <span>{title}</span>
    </>
  );

  return (
    <article className="home-summary-card">
      <h2>
        {href ? (
          <Link to={href} className="home-card-detail-link">
            {titleContent}
            <ChevronRight size={13} aria-hidden="true" />
          </Link>
        ) : titleContent}
      </h2>
      <div className="home-card-metrics">
        {metrics.map((metric) => (
          <SummaryMetric key={metric.id} metric={metric} showLabel={metrics.length > 1} />
        ))}
      </div>
    </article>
  );
}

export default function HomePage() {
  const { member } = useAuth();
  const displayName = member?.name?.trim() || member?.login_id || "회원";

  return (
    <div className="home-page home-summary">
      <header className="home-summary-heading">
        <h1 id="health-summary-title">건강 요약</h1>
        <p>안녕하세요, {displayName}님!</p>
      </header>

      {homeHealthCards.length > 0 && (
        <section className="home-summary-grid" aria-labelledby="health-summary-title">
          <div className="home-summary-figure" aria-hidden="true">
            <svg viewBox="0 0 110 300" focusable="false">
              <path d="M55 7c-14 0-22 10-22 23 0 10 5 18 11 23v10L26 71c-8 4-12 12-14 23L5 147c-2 15-3 27-3 35 0 5 7 7 9 1l9-41 6-30 1 58 5 40 2 67-5 10c-2 4 0 7 4 7h11c4 0 6-3 6-7l2-73 3-34 3 34 2 73c0 4 2 7 6 7h11c4 0 6-3 4-7l-5-10 2-67 5-40 1-58 6 30 9 41c2 6 9 4 9-1 0-8-1-20-3-35l-7-53c-2-11-6-19-14-23l-18-8V53c6-5 11-13 11-23 0-13-8-23-22-23Z" />
            </svg>
          </div>
          {homeHealthCards.map((card) => <SummaryCard key={card.id} card={card} />)}
        </section>
      )}

      <Link to="/chat" className="home-summary-chat">
        <span className="home-chat-icon"><Mic size={21} aria-hidden="true" /></span>
        <strong>FITIF AI에 건강 이야기하기</strong>
        <Send size={19} aria-hidden="true" />
      </Link>

      <div className="medical-notice">
        <Info size={20} aria-hidden="true" />
        <p>FITIF는 건강 관리를 돕는 정보를 제공하며, 의료 전문가의 진단이나 치료를 대신하지 않습니다.</p>
      </div>
    </div>
  );
}
