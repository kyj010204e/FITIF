
import { Navigate, Outlet } from "react-router";
import { useAuth } from "./AuthProvider";

export default function ProtectedRoute() {
  const { authStatus } = useAuth();

  // 로그인 복구 중에는 페이지 이동하지 않는다.
  if (authStatus === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          minHeight: "60vh",
          justifyContent: "center",
          alignItems: "center",
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
