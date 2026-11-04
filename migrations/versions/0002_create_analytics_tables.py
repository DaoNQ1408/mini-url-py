"""create analytics tables (clicks partitioned by month, daily stats)

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = [
    # clicks: one row per redirect. No raw IP (NFR7); bots stored but excluded from stats.
    """
    CREATE TABLE clicks (
        id               BIGSERIAL,
        link_id          BIGINT        NOT NULL REFERENCES links(id),
        clicked_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
        visitor_hash     CHAR(64),
        country_code     CHAR(2),
        device_type      VARCHAR(20)   NOT NULL DEFAULT 'OTHER'
                         CHECK (device_type IN ('DESKTOP', 'MOBILE', 'TABLET', 'BOT', 'OTHER')),
        browser          VARCHAR(50),
        os               VARCHAR(50),
        referrer_domain  VARCHAR(255),
        is_bot           BOOLEAN       NOT NULL DEFAULT FALSE,
        PRIMARY KEY (id, clicked_at)
    ) PARTITION BY RANGE (clicked_at)
    """,
    "CREATE INDEX idx_clicks_link_time ON clicks (link_id, clicked_at)",

    # Creates the monthly partition containing the given date (safe to call twice).
    # A scheduled job should call it monthly:
    #   SELECT create_clicks_partition((now() + interval '1 month')::date)
    """
    CREATE FUNCTION create_clicks_partition(for_date DATE) RETURNS void AS $$
    DECLARE
        start_d DATE := date_trunc('month', for_date)::date;
        end_d   DATE := (date_trunc('month', for_date) + interval '1 month')::date;
        name    TEXT := format('clicks_%s', to_char(start_d, 'YYYY_MM'));
    BEGIN
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF clicks FOR VALUES FROM (%L) TO (%L)',
            name, start_d, end_d);
    END;
    $$ LANGUAGE plpgsql
    """,

    # current month plus the next two; anything else lands in clicks_default
    """
    DO $$
    BEGIN
        PERFORM create_clicks_partition(now()::date);
        PERFORM create_clicks_partition((now() + interval '1 month')::date);
        PERFORM create_clicks_partition((now() + interval '2 months')::date);
    END
    $$
    """,
    "CREATE TABLE clicks_default PARTITION OF clicks DEFAULT",

    # daily_link_stats: filled by a job so charts never scan raw clicks
    """
    CREATE TABLE daily_link_stats (
        link_id          BIGINT  NOT NULL REFERENCES links(id),
        stat_date        DATE    NOT NULL,
        clicks           INT     NOT NULL DEFAULT 0,
        unique_visitors  INT     NOT NULL DEFAULT 0,
        bot_clicks       INT     NOT NULL DEFAULT 0,
        PRIMARY KEY (link_id, stat_date)
    )
    """,

    # daily_link_breakdowns: one row per link, day, dimension and value
    """
    CREATE TABLE daily_link_breakdowns (
        link_id     BIGINT        NOT NULL REFERENCES links(id),
        stat_date   DATE          NOT NULL,
        dimension   VARCHAR(20)   NOT NULL
                    CHECK (dimension IN ('COUNTRY', 'DEVICE', 'BROWSER', 'OS', 'REFERRER')),
        value       VARCHAR(255)  NOT NULL DEFAULT '',
        clicks      INT           NOT NULL DEFAULT 0,
        PRIMARY KEY (link_id, dimension, stat_date, value)
    )
    """,
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS daily_link_breakdowns",
    "DROP TABLE IF EXISTS daily_link_stats",
    "DROP TABLE IF EXISTS clicks CASCADE",   # CASCADE also drops every monthly partition
    "DROP FUNCTION IF EXISTS create_clicks_partition(date)",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
