"""
Database operations for the WrestleRank system.

This module provides functions for common database operations,
such as adding, updating, and querying entities.
"""

from sqlalchemy.exc import IntegrityError
from . import get_session
from .models import Team, Wrestler, Match, Ranking, RankingSnapshot, WeightClass

# Team operations
def add_team(name, short_name=None, location=None, state=None, website=None):
    """
    Add a new team to the database.
    
    Args:
        name (str): Team name
        short_name (str, optional): Abbreviated team name
        location (str, optional): Team location
        state (str, optional): Two-letter state code
        website (str, optional): Team website URL
        
    Returns:
        Team: The created team object
    """
    session = get_session()
    try:
        team = Team(
            name=name,
            short_name=short_name,
            location=location,
            state=state,
            website=website
        )
        session.add(team)
        session.commit()
        return team
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()

def get_team_by_name(name):
    """
    Get a team by name.
    
    Args:
        name (str): Team name to search for
        
    Returns:
        Team: The team object if found, None otherwise
    """
    session = get_session()
    try:
        return session.query(Team).filter(Team.name == name).first()
    finally:
        session.close()

# Wrestler operations
def add_wrestler(name, team_id, weight_class, grade=None):
    """
    Add a new wrestler to the database.
    
    Args:
        name (str): Wrestler name
        team_id (int): ID of the wrestler's team
        weight_class (WeightClass): Wrestler's weight class
        grade (int, optional): Wrestler's grade (9-12)
        
    Returns:
        Wrestler: The created wrestler object
    """
    session = get_session()
    try:
        wrestler = Wrestler(
            name=name,
            team_id=team_id,
            weight_class=weight_class,
            grade=grade,
            wins=0,
            losses=0
        )
        session.add(wrestler)
        session.commit()
        return wrestler
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()

def get_wrestlers_by_weight_class(weight_class):
    """
    Get all wrestlers in a specific weight class.
    
    Args:
        weight_class (WeightClass): Weight class to filter by
        
    Returns:
        list: List of Wrestler objects
    """
    session = get_session()
    try:
        return session.query(Wrestler).filter(Wrestler.weight_class == weight_class).all()
    finally:
        session.close()

# Match operations
def add_match(wrestler1_id, wrestler2_id, winner_id, date, weight_class, 
              match_type=None, tournament_name=None, score=None):
    """
    Add a new match to the database.
    
    Args:
        wrestler1_id (int): ID of the first wrestler
        wrestler2_id (int): ID of the second wrestler
        winner_id (int): ID of the winning wrestler
        date (date): Date of the match
        weight_class (WeightClass): Weight class of the match
        match_type (MatchType, optional): Type of match
        tournament_name (str, optional): Name of tournament if applicable
        score (str, optional): Match score or result description
        
    Returns:
        Match: The created match object
    """
    session = get_session()
    try:
        match = Match(
            wrestler1_id=wrestler1_id,
            wrestler2_id=wrestler2_id,
            winner_id=winner_id,
            date=date,
            weight_class=weight_class,
            match_type=match_type,
            tournament_name=tournament_name,
            score=score
        )
        session.add(match)
        
        # Update wrestler records
        wrestler1 = session.query(Wrestler).get(wrestler1_id)
        wrestler2 = session.query(Wrestler).get(wrestler2_id)
        
        if winner_id == wrestler1_id:
            wrestler1.wins += 1
            wrestler2.losses += 1
        else:
            wrestler1.losses += 1
            wrestler2.wins += 1
            
        # Update win percentages
        wrestler1.win_percentage = wrestler1.calculate_win_percentage
        wrestler2.win_percentage = wrestler2.calculate_win_percentage
        
        # Update last match date
        if wrestler1.last_match_date is None or date > wrestler1.last_match_date:
            wrestler1.last_match_date = date
        if wrestler2.last_match_date is None or date > wrestler2.last_match_date:
            wrestler2.last_match_date = date
            
        session.commit()
        return match
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()

# Ranking operations
def add_ranking(wrestler_id, weight_class, rank, date, algorithm=None, 
                algorithm_parameters=None, win_percentage=None, rpi=None):
    """
    Add a new ranking to the database.
    
    Args:
        wrestler_id (int): ID of the wrestler
        weight_class (WeightClass): Weight class of the ranking
        rank (int): Numerical rank (1 is best)
        date (date): Date of the ranking
        algorithm (str, optional): Algorithm used to generate the ranking
        algorithm_parameters (str, optional): JSON string of algorithm parameters
        win_percentage (float, optional): Wrestler's win percentage at time of ranking
        rpi (float, optional): Wrestler's RPI at time of ranking
        
    Returns:
        Ranking: The created ranking object
    """
    session = get_session()
    try:
        # If win_percentage or RPI not provided, get from wrestler
        if win_percentage is None or rpi is None:
            wrestler = session.query(Wrestler).get(wrestler_id)
            if win_percentage is None:
                win_percentage = wrestler.win_percentage
            if rpi is None:
                rpi = wrestler.rpi
                
        ranking = Ranking(
            wrestler_id=wrestler_id,
            weight_class=weight_class,
            rank=rank,
            date=date,
            algorithm=algorithm,
            algorithm_parameters=algorithm_parameters,
            win_percentage=win_percentage,
            rpi=rpi
        )
        session.add(ranking)
        session.commit()
        return ranking
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()

def get_rankings_by_date_and_weight(date, weight_class):
    """
    Get all rankings for a specific date and weight class.
    
    Args:
        date (date): Date of the rankings
        weight_class (WeightClass): Weight class to filter by
        
    Returns:
        list: List of Ranking objects ordered by rank
    """
    session = get_session()
    try:
        return session.query(Ranking).filter(
            Ranking.date == date,
            Ranking.weight_class == weight_class
        ).order_by(Ranking.rank).all()
    finally:
        session.close() 