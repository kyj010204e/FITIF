
"""
FITIF Refresh Token 관리

- 최초 로그인 세션 생성
- Refresh Token SHA-256 해시 저장
- Refresh Token 회전
- 로그아웃 시 세션 폐기
- 폐기된 토큰 재사용 탐지

실제 토큰은 DB에 저장하지 않는다.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from .database import get_write_connection


REFRESH_EXPIRE_DAYS = 7


def _token_hash(token: str) -> str:
    """Refresh Token의 SHA-256 해시를 반환한다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    """예측하기 어려운 Refresh Token을 생성한다."""
    return secrets.token_urlsafe(48)


def create_refresh_session(member_id: int):
    """
    최초 로그인 성공 시 Refresh 세션을 생성한다.

    반환값:
        (refresh_token, expires_at)
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=REFRESH_EXPIRE_DAYS)

    token = _new_token()
    family_id = uuid.uuid4()

    conn = get_write_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.auth_refresh_session (
                        member_id,
                        family_id,
                        token_hash,
                        created_at,
                        expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        member_id,
                        str(family_id),
                        _token_hash(token),
                        now,
                        expires_at,
                    ),
                )
    finally:
        conn.close()

    return token, expires_at


def rotate_refresh_session(refresh_token: str):
    """
    기존 Refresh Token을 검증하고 회전한다.

    정상:
        (new_token, expires_at, member_id)

    무효·만료·재사용:
        None

    이전 토큰이 재사용되면 해당 family를 폐기한다.
    """
    token_hash = _token_hash(refresh_token)
    now = datetime.now(timezone.utc)

    conn = get_write_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        session_id,
                        member_id,
                        family_id,
                        expires_at,
                        revoked_at
                    FROM public.auth_refresh_session
                    WHERE token_hash = %s
                    FOR UPDATE
                    """,
                    (token_hash,),
                )

                row = cur.fetchone()

                if row is None:
                    return None

                (
                    session_id,
                    member_id,
                    family_id,
                    expires_at,
                    revoked_at,
                ) = row

                # 이미 폐기된 토큰의 재사용 감지
                if revoked_at is not None:
                    cur.execute(
                        """
                        UPDATE public.auth_refresh_session
                        SET revoked_at = COALESCE(revoked_at, %s)
                        WHERE family_id = %s
                        """,
                        (now, family_id),
                    )
                    return None

                # 최초 로그인 시점 기준 최대 7일
                if expires_at <= now:
                    cur.execute(
                        """
                        UPDATE public.auth_refresh_session
                        SET revoked_at = %s
                        WHERE session_id = %s
                        """,
                        (now, session_id),
                    )
                    return None

                new_token = _new_token()

                # 새 토큰은 기존 세션 만료일을 그대로 사용
                cur.execute(
                    """
                    INSERT INTO public.auth_refresh_session (
                        member_id,
                        family_id,
                        token_hash,
                        created_at,
                        expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING session_id
                    """,
                    (
                        member_id,
                        family_id,
                        _token_hash(new_token),
                        now,
                        expires_at,
                    ),
                )

                new_session_id = cur.fetchone()[0]

                # 기존 토큰 폐기 및 대체 토큰 연결
                cur.execute(
                    """
                    UPDATE public.auth_refresh_session
                    SET
                        revoked_at = %s,
                        replaced_by = %s
                    WHERE session_id = %s
                    """,
                    (now, new_session_id, session_id),
                )

                return new_token, expires_at, member_id

    finally:
        conn.close()


def revoke_refresh_session(refresh_token: str):
    """
    로그아웃 시 해당 로그인 family 전체를 폐기한다.
    """
    token_hash = _token_hash(refresh_token)
    now = datetime.now(timezone.utc)

    conn = get_write_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT family_id
                    FROM public.auth_refresh_session
                    WHERE token_hash = %s
                    """,
                    (token_hash,),
                )

                row = cur.fetchone()

                if row is None:
                    return

                family_id = row[0]

                cur.execute(
                    """
                    UPDATE public.auth_refresh_session
                    SET revoked_at = COALESCE(revoked_at, %s)
                    WHERE family_id = %s
                    """,
                    (now, family_id),
                )
    finally:
        conn.close()
