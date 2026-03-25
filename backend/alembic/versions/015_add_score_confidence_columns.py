"""Add per-dimension confidence columns to scores.

Each scoring dimension gets a confidence level (low/medium/high) and a
cached low_confidence_count for quick UI display.
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

DIMENSIONS = [
    "problem_severity", "market_evidence", "revenue_model",
    "distribution_feasibility", "purchaser_quality", "build_complexity",
    "founder_market_fit", "time_to_revenue", "founder_constraints",
    "competition_level", "defensibility_potential",
]


def upgrade() -> None:
    for dim in DIMENSIONS:
        op.add_column(
            "scores",
            sa.Column(
                f"{dim}_confidence",
                sa.String(10),
                nullable=False,
                server_default="low",
            ),
        )
    op.add_column(
        "scores",
        sa.Column(
            "low_confidence_count",
            sa.Integer,
            nullable=False,
            server_default="11",
        ),
    )


def downgrade() -> None:
    for dim in DIMENSIONS:
        op.drop_column("scores", f"{dim}_confidence")
    op.drop_column("scores", "low_confidence_count")
