from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AccountUpdateRequest, LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import auth as auth_service

router = APIRouter()


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.user_id),
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.register_user(db, payload)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    return _token_for(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        # Same message for "no such email" and "wrong password".
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return _token_for(user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: AccountUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide at least one account change.")

    new_password = changes.pop("new_password", None)
    current_password = changes.pop("current_password", None)
    if new_password is not None:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
        user.password_hash = hash_password(new_password)
    elif current_password is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide a new password too.")

    for key, value in changes.items():
        setattr(user, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    await db.refresh(user)
    return user
