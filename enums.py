from enum import Enum


class RoleEnum(str, Enum):
    admin = "admin"
    operator = "operator"


class RequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revoked = "revoked"


class AuthProvider(str, Enum):
    local = "local"
    google = "google"
