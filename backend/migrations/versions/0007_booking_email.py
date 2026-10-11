from alembic import op

revision = "0007_booking_email"
down_revision = "0006_google_calendar"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.email_jobs (
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        revision integer NOT NULL CHECK(revision>=1),
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        status varchar(20) NOT NULL DEFAULT 'queued'
            CHECK(status IN ('queued','working','retry','accepted','failed','uncertain')),
        attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
        due_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
        lease_token uuid, lease_until timestamptz, capability_ciphertext text,
        payload_ciphertext text, frozen_at timestamptz, provider_id varchar(100),
        last_error varchar(40), event_type varchar(40) NOT NULL DEFAULT 'booking_confirmed'
            CHECK(event_type='booking_confirmed'), PRIMARY KEY(booking_id,revision),
        FOREIGN KEY(booking_id,revision,event_type) REFERENCES
            app_private.booking_outbox(booking_id,revision,event_type) ON DELETE CASCADE
    )""")
    op.execute("CREATE INDEX email_jobs_due ON app_private.email_jobs(status,due_at)")
    op.execute("ALTER TABLE app_private.email_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.email_jobs FORCE ROW LEVEL SECURITY")
    op.execute("CREATE ROLE petitecalendar_email_worker NOLOGIN")
    op.execute("GRANT petitecalendar_email_worker TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA app_private TO petitecalendar_email_worker")
    op.execute("GRANT SELECT,UPDATE ON app_private.email_jobs TO petitecalendar_email_worker")
    op.execute("""CREATE POLICY email_worker_jobs ON app_private.email_jobs
        TO petitecalendar_email_worker USING(true) WITH CHECK(true)""")
    op.execute("""GRANT SELECT(id,user_id,start_at,end_at,duration,invitee_name,invitee_email,
        invitee_timezone,snapshot,status,revision,created_at)
        ON app_private.bookings TO petitecalendar_email_worker""")
    op.execute("""CREATE POLICY email_worker_bookings ON app_private.bookings
        FOR SELECT TO petitecalendar_email_worker USING(true)""")
    op.execute("GRANT SELECT ON app_private.calendar_jobs TO petitecalendar_email_worker")
    op.execute("""CREATE POLICY email_worker_calendar ON app_private.calendar_jobs
        FOR SELECT TO petitecalendar_email_worker USING(true)""")
    for role in ("petitecalendar_api", "petitecalendar_booking"):
        op.execute(f"""GRANT SELECT(booking_id,revision,user_id,status,last_error)
            ON app_private.email_jobs TO {role}""")
    op.execute("GRANT INSERT ON app_private.email_jobs TO petitecalendar_booking")
    op.execute("""CREATE POLICY host_email_status ON app_private.email_jobs
        FOR SELECT TO petitecalendar_api
        USING(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute("""CREATE POLICY booking_email_status ON app_private.email_jobs
        FOR SELECT TO petitecalendar_booking
        USING(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid OR EXISTS (
            SELECT 1 FROM app_private.bookings b WHERE b.id=booking_id
            AND b.capability_hash=current_setting('app.booking_capability',true)))""")
    op.execute("""CREATE POLICY booking_queues_email ON app_private.email_jobs
        FOR INSERT TO petitecalendar_booking
        WITH CHECK(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid
            AND EXISTS(SELECT 1 FROM app_private.bookings b
                WHERE b.id=booking_id AND b.user_id=email_jobs.user_id
                    AND b.revision=email_jobs.revision))""")


def downgrade():
    op.drop_table("email_jobs", schema="app_private")
    op.execute("DROP POLICY email_worker_bookings ON app_private.bookings")
    op.execute("DROP POLICY email_worker_calendar ON app_private.calendar_jobs")
    op.execute("DROP OWNED BY petitecalendar_email_worker")
    op.execute("DROP ROLE petitecalendar_email_worker")
