"""add subscription hwid and userinfo

Revision ID: 50ed7b07d8df
Revises: 421167862978
Create Date: 2026-04-30 20:14:01.426583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50ed7b07d8df'
down_revision: Union[str, None] = '421167862978'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
