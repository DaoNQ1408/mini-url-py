"""create core tables (users, auth, links, admin)

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = [
    # fast "contains" search on links (FR18)
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",

    # users (FR16, FR23): never removed; closing an account sets status = 'DELETED'
    """
    CREATE TABLE users (
        id              BIGSERIAL     PRIMARY KEY,
        email           VARCHAR(255)  NOT NULL,
        password_hash   VARCHAR(100)  NOT NULL,
        display_name    VARCHAR(100),
        role            VARCHAR(20)   NOT NULL DEFAULT 'USER'
                        CHECK (role IN ('USER', 'ADMIN')),
        status          VARCHAR(20)   NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE', 'BANNED', 'DELETED')),
        banned_at       TIMESTAMPTZ,
        banned_reason   VARCHAR(500),
        deleted_at      TIMESTAMPTZ,
        last_login_at   TIMESTAMPTZ,
        created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),

        CONSTRAINT chk_users_banned  CHECK ((status = 'BANNED')  = (banned_at  IS NOT NULL)),
        CONSTRAINT chk_users_deleted CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL))
    )
    """,
    # case-insensitive unique email
    "CREATE UNIQUE INDEX uq_users_email ON users (lower(email))",

    # refresh_tokens (FR16, NFR6): stored as SHA-256 hash
    """
    CREATE TABLE refresh_tokens (
        id            BIGSERIAL     PRIMARY KEY,
        user_id       BIGINT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash    CHAR(64)      NOT NULL UNIQUE,
        user_agent    VARCHAR(255),
        expires_at    TIMESTAMPTZ   NOT NULL,
        revoked_at    TIMESTAMPTZ,
        created_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX idx_refresh_tokens_user_active ON refresh_tokens (user_id) WHERE revoked_at IS NULL",

    # reserved_aliases (FR3, FR26): rows seeded in 0004, enforced by a trigger in 0003
    """
    CREATE TABLE reserved_aliases (
        alias       VARCHAR(32)   PRIMARY KEY CHECK (alias = lower(alias)),
        reason      VARCHAR(100),
        created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
    )
    """,

    # links (FR1-FR9, FR17-FR19, FR22, FR25)
    """
    CREATE TABLE links (
        id                BIGSERIAL     PRIMARY KEY,
        short_code        VARCHAR(32)   NOT NULL UNIQUE,
        original_url      TEXT          NOT NULL CHECK (original_url ~* '^https?://'),
        title             VARCHAR(255),
        user_id           BIGINT        REFERENCES users(id) ON DELETE RESTRICT,
        is_custom_alias   BOOLEAN       NOT NULL DEFAULT FALSE,
        password_hash     VARCHAR(100),
        expires_at        TIMESTAMPTZ,
        status            VARCHAR(20)   NOT NULL DEFAULT 'ACTIVE'
                          CHECK (status IN ('ACTIVE', 'DISABLED', 'EXPIRED', 'DELETED')),
        disabled_by       BIGINT        REFERENCES users(id),
        disabled_reason   VARCHAR(500),
        deleted_at        TIMESTAMPTZ,
        creator_ip_hash   CHAR(64),
        click_count       BIGINT        NOT NULL DEFAULT 0,
        last_clicked_at   TIMESTAMPTZ,
        created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),

        CONSTRAINT chk_links_alias_format
            CHECK (NOT is_custom_alias OR short_code ~ '^[a-z0-9-]{3,30}$'),
        CONSTRAINT chk_links_random_format
            CHECK (is_custom_alias OR short_code ~ '^[A-Za-z0-9]{6,12}$'),
        CONSTRAINT chk_links_guest_alias
            CHECK (user_id IS NOT NULL OR NOT is_custom_alias),
        CONSTRAINT chk_links_guest_expiry
            CHECK (user_id IS NOT NULL OR expires_at IS NOT NULL),
        CONSTRAINT chk_links_deleted_at
            CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL))
    )
    """,
    "CREATE INDEX idx_links_user_created ON links (user_id, created_at DESC) WHERE status <> 'DELETED'",
    "CREATE INDEX idx_links_expiring ON links (expires_at) WHERE status = 'ACTIVE' AND expires_at IS NOT NULL",
    "CREATE INDEX idx_links_search_url ON links USING gin (original_url gin_trgm_ops)",
    "CREATE INDEX idx_links_search_title ON links USING gin (title gin_trgm_ops)",

    # api_keys (FR21): only a hash is stored
    """
    CREATE TABLE api_keys (
        id            BIGSERIAL     PRIMARY KEY,
        user_id       BIGINT        NOT NULL REFERENCES users(id),
        name          VARCHAR(100)  NOT NULL,
        key_prefix    VARCHAR(12)   NOT NULL,
        key_hash      CHAR(64)      NOT NULL UNIQUE,
        last_used_at  TIMESTAMPTZ,
        expires_at    TIMESTAMPTZ,
        revoked_at    TIMESTAMPTZ,
        created_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX idx_api_keys_user ON api_keys (user_id)",

    # blocked_domains (FR24)
    """
    CREATE TABLE blocked_domains (
        id          BIGSERIAL     PRIMARY KEY,
        domain      VARCHAR(255)  NOT NULL UNIQUE CHECK (domain = lower(domain)),
        reason      VARCHAR(255),
        source      VARCHAR(20)   NOT NULL DEFAULT 'ADMIN' CHECK (source IN ('ADMIN', 'FEED')),
        created_by  BIGINT        REFERENCES users(id),
        created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
    )
    """,

    # admin_audit_log (FR22, FR23): append-only, enforced by a trigger in 0003
    """
    CREATE TABLE admin_audit_log (
        id           BIGSERIAL     PRIMARY KEY,
        admin_id     BIGINT        NOT NULL REFERENCES users(id),
        action       VARCHAR(30)   NOT NULL
                     CHECK (action IN ('DISABLE_LINK', 'ENABLE_LINK', 'DELETE_LINK',
                                       'BAN_USER', 'UNBAN_USER',
                                       'BLOCK_DOMAIN', 'UNBLOCK_DOMAIN')),
        target_type  VARCHAR(20)   NOT NULL CHECK (target_type IN ('LINK', 'USER', 'DOMAIN')),
        target_id    BIGINT        NOT NULL,
        reason       VARCHAR(500),
        details      JSONB,
        created_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX idx_audit_target ON admin_audit_log (target_type, target_id, created_at DESC)",
    "CREATE INDEX idx_audit_admin ON admin_audit_log (admin_id, created_at DESC)",
]

# Reverse dependency order. pg_trgm is left installed: other schemas may use it.
DOWNGRADE = [
    "DROP TABLE IF EXISTS admin_audit_log",
    "DROP TABLE IF EXISTS blocked_domains",
    "DROP TABLE IF EXISTS api_keys",
    "DROP TABLE IF EXISTS links",
    "DROP TABLE IF EXISTS reserved_aliases",
    "DROP TABLE IF EXISTS refresh_tokens",
    "DROP TABLE IF EXISTS users",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
