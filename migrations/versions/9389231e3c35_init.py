"""init
Revision ID: 9389231e3c35
Revises: 
Create Date: 2025-07-05 18:24:57.088033
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9389231e3c35'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define ENUM types
role_enum = postgresql.ENUM('admin', 'operator', name='roleenum', create_type=False)
request_status_enum = postgresql.ENUM('pending', 'approved', 'rejected', name='requeststatus', create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    
    # Manually create ENUM types if they don't exist
    res_role = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'roleenum'"))
    if res_role.scalar() is None:
        role_enum.create(conn, checkfirst=False)

    res_status = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'requeststatus'"))
    if res_status.scalar() is None:
        request_status_enum.create(conn, checkfirst=False)

    op.create_table('admins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.VARCHAR(), nullable=True),
        sa.Column('email', sa.VARCHAR(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('role', role_enum, nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admins_email'), 'admins', ['email'], unique=True)
    op.create_index(op.f('ix_admins_id'), 'admins', ['id'], unique=False)
    op.create_index(op.f('ix_admins_username'), 'admins', ['username'], unique=True)
    
    op.create_table('parking_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lot_id', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('available_spaces', sa.Integer(), nullable=False),
        sa.Column('total_spaces', sa.Integer(), nullable=False),
        sa.Column('occupied_spaces', sa.Integer(), nullable=False),
        sa.Column('occupacy_rate', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('processing_time_seconds', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_parking_snapshots_id'), 'parking_snapshots', ['id'], unique=False)
    
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    
    op.create_table('license_plate_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plate_number', sa.String(length=20), nullable=False),
        sa.Column('plate_image_url', sa.Text(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('status', request_status_enum, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'license_plates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plate_number', sa.String(), nullable=False),
        sa.Column('plate_image_url', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plate_number')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('license_plates')
    op.drop_table('license_plate_requests')
    op.drop_table('users')
    op.drop_index(op.f('ix_parking_snapshots_id'), table_name='parking_snapshots')
    op.drop_table('parking_snapshots')
    op.drop_index(op.f('ix_admins_username'), table_name='admins')
    op.drop_index(op.f('ix_admins_id'), table_name='admins')
    op.drop_index(op.f('ix_admins_email'), table_name='admins')
    op.drop_table('admins')
    
    # Manually drop ENUM types
    role_enum.drop(op.get_bind(), checkfirst=False)
    request_status_enum.drop(op.get_bind(), checkfirst=False)
