"""Host-only new-booking jobs and verified-email guest history."""

from alembic import op

revision = "0010_host_guest"
down_revision = "0009_event_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.host_email_jobs (
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        revision integer NOT NULL CHECK(revision>=1),
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        event_type varchar(40) NOT NULL DEFAULT 'booking_confirmed'
          CHECK(event_type='booking_confirmed'),
        status varchar(20) NOT NULL DEFAULT 'queued'
          CHECK(status IN ('queued','working','retry','accepted','failed','uncertain')),
        attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
        due_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
        lease_token uuid, lease_until timestamptz,
        capability_ciphertext text CHECK(capability_ciphertext IS NULL),
        payload_ciphertext text, frozen_at timestamptz,
        provider_id varchar(100), last_error varchar(40),
        PRIMARY KEY(booking_id,revision),
        FOREIGN KEY(booking_id,revision,event_type) REFERENCES
          app_private.booking_outbox(booking_id,revision,event_type) ON DELETE CASCADE)""")
    op.execute("CREATE INDEX host_email_jobs_due ON app_private.host_email_jobs(status,due_at)")
    op.execute("ALTER TABLE app_private.host_email_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.host_email_jobs FORCE ROW LEVEL SECURITY")
    op.execute("GRANT INSERT ON app_private.host_email_jobs TO petitecalendar_booking")
    op.execute("""CREATE POLICY host_email_enqueue ON app_private.host_email_jobs
        FOR INSERT TO petitecalendar_booking WITH CHECK (
          user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid
          AND EXISTS (SELECT 1 FROM app_private.bookings b
            WHERE b.id=booking_id AND b.user_id=host_email_jobs.user_id
              AND b.revision=host_email_jobs.revision))""")
    op.execute("GRANT SELECT,UPDATE ON app_private.host_email_jobs TO petitecalendar_email_worker")
    op.execute("""CREATE POLICY host_email_worker ON app_private.host_email_jobs
        TO petitecalendar_email_worker USING(true) WITH CHECK(true)""")
    op.execute(
        "GRANT SELECT(booking_id,revision,status) ON app_private.host_email_jobs "
        "TO petitecalendar_api"
    )
    op.execute("""CREATE POLICY host_notification_status ON app_private.host_email_jobs
        FOR SELECT TO petitecalendar_api
        USING(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute("""CREATE FUNCTION app_private.host_notification_email(p_id uuid,p_revision integer)
        RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
        SELECT u.email::text FROM auth.users u
        JOIN app_private.host_email_jobs j ON j.user_id=u.id
        WHERE j.booking_id=p_id AND j.revision=p_revision
          AND u.email_confirmed_at IS NOT NULL LIMIT 1
        $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION app_private.host_notification_email(uuid,integer) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_private.host_notification_email(uuid,integer) "
        "TO petitecalendar_email_worker"
    )
    op.execute("CREATE ROLE petitecalendar_guest NOLOGIN")
    # The restricted runtime login already has API membership; no hosted credential change.
    op.execute("GRANT petitecalendar_guest TO petitecalendar_api")
    op.execute("GRANT petitecalendar_guest TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA app_private TO petitecalendar_guest")
    op.execute("""GRANT SELECT(id,start_at,end_at,duration,invitee_name,invitee_email,
        invitee_timezone,snapshot,status,revision)
        ON app_private.bookings TO petitecalendar_guest""")
    op.execute("""CREATE POLICY guest_reads_own_bookings ON app_private.bookings
        FOR SELECT TO petitecalendar_guest USING (
          lower(invitee_email)=NULLIF(current_setting('app.guest_email',true),''))""")
    op.execute(
        "CREATE INDEX bookings_guest_start ON app_private.bookings"
        "(lower(invitee_email),start_at DESC,id DESC)"
    )
    for table in ("calendar_jobs", "email_jobs"):
        columns = (
            "booking_id,revision,status,meet_url"
            if table == "calendar_jobs"
            else "booking_id,revision,status"
        )
        op.execute(f"GRANT SELECT({columns}) ON app_private.{table} TO petitecalendar_guest")
        op.execute(f"""CREATE POLICY guest_delivery_status ON app_private.{table}
            FOR SELECT TO petitecalendar_guest USING (EXISTS (
              SELECT 1 FROM app_private.bookings b WHERE b.id=booking_id))""")


def downgrade():
    op.execute("DROP FUNCTION app_private.host_notification_email(uuid,integer)")
    op.drop_table("host_email_jobs", schema="app_private")
    for table in ("calendar_jobs", "email_jobs"):
        op.execute(f"DROP POLICY guest_delivery_status ON app_private.{table}")
    op.execute("DROP POLICY guest_reads_own_bookings ON app_private.bookings")
    op.execute("DROP INDEX app_private.bookings_guest_start")
    op.execute("DROP OWNED BY petitecalendar_guest")
    op.execute("DROP ROLE petitecalendar_guest")
