from enum import Enum


class RoleEnum(str, Enum):
    admin = "admin"
    operator = "operator"


class RequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
