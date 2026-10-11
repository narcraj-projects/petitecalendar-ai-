from alembic import op

revision = "0005_booking_outbox"
down_revision = "0004_bookings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.booking_outbox (
        booking_id uuid NOT NULL REFERENCES app_private.bookings(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES app_private.host_profiles(user_id),
        revision integer NOT NULL CHECK(revision>=1),
        event_type varchar(40) NOT NULL CHECK(event_type='booking_confirmed'),
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(booking_id,revision,event_type)
    )""")
    op.execute("ALTER TABLE app_private.booking_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.booking_outbox FORCE ROW LEVEL SECURITY")
    op.execute("GRANT INSERT ON app_private.booking_outbox TO petitecalendar_booking")
    op.execute("""CREATE POLICY booking_emits_event ON app_private.booking_outbox
        FOR INSERT TO petitecalendar_booking
        WITH CHECK(user_id=NULLIF(current_setting('app.booking_host',true),'')::uuid)""")


def downgrade():
    op.drop_table("booking_outbox", schema="app_private")
