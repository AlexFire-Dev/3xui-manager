"""add maintenance audit enum values

Revision ID: 04e22974b2db
Revises: cea2e27652ee
Create Date: 2026-05-14 08:11:50.188727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04e22974b2db'
down_revision: Union[str, None] = 'cea2e27652ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'daily_traffic_snapshot_created'")
        op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'traffic_reset'")
        op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'maintenance_started'")
        op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'maintenance_finished'")


def downgrade() -> None:
    pass
