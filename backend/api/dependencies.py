from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.infrastructure.database.session import get_db
from backend.infrastructure.database.repositories.battery_repository_impl import SQLAlchemyBatteryRepository
from backend.application.services.battery_service import BatteryService
from backend.application.services.analytics_service import AnalyticsService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
settings = get_settings()


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return {"username": username, "role": payload.get("role", "viewer")}
    except JWTError:
        raise credentials_exception


async def get_battery_service(db: AsyncSession = Depends(get_db)) -> BatteryService:
    repo = SQLAlchemyBatteryRepository(db)
    return BatteryService(repo)


async def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


CurrentUser = Annotated[dict, Depends(get_current_user)]
