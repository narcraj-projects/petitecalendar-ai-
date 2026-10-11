from alembic import op

revision = "0003_availability"
down_revision = "0002_event_types"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app_private.availability (
        user_id uuid PRIMARY KEY REFERENCES app_private.host_profiles(user_id) ON DELETE CASCADE,
        payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
        revision integer NOT NULL CHECK (revision >= 1),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("ALTER TABLE app_private.availability ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.availability FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT, UPDATE ON app_private.availability TO petitecalendar_api")
    op.execute("GRANT SELECT ON app_private.availability TO petitecalendar_public")
    op.execute("""CREATE POLICY host_owns_availability ON app_private.availability
        TO petitecalendar_api
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)""")
    op.execute("""CREATE POLICY published_availability ON app_private.availability
        FOR SELECT TO petitecalendar_public USING (EXISTS (
            SELECT 1 FROM app_private.event_types e
            WHERE e.user_id = availability.user_id AND e.published))""")


def downgrade():
    op.drop_table("availability", schema="app_private")
