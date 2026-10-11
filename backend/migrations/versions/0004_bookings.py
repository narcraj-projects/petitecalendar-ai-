from alembic import op

revision = "0004_bookings"
down_revision = "0003_availability"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions")
    op.execute("SET LOCAL search_path TO app_private, extensions, public")
    op.execute("""CREATE TABLE app_private.bookings (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        event_id uuid NOT NULL REFERENCES app_private.event_types(id),
        start_at timestamptz NOT NULL, end_at timestamptz NOT NULL,
        blocked_start timestamptz NOT NULL, blocked_end timestamptz NOT NULL,
        duration integer NOT NULL CHECK(duration BETWEEN 5 AND 240),
        invitee_name varchar(80) NOT NULL, invitee_email varchar(254) NOT NULL,
        invitee_timezone varchar(100) NOT NULL,
        snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
        status varchar(20) NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed','cancelled')),
        revision integer NOT NULL DEFAULT 1 CHECK(revision>=1),
        idempotency_key uuid NOT NULL UNIQUE, request_hash varchar(64) NOT NULL,
        capability_hash varchar(64) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK(end_at > start_at AND blocked_start <= start_at AND blocked_end >= end_at),
        CHECK(end_at = start_at + duration * interval '1 minute'),
        EXCLUDE USING gist (user_id WITH =, tstzrange(blocked_start,blocked_end,'[)') WITH &&)
            WHERE (status='confirmed')
    )""")
    op.execute("CREATE INDEX bookings_host_start ON app_private.bookings(user_id,start_at)")
    op.execute("CREATE ROLE petitecalendar_booking NOLOGIN")
    op.execute("GRANT petitecalendar_booking TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA app_private TO petitecalendar_booking")
    for table in ("host_profiles", "event_types", "availability"):
        op.execute(f"GRANT SELECT ON app_private.{table} TO petitecalendar_booking")
        op.execute(f"""CREATE POLICY booking_host_read ON app_private.{table}
            FOR SELECT TO petitecalendar_booking
            USING(user_id = NULLIF(current_setting('app.booking_host',true),'')::uuid)""")
    # FOR UPDATE needs UPDATE privilege; no write policy grants booking-role mutations.
    op.execute("GRANT UPDATE(user_id) ON app_private.host_profiles TO petitecalendar_booking")
    op.execute("""CREATE POLICY booking_host_lock ON app_private.host_profiles
        FOR UPDATE TO petitecalendar_booking
        USING(user_id = NULLIF(current_setting('app.booking_host',true),'')::uuid)
        WITH CHECK(false)""")
    op.execute("ALTER TABLE app_private.bookings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.bookings FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT,INSERT ON app_private.bookings TO petitecalendar_booking")
    op.execute("GRANT SELECT ON app_private.bookings TO petitecalendar_api")
    op.execute("""CREATE POLICY booking_service_scope ON app_private.bookings
        TO petitecalendar_booking
        USING(user_id = NULLIF(current_setting('app.booking_host',true),'')::uuid
            OR capability_hash = current_setting('app.booking_capability',true))
        WITH CHECK(user_id = NULLIF(current_setting('app.booking_host',true),'')::uuid)""")
    op.execute("""CREATE POLICY host_reads_bookings ON app_private.bookings
        FOR SELECT TO petitecalendar_api
        USING(user_id = NULLIF(current_setting('app.user_id',true),'')::uuid)""")


def downgrade():
    op.drop_table("bookings", schema="app_private")
    op.execute("DROP POLICY booking_host_lock ON app_private.host_profiles")
    for table in ("host_profiles", "event_types", "availability"):
        op.execute(f"DROP POLICY booking_host_read ON app_private.{table}")
    op.execute("DROP OWNED BY petitecalendar_booking")
    op.execute("DROP ROLE petitecalendar_booking")
