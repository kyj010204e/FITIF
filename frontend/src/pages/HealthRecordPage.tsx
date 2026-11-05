
import { Link } from "react-router";

export default function HealthRecordPage() {
  return (
    <section className="placeholder-page">
      <h2>내 건강기록</h2>
      <p>혈당과 의료문서 기록을 관리하는 공간입니다.</p>

      <Link className="primary-button" to="/glucose">
        혈당 기록 확인하기
      </Link>
    </section>
  );
}
