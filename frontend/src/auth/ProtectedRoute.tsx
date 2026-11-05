
import { Navigate, Outlet } from "react-router";
import { useAuth } from "./AuthProvider";

// 로그인되지 않은 사용자는 앱 내부 페이지를 볼 수 없다.
export default function ProtectedRoute() {
  const { token } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
