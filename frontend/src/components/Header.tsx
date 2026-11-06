
import { useLocation } from "react-router";

// 페이지 주소에 따라 상단 제목을 다르게 표시한다.
const pageTitles: Record<string, string> = {
  "/home": "FITIF",
  "/glucose": "혈당 관리",
  "/records": "건강기록",
  "/chat": "FITIF AI",
  "/profile": "내 정보",
};

export default function Header() {
  const location = useLocation();

  // 현재 페이지에 해당하는 제목을 찾는다.
  const title = pageTitles[location.pathname] ?? "FITIF";

  return (
    <header className="app-header">
      <h1>{title}</h1>

      {/* 실제 DB 연결 전에는 실사용 데이터가 아님을 표시 */}
      <span className="demo-badge">
        UI 미리보기
      </span>
    </header>
  );
}
