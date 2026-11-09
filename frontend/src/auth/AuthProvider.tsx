
import {
  createContext,
  useCallback,
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

export type AuthStatus =
  | "loading"
  | "authenticated"
  | "unauthenticated";

type AuthContextType = {
  token: string | null;
  member: AuthMember | null;
  authStatus: AuthStatus;

  login: (id: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in?: number;
};

type AuthSession = {
  token: string;
  member: AuthMember;
  expiresAt: number;
};

const AuthContext =
  createContext<AuthContextType | null>(null);

// Access Token 만료 1분 전에 갱신
const REFRESH_BUFFER_MS = 60 * 1000;

// 서버의 기존 Access Token 만료 시간: 30분
const DEFAULT_EXPIRES_IN_SECONDS = 30 * 60;

// 인증 복구 및 자동 갱신 요청 중복 방지
let pendingRefresh: Promise<TokenResponse> | null = null;

// ==========================================
// 2. 공통 API 함수
// ==========================================

function validateToken(data: TokenResponse): string {
  if (
    typeof data.access_token !== "string" ||
    !data.access_token ||
    data.token_type?.toLowerCase() !== "bearer"
  ) {
    throw new Error(
      "서버에서 올바른 인증 정보를 받지 못했습니다.",
    );
  }

  return data.access_token;
}

function getTokenExpiresAt(data: TokenResponse): number {
  const expiresIn =
    typeof data.expires_in === "number" &&
    Number.isFinite(data.expires_in) &&
    data.expires_in > 0
      ? data.expires_in
      : DEFAULT_EXPIRES_IN_SECONDS;

  return Date.now() + expiresIn * 1000;
}

async function fetchMember(
  token: string,
): Promise<AuthMember> {
  const response = await fetch("/api/auth/me", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(
      "로그인 사용자 정보를 가져오지 못했습니다.",
    );
  }

  const member: AuthMember = await response.json();

  if (
    !Number.isInteger(member.member_id) ||
    member.member_id < 1 ||
    typeof member.login_id !== "string" ||
    !member.login_id
  ) {
    throw new Error(
      "사용자 정보가 올바르지 않습니다.",
    );
  }

  return member;
}

// ------------------------------------------
// Refresh Token 쿠키로 Access Token 재발급
// ------------------------------------------

function requestRefresh(): Promise<TokenResponse> {
  if (pendingRefresh !== null) {
    return pendingRefresh;
  }

  const promise = (async () => {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(
        "로그인 세션을 갱신하지 못했습니다.",
      );
    }

    const data: TokenResponse = await response.json();
    validateToken(data);

    return data;
  })();

  pendingRefresh = promise;

  // 요청이 끝나면 중복 방지 상태 해제
  void promise.then(
    () => {
      if (pendingRefresh === promise) {
        pendingRefresh = null;
      }
    },
    () => {
      if (pendingRefresh === promise) {
        pendingRefresh = null;
      }
    },
  );

  return promise;
}

// ==========================================
// 3. AuthProvider
// ==========================================

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  // JWT는 메모리에만 저장
  const [token, setToken] =
    useState<string | null>(null);

  const [member, setMember] =
    useState<AuthMember | null>(null);

  // 앱 최초 실행 시 로그인 복구 여부 확인
  const [authStatus, setAuthStatus] =
    useState<AuthStatus>("loading");

  // 인증 요청 간 상태 충돌 방지
  const authGeneration = useRef(0);

  // 자동 갱신 타이머
  const refreshTimer = useRef<
    ReturnType<typeof setTimeout> | null
  >(null);

  // Access Token 만료 예상 시각
  const tokenExpiresAt = useRef<number | null>(null);

  // ----------------------------------------
  // 4. 타이머 및 상태 관리
  // ----------------------------------------

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimer.current !== null) {
      clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    }
  }, []);

  const clearAuthState = useCallback(() => {
    clearRefreshTimer();

    tokenExpiresAt.current = null;

    setToken(null);
    setMember(null);
    setAuthStatus("unauthenticated");
  }, [clearRefreshTimer]);

  const applySession = useCallback(
    (session: AuthSession) => {
      setToken(session.token);
      setMember(session.member);
      tokenExpiresAt.current = session.expiresAt;
      setAuthStatus("authenticated");
    },
    [],
  );

  // ----------------------------------------
  // 5. Refresh Token을 이용한 JWT 갱신
  // ----------------------------------------

  const refreshAccessToken = useCallback(
    async (): Promise<string | null> => {
      const generation = authGeneration.current;

      try {
        const data = await requestRefresh();

        if (authGeneration.current !== generation) {
          return null;
        }

        const newToken = validateToken(data);

        // Refresh 세션이 유효해도 회원이 삭제됐거나
        // 비활성화된 상태라면 인증을 복구하지 않는다.
        const newMember = await fetchMember(newToken);

        if (authGeneration.current !== generation) {
          return null;
        }

        applySession({
          token: newToken,
          member: newMember,
          expiresAt: getTokenExpiresAt(data),
        });

        return newToken;
      } catch {
        if (authGeneration.current === generation) {
          clearAuthState();
        }

        return null;
      }
    },
    [applySession, clearAuthState],
  );

  // ----------------------------------------
  // 6. 앱 최초 실행 시 자동 로그인
  // ----------------------------------------

  useEffect(() => {
    // React StrictMode에서도 한 번의 Refresh 요청을
    // 공유하도록 requestRefresh()가 처리한다.
    const generation = authGeneration.current;
    let active = true;

    async function initializeAuth() {
      try {
        const data = await requestRefresh();
        const newToken = validateToken(data);
        const newMember = await fetchMember(newToken);

        if (
          !active ||
          authGeneration.current !== generation
        ) {
          return;
        }

        applySession({
          token: newToken,
          member: newMember,
          expiresAt: getTokenExpiresAt(data),
        });
      } catch {
        if (
          !active ||
          authGeneration.current !== generation
        ) {
          return;
        }

        clearAuthState();
      }
    }

    void initializeAuth();

    return () => {
      active = false;
    };
  }, [applySession, clearAuthState]);

  // ----------------------------------------
  // 7. Access Token 만료 전 자동 갱신
  // ----------------------------------------

  useEffect(() => {
    clearRefreshTimer();

    if (
      authStatus !== "authenticated" ||
      !token ||
      tokenExpiresAt.current === null
    ) {
      return;
    }

    const remainingMs =
      tokenExpiresAt.current -
      Date.now() -
      REFRESH_BUFFER_MS;

    // 만료 시간이 임박했다면 즉시 갱신
    const delay = Math.max(0, remainingMs);

    refreshTimer.current = setTimeout(() => {
      void refreshAccessToken();
    }, delay);

    return clearRefreshTimer;
  }, [
    token,
    authStatus,
    refreshAccessToken,
    clearRefreshTimer,
  ]);

  // ----------------------------------------
  // 8. 로그인
  // ----------------------------------------

  const login = useCallback(
    async (id: string, password: string): Promise<void> => {
      authGeneration.current += 1;
      const generation = authGeneration.current;

      clearAuthState();

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
        throw new Error(
          "아이디 또는 비밀번호를 확인해 주세요.",
        );
      }

      const data: TokenResponse = await response.json();
      const newToken = validateToken(data);
      const newMember = await fetchMember(newToken);

      if (authGeneration.current !== generation) {
        return;
      }

      applySession({
        token: newToken,
        member: newMember,
        expiresAt: getTokenExpiresAt(data),
      });
    },
    [applySession, clearAuthState],
  );

  // ----------------------------------------
  // 9. 로그아웃
  // ----------------------------------------

  const logout = useCallback(async (): Promise<void> => {
    authGeneration.current += 1;

    // 기존 자동 갱신 타이머 중지
    clearRefreshTimer();

    // 서버에 Refresh Token 세션 폐기 요청
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(
        "서버 로그아웃에 실패했습니다. 다시 시도해 주세요.",
      );
    }

    // 로그아웃 완료 후 클라이언트 인증 정보 제거
    clearAuthState();
  }, [clearAuthState, clearRefreshTimer]);

  // ----------------------------------------
  // 10. Context 제공
  // ----------------------------------------

  return (
    <AuthContext.Provider
      value={{
        token,
        member,
        authStatus,
        login,
        logout,
        refreshAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ==========================================
// 11. 인증 Context Hook
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
