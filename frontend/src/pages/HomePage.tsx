
import { Link } from "react-router";

import {
  UserRound,
  ChevronRight,
  Sparkles,
  Info,
  Droplets,
} from "lucide-react";

export default function HomePage() {
  /*
   * 현재는 인증 및 실사용 혈당 통계 API가
   * 연결되지 않은 상태다.
   *
   * Figma에 있는 TIR 62%, 평균 혈당 152 등의
   * 샘플 수치를 실제 사용자 데이터처럼 표시하지 않는다.
   *
   * 추후 API 연동 시 이 부분을 사용자별
   * 실제 조회 결과로 대체할 예정이다.
   */

  return (
    <div className="home-page">

      {/* 1. 사용자 인사 영역 */}
      <section className="greeting-section">
        <div>
          <h2>FITIF에 오신 것을 환영합니다</h2>
          <p>오늘도 건강한 하루를 기록해 보세요.</p>
        </div>

        <div className="profile-icon">
          <UserRound size={28} />
        </div>
      </section>

      {/* 2. 혈당 정보 카드 */}
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

        <div className="empty-state">
          <div className="empty-icon">
            <Droplets size={34} />
          </div>

          <strong>아직 연결된 혈당 정보가 없어요</strong>

          <p>
            로그인과 혈당 조회 API가 연결되면
            이곳에 내 기록이 표시됩니다.
          </p>
        </div>

        <Link
          className="primary-button"
          to="/glucose"
        >
          혈당 관리 화면으로 이동
        </Link>
      </section>

      {/* 3. AI 추천 질문 영역 */}
      <Link
        to="/chat"
        className="quick-action-card"
      >
        <Sparkles size={24} />

        <div className="quick-action-text">
          <strong>오늘의 실천과 AI 추천 질문</strong>
          <span>운동·식단 목표를 이어가 보세요</span>
        </div>

        <ChevronRight size={20} />
      </Link>

      {/* 4. 의료정보 안내 */}
      <div className="medical-notice">
        <Info size={20} />

        <p>
          FITIF는 건강관리를 돕는 정보를 제공하며,
          의학적 진단이나 치료를 대신하지 않습니다.
        </p>
      </div>
    </div>
  );
}
