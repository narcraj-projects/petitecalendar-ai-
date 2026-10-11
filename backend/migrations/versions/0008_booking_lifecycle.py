from alembic import op

revision = "0008_booking_lifecycle"
down_revision = "0007_booking_email"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE app_private.bookings ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "ALTER TABLE app_private.calendar_jobs ADD COLUMN operation varchar(20) "
        "NOT NULL DEFAULT 'upsert' CHECK(operation IN ('upsert','cancel'))"
    )
    for table in ("booking_outbox", "email_jobs"):
        op.execute(f"ALTER TABLE app_private.{table} DROP CONSTRAINT {table}_event_type_check")
        op.execute(
            f"ALTER TABLE app_private.{table} ADD CHECK(event_type IN "
            "('booking_confirmed','booking_rescheduled','booking_cancelled'))"
        )
    op.execute("""CREATE TABLE app_private.booking_changes (
        id uuid PRIMARY KEY,
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        booking_revision integer NOT NULL, candidates jsonb NOT NULL,
        timezone varchar(100) NOT NULL, capability_ciphertext text,
        status varchar(20) NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','declined','withdrawn','superseded')),
        created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE UNIQUE INDEX one_pending_change ON app_private.booking_changes(booking_id) "
        "WHERE status='pending'"
    )
    op.execute("""CREATE TABLE app_private.booking_actions (
        id uuid PRIMARY KEY,
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        request_hash varchar(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for table in ("booking_changes", "booking_actions"):
        op.execute(f"ALTER TABLE app_private.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app_private.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"GRANT SELECT,INSERT,UPDATE ON app_private.{table} TO petitecalendar_booking")
        op.execute(f"""CREATE POLICY lifecycle_scope ON app_private.{table}
            TO petitecalendar_booking
            USING(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid OR EXISTS (
                SELECT 1 FROM app_private.bookings b WHERE b.id=booking_id
                AND b.capability_hash=current_setting('app.booking_capability',true)))
            WITH CHECK(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid)""")
    op.execute("""GRANT SELECT(id,booking_id,user_id,booking_revision,candidates,
        timezone,status,created_at)
        ON app_private.booking_changes TO petitecalendar_api""")
    op.execute("""CREATE POLICY host_change_status ON app_private.booking_changes
        FOR SELECT TO petitecalendar_api
        USING(user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute("""GRANT UPDATE(start_at,end_at,blocked_start,blocked_end,
        invitee_timezone,status,revision,updated_at)
        ON app_private.bookings TO petitecalendar_booking""")
    for role in ("petitecalendar_worker", "petitecalendar_email_worker"):
        op.execute(f"GRANT SELECT(updated_at) ON app_private.bookings TO {role}")


def downgrade():
    # Lifecycle history cannot safely be removed after real changes.
    raise RuntimeError("Restore a pre-lifecycle backup to downgrade this migration.")
