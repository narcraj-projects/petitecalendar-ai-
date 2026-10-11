"""Event drafts, publication and public metadata access."""

from alembic import op

revision = "0002_event_types"
down_revision = "0001_host_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.event_types (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id) ON DELETE CASCADE,
        title varchar(100) NOT NULL CHECK (length(title) >= 2),
        description varchar(2000) NOT NULL DEFAULT '',
        slug varchar(64) NOT NULL CHECK (
            length(slug) >= 3 AND slug ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
        durations jsonb NOT NULL CHECK (
            jsonb_typeof(durations) = 'array' AND jsonb_array_length(durations) BETWEEN 1 AND 6),
        default_duration integer NOT NULL CHECK (default_duration BETWEEN 5 AND 240),
        location varchar(160) NOT NULL,
        notice_minutes integer NOT NULL CHECK (notice_minutes BETWEEN 0 AND 10080),
        horizon_days integer NOT NULL CHECK (horizon_days BETWEEN 1 AND 365),
        buffer_before integer NOT NULL CHECK (buffer_before BETWEEN 0 AND 240),
        buffer_after integer NOT NULL CHECK (buffer_after BETWEEN 0 AND 240),
        max_per_day integer NOT NULL CHECK (max_per_day BETWEEN 1 AND 50),
        cancellation_hours integer NOT NULL CHECK (cancellation_hours BETWEEN 0 AND 720),
        reschedule_hours integer NOT NULL CHECK (reschedule_hours BETWEEN 0 AND 720),
        reschedule_requires_approval boolean NOT NULL,
        allow_alternatives boolean NOT NULL,
        published boolean NOT NULL DEFAULT false,
        revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT event_host_slug UNIQUE (user_id, slug)
    )""")
    op.execute("ALTER TABLE app_private.event_types ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.event_types FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE ON app_private.event_types TO petitecalendar_api")
    op.execute("""CREATE POLICY host_owns_event ON app_private.event_types TO petitecalendar_api
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)""")
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'petitecalendar_public') THEN
            CREATE ROLE petitecalendar_public NOLOGIN;
        END IF;
        EXECUTE format('GRANT petitecalendar_public TO %I', current_user);
    END $$""")
    op.execute("GRANT USAGE ON SCHEMA app_private TO petitecalendar_public")
    op.execute("GRANT SELECT ON app_private.event_types TO petitecalendar_public")
    op.execute(
        "GRANT SELECT (user_id, display_name, username, timezone) "
        "ON app_private.host_profiles TO petitecalendar_public"
    )
    op.execute("""CREATE POLICY published_event ON app_private.event_types
        FOR SELECT TO petitecalendar_public USING (published)""")
    op.execute("""CREATE POLICY published_host ON app_private.host_profiles
        FOR SELECT TO petitecalendar_public
        USING (EXISTS (SELECT 1 FROM app_private.event_types e
            WHERE e.user_id = host_profiles.user_id AND e.published))""")


def downgrade():
    op.execute("DROP POLICY published_host ON app_private.host_profiles")
    op.drop_table("event_types", schema="app_private")
