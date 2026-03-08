from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.logging import logger
from app.models.user import User


ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        return None


async def get_user_by_email(
    db: AsyncSession,
    email: str,
) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(
    db: AsyncSession,
    user_id: int,
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    existing = await get_user_by_email(db, email)
    if existing:
        raise ValueError(f"User with email {email} already exists")

    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("user_created", email=email, user_id=user.id)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    user = await get_user_by_email(db, email)

    if not user:
        logger.warning("login_failed_user_not_found", email=email)
        return None

    if not verify_password(password, user.hashed_password):
        logger.warning("login_failed_wrong_password", email=email)
        return None

    if not user.is_active:
        logger.warning("login_failed_inactive_user", email=email)
        return None

    logger.info("user_authenticated", email=email, user_id=user.id)
    return user