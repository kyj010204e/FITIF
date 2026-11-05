
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import fitifLogo from "../assets/fitif-logo.png";

export default function RegisterPage() {
  const navigate = useNavigate();

  // ==========================================
  // 1. 회원가입 입력값
  // ==========================================

  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");

  const [name, setName] = useState("");
  const [sex, setSex] = useState("");
  const [birthYear, setBirthYear] = useState("");

  // 개인정보 수집·이용 동의 여부
  const [privacyAgreed, setPrivacyAgreed] = useState(false);

  // 오류 메시지 및 API 요청 상태
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // ==========================================
  // 2. 회원가입 처리
  // ==========================================

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    // --------------------------------------
    // 2-1. 아이디 검증
    // --------------------------------------

    if (!/^[a-z0-9]{4,20}$/.test(loginId)) {
      setError("아이디는 영문 소문자·숫자 4~20자로 입력해 주세요.");
      return;
    }

    // --------------------------------------
    // 2-2. 비밀번호 검증
    // --------------------------------------

    if (password.length < 9 || password.length > 128) {
      setError("비밀번호는 9~128자로 입력해 주세요.");
      return;
    }

    if (password !== passwordConfirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }

    // --------------------------------------
    // 2-3. 이름 검증
    // --------------------------------------

    const trimmedName = name.trim();

    if (!trimmedName || trimmedName.length > 50) {
      setError("이름은 1~50자로 입력해 주세요.");
      return;
    }

    // --------------------------------------
    // 2-4. 성별 검증
    // --------------------------------------

    if (sex !== "M" && sex !== "F") {
      setError("성별을 선택해 주세요.");
      return;
    }

    // --------------------------------------
    // 2-5. 출생연도 검증
    // --------------------------------------

    const year = Number(birthYear);
    const currentYear = new Date().getFullYear();

    if (
      !/^\d{4}$/.test(birthYear) ||
      !Number.isInteger(year) ||
      year < 1900 ||
      year > currentYear
    ) {
      setError("올바른 출생연도를 입력해 주세요.");
      return;
    }

    // --------------------------------------
    // 2-6. 개인정보 동의 확인
    // --------------------------------------

    if (!privacyAgreed) {
      setError("개인정보 수집·이용에 동의해 주세요.");
      return;
    }

    // ======================================
    // 3. FastAPI 회원가입 요청
    // ======================================

    setLoading(true);

    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          login_id: loginId,
          password: password,
          name: trimmedName,
          sex: sex,
          birth_year: year,
          privacy_agreed: privacyAgreed,
        }),
      });

      // 아이디 중복
      if (response.status === 409) {
        setError("이미 사용 중인 아이디입니다.");
        return;
      }

      // 기타 오류
      if (!response.ok) {
        let message = `회원가입에 실패했습니다. (HTTP ${response.status})`;

        try {
          const result = await response.json();

          if (typeof result.detail === "string") {
            message = result.detail;
          }
        } catch {
          // JSON이 아닌 오류 응답은 기본 메시지 사용
        }

        setError(message);
        return;
      }

      // 회원가입 성공 → 로그인 화면으로 이동
      navigate("/login", { replace: true });
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  // ==========================================
  // 4. 회원가입 화면
  // ==========================================

  return (
    <main className="auth-page">
      <div className="auth-card">
        {/* FITIF 로고 */}
        <div className="auth-brand">
          <img
            src={fitifLogo}
            alt="FITIF 로고"
            className="auth-brand-logo"
          />
        </div>

        <form onSubmit={handleSubmit}>
          {/* 아이디 */}
          <label htmlFor="register-id">아이디</label>
          <input
            id="register-id"
            type="text"
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            placeholder="영문 소문자·숫자 4~20자"
            autoComplete="username"
            minLength={4}
            maxLength={20}
            required
          />

          {/* 비밀번호 */}
          <label htmlFor="register-password">비밀번호</label>
          <input
            id="register-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="9자 이상 입력"
            autoComplete="new-password"
            minLength={9}
            maxLength={128}
            required
          />

          {/* 비밀번호 확인 */}
          <label htmlFor="register-confirm">
            비밀번호 확인
          </label>
          <input
            id="register-confirm"
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder="비밀번호를 다시 입력해 주세요"
            autoComplete="new-password"
            required
          />

          {/* 이름 */}
          <label htmlFor="register-name">이름</label>
          <input
            id="register-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름을 입력해 주세요"
            autoComplete="name"
            maxLength={50}
            required
          />

          {/* 성별 */}
          <label htmlFor="register-sex">성별</label>
          <select
            id="register-sex"
            value={sex}
            onChange={(e) => setSex(e.target.value)}
            required
          >
            <option value="">성별을 선택해 주세요</option>
            <option value="M">남성</option>
            <option value="F">여성</option>
          </select>

          {/* 출생연도 */}
          <label htmlFor="register-year">출생연도</label>
          <input
            id="register-year"
            type="number"
            value={birthYear}
            onChange={(e) => setBirthYear(e.target.value)}
            placeholder="예: 2001"
            min={1900}
            max={new Date().getFullYear()}
            step={1}
            required
          />

          {/* ==================================
              개인정보 수집·이용 동의
              ================================== */}

          <div className="privacy-consent">
            <label className="privacy-consent-label">
              <input
                type="checkbox"
                checked={privacyAgreed}
                onChange={(e) =>
                  setPrivacyAgreed(e.target.checked)
                }
                required
              />

              <span>
                <strong>
                  [필수] 개인정보 수집·이용 동의
                </strong>

                <small>
                  회원가입 및 계정 관리를 위한 개인정보
                  수집·이용에 동의합니다.
                </small>
              </span>
            </label>

            <details className="privacy-details">
              <summary>개인정보 수집·이용 안내 보기</summary>

              <p>
                <strong>수집 항목</strong>
                {" "}이름, 아이디, 비밀번호 해시,
                성별, 출생연도
              </p>

              <p>
                <strong>이용 목적</strong>
                {" "}회원 식별, 계정 관리 및
                사용자 맞춤형 서비스 제공
              </p>

              <p>
                <strong>보유기간 및 동의 거부 안내</strong>
                {" "}최종 개인정보 처리방침에서
                구체적인 내용을 안내할 예정입니다.
              </p>
            </details>
          </div>

          {/* 오류 메시지 */}
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          {/* 회원가입 버튼 */}
          <button
            type="submit"
            className="primary-button"
            disabled={loading || !privacyAgreed}
          >
            {loading ? "가입 처리 중..." : "회원가입"}
          </button>
        </form>

        {/* 로그인 페이지 이동 */}
        <p className="auth-footer">
          이미 계정이 있으신가요?{" "}
          <Link to="/login">로그인</Link>
        </p>
      </div>
    </main>
  );
}
