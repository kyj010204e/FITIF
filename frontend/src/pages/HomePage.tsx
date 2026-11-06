
import { Link } from "react-router";

import {
  UserRound,
  ChevronRight,
  Sparkles,
  Info,
  Droplets,
} from "lucide-react";

import { useAuth } from "../auth/AuthProvider";

export default function HomePage() {
  // ==========================================
  // 1. 로그인 사용자 정보
  // ==========================================

  // AuthProvider에서 현재 로그인 사용자 정보를 가져온다.
  const { member } = useAuth();

  // 이름이 저장되어 있으면 이름을 사용한다.
  // 기존 회원처럼 이름이 없으면 로그인 아이디를 사용한다.
  const displayName =
    member?.name?.trim() || member?.login_id || "회원";

  return (
    <div className="home-page">
      {/* ==================================
          2. 사용자 맞춤 인사 영역
          ================================== */}

      <section className="greeting-section">
        <div>
          <h2>안녕하세요, {displayName}님!</h2>

          <p>
            오늘도 FITIF와 함께 건강한 하루를 시작하세요.
          </p>
        </div>

        <div className="profile-icon">
          <UserRound size={28} />
        </div>
      </section>

      {/* ==================================
          3. 혈당 정보 카드
          ================================== */}

      <section className="health-card">
        <Link
          to="/glucose"
          className="card-heading"
        >
          <h3>내 혈당 기록</h3>
          <ChevronRight size={22} />
        </Link>

        <p className="card-description">
          기록한 혈당을 확인하고 관리해 보세요.
        </p>

        {/*
          현재 홈 화면에는 혈당 통계 API가 연결되지
          않았으므로 임의의 혈당 수치를 표시하지 않는다.

          추후 사용자별 혈당 조회 API를 연결하면
          이 영역을 실제 기록 및 통계로 변경할 예정이다.
        */}
        <div className="empty-state">
          <div className="empty-icon">
            <Droplets size={34} />
          </div>

          <strong>혈당 기록을 확인해 보세요.</strong>

          <p>
            혈당 관리 화면에서 혈당을 기록하고
            기존 기록을 조회할 수 있습니다.
          </p>
        </div>

        <Link
          className="primary-button"
          to="/glucose"
        >
          혈당 관리 화면으로 이동
        </Link>
      </section>

      {/* ==================================
          4. AI 추천 질문 영역
          ================================== */}

      <Link
        to="/chat"
        className="quick-action-card"
      >
        <Sparkles size={24} />

        <div className="quick-action-text">
          <strong>AI 건강 상담</strong>

          <span>
            FITIF AI와 함께 건강 관리에 대해 이야기해 보세요.
          </span>
        </div>

        <ChevronRight size={20} />
      </Link>

      {/* ==================================
          5. 의료정보 안내
          ================================== */}

      <div className="medical-notice">
        <Info size={20} />

        <p>
          FITIF는 건강 관리를 돕는 정보를 제공하며,
          의료 전문가의 진단이나 치료를 대신하지 않습니다.
        </p>
      </div>
    </div>
  );
}
