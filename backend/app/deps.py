import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app import models, security
from app.database import get_db

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials,
            security.JWT_SECRET_KEY,
            algorithms=[security.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise JWTError("Token payload missing 'sub'")
    except JWTError as exc:
        logger.info("Rejected request with invalid/expired token: %s", exc)
        raise unauthorized from exc

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise unauthorized
    return user
