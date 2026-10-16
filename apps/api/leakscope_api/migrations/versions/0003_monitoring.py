"""Bounded long-running monitoring, independent capture windows and experiments."""

from alembic import op
from sqlalchemy import Table
from typing import cast
from leakscope_api.models import Monitor, MonitorSample, CaptureWindow, Anomaly, Experiment

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    for model in (Monitor, MonitorSample, CaptureWindow, Anomaly, Experiment):
        cast(Table, model.__table__).create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (Experiment, Anomaly, CaptureWindow, MonitorSample, Monitor):
        cast(Table, model.__table__).drop(op.get_bind(), checkfirst=True)
