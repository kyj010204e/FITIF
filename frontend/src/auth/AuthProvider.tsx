
import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";

type AuthContextType = {
  token: string | null;
  login: (id: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  // 토큰은 메모리에만 저장한다.
  const [token, setToken] = useState<string | null>(null);

  async function login(id: string, password: string) {
    // FastAPI 인증 서버에 실제 로그인 요청
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
      throw new Error("로그인에 실패했습니다.");
    }

    const data: {
      access_token: string;
      token_type: string;
    } = await response.json();

    // JWT 구조 및 사용자 조회 API로 검증
    if (
      !data.access_token ||
      data.token_type.toLowerCase() !== "bearer"
    ) {
      throw new Error("인증 응답이 올바르지 않습니다.");
    }

    const meResponse = await fetch("/api/auth/me", {
      headers: {
        Authorization: `Bearer ${data.access_token}`,
      },
    });

    if (!meResponse.ok) {
      throw new Error("사용자 인증 확인에 실패했습니다.");
    }

    setToken(data.access_token);
  }

  function logout() {
    setToken(null);
  }

  return (
    <AuthContext.Provider value={{ token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("AuthProvider 내부에서 사용해야 합니다.");
  }

  return context;
}
