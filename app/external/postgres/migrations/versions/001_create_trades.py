"""Create trades table

Revision ID: 001
Revises:
Create Date: 2026-07-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("strike", sa.Integer, nullable=False),
        sa.Column("option_type", sa.String(2), nullable=False),   # CE | PE
        sa.Column("side", sa.String(5), nullable=False),           # LONG | SHORT
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("pnl", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("signal_reason", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Notification tracking columns
        sa.Column(
            "notification_sent",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("notification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notification_failed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "notification_retry_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_index("ix_trades_created_at", "trades", ["created_at"])
    op.create_index("ix_trades_notification_sent", "trades", ["notification_sent"])
    op.create_index("ix_trades_strike", "trades", ["strike"])


def downgrade() -> None:
    op.drop_index("ix_trades_strike", table_name="trades")
    op.drop_index("ix_trades_notification_sent", table_name="trades")
    op.drop_index("ix_trades_created_at", table_name="trades")
    op.drop_table("trades")
