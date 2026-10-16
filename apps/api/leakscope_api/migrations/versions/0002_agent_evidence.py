"""Bounded operation and Python function evidence."""

from leakscope_api.models import AgentRecord
from alembic import op
from sqlalchemy import Table
from typing import cast

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    cast(Table, AgentRecord.__table__).create(op.get_bind(), checkfirst=True)


def downgrade():
    cast(Table, AgentRecord.__table__).drop(op.get_bind(), checkfirst=True)
