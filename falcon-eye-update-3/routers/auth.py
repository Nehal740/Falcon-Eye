from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

import audit
import email_service
import email_tokens
from config import settings
from database import get_db
from deps import client_ip, get_current_user
from errors import AppError
from models import EmailToken, RevokedToken, User, Workspace, WorkspaceMember, aware, utcnow
from rate_limiter import limiter
from schemas import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, RegisterIn, ResetPasswordIn, TokenIn,
)
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
        "email_verified": user.email_verified_at is not None,
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
             background: BackgroundTasks, db: Session = Depends(get_db)):
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
    welcome = None
    if settings.email_available:
        raw = email_tokens.issue(db, user, email_tokens.VERIFY_EMAIL,
                                 timedelta(hours=settings.verify_token_hours))
        welcome = email_service.welcome_and_verify(user.full_name, raw)
    db.commit()
    if welcome is not None:
        # Sent after the response; a mail problem never blocks sign-up.
        background.add_task(email_service.send_email, user.email, welcome)

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
    return {"user": user_out(user), "workspaces": workspaces_for(db, user),
            "email_available": settings.email_available}


@router.post("/onboarding/complete", summary="Mark the first-time guide as finished")
def complete_onboarding(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.onboarding_completed = True
    db.commit()
    return {"user": user_out(user)}


@router.post("/change-password", summary="Change your password")
def change_password(body: ChangePasswordIn, request: Request, response: Response,
                    background: BackgroundTasks,
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
    background.add_task(email_service.send_email, user.email,
                        email_service.password_changed(user.full_name))
    _set_cookie(response, token)
    return {"message": "Password changed. Other devices were signed out.",
            "access_token": token, "token_type": "bearer"}


# --------------------------------------------------------------------------
# Email: confirm address and reset a forgotten password
# --------------------------------------------------------------------------

def _require_email() -> None:
    if not settings.email_available:
        raise AppError(503, "email_not_configured",
                       "Email is not set up on this server, so we cannot send the message.",
                       "Ask your administrator to configure SMTP (see docs/EMAIL.md).")


def _limit(key: str, limit: int, window: int) -> bool:
    allowed, retry = limiter.hit(key, limit, window)
    if not allowed:
        raise AppError(429, "rate_limited", "Too many requests.",
                       f"Try again in about {retry // 60 + 1} minute(s).",
                       headers={"Retry-After": str(retry)})
    return True


def _invalid_link() -> AppError:
    return AppError(
        400, "invalid_or_expired_token",
        "This link is invalid, has expired or was already used.",
        "Request a new one: use 'Forgot password' on the sign-in page, "
        "or 'Resend confirmation email' inside Falcon Eye.")


@router.post("/forgot-password", summary="Email a password reset link")
def forgot_password(body: ForgotPasswordIn, request: Request, background: BackgroundTasks,
                    db: Session = Depends(get_db)):
    """Always answers the same way, whether or not the address has an account,
    so it cannot be used to find out who is registered."""
    ip = client_ip(request)
    _limit(f"forgot-ip:{ip}", 10, 3600)
    _require_email()
    reply = {"message": "If an account exists for that email address, a reset link is on its way. "
                        "It can take a few minutes; check your spam folder too."}

    # At most 3 emails per address per hour. Extra requests get the same
    # answer but send nothing, which also stops mail flooding of a victim.
    allowed, _retry = limiter.hit(f"forgot-email:{body.email}", 3, 3600)
    if not allowed:
        return reply

    user = db.query(User).filter(User.email == body.email).first()
    if user is not None and user.is_active:
        raw = email_tokens.issue(db, user, email_tokens.RESET_PASSWORD,
                                 timedelta(minutes=settings.reset_token_minutes))
        audit.record(db, "user.password_reset_requested", actor_type="user", actor_id=user.id,
                     actor_label=user.email, ip=ip)
        email_tokens.purge_old(db)
        db.commit()
        background.add_task(email_service.send_email, user.email,
                            email_service.password_reset(user.full_name, raw))
    return reply


@router.post("/reset-password", summary="Set a new password using the emailed link")
def reset_password(body: ResetPasswordIn, request: Request, background: BackgroundTasks,
                   db: Session = Depends(get_db)):
    ip = client_ip(request)
    _limit(f"reset-ip:{ip}", 20, 3600)
    user = email_tokens.consume(db, body.token, email_tokens.RESET_PASSWORD)
    if user is None:
        raise _invalid_link()
    now = utcnow()
    user.hashed_password = hash_password(body.new_password)
    user.token_valid_after = now          # every signed-in device is signed out
    user.failed_login_count = 0
    user.locked_until = None
    if user.email_verified_at is None:
        user.email_verified_at = now      # they just proved they own this inbox
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id, EmailToken.purpose == email_tokens.RESET_PASSWORD,
        EmailToken.used_at.is_(None)).update({EmailToken.used_at: now}, synchronize_session=False)
    audit.record(db, "user.password_reset", actor_type="user", actor_id=user.id,
                 actor_label=user.email, ip=ip)
    db.commit()
    background.add_task(email_service.send_email, user.email,
                        email_service.password_changed(user.full_name))
    return {"message": "Your password has been changed. Sign in with your new password."}


@router.post("/verify-email", summary="Confirm your email address using the emailed link")
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    _limit(f"verify-ip:{client_ip(request)}", 30, 3600)
    user = email_tokens.consume(db, body.token, email_tokens.VERIFY_EMAIL)
    if user is None:
        raise _invalid_link()
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    audit.record(db, "user.email_verified", actor_type="user", actor_id=user.id,
                 actor_label=user.email, ip=client_ip(request))
    db.commit()
    return {"message": "Your email address is confirmed.", "email_verified": True}


@router.post("/resend-verification", summary="Send the email confirmation link again")
def resend_verification(background: BackgroundTasks,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email_verified_at is not None:
        return {"message": "Your email address is already confirmed.", "email_verified": True}
    _require_email()
    _limit(f"resend-verify:{user.id}", 3, 3600)
    raw = email_tokens.issue(db, user, email_tokens.VERIFY_EMAIL,
                             timedelta(hours=settings.verify_token_hours))
    db.commit()
    background.add_task(email_service.send_email, user.email,
                        email_service.verify_again(user.full_name, raw))
    return {"message": f"We sent a confirmation link to {user.email}.", "email_verified": False}
