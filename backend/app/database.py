from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

DATABASE_URL = get_settings().DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Explicit naming convention for every constraint type. Required for
# Alembic's SQLite "batch mode" (see alembic/env.py's render_as_batch=True)
# to work at all — batch mode recreates the table under the hood and needs
# every constraint to have a discoverable name, but SQLAlchemy leaves
# constraints unnamed by default unless a convention like this is set.
# Also just generally good practice: predictable constraint names instead
# of dialect-generated ones that differ across environments.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base = declarative_base(metadata=MetaData(naming_convention=_NAMING_CONVENTION))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
