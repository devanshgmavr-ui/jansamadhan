import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure backend/ is on sys.path so `app.*` imports work
# when running `alembic` from backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models.user  # noqa: E402,F401  (register User metadata)
import app.models.profile  # noqa: E402,F401
import app.models.otp  # noqa: E402,F401
import app.models.auth_tokens  # noqa: E402,F401
import app.models.problem  # noqa: E402,F401
import app.models.ai_review  # noqa: E402,F401
import app.models.solution  # noqa: E402,F401
import app.models.contribution  # noqa: E402,F401
import app.models.collaboration  # noqa: E402,F401
import app.models.revoked_token  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Database URL always comes from application configuration (.env),
# never permanently hard-coded in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
