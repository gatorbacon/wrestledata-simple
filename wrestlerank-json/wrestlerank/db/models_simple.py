"""
Simplified database models for the WrestleRank system.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, 
    ForeignKey, Table, Text, Enum, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

# Create the base class for all models
Base = declarative_base()

# Define enums for consistent data representation
class WeightClass(enum.Enum):
    """Standard weight classes for high school wrestling."""
    W106 = "106"
    W113 = "113"
    W120 = "120"
    W126 = "126"
    W132 = "132"
    W138 = "138"
    W144 = "144"
    W150 = "150"
    W157 = "157"
    W165 = "165"
    W175 = "175"
    W190 = "190"
    W215 = "215"
    W285 = "285"

class Team(Base):
    """Represents a wrestling team."""
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(50))
    state = Column(String(2))
    
    # Relationships
    wrestlers = relationship("Wrestler", back_populates="team")
    
    def __repr__(self):
        return f"<Team(id={self.id}, name='{self.name}')>"

class Wrestler(Base):
    """Represents an individual wrestler."""
    __tablename__ = 'wrestlers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    team_id = Column(Integer, ForeignKey('teams.id'))
    weight_class = Column(Enum(WeightClass), nullable=False)
    
    # Stats
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
    # Relationships
    team = relationship("Team", back_populates="wrestlers")
    
    @property
    def full_record(self):
        """Return the wrestler's record as a string."""
        return f"{self.wins}-{self.losses}"
    
    def __repr__(self):
        return f"<Wrestler(id={self.id}, name='{self.name}', record={self.full_record})>" 