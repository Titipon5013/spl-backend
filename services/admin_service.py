from repository.admin_repository import ImplAdminRepositoryInterface
from fastapi import HTTPException, status
from schemas.admin import AdminOut, AdminResponse, AdminCreate, AdminUpdate
from db.models import Admin
from passlib.context import CryptContext
from pydantic import ValidationError
from enums import RoleEnum
from auth.utils import authorize_admin_or_self

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AdminService:
    def __init__(self, admin_repo: ImplAdminRepositoryInterface):
        self.admin_repo = admin_repo

    def _get_validated_admin(self, email: str) -> AdminOut:
        admin = self.admin_repo.get_admin_by_email(email)
        if not admin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        try:
            return AdminOut.model_validate(admin)
        except ValidationError as e:
            # Log the validation error for debugging
            print(f"Validation Failed for admin {email}: {e}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")

    def authenticate_admin(self, email, password):
        validated_admin = self._get_validated_admin(email)
        if not pwd_context.verify(password, validated_admin.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return validated_admin

    def get_all_admins(self, current_user: Admin, page: int = 1, limit: int = 10):
        authorize_admin_or_self(current_user.id, current_user, require_admin=True)
        admins, total_admins = self.admin_repo.get_all_admins(page, limit)
        total_pages = (total_admins + limit - 1) // limit
        return {
            "admins": [AdminResponse.model_validate(admin) for admin in admins],
            "total_pages": total_pages
        }

    def create_admin(self, admin: AdminCreate, current_user: AdminOut):
        authorize_admin_or_self(current_user.id, current_user, require_admin=True)
        if self.admin_repo.get_admin_by_email(admin.email):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
        new_admin = Admin(
            username=admin.username,
            email=admin.email,
            hashed_password=pwd_context.hash(admin.password),
            role=admin.role,
        )
        created_admin = self.admin_repo.create_admin(new_admin)
        return AdminResponse.model_validate(created_admin)

    def update_admin(self, admin_id: int, data: AdminUpdate, current_user: AdminOut):
        admin_to_edit = self.admin_repo.get_admin_by_id(admin_id)
        if not admin_to_edit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        authorize_admin_or_self(admin_id, current_user)

        update_data = data.model_dump(exclude_unset=True)
        if "password" in update_data and update_data["password"]:
            # Ensure only admins or the user themselves can change the password
            if current_user.role != RoleEnum.admin.value:
                if current_user.id != admin_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to change password")
            update_data["hashed_password"] = pwd_context.hash(update_data.pop("password"))

        updated_admin = self.admin_repo.update_admin(admin_id, update_data)
        return AdminResponse.model_validate(updated_admin)

    def delete_admin(self, admin_id: int, current_user: AdminOut):
        admin_to_delete = self.admin_repo.get_admin_by_id(admin_id)
        if not admin_to_delete:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        authorize_admin_or_self(admin_id, current_user)
        self.admin_repo.delete_admin(admin_id)
