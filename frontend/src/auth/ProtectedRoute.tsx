
import { Navigate, Outlet } from "react-router";
import { useAuth } from "./AuthProvider";

export default function ProtectedRoute() {
  const { authStatus } = useAuth();

  // 쿠키를 이용한 로그인 복구가 끝나기 전에는
  // 로그인 페이지로 이동시키지 않는다.
  if (authStatus === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          minHeight: "60vh",
          alignItems: "center",
          justifyContent: "center",
          color: "#168a73",
        }}
      >
        로그인 상태를 확인하고 있습니다...
      </div>
    );
  }

  if (authStatus === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
