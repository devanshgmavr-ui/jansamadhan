import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.db.database import get_db
from app.models.government import GovernmentUser
from app.models.revoked_token import RevokedToken
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)
optional_bearer_scheme = HTTPBearer(auto_error=False)


def _reject_revoked(db: Session, payload: dict) -> None:
    jti = payload.get("jti")
    if jti and db.get(RevokedToken, jti) is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been signed out. Please sign in again.",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = security.decode_token(credentials.credentials, expected_type="access")
    _reject_revoked(db, payload)
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not activated.",
        )
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Authenticated viewer when a valid token is supplied, else None.
    An invalid token that is explicitly supplied is rejected (401)."""
    if credentials is None:
        return None
    payload = security.decode_token(credentials.credentials, expected_type="access")
    _reject_revoked(db, payload)
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    return user


def get_current_government_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> GovernmentUser:
    """Government-only authentication. Accepts solely tokens whose type claim
    is "government": public access tokens ("access") are rejected by the
    type check, so a public JWT can never authenticate here — and, by
    symmetry, a government JWT fails get_current_user/get_optional_user.
    Sessions end via the government revocation set (logout)."""
    from app.core import gov_revocation

    payload = security.decode_token(
        credentials.credentials,
        expected_type=security.GOVERNMENT_TOKEN_TYPE,
    )
    jti = payload.get("jti")
    if gov_revocation.is_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been signed out. Please sign in again.",
        )
    try:
        official_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    official = db.get(GovernmentUser, official_id)
    if official is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    if not official.is_active:
        # Matches the public convention (inactive public accounts get 403).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not activated.",
        )
    return official
