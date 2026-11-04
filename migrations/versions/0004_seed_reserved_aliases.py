"""seed reserved aliases that no short code may use (FR3)

To reserve more words later, add a new revision; never edit one that has run.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ROUTES = [
    "api", "admin", "login", "logout", "register", "signup", "dashboard", "settings",
    "account", "static", "assets", "health", "actuator", "swagger-ui", "docs", "qr",
]
BRAND = ["help", "support", "about", "terms", "privacy", "security"]

ALIASES = [(a, "route") for a in ROUTES] + [(a, "brand") for a in BRAND]


def upgrade() -> None:
    reserved = sa.table(
        "reserved_aliases",
        sa.column("alias", sa.String),
        sa.column("reason", sa.String),
    )
    op.bulk_insert(reserved, [{"alias": a, "reason": r} for a, r in ALIASES])


def downgrade() -> None:
    reserved = sa.table("reserved_aliases", sa.column("alias", sa.String))
    op.execute(reserved.delete().where(reserved.c.alias.in_([a for a, _ in ALIASES])))
