
import { Link } from "react-router";

function GlucosePage() {
  return (
    <main style={{ padding: "40px" }}>
      <h1>혈당 관리</h1>

      <p>혈당 기록 입력 및 조회 기능을 구현할 예정입니다.</p>

      <Link to="/home">홈으로 돌아가기</Link>
    </main>
  );
}

export default GlucosePage;
