"""
Database models for the WrestleRank system.

This module defines the SQLAlchemy ORM models that represent the core entities
in the wrestling ranking system: Teams, Wrestlers, Matches, and Rankings.
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

class MatchType(enum.Enum):
    """Types of wrestling matches."""
    REGULAR = "regular"
    TOURNAMENT = "tournament"
    DUAL = "dual"
    CHAMPIONSHIP = "championship"

class Team(Base):
    """
    Represents a wrestling team.
    
    This model stores information about wrestling teams, including their name,
    location, and other identifying information.
    """
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(50))
    location = Column(String(100))
    state = Column(String(2))
    website = Column(String(255))
    
    # Relationships
    wrestlers = relationship("Wrestler", back_populates="team")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Team(id={self.id}, name='{self.name}')>"

class Wrestler(Base):
    """
    Represents an individual wrestler.
    
    This model stores information about wrestlers, including their name,
    weight class, team affiliation, and record.
    """
    __tablename__ = 'wrestlers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    team_id = Column(Integer, ForeignKey('teams.id'))
    weight_class = Column(Enum(WeightClass), nullable=False)
    grade = Column(Integer)  # 9-12 for high school
    
    # Stats
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
    # Calculated metrics
    win_percentage = Column(Float)
    rpi = Column(Float)
    
    # Relationships
    team = relationship("Team", back_populates="wrestlers")
    matches_as_wrestler1 = relationship("Match", foreign_keys="Match.wrestler1_id", back_populates="wrestler1")
    matches_as_wrestler2 = relationship("Match", foreign_keys="Match.wrestler2_id", back_populates="wrestler2")
    rankings = relationship("Ranking", back_populates="wrestler")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_match_date = Column(Date)
    
    def __repr__(self):
        return f"<Wrestler(id={self.id}, name='{self.name}', weight_class={self.weight_class})>"
    
    @property
    def full_record(self):
        """Return the wrestler's record as a string (W-L)."""
        return f"{self.wins}-{self.losses}"
    
    @property
    def calculate_win_percentage(self):
        """Calculate and return the win percentage."""
        total_matches = self.wins + self.losses
        if total_matches == 0:
            return 0.0
        return self.wins / total_matches

class Match(Base):
    """
    Represents a match between two wrestlers.
    
    This model stores information about individual matches, including the
    participants, result, date, and context.
    """
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True)
    wrestler1_id = Column(Integer, ForeignKey('wrestlers.id'), nullable=False)
    wrestler2_id = Column(Integer, ForeignKey('wrestlers.id'), nullable=False)
    
    # Match details
    date = Column(Date, nullable=False)
    weight_class = Column(Enum(WeightClass), nullable=False)
    match_type = Column(Enum(MatchType), default=MatchType.REGULAR)
    tournament_name = Column(String(255))
    
    # Result
    winner_id = Column(Integer, ForeignKey('wrestlers.id'))
    score = Column(String(20))  # e.g., "Fall 2:30", "Dec 5-2"
    
    # Relationships
    wrestler1 = relationship("Wrestler", foreign_keys=[wrestler1_id], back_populates="matches_as_wrestler1")
    wrestler2 = relationship("Wrestler", foreign_keys=[wrestler2_id], back_populates="matches_as_wrestler2")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        # Prevent duplicate matches between the same wrestlers on the same date
        UniqueConstraint('wrestler1_id', 'wrestler2_id', 'date', name='unique_match'),
    )
    
    def __repr__(self):
        return f"<Match(id={self.id}, date='{self.date}', w1={self.wrestler1_id}, w2={self.wrestler2_id})>"

class Ranking(Base):
    """
    Represents a wrestler's ranking.
    
    This model stores information about a wrestler's ranking within their
    weight class, including the ranking date and algorithm used.
    """
    __tablename__ = 'rankings'
    
    id = Column(Integer, primary_key=True)
    wrestler_id = Column(Integer, ForeignKey('wrestlers.id'), nullable=False)
    weight_class = Column(Enum(WeightClass), nullable=False)
    rank = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    
    # Algorithm details
    algorithm = Column(String(50))  # e.g., "pagerank", "mfas", "simulated_annealing"
    algorithm_parameters = Column(Text)  # JSON string of parameters used
    
    # Metrics at time of ranking
    win_percentage = Column(Float)
    rpi = Column(Float)
    
    # Relationships
    wrestler = relationship("Wrestler", back_populates="rankings")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        # Ensure unique rank per weight class per date
        UniqueConstraint('weight_class', 'rank', 'date', name='unique_rank'),
        # Ensure wrestler is only ranked once per date
        UniqueConstraint('wrestler_id', 'date', name='unique_wrestler_ranking'),
    )
    
    def __repr__(self):
        return f"<Ranking(wrestler_id={self.wrestler_id}, rank={self.rank}, date='{self.date}')>"

class RankingSnapshot(Base):
    """
    Represents a complete snapshot of rankings for a weight class on a specific date.
    
    This model allows for tracking the history of rankings over time and
    comparing different ranking algorithms.
    """
    __tablename__ = 'ranking_snapshots'
    
    id = Column(Integer, primary_key=True)
    weight_class = Column(Enum(WeightClass), nullable=False)
    date = Column(Date, nullable=False)
    algorithm = Column(String(50), nullable=False)
    
    # Metrics
    total_anomalies = Column(Integer)
    description = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        # Ensure unique snapshot per weight class, date, and algorithm
        UniqueConstraint('weight_class', 'date', 'algorithm', name='unique_snapshot'),
    )
    
    def __repr__(self):
        return f"<RankingSnapshot(weight_class={self.weight_class}, date='{self.date}', algorithm='{self.algorithm}')>" 