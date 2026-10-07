"""seed-admin

Revision ID: fc4d31ccbf46
Revises: 9389231e3c35
Create Date: 2025-07-05 18:27:21.321283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from db.models import Admin
from enums import RoleEnum
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# revision identifiers, used by Alembic.
revision: str = 'fc4d31ccbf46'
down_revision: Union[str, Sequence[str], None] = '9389231e3c35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Check if any users exist
    existing_user = session.query(Admin).first()
    if not existing_user:
        user = Admin(
            username="admin",
            email="admin@gmail.com",
            hashed_password=pwd_context.hash(
                "admin123"
            ),  # use a strong real password in production
            role=RoleEnum.admin,
        )
        session.add(user)
        session.commit()


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.query(Admin).filter_by(username="admin").delete()
    session.commit()
