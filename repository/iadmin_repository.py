from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from db.models import Admin

class AdminRepositoryInterface(ABC):

    @abstractmethod
    def get_admin_by_id(self, admin_id) -> Optional[Admin]:
        pass

    @abstractmethod
    def get_admin_by_email(self, email) -> Optional[Admin]:
        pass

    @abstractmethod
    def get_all_admins(self, page: int, limit: int) -> Tuple[List[Admin], int]:
        pass

    @abstractmethod
    def create_admin(self, admin: Admin) -> Admin:
        pass
    
    @abstractmethod
    def update_admin(self, admin_id, update_data: dict) -> Optional[Admin]:
        pass

    @abstractmethod
    def delete_admin(self, admin_id):
        pass
