from abc import ABC, abstractmethod
from db.models import User
from typing import Optional
class LicensePlateRequestRepositoryInferface(ABC):

    @abstractmethod
    def get_user_by_email(self, email) -> Optional[User]:
        pass
