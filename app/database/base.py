"""
Declarative base for all SQLAlchemy ORM models.
Import Base here (not from connection.py) to avoid circular imports.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this single base."""
    pass
