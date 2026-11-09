
"""
FITIF 회원가입 및 로그인 API

POST /api/auth/register : 신규 계정 생성
POST /api/auth/login    : 로그인 후 JWT 발급
GET  /api/auth/me       : 인증된 사용자 조회
"""
import logging
logger = logging.getLogger(__name__)

from typing import Literal
import os
import re
from datetime import datetime, timedelta, timezone

import jwt
import psycopg2

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from ..refresh_tokens import (
    create_refresh_session,
    rotate_refresh_session,
    revoke_refresh_session,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from pwdlib import PasswordHash

from ..database import get_connection, get_write_connection


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# 비밀번호는 Argon2 방식으로 해싱한다.
password_hasher = PasswordHash.recommended()

# Authorization: Bearer <토큰> 헤더를 읽는다.
bearer_scheme = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "fitif-api"
JWT_AUDIENCE = "fitif-web"
JWT_EXPIRE_MINUTES = 30

# ------------------------------------------
# Refresh Token 쿠키 설정
# ------------------------------------------

REFRESH_COOKIE_NAME = "fitif_refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"

# 개발 환경에서는 localhost HTTP를 사용한다.
# 운영 환경에서는 반드시 HTTPS + Secure 쿠키 사용.
COOKIE_SECURE = (
    os.getenv("FITIF_ENV", "production").lower()
    != "development"
)

# 인증 API에 요청할 수 있는 프론트엔드 출처
# 운영 배포 전 실제 서비스 주소로 설정해야 한다.
AUTH_ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.getenv(
        "AUTH_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
}


def verify_auth_origin(request: Request) -> None:
    """
    쿠키를 사용하는 인증 요청의 출처를 검증한다.

    Origin 헤더가 없거나 허용 목록에 없으면 거부한다.
    """
    origin = request.headers.get("origin")

    if origin not in AUTH_ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=403,
            detail="허용되지 않은 요청 출처입니다.",
        )


def set_refresh_cookie(
    response: Response,
    token: str,
    expires_at: datetime,
) -> None:
    """HttpOnly Refresh Token 쿠키를 설정한다."""

    seconds_remaining = int(
        (expires_at - datetime.now(timezone.utc)).total_seconds()
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max(0, seconds_remaining),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Refresh Token 쿠키를 삭제한다."""

    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )



# ------------------------------------------
# 1. 요청 및 응답 데이터
# ------------------------------------------
from typing import Literal

class RegisterRequest(BaseModel):
    # 회원가입 기본 정보
    login_id: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=9, max_length=128)

    # 사용자 개인정보
    name: str = Field(min_length=1, max_length=50)
    sex: Literal["M", "F"]
    birth_year: int = Field(ge=1900, le=2026)

    # 개인정보 수집·이용 동의는 반드시 True
    privacy_agreed: Literal[True]

    @field_validator("login_id")
    @classmethod
    def validate_login_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9]{4,20}", value):
            raise ValueError(
                "아이디는 영문 소문자와 숫자 4~20자여야 합니다."
            )
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("이름을 입력해 주세요.")

        return value


class LoginRequest(BaseModel):
    login_id: str
    password: str


class MemberResponse(BaseModel):
    member_id: int
    login_id: str
    name: str | None = None

# ------------------------------------------
# 2. 공통 인증 처리
# ------------------------------------------

def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured securely"
        )

    return secret


def create_access_token(member_id: int) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        # JWT sub는 문자열로 저장한다.
        "sub": str(member_id),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효한 로그인이 필요합니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_member(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:
    """
    JWT 검증 후 실제 DB 회원을 조회한다.

    클라이언트가 직접 전달한 member_id를
    로그인 사용자 ID로 신뢰하지 않는다.
    """
    if credentials is None:
        raise unauthorized()

    try:
        payload = jwt.decode(
            credentials.credentials,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "require": ["sub", "exp", "iss", "aud"]
            },
        )

        member_id = int(payload["sub"])

        if member_id < 1:
            raise ValueError("Invalid member id")

    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise unauthorized()

    try:
        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT member_id, login_id, name
                        FROM public.member
                        WHERE member_id = %s
                          AND login_id IS NOT NULL
                        """,
                        (member_id,),
                    )
                    row = cur.fetchone()
        finally:
            conn.close()

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from exc

    if row is None:
        raise unauthorized()

    return {
        "member_id": row[0],
        "login_id": row[1],
	"name": row[2],
    }


# ------------------------------------------
# 3. 회원가입
# ------------------------------------------

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=MemberResponse,
)
def register(data: RegisterRequest):
    # 비밀번호 원문은 DB에 저장하지 않는다.
    hashed_password = password_hasher.hash(data.password)

    try:
        conn = get_write_connection()

        try:
            with conn:
                with conn.cursor() as cur:
                    # member_id는 PostgreSQL에서 자동 생성된다.
                    # 기존 샘플 사용자의 pseudo_code는
                    # 신규 계정에 사용하지 않는다.
                    cur.execute(
                        """
                        INSERT INTO public.member (
                            login_id,
                            password_hash,
                            name,
                            sex,
                            birth_year
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING member_id, login_id
                        """,
                        (
                            data.login_id,
                            hashed_password,
                            data.name,
                            data.sex,
                            data.birth_year,
                        ),
                    )
                    row = cur.fetchone()
        finally:
            conn.close()

    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=409,
            detail="이미 사용 중인 아이디입니다.",
        ) from exc

    except psycopg2.Error as exc:
        # PostgreSQL 오류 코드를 서버 로그에만 기록
        logger.error(
            "Registration DB error: SQLSTATE=%s, TYPE=%s",
            exc.pgcode,
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=503,
            detail="회원가입 처리 중 DB 오류가 발생했습니다.",
        ) from exc

    return {
        "member_id": row[0],
        "login_id": row[1],
	"name" : data.name,
    }


# ------------------------------------------
# 4. 로그인
# ------------------------------------------

@router.post("/login")
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
):
    verify_auth_origin(request)
    try:
        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT member_id, password_hash
                        FROM public.member
                        WHERE login_id = %s
                        """,
                        (data.login_id,),
                    )
                    row = cur.fetchone()
        finally:
            conn.close()

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from exc

    # 사용자 ID와 비밀번호 중 무엇이 틀렸는지
    # 외부에 구체적으로 알리지 않는다.
    if row is None or row[1] is None:
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    member_id, hashed_password = row

    try:
        valid = password_hasher.verify(
            data.password,
            hashed_password,
        )
    except (ValueError, TypeError):
        valid = False

    if not valid:
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )


    # 기존 Access Token 발급
    token = create_access_token(member_id)

    # 자동 로그인 세션 생성 및 쿠키 설정
    try:
        refresh_token, refresh_expires_at = (
            create_refresh_session(member_id)
        )
    except psycopg2.Error as exc:
        logger.error(
            "Refresh session creation failed: SQLSTATE=%s",
            exc.pgcode,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 세션 생성 중 오류가 발생했습니다.",
        ) from exc

    set_refresh_cookie(
        response,
        refresh_token,
        refresh_expires_at,
    )

    # 기존 React에서 사용하던 응답 형식 유지
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }



# ------------------------------------------
# 5. 로그인 사용자 정보
# ------------------------------------------

@router.get("/me", response_model=MemberResponse)
def get_me(
    member: dict = Depends(get_current_member),
):
    return member


# ------------------------------------------
# 6. Refresh Token을 통한 자동 로그인
# ------------------------------------------

@router.post("/refresh")
def refresh_login(
    request: Request,
    response: Response,
):
    verify_auth_origin(request)

    refresh_token = request.cookies.get(
        REFRESH_COOKIE_NAME
    )

    if not refresh_token:
        raise unauthorized()

    try:
        result = rotate_refresh_session(refresh_token)
    except psycopg2.Error as exc:
        logger.error(
            "Refresh DB error: SQLSTATE=%s",
            exc.pgcode,
        )
        raise HTTPException(
            status_code=503,
            detail="로그인 복구 중 DB 오류가 발생했습니다.",
        ) from exc

    if result is None:
        clear_refresh_cookie(response)
        raise unauthorized()

    new_token, expires_at, member_id = result

    # 새로운 Refresh Token 쿠키로 교체
    set_refresh_cookie(
        response,
        new_token,
        expires_at,
    )

    # 기존과 동일한 Access Token 발급
    return {
        "access_token": create_access_token(member_id),
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }


# ------------------------------------------
# 7. 로그아웃
# ------------------------------------------

@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
):
    verify_auth_origin(request)

    refresh_token = request.cookies.get(
        REFRESH_COOKIE_NAME
    )

    if refresh_token:
        try:
            revoke_refresh_session(refresh_token)
        except psycopg2.Error as exc:
            logger.error(
                "Logout DB error: SQLSTATE=%s",
                exc.pgcode,
            )
            raise HTTPException(
                status_code=503,
                detail="로그아웃 처리 중 DB 오류가 발생했습니다.",
            ) from exc

    clear_refresh_cookie(response)
    response.status_code = 204
    return None
