from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Demo users — in production these live in the DB
DEMO_USERS = {
    "chairman": {
        "username": "chairman",
        "hashed_password": pwd_context.hash("sunmobility2024"),
        "role": "executive",
        "full_name": "Chairman's Office",
    },
    "analyst": {
        "username": "analyst",
        "hashed_password": pwd_context.hash("analyst2024"),
        "role": "analyst",
        "full_name": "Product Analytics",
    },
    "ops": {
        "username": "ops",
        "hashed_password": pwd_context.hash("ops2024"),
        "role": "operations",
        "full_name": "Operations Strategy",
    },
}


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    role: str
    full_name: str


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


@router.post("/token", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = DEMO_USERS.get(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        role=user["role"],
        full_name=user["full_name"],
    )


@router.get("/me")
async def get_me(current_user: dict = Depends(lambda: {"username": "demo", "role": "analyst"})):
    return current_user
