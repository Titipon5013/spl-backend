from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from services.admin_service import AdminService
from auth.dependencies import create_access_token
from services.dependencies import get_admin_service

login_router: APIRouter = APIRouter(tags=["Login"])

@login_router.post("/api/login")
def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    admin_service: AdminService = Depends(get_admin_service),
):
    admin = admin_service.authenticate_admin(credentials.username, credentials.password)

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        {"user_id": admin.id, "role": admin.role.value}
    )
    return {"access_token": access_token, "token_type": "bearer"}
