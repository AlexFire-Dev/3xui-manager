from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import AdminPrincipal, create_access_token, require_admin, verify_admin_credentials
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    username: str
    scope: str = "admin"


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    if not verify_admin_credentials(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return TokenResponse(
        access_token=create_access_token(payload.username),
        expires_in=settings.admin_token_ttl_seconds,
    )


@router.get("/me", response_model=MeResponse)
def me(principal: AdminPrincipal = Depends(require_admin)):
    return MeResponse(username=principal.username)
