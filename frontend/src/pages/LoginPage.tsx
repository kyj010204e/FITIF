import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import fitifLogo from "../assets/fitif-logo.png";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, authStatus } = useAuth();

  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(id, password);
      navigate("/home", { replace: true });
    } catch {
      setError("로그인에 실패했습니다. 계정 정보를 확인해 주세요.");
    } finally {
      setLoading(false);
    }
  }
  // 앱 실행 시 Refresh Token으로 인증을 복구하는 동안 대기
  if (authStatus === "loading") {
    return (
      <main className="auth-page">
        <div className="auth-card" role="status">
          <p>로그인 상태를 확인하고 있습니다...</p>
        </div>
      </main>
    );
  }

  // 이미 로그인된 사용자는 로그인 화면 대신 홈으로 이동
  if (authStatus === "authenticated") {
    return <Navigate to="/home" replace />;
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img
            src={fitifLogo}
            alt="FITIF 로고"
            className="auth-brand-logo"
          />
          <p className="auth-brand-text">
            당신의 건강한 일상을 함께합니다.
          </p>
        </div>


        <form onSubmit={handleSubmit}>
          <label htmlFor="login-id">아이디</label>
          <input
            id="login-id"
            type="text"
            autoComplete="username"
            value={id}
            onChange={(e) => setId(e.target.value)}
            required
          />

          <label htmlFor="login-password">비밀번호</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && <p className="auth-error">{error}</p>}

          <button
            className="primary-button"
            type="submit"
            disabled={loading}
          >
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <p className="auth-footer">
          아직 계정이 없으신가요? <Link to="/register">회원가입</Link>
        </p>
      </div>
    </main>
  );
}