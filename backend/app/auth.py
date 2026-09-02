from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

from app.firebase import firebase_app

bearer_security = HTTPBearer(
    bearerFormat="Firebase ID token",
    auto_error=False,
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_security),
    ],
) -> dict[str, Any]:
    """Verify a Firebase ID token and return its decoded claims."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decoded_token = auth.verify_id_token(
            credentials.credentials,
            app=firebase_app,
            check_revoked=True,
        )

    except auth.ExpiredIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except auth.RevokedIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except auth.UserDisabledError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This user account has been disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except auth.InvalidIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    uid = decoded_token.get("uid")

    if not isinstance(uid, str) or not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token does not contain a user ID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decoded_token
