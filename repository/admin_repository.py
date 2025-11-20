from repository.iadmin_repository import AdminRepositoryInterface
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from db.models import Admin

class ImplAdminRepositoryInterface(AdminRepositoryInterface):
    def __init__(self, db: Session):
        self.db = db

    def get_admin_by_id(self, admin_id) -> Optional[Admin]:
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        return admin
    
    def get_admin_by_email(self, email) -> Optional[Admin]:
        admin = self.db.query(Admin).filter(Admin.email == email).first()
        return admin
    
    def get_all_admins(self, page: int = 1, limit: int = 10) -> Tuple[List[Admin], int]:
        total_admins = self.db.query(Admin).count()
        admins = self.db.query(Admin).offset((page - 1) * limit).limit(limit).all()
        return admins, total_admins
    
    def create_admin(self, admin: Admin) -> Admin:
        self.db.add(admin)
        self.db.commit()
        self.db.refresh(admin)
        return admin
    
    def update_admin(self, admin_id: int, update_data: dict) -> Optional[Admin]:
        admin = self.get_admin_by_id(admin_id)
        if not admin:
            return None
        for key, value in update_data.items():
            setattr(admin, key, value)
        self.db.commit()
        self.db.refresh(admin)
        return admin
    
    
    def delete_admin(self, admin_id):
        to_delete = self.db.query(Admin).filter_by(id=admin_id).first()
        self.db.delete(to_delete)
        self.db.commit()
        return
