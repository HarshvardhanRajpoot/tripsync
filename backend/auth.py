"""
Auth utilities: password hashing + JWT tokens.

- Passwords are never stored in plain text — we store a bcrypt hash.
- Login returns a JWT ("access token"). The frontend sends this token
  back on every request that needs to know "who is this user".
"""

import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

# --- Config -----------------------------------------------------------
# In production these should come from environment variables (.env),
# never hardcoded. SECRET_KEY signs the JWTs — if someone else knows
# it, they can forge tokens and impersonate any user.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days, fine for a student project

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password hashing ---------------------------------------------------
def hash_password(plain_password: str) -> str:
    """Turn a plain password into a bcrypt hash to store in the DB."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a login attempt's password against the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT tokens -----------------------------------------------------------
def create_access_token(data: dict) -> str:
    """
    Build a signed JWT containing `data` (we put the user's id in it as "sub").
    The token is opaque to the frontend — it just stores it and sends it back.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Verify a token's signature + expiry and return its payload, or None if invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# --- Getting the current logged-in user ------------------------------------
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    """Reads the JWT from the request and figures out which user it belongs to."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user