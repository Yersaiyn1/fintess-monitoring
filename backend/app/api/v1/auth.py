from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_doctor, get_current_user
from app.core.rate_limit import check_auth_rate_limit
from app.core.security import ROLE_DOCTOR, ROLE_USER, create_access_token
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.doctor import DoctorLoginRequest, DoctorResponse, DoctorTokenResponse
from app.services import auth as auth_service

router = APIRouter()


def _client_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "local"
    return f"{host}:{email}"


def _token_for(user: User, refresh_token: str | None = None) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.user_id, ROLE_USER),
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


def _token_for_doctor(doctor: Doctor, refresh_token: str | None = None) -> DoctorTokenResponse:
    return DoctorTokenResponse(
        access_token=create_access_token(doctor.doctor_id, ROLE_DOCTOR),
        refresh_token=refresh_token,
        doctor=DoctorResponse.model_validate(doctor),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)
):
    check_auth_rate_limit(_client_key(request, payload.email))
    try:
        user = await auth_service.register_user(db, payload)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    refresh_token = await auth_service.create_refresh_token(db, user.user_id, ROLE_USER)
    return _token_for(user, refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    check_auth_rate_limit(_client_key(request, payload.email))
    user = await auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        # Same message for "no such email" and "wrong password".
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    refresh_token = await auth_service.create_refresh_token(db, user.user_id, ROLE_USER)
    return _token_for(user, refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/doctor/login", response_model=DoctorTokenResponse)
async def doctor_login(
    request: Request, payload: DoctorLoginRequest, db: AsyncSession = Depends(get_db)
):
    check_auth_rate_limit(_client_key(request, payload.email))
    doctor = await auth_service.authenticate_doctor(db, payload.email, payload.password)
    if doctor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    refresh_token = await auth_service.create_refresh_token(db, doctor.doctor_id, ROLE_DOCTOR)
    return _token_for_doctor(doctor, refresh_token)


@router.get("/doctor/me", response_model=DoctorResponse)
async def doctor_me(doctor: Doctor = Depends(get_current_doctor)):
    return doctor


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        access_token, refresh_token, role = await auth_service.rotate_refresh_token(
            db, payload.refresh_token
        )
    except auth_service.InvalidRefreshToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token.")
    return RefreshTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=role,
    )


@router.post("/logout")
async def logout(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.revoke_refresh_token(db, payload.refresh_token)
    return {"status": "logged_out"}
