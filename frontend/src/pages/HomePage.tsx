import { Link } from "react-router";
import { UserRound, ChevronRight, Sparkles, Info } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import RecentGlucosePreview from "../components/RecentGlucosePreview";

export default function HomePage() {
  const { member } = useAuth();

  // 이름이 없으면 로그인 아이디를 표시한다.
  const displayName =
    member?.name?.trim() || member?.login_id || "회원";

  return (
    <div className="home-page">
      <section className="greeting-section">
        <div>
          <h2>안녕하세요, {displayName}님!</h2>
          <p>오늘도 FITIF와 함께 건강한 하루를 시작하세요.</p>
        </div>

        <Link to="/profile" className="profile-icon" aria-label="내 정보">
          <UserRound size={28} aria-hidden="true" />
        </Link>
      </section>

      <section className="health-card">
        <Link to="/glucose" className="card-heading">
          <h3>내 혈당 기록</h3>
          <ChevronRight size={22} aria-hidden="true" />
        </Link>

        <p className="card-description">
          기록한 혈당을 확인하고 관리해 보세요.
        </p>

        <RecentGlucosePreview />

        <Link className="primary-button" to="/glucose">
          혈당 관리 화면으로 이동
        </Link>
      </section>

      <Link to="/chat" className="quick-action-card">
        <Sparkles size={24} aria-hidden="true" />

        <div className="quick-action-text">
          <strong>AI 건강 상담</strong>
          <span>FITIF AI와 함께 건강 관리에 대해 이야기해 보세요.</span>
        </div>

        <ChevronRight size={20} aria-hidden="true" />
      </Link>

      <div className="medical-notice">
        <Info size={20} aria-hidden="true" />
        <p>
          FITIF는 건강 관리를 돕는 정보를 제공하며,
          의료 전문가의 진단이나 치료를 대신하지 않습니다.
        </p>
      </div>
    </div>
  );
}