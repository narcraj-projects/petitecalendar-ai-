"""Private host profile and transaction-scoped tenant isolation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_host_profiles"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS app_private")
    op.execute("REVOKE ALL ON SCHEMA app_private FROM PUBLIC")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'petitecalendar_api') THEN
                CREATE ROLE petitecalendar_api NOLOGIN;
            END IF;
            EXECUTE format('GRANT petitecalendar_api TO %I', current_user);
        END $$
    """)
    op.create_table(
        "host_profiles",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("username ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'", name="valid_username"),
        schema="app_private",
    )
    op.execute("ALTER TABLE app_private.host_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_private.host_profiles FORCE ROW LEVEL SECURITY")
    op.execute("GRANT USAGE ON SCHEMA app_private TO petitecalendar_api")
    op.execute("GRANT SELECT, INSERT, UPDATE ON app_private.host_profiles TO petitecalendar_api")
    op.execute("""
        CREATE POLICY host_owns_profile ON app_private.host_profiles TO petitecalendar_api
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
    """)


def downgrade():
    op.drop_table("host_profiles", schema="app_private")
    # Keep the shared schema and role, which later migrations may use.
