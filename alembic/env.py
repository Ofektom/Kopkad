import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context

# Load config from alembic.ini
config = context.config

# Load .env variables
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your settings and models
from config.settings import settings
from database.postgres import Base
from models.user import User
from models.business import Business
from models.user_business import user_business
from models.settings import Settings
from models.audit import AuditMixin

# Set the SQLAlchemy URL dynamically from settings
config.set_main_option("sqlalchemy.url", settings.POSTGRES_URI)

# Define target metadata
target_metadata = Base.metadata

def run_migrations_offline() -> None:
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    print(f"Connecting to database: {config.get_main_option('sqlalchemy.url')}")
    with connectable.connect() as connection:
        # Set and verify search_path
        connection.execute(text("SET search_path TO public"))
        result = connection.execute(text("SHOW search_path")).fetchone()
        print(f"Database search_path: {result}")
        # Debug: Check for paymentrequeststatus ENUM
        result = connection.execute(
            text("SELECT typname FROM pg_type WHERE typname = 'paymentrequeststatus'")
        ).fetchone()
        print(f"ENUM paymentrequeststatus exists: {bool(result)}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()