
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ==========================================
// 1. 인증 데이터 타입
// ==========================================

export type AuthMember = {
  member_id: number;
  login_id: string;
  name: string | null;
};

type AuthStatus =
  | "loading"
  | "authenticated"
  | "unauthenticated";

type AuthContextType = {
  token: string | null;
  member: AuthMember | null;
  authStatus: AuthStatus;
  login: (id: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in?: number;
};

type AuthSession = {
  token: string;
  member: AuthMember;
};

const AuthContext = createContext<AuthContextType | null>(null);

// ==========================================
// 2. 응답 데이터 검증
// ==========================================

function validateToken(data: TokenResponse): string {
  if (
    typeof data.access_token !== "string" ||
    !data.access_token ||
    data.token_type?.toLowerCase() !== "bearer"
  ) {
    throw new Error("서버에서 올바른 인증 정보를 받지 못했습니다.");
  }

  return data.access_token;
}

async function fetchMember(token: string): Promise<AuthMember> {
  const response = await fetch("/api/auth/me", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("로그인 사용자 정보를 가져오지 못했습니다.");
  }

  const member: AuthMember = await response.json();

  if (
    !Number.isInteger(member.member_id) ||
    member.member_id < 1 ||
    typeof member.login_id !== "string" ||
    !member.login_id
  ) {
    throw new Error("사용자 정보가 올바르지 않습니다.");
  }

  return member;
}

// ==========================================
// 3. 로그인 복구
// ==========================================

// React StrictMode에서 개발 중 초기 effect가 두 번
// 실행되더라도 Refresh 요청은 하나만 보내도록 공유한다.
let pendingRestore: Promise<AuthSession> | null = null;

function restoreSession(): Promise<AuthSession> {
  if (pendingRestore) {
    return pendingRestore;
  }

  const task = async (): Promise<AuthSession> => {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error("로그인 세션을 복구하지 못했습니다.");
    }

    const data: TokenResponse = await response.json();
    const token = validateToken(data);
    const member = await fetchMember(token);

    return { token, member };
  };

  const promise = task();
  pendingRestore = promise;

  // 성공과 실패 양쪽에서 공유 요청 상태를 정리
  void promise.then(
    () => {
      if (pendingRestore === promise) {
        pendingRestore = null;
      }
    },
    () => {
      if (pendingRestore === promise) {
        pendingRestore = null;
      }
    },
  );

  return promise;
}

// ==========================================
// 4. 인증 상태 관리
// ==========================================

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [token, setToken] = useState<string | null>(null);
  const [member, setMember] = useState<AuthMember | null>(null);

  // 처음 실행할 때는 인증 복구가 끝날 때까지 대기
  const [authStatus, setAuthStatus] =
    useState<AuthStatus>("loading");

  // 오래된 비동기 요청이 최신 인증 상태를 덮어쓰지
  // 않도록 요청 세대를 관리한다.
  const authGeneration = useRef(0);

  // ========================================
  // 5. 앱 시작 시 자동 로그인
  // ========================================

  useEffect(() => {
    let active = true;
    const generation = authGeneration.current;

    async function initializeAuth() {
      try {
        const session = await restoreSession();

        if (
          !active ||
          authGeneration.current !== generation
        ) {
          return;
        }

        setToken(session.token);
        setMember(session.member);
        setAuthStatus("authenticated");
      } catch {
        if (
          !active ||
          authGeneration.current !== generation
        ) {
          return;
        }

        setToken(null);
        setMember(null);
        setAuthStatus("unauthenticated");
      }
    }

    void initializeAuth();

    return () => {
      active = false;
    };
  }, []);

  // ========================================
  // 6. 로그인
  // ========================================

  async function login(id: string, password: string) {
    authGeneration.current += 1;
    const generation = authGeneration.current;

    setToken(null);
    setMember(null);
    setAuthStatus("unauthenticated");

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
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

      const data: TokenResponse = await response.json();
      const newToken = validateToken(data);
      const newMember = await fetchMember(newToken);

      if (authGeneration.current !== generation) {
        return;
      }

      setToken(newToken);
      setMember(newMember);
      setAuthStatus("authenticated");
    } catch (error) {
      if (authGeneration.current === generation) {
        setToken(null);
        setMember(null);
        setAuthStatus("unauthenticated");
      }

      throw error;
    }
  }

  // ========================================
  // 7. 로그아웃
  // ========================================

  async function logout() {
    authGeneration.current += 1;

    // 서버 세션 폐기를 먼저 확인한다.
    // 실패하면 성공한 로그아웃처럼 처리하지 않는다.
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(
        "서버 로그아웃에 실패했습니다. 다시 시도해 주세요.",
      );
    }

    // 서버가 Refresh 쿠키를 삭제한 뒤
    // React 메모리의 JWT와 회원정보도 제거한다.
    setToken(null);
    setMember(null);
    setAuthStatus("unauthenticated");
  }

  // ========================================
  // 8. Context 제공
  // ========================================

  return (
    <AuthContext.Provider
      value={{
        token,
        member,
        authStatus,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ==========================================
// 9. 공통 인증 Hook
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
