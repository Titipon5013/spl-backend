from fastapi import APIRouter, Depends, status, Query, Response
from schemas.admin import AdminResponse, AdminCreate, AdminUpdate, AdminListResponse
from auth import dependencies
from services.admin_service import AdminService
from services.dependencies import get_admin_service
from db.models import Admin

router = APIRouter(
    tags=["Admins"],
    responses={
        401: {"description": "Unauthorized"},
    },
)


@router.get("/api/admins", response_model=AdminListResponse)
async def get_all_admins(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    admin_service: AdminService = Depends(get_admin_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    """
    Get all admin users with pagination.
    Requires admin privileges.
    """
    admins = admin_service.get_all_admins(current_user, page, limit)
    return admins


@router.post("/api/admins", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def create_admin(
    new_admin: AdminCreate,
    admin_service: AdminService = Depends(get_admin_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    """
    Create a new admin user.
    Requires admin privileges.
    """
    admin = admin_service.create_admin(new_admin, current_user)
    return admin


@router.patch("/api/admins/{admin_id}", response_model=AdminResponse)
async def update_admin(
    admin_id: int,
    admin_update: AdminUpdate,
    admin_service: AdminService = Depends(get_admin_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    """
    Update an admin's credentials.
    Requires admin privileges.
    """
    updated_admin = admin_service.update_admin(admin_id, admin_update, current_user)
    return updated_admin


@router.delete("/api/admins/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_id: int,
    admin_service: AdminService = Depends(get_admin_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    """
    Delete an admin user.
    Requires admin privileges.
    """
    admin_service.delete_admin(admin_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
