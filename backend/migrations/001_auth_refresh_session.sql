
-- FITIF 자동 로그인 세션 테이블
-- 기존 테이블이 있으면 재생성하지 않는다.

CREATE TABLE IF NOT EXISTS public.auth_refresh_session (
    session_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    member_id BIGINT NOT NULL
        REFERENCES public.member(member_id)
        ON DELETE CASCADE,

    family_id UUID NOT NULL,

    token_hash CHAR(64) NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    rotated_at TIMESTAMPTZ,

    replaced_by BIGINT
        REFERENCES public.auth_refresh_session(session_id),

    CONSTRAINT chk_auth_session_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_member
ON public.auth_refresh_session(member_id);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_family
ON public.auth_refresh_session(family_id);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_expiry
ON public.auth_refresh_session(expires_at);

-- 기존 DB에 테이블이 이미 존재하는 경우를 위한 보완
ALTER TABLE public.auth_refresh_session
ADD COLUMN IF NOT EXISTS rotated_at TIMESTAMPTZ;