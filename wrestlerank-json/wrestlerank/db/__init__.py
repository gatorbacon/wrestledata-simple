"""
Database initialization and connection management.

This module provides functions for initializing the database,
creating a session, and managing database connections.
"""

# Import the sqlite_db module to make it available through the package
from . import sqlite_db

# For backward compatibility, expose the main functions
from .sqlite_db import init_db, create_tables, close_db

# This is a placeholder to indicate we're using SQLite directly
# instead of SQLAlchemy
DB_TYPE = "sqlite"

# Global variables
engine = None
Session = None

def init_db(db_url='sqlite:///wrestlerank.db', echo=False):
    """
    Initialize the database connection.
    
    Args:
        db_url (str): SQLAlchemy database URL
        echo (bool): Whether to echo SQL statements
        
    Returns:
        engine: SQLAlchemy engine
    """
    global engine, Session
    
    # Create engine
    engine = create_engine(db_url, echo=echo)
    
    # Create session factory
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    
    return engine

def create_tables():
    """
    Create all tables defined in the models.
    
    This should be called after init_db() and before any database operations.
    """
    if engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    Base.metadata.create_all(engine)

def get_session():
    """
    Get a database session.
    
    Returns:
        Session: SQLAlchemy session
    """
    if Session is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    return Session()

def close_session(session):
    """
    Close a database session.
    
    Args:
        session: SQLAlchemy session to close
    """
    session.close() 