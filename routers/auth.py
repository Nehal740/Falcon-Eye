from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

import audit
from config import settings
from database import get_db
from deps import client_ip, get_current_user
from errors import AppError
from models import RevokedToken, User, Workspace, WorkspaceMember, aware, utcnow
from rate_limiter import limiter
from schemas import ChangePasswordIn, LoginIn, RegisterIn
from security import (
    burn_password_check, create_access_token, hash_password, verify_password,
)
from workspace_service import create_workspace, personal_workspace_name, workspace_out

router = APIRouter(prefix="/auth", tags=["Authentication"])


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "onboarding_completed": bool(user.onboarding_completed),
    }


def workspaces_for(db: Session, user: User) -> list[dict]:
    rows = (db.query(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .filter(WorkspaceMember.user_id == user.id)
            .order_by(Workspace.id).all())
    return [workspace_out(w, role) for w, role in rows]


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name, value=token, httponly=True,
        secure=settings.cookie_secure, samesite="lax",
        max_age=settings.access_token_minutes * 60, path="/",
    )


@router.post("/register", status_code=201, summary="Create an account and your first workspace")
def register(body: RegisterIn, request: Request, response: Response,
             db: Session = Depends(get_db)):
    ip = client_ip(request)
    allowed, retry = limiter.hit(f"register:{ip}", 10, 3600)
    if not allowed:
        raise AppError(429, "rate_limited", "Too many accounts were created from this address.",
                       f"Try again in about {retry // 60 + 1} minutes.",
                       headers={"Retry-After": str(retry)})

    if db.query(User).filter(User.email == body.email).first():
        raise AppError(409, "email_taken", "That email address already has an account.",
                       "Try signing in instead, or use a different email address.")

    user = User(full_name=body.full_name, email=body.email,
                hashed_password=hash_password(body.password))
    db.add(user)
    db.flush()
    workspace = create_workspace(db, user, personal_workspace_name(user.full_name))
    audit.record(db, "user.registered", workspace_id=workspace.id, actor_type="user",
                 actor_id=user.id, actor_label=user.email, ip=ip)
    token, _jti, _exp = create_access_token(user.id)
    db.commit()

    _set_cookie(response, token)
    return {
        "message": "Your account is ready.",
        "user": user_out(user),
        "workspaces": [workspace_out(workspace, "owner")],
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/login", summary="Sign in")
def login(body: LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db)):
    ip = client_ip(request)
    for key, limit, window in ((f"login-ip:{ip}", 30, 300),
                               (f"login-email:{body.email}", 15, 900)):
        allowed, retry = limiter.hit(key, limit, window)
        if not allowed:
            raise AppError(429, "rate_limited", "Too many sign-in attempts.",
                           f"Wait {retry // 60 + 1} minute(s) and try again.",
                           headers={"Retry-After": str(retry)})

    generic = AppError(401, "invalid_credentials", "The email or password is not correct.",
                       "Check them and try again. Passwords are case-sensitive.")
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not user.is_active:
        burn_password_check(body.password)
        raise generic

    now = utcnow()
    locked_until = aware(user.locked_until)
    if locked_until and locked_until > now:
        minutes = int((locked_until - now).total_seconds() // 60) + 1
        raise AppError(429, "account_locked",
                       "This account is temporarily locked after too many wrong passwords.",
                       f"Try again in about {minutes} minute(s).",
                       headers={"Retry-After": str(minutes * 60)})

    if not verify_password(body.password, user.hashed_password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        locked = user.failed_login_count >= settings.login_max_attempts
        if locked:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
        audit.record(db, "user.login_failed", actor_type="user", actor_id=user.id,
                     actor_label=user.email, ip=ip, details={"locked": locked})
        db.commit()
        raise generic

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token, _jti, _exp = create_access_token(user.id)
    audit.record(db, "user.login", actor_type="user", actor_id=user.id,
                 actor_label=user.email, ip=ip)
    db.commit()

    _set_cookie(response, token)
    return {
        "message": "Signed in.",
        "user": user_out(user),
        "workspaces": workspaces_for(db, user),
        "access_token": token,
        "token_type": "bearer",
    }


def iso_to_dt(timestamp) -> datetime:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)


@router.post("/logout", summary="Sign out and invalidate this session")
def logout(request: Request, response: Response,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    claims = request.state.token_claims
    db.add(RevokedToken(jti=claims["jti"],
                        expires_at=iso_to_dt(claims["exp"])))
    # Tidy up tokens that have expired anyway.
    db.query(RevokedToken).filter(RevokedToken.expires_at < utcnow()).delete(
        synchronize_session=False)
    audit.record(db, "user.logout", actor_type="user", actor_id=user.id,
                 actor_label=user.email, ip=client_ip(request))
    db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"message": "You have been signed out."}


@router.post("/refresh", summary="Get a fresh access token while you are still signed in")
def refresh(response: Response, user: User = Depends(get_current_user)):
    """The browser calls this shortly before its token expires. The old token
    keeps working until its own expiry; signing out revokes it."""
    token, _jti, _exp = create_access_token(user.id)
    _set_cookie(response, token)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", summary="Who am I, and which workspaces can I use?")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"user": user_out(user), "workspaces": workspaces_for(db, user)}


@router.post("/onboarding/complete", summary="Mark the first-time guide as finished")
def complete_onboarding(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.onboarding_completed = True
    db.commit()
    return {"user": user_out(user)}


@router.post("/change-password", summary="Change your password")
def change_password(body: ChangePasswordIn, request: Request, response: Response,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise AppError(400, "wrong_password", "Your current password is not correct.",
                       "Re-enter it and try again.")
    if body.current_password == body.new_password:
        raise AppError(400, "same_password", "The new password is the same as the old one.",
                       "Choose a different password.")
    user.hashed_password = hash_password(body.new_password)
    # Every other signed-in session stops working; this one gets a new token.
    now = utcnow()
    user.token_valid_after = now
    token, _jti, _exp = create_access_token(user.id)
    audit.record(db, "user.password_changed", actor_type="user", actor_id=user.id,
                 actor_label=user.email, ip=client_ip(request))
    db.commit()
    _set_cookie(response, token)
    return {"message": "Password changed. Other devices were signed out.",
            "access_token": token, "token_type": "bearer"}
