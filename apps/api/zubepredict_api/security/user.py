from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from zubepredict_core.repositories.supabase import (
    AuthenticatedSupabaseSession,
    SupabaseConfigurationError,
    SupabaseRepositoryError,
    create_authenticated_session,
)
from zubepredict_core.shared.config import get_settings

from zubepredict_api.security.quotas import enforce_user_rate

bearer = HTTPBearer(auto_error=False)


def require_user_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedSupabaseSession:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A bearer access token is required.")
    try:
        session = create_authenticated_session(get_settings(), credentials.credentials)
        enforce_user_rate(session.user_id)
        return session
    except SupabaseConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The access token is invalid.") from exc
