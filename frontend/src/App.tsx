
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router";

import {
  AuthProvider,
  useAuth,
} from "./auth/AuthProvider";

import ProtectedRoute from "./auth/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";

import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import HomePage from "./pages/HomePage";
import HealthRecordPage from "./pages/HealthRecordPage";
import GlucosePage from "./pages/GlucosePage";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";

// ==========================================
// 최초 진입 페이지
// ==========================================

function StartPage() {
  const { authStatus } = useAuth();

  // 쿠키를 통한 인증 복구가 끝날 때까지 대기
  if (authStatus === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          minHeight: "100vh",
          alignItems: "center",
          justifyContent: "center",
          color: "#168a73",
        }}
      >
        로그인 상태를 확인하고 있습니다...
      </div>
    );
  }

  return (
    <Navigate
      to={
        authStatus === "authenticated"
          ? "/home"
          : "/login"
      }
      replace
    />
  );
}

// ==========================================
// 라우팅
// ==========================================

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<StartPage />} />

      {/* 누구나 접근 가능한 인증 화면 */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 인증된 사용자만 접근하는 앱 화면 */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/home" element={<HomePage />} />
          <Route path="/records" element={<HealthRecordPage />} />
          <Route path="/glucose" element={<GlucosePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>

      <Route path="*" element={<StartPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
