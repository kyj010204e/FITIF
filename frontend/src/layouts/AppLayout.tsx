
import { Outlet } from "react-router";

import Header from "../components/Header";
import BottomNavigation from "../components/BottomNavigation";

export default function AppLayout() {
  return (
    <div className="app-shell">
      {/* 모든 메인 화면에서 공통으로 보이는 헤더 */}
      <Header />

      {/* 현재 주소에 해당하는 페이지가 표시된다. */}
      <main className="app-content">
        <Outlet />
      </main>

      {/* 하단 메뉴는 페이지가 바뀌어도 유지된다. */}
      <BottomNavigation />
    </div>
  );
}
