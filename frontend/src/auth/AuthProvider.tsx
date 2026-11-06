
import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";

// ==========================================
// 1. 인증 데이터 타입
// ==========================================

// FastAPI /api/auth/me 응답 형식
export type AuthMember = {
  member_id: number;
  login_id: string;
  name: string | null;
};

// 다른 컴포넌트에서 사용할 인증 정보
type AuthContextType = {
  token: string | null;
  member: AuthMember | null;
  login: (id: string, password: string) => Promise<void>;
  logout: () => void;
};

// 인증 데이터를 공유하는 Context
const AuthContext = createContext<AuthContextType | null>(null);

// ==========================================
// 2. 인증 상태 관리
// ==========================================

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  // JWT와 회원정보는 브라우저 메모리에만 보관
  const [token, setToken] = useState<string | null>(null);
  const [member, setMember] = useState<AuthMember | null>(null);

  // ========================================
  // 3. 로그인
  // ========================================

  async function login(id: string, password: string) {
    // 새로운 로그인 시도 전에 기존 인증정보 초기화
    setToken(null);
    setMember(null);

    // ① FastAPI에 로그인 요청
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        login_id: id,
        password,
      }),
    });

    if (!response.ok) {
      throw new Error("아이디 또는 비밀번호를 확인해 주세요.");
    }

    const data: {
      access_token: string;
      token_type: string;
    } = await response.json();

    // ② JWT 발급 결과 확인
    if (
      !data.access_token ||
      data.token_type?.toLowerCase() !== "bearer"
    ) {
      throw new Error("서버에서 올바른 인증 정보를 받지 못했습니다.");
    }

    // ③ JWT로 실제 로그인 사용자 정보 조회
    const meResponse = await fetch("/api/auth/me", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${data.access_token}`,
      },
    });

    if (!meResponse.ok) {
      throw new Error("로그인 사용자 정보를 가져오지 못했습니다.");
    }

    const memberData: AuthMember = await meResponse.json();

    // ④ 최소한의 응답 데이터 검증
    if (
      !Number.isInteger(memberData.member_id) ||
      memberData.member_id < 1 ||
      typeof memberData.login_id !== "string" ||
      !memberData.login_id
    ) {
      throw new Error("사용자 정보가 올바르지 않습니다.");
    }

    // ⑤ 인증에 성공한 경우에만 상태 저장
    setMember(memberData);
    setToken(data.access_token);
  }

  // ========================================
  // 4. 로그아웃
  // ========================================

  function logout() {
    // 토큰과 사용자 정보를 함께 초기화
    setToken(null);
    setMember(null);
  }

  // ========================================
  // 5. Context 제공
  // ========================================

  return (
    <AuthContext.Provider
      value={{
        token,
        member,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ==========================================
// 6. 인증정보를 사용하는 공통 Hook
// ==========================================

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth는 AuthProvider 내부에서 사용해야 합니다.",
    );
  }

  return context;
}
