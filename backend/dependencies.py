"""
Shared FastAPI "dependencies" — reusable pieces that endpoints ask for.

get_db          -> gives an endpoint a database session, closes it after
get_current_user -> reads the "Authorization: Bearer <token>" header,
                     verifies it, and returns the matching User row.
                     Any endpoint that needs to know "who is logged in"
                     just adds `current_user: models.User = Depends(get_current_user)`
                     as a parameter and FastAPI handles the rest.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import models
from auth import decode_access_token
from database import SessionLocal

# Tells FastAPI's auto-docs (/docs) where the login endpoint is, and
# tells it to expect a "Bearer <token>" header on protected routes.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_error

    return user
