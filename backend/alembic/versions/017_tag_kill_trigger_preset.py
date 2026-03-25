"""Tag existing kill triggers with standard preset.

Adds validation_mode_preset field to every trigger entry in existing
ideas so we can distinguish standard vs speed triggers. No key renaming,
fully reversible.
"""

from alembic import op
from sqlalchemy.sql import text
import json

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT id, kill_triggers FROM ideas WHERE kill_triggers IS NOT NULL")
    ).fetchall()
    for row in rows:
        triggers = row.kill_triggers if isinstance(row.kill_triggers, dict) else json.loads(row.kill_triggers)
        updated = {}
        for key, val in triggers.items():
            updated[key] = {**val, "validation_mode_preset": "standard"}
        conn.execute(
            text("UPDATE ideas SET kill_triggers = :t::jsonb WHERE id = :id"),
            {"t": json.dumps(updated), "id": row.id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT id, kill_triggers FROM ideas WHERE kill_triggers IS NOT NULL")
    ).fetchall()
    for row in rows:
        triggers = row.kill_triggers if isinstance(row.kill_triggers, dict) else json.loads(row.kill_triggers)
        updated = {
            k: {kk: vv for kk, vv in v.items() if kk != "validation_mode_preset"}
            for k, v in triggers.items()
        }
        conn.execute(
            text("UPDATE ideas SET kill_triggers = :t::jsonb WHERE id = :id"),
            {"t": json.dumps(updated), "id": row.id},
        )
