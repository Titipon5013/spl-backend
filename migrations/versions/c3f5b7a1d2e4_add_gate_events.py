"""add gate events

Revision ID: c3f5b7a1d2e4
Revises: 0a0dac8b1e0c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f5b7a1d2e4"
down_revision: Union[str, Sequence[str], None] = "0a0dac8b1e0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "gate_events" not in inspector.get_table_names():
        op.create_table(
            "gate_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("event", sa.String(length=10), nullable=False),
            sa.Column("event_id", sa.String(length=100), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", name="uq_gate_events_event_id"),
        )
        inspector = sa.inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("gate_events")}
    if "ix_gate_events_id" not in indexes:
        op.create_index("ix_gate_events_id", "gate_events", ["id"], unique=False)
    if "ix_gate_events_event_id" not in indexes:
        op.create_index(
            "ix_gate_events_event_id", "gate_events", ["event_id"], unique=True
        )
    if "ix_gate_events_timestamp" not in indexes:
        op.create_index(
            "ix_gate_events_timestamp", "gate_events", ["timestamp"], unique=False
        )


def downgrade() -> None:
    op.drop_index("ix_gate_events_timestamp", table_name="gate_events")
    op.drop_index("ix_gate_events_event_id", table_name="gate_events")
    op.drop_index("ix_gate_events_id", table_name="gate_events")
    op.drop_table("gate_events")
