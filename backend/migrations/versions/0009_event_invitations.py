from alembic import op

revision = "0009_event_invitations"
down_revision = "0008_booking_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.invitation_batches (
        id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        event_id uuid NOT NULL REFERENCES app_private.event_types(id),
        request_hash varchar(64) NOT NULL,
        recipient_count integer NOT NULL CHECK(recipient_count BETWEEN 1 AND 10),
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE app_private.invitation_jobs (
        id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES app_private.invitation_batches(id),
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        status varchar(20) NOT NULL DEFAULT 'queued'
          CHECK(status IN ('queued','working','retry','accepted','failed','uncertain')),
        attempts integer NOT NULL DEFAULT 0, due_at timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now(),
        lease_token uuid, lease_until timestamptz,
        payload_ciphertext text, frozen_at timestamptz,
        provider_id varchar(100), last_error varchar(40))""")
    op.execute("CREATE INDEX invitation_jobs_due ON app_private.invitation_jobs(status,due_at)")
    op.execute(
        "CREATE INDEX invitation_batches_host ON app_private.invitation_batches(user_id,created_at)"
    )
    for table in ("invitation_batches", "invitation_jobs"):
        op.execute(f"ALTER TABLE app_private.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app_private.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"GRANT INSERT ON app_private.{table} TO petitecalendar_api")
        op.execute(f"""CREATE POLICY invitation_host ON app_private.{table} TO petitecalendar_api
            USING(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)
            WITH CHECK(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute("GRANT SELECT ON app_private.invitation_batches TO petitecalendar_api")
    op.execute(
        "GRANT SELECT(id,batch_id,user_id,status) "
        "ON app_private.invitation_jobs TO petitecalendar_api"
    )
    op.execute("GRANT SELECT,UPDATE ON app_private.invitation_jobs TO petitecalendar_email_worker")
    op.execute("""CREATE POLICY invitation_worker ON app_private.invitation_jobs
        TO petitecalendar_email_worker USING(true) WITH CHECK(true)""")
    # Global counter contains no contacts; reserve room for booking confirmation traffic.
    op.execute("""CREATE TABLE app_private.invitation_budget (
        day date PRIMARY KEY, recipients integer NOT NULL CHECK(recipients BETWEEN 0 AND 50))""")
    op.execute("GRANT SELECT,INSERT,UPDATE ON app_private.invitation_budget TO petitecalendar_api")
    op.execute("ALTER TABLE app_private.invitation_budget ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.invitation_budget FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY invitation_budget ON app_private.invitation_budget
        TO petitecalendar_api USING(true) WITH CHECK(true)""")


def downgrade():
    raise RuntimeError("Retain invitation history; restore a pre-invitation backup to downgrade.")
