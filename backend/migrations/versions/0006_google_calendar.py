from alembic import op

revision = "0006_google_calendar"
down_revision = "0005_booking_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.google_connections (
        user_id uuid PRIMARY KEY REFERENCES app_private.host_profiles(user_id),
        generation uuid NOT NULL, revision integer NOT NULL CHECK(revision>=1),
        account_id varchar(1024) NOT NULL, token_ciphertext text,
        status varchar(30) NOT NULL
            CHECK(status IN ('connected','disconnected','reconnect_required')),
        blocking_ids jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(blocking_ids)='array'),
        destination_id varchar(1024), create_meet boolean NOT NULL DEFAULT true,
        connected_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE app_private.google_oauth_states (
        state_hash varchar(64) PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        binding_hash varchar(64) NOT NULL, verifier_ciphertext text NOT NULL,
        expires_at timestamptz NOT NULL
    )""")
    op.execute("""CREATE TABLE app_private.calendar_jobs (
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        revision integer NOT NULL CHECK(revision>=1),
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        generation uuid NOT NULL, destination_id varchar(1024) NOT NULL,
        create_meet boolean NOT NULL,
        status varchar(20) NOT NULL DEFAULT 'queued'
            CHECK(status IN ('queued','working','retry','synced','failed')),
        attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
        due_at timestamptz NOT NULL DEFAULT now(), lease_token uuid, lease_until timestamptz,
        last_error varchar(40), event_id varchar(100), meet_url varchar(2048),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(booking_id,revision)
    )""")
    op.execute("CREATE INDEX calendar_jobs_due ON app_private.calendar_jobs(status,due_at)")
    op.execute("CREATE ROLE petitecalendar_calendar NOLOGIN")
    op.execute("CREATE ROLE petitecalendar_worker NOLOGIN")
    op.execute("GRANT petitecalendar_calendar, petitecalendar_worker TO CURRENT_USER")
    op.execute(
        "GRANT USAGE ON SCHEMA app_private TO petitecalendar_calendar, petitecalendar_worker"
    )
    for table in ("google_connections", "google_oauth_states", "calendar_jobs"):
        op.execute(f"ALTER TABLE app_private.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app_private.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE,DELETE ON app_private.{table} TO petitecalendar_api"
        )
        op.execute(f"""CREATE POLICY host_owns_google_data ON app_private.{table}
            TO petitecalendar_api
            USING(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)
            WITH CHECK(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute(
        "GRANT SELECT ON app_private.google_connections "
        "TO petitecalendar_calendar, petitecalendar_worker"
    )
    op.execute(
        "GRANT UPDATE(status) ON app_private.google_connections "
        "TO petitecalendar_calendar, petitecalendar_worker"
    )
    op.execute("""CREATE POLICY calendar_service_host ON app_private.google_connections
        TO petitecalendar_calendar
        USING(user_id=NULLIF(current_setting('app.calendar_host',true),'')::uuid)
        WITH CHECK(user_id=NULLIF(current_setting('app.calendar_host',true),'')::uuid)""")
    op.execute("""CREATE POLICY worker_reads_connection ON app_private.google_connections
        TO petitecalendar_worker USING(true) WITH CHECK(true)""")
    op.execute("""GRANT SELECT(user_id,generation,revision,status,
        blocking_ids,destination_id,create_meet)
        ON app_private.google_connections TO petitecalendar_booking""")
    op.execute("""CREATE POLICY booking_reads_connection ON app_private.google_connections
        FOR SELECT TO petitecalendar_booking
        USING(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid)""")
    op.execute("GRANT SELECT,DELETE ON app_private.google_oauth_states TO petitecalendar_calendar")
    op.execute("""CREATE POLICY callback_consumes_state ON app_private.google_oauth_states
        TO petitecalendar_calendar
        USING(state_hash=current_setting('app.oauth_state',true)
            AND binding_hash=current_setting('app.oauth_binding',true))""")
    op.execute("GRANT SELECT,INSERT ON app_private.calendar_jobs TO petitecalendar_booking")
    op.execute("""CREATE POLICY booking_job_scope ON app_private.calendar_jobs
        TO petitecalendar_booking
        USING(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid OR EXISTS (
            SELECT 1 FROM app_private.bookings b WHERE b.id=booking_id
            AND b.capability_hash=current_setting('app.booking_capability',true)))
        WITH CHECK(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid)""")
    op.execute("GRANT SELECT,UPDATE ON app_private.calendar_jobs TO petitecalendar_worker")
    op.execute(
        "CREATE POLICY worker_jobs ON app_private.calendar_jobs "
        "TO petitecalendar_worker USING(true) WITH CHECK(true)"
    )
    op.execute("""GRANT SELECT(id,user_id,start_at,end_at,invitee_name,snapshot,status,revision)
        ON app_private.bookings TO petitecalendar_worker""")
    op.execute(
        "CREATE POLICY worker_reads_booking ON app_private.bookings "
        "FOR SELECT TO petitecalendar_worker USING(true)"
    )


def downgrade():
    op.drop_table("calendar_jobs", schema="app_private")
    op.drop_table("google_oauth_states", schema="app_private")
    op.drop_table("google_connections", schema="app_private")
    op.execute("DROP POLICY worker_reads_booking ON app_private.bookings")
    op.execute("DROP OWNED BY petitecalendar_calendar, petitecalendar_worker")
    op.execute("DROP ROLE petitecalendar_calendar, petitecalendar_worker")
