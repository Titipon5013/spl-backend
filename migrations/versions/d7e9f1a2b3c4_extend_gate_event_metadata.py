"""store gate event metadata

Revision ID: d7e9f1a2b3c4
Revises: c3f5b7a1d2e4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e9f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c3f5b7a1d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("gate_events")}
    if "gate_id" not in columns:
        op.add_column("gate_events", sa.Column("gate_id", sa.String(length=50), nullable=True))
    if "vehicle_class" not in columns:
        op.add_column("gate_events", sa.Column("vehicle_class", sa.String(length=30), nullable=True))
    if "confidence" not in columns:
        op.add_column("gate_events", sa.Column("confidence", sa.Float(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE gate_events SET gate_id = 'CAMT_EXIT_01' "
            "WHERE gate_id IS NULL"
        )
    )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("gate_events")}
    if "ix_gate_events_gate_id" not in indexes:
        op.create_index("ix_gate_events_gate_id", "gate_events", ["gate_id"], unique=False)
    timestamp_column = next(
        column for column in sa.inspect(bind).get_columns("gate_events")
        if column["name"] == "timestamp"
    )
    timestamp_type = timestamp_column["type"]
    if not getattr(timestamp_type, "timezone", False):
        op.alter_column(
            "gate_events",
            "timestamp",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
    op.alter_column(
        "gate_events",
        "gate_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "gate_events",
        "gate_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "gate_events",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )
    op.drop_index("ix_gate_events_gate_id", table_name="gate_events")
    op.drop_column("gate_events", "confidence")
    op.drop_column("gate_events", "vehicle_class")
    op.drop_column("gate_events", "gate_id")
