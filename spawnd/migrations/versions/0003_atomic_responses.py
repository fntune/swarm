"""Make clarification responses single-writer.

Revision ID: 0003_atomic_responses
Revises: 0002_unattended_readiness
Create Date: 2026-07-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_atomic_responses"
down_revision = "0002_unattended_readiness"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_responses_run_clarification"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM responses
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY run_id, clarification_id
                            ORDER BY created_at, id
                        ) AS response_number
                    FROM responses
                ) AS ranked_responses
                WHERE response_number > 1
            )
            """
        )
    )
    with op.batch_alter_table("responses") as batch:
        batch.create_unique_constraint(CONSTRAINT_NAME, ["run_id", "clarification_id"])


def downgrade() -> None:
    with op.batch_alter_table("responses") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="unique")
