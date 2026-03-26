"""Initial schema

Revision ID: 001
Revises: None
Create Date: 2026-03-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "councils",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("authority_code", sa.String(100), nullable=False, unique=True),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("schedule_cron", sa.String(50), server_default="0 3 * * *"),
        sa.Column("requires_js", sa.Boolean(), server_default="false"),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("last_successful_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("council_id", sa.Integer(), sa.ForeignKey("councils.id"), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("application_type", sa.String(255)),
        sa.Column("status", sa.String(100)),
        sa.Column("decision", sa.String(255)),
        sa.Column("date_received", sa.Date()),
        sa.Column("date_validated", sa.Date()),
        sa.Column("ward", sa.String(255)),
        sa.Column("parish", sa.String(255)),
        sa.Column("applicant_name", sa.String(255)),
        sa.Column("case_officer", sa.String(255)),
        sa.Column("first_scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_data", sa.JSON()),
        sa.UniqueConstraint("council_id", "reference", name="uq_council_reference"),
    )

    # Index for full-text search on description and address
    op.create_index("ix_applications_description", "applications", ["description"], postgresql_using="gin",
                    postgresql_ops={"description": "gin_trgm_ops"})
    op.create_index("ix_applications_council_id", "applications", ["council_id"])
    op.create_index("ix_applications_date_received", "applications", ["date_received"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("council_id", sa.Integer(), sa.ForeignKey("councils.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("applications_found", sa.Integer(), server_default="0"),
        sa.Column("applications_updated", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("date_range_from", sa.Date()),
        sa.Column("date_range_to", sa.Date()),
    )

    op.create_index("ix_scrape_runs_council_id", "scrape_runs", ["council_id"])


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("applications")
    op.drop_table("councils")
