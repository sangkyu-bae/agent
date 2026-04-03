"""Base class for SQLAlchemy ORM models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models.

    All models should inherit from this class to be registered
    with SQLAlchemy's metadata.
    """

    pass
