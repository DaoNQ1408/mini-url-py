"""add triggers that enforce business rules inside the database

updated_at, permanent short codes (FR25), reserved words (FR3), append-only audit log.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = [
    # updated_at
    """
    CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
    BEGIN
        NEW.updated_at := now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_links_updated_at BEFORE UPDATE ON links FOR EACH ROW EXECUTE FUNCTION set_updated_at()",

    # a short code can never be changed (FR25)
    """
    CREATE FUNCTION forbid_short_code_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'short_code is permanent and cannot be changed (link id %)', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_links_short_code_immutable
        BEFORE UPDATE OF short_code ON links
        FOR EACH ROW WHEN (OLD.short_code IS DISTINCT FROM NEW.short_code)
        EXECUTE FUNCTION forbid_short_code_change()
    """,

    # a link row can never be removed, because that would free its code (FR25)
    """
    CREATE FUNCTION forbid_link_delete() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'links are never deleted; set status = ''DELETED'' instead (link id %)', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_links_no_delete
        BEFORE DELETE ON links
        FOR EACH ROW EXECUTE FUNCTION forbid_link_delete()
    """,

    # no short code may be a reserved word (FR3)
    """
    CREATE FUNCTION check_reserved_alias() RETURNS trigger AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM reserved_aliases WHERE alias = lower(NEW.short_code)) THEN
            RAISE EXCEPTION 'short code "%" is reserved', NEW.short_code
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_links_reserved
        BEFORE INSERT ON links
        FOR EACH ROW EXECUTE FUNCTION check_reserved_alias()
    """,

    # audit log is append-only (FR22, FR23)
    """
    CREATE FUNCTION forbid_audit_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'admin_audit_log is append-only';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_audit_append_only
        BEFORE UPDATE OR DELETE ON admin_audit_log
        FOR EACH ROW EXECUTE FUNCTION forbid_audit_change()
    """,
]

DOWNGRADE = [
    "DROP TRIGGER IF EXISTS trg_audit_append_only ON admin_audit_log",
    "DROP FUNCTION IF EXISTS forbid_audit_change()",
    "DROP TRIGGER IF EXISTS trg_links_reserved ON links",
    "DROP FUNCTION IF EXISTS check_reserved_alias()",
    "DROP TRIGGER IF EXISTS trg_links_no_delete ON links",
    "DROP FUNCTION IF EXISTS forbid_link_delete()",
    "DROP TRIGGER IF EXISTS trg_links_short_code_immutable ON links",
    "DROP FUNCTION IF EXISTS forbid_short_code_change()",
    "DROP TRIGGER IF EXISTS trg_links_updated_at ON links",
    "DROP TRIGGER IF EXISTS trg_users_updated_at ON users",
    "DROP FUNCTION IF EXISTS set_updated_at()",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
