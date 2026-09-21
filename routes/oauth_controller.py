import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth.dependencies import create_access_token
from auth.google_oauth import FRONTEND_URL, exchange_code_for_user_info, get_google_login_url
from db.models import Admin
from db.session import get_db
from enums import ApprovalStatus, AuthProvider, RoleEnum

router = APIRouter(tags=["OAuth"])

OAUTH_STATE_COOKIE = "oauth_state"


@router.get("/api/oauth/google/login")
async def google_login():
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(url=get_google_login_url(state=state))
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/api/oauth/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )

    try:
        user_info = await exchange_code_for_user_info(code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth failed: {exc}",
        ) from exc

    admin = db.query(Admin).filter(Admin.email == user_info["email"]).first()
    if not admin:
        admin = Admin(
            username=user_info["name"],
            email=user_info["email"],
            oauth_sub=user_info["sub"],
            auth_provider=AuthProvider.google,
            approval_status=ApprovalStatus.pending,
            role=RoleEnum.operator,
            hashed_password=None,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    else:
        admin.oauth_sub = user_info["sub"]
        admin.auth_provider = AuthProvider.google
        if admin.approval_status == ApprovalStatus.rejected:
            admin.approval_status = ApprovalStatus.pending
        db.commit()
        db.refresh(admin)

    if admin.approval_status != ApprovalStatus.approved:
        params = urlencode({"oauth_status": admin.approval_status.value})
        response = RedirectResponse(url=f"{FRONTEND_URL}/login?{params}")
        response.delete_cookie(OAUTH_STATE_COOKIE)
        return response

    token = create_access_token({"user_id": admin.id, "role": admin.role.value})
    params = urlencode({"token": token})
    response = RedirectResponse(url=f"{FRONTEND_URL}/login?{params}")
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response
