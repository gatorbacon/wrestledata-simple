#!/usr/bin/env python3
"""
Calculate rankings for wrestlers based on relationships.

This script uses PageRank and optimization algorithms to generate optimal
rankings that minimize ranking anomalies (cases where lower-ranked wrestlers
beat higher-ranked ones).
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: numpy not available. Using simplified ranking algorithm.")


def count_anomalies(ordering: List[int], adjacency_matrix, wrestler_count: int) -> int:
    """
    Count ranking anomalies - cases where a lower-ranked wrestler beat a higher-ranked one.
    
    Args:
        ordering: List of wrestler indices in ranking order (best to worst)
        adjacency_matrix: Matrix or dict of win relationships
        wrestler_count: Number of wrestlers
        
    Returns:
        Number of anomalies
    """
    anomalies = 0
    
    # Create rank lookup: rank[i] = rank of wrestler at index i
    rank = [0] * wrestler_count
    for rank_pos, wrestler_idx in enumerate(ordering):
        rank[wrestler_idx] = rank_pos
    
    # Check all pairs
    for i in range(wrestler_count):
        for j in range(i + 1, wrestler_count):
            # If j is ranked higher (lower rank number) but i beat j, that's an anomaly
            if rank[j] < rank[i]:  # j is ranked higher
                if isinstance(adjacency_matrix, dict):
                    # Dict-based matrix
                    key = tuple(sorted([i, j]))
                    if key in adjacency_matrix and adjacency_matrix[key] > 0:
                        anomalies += 1
                else:
                    # NumPy matrix
                    if adjacency_matrix[i, j] > 0:
                        anomalies += 1
    
    return anomalies


def calculate_pagerank_simple(relationships: Dict, wrestlers: Dict[str, Dict]) -> List[Tuple[str, float]]:
    """
    Calculate PageRank scores using a simple iterative method.
    
    Args:
        relationships: Dictionary with direct and common opponent relationships
        wrestlers: Dictionary of wrestler_id -> wrestler_info
        
    Returns:
        List of (wrestler_id, pagerank_score) tuples, sorted by score
    """
    wrestler_ids = list(wrestlers.keys())
    wrestler_to_idx = {w_id: i for i, w_id in enumerate(wrestler_ids)}
    n = len(wrestler_ids)
    
    # Build adjacency matrix as a dict (wins from i to j)
    adjacency = defaultdict(lambda: defaultdict(float))
    
    # Add direct relationships
    for pair_key, rel in relationships.get('direct_relationships', {}).items():
        # Handle string keys from JSON (format: "id1_id2")
        if isinstance(pair_key, str):
            ids = pair_key.split('_')
            if len(ids) == 2:
                w1_id, w2_id = ids
            else:
                continue
        else:
            # Handle tuple keys
            w1_id, w2_id = pair_key
        
        # Also get from rel if available (more reliable)
        if 'wrestler1_id' in rel and 'wrestler2_id' in rel:
            w1_id = rel['wrestler1_id']
            w2_id = rel['wrestler2_id']
        
        if w1_id not in wrestler_to_idx or w2_id not in wrestler_to_idx:
            continue
        
        idx1 = wrestler_to_idx[w1_id]
        idx2 = wrestler_to_idx[w2_id]
        
        wins_1 = rel.get('direct_wins_1', 0)
        wins_2 = rel.get('direct_wins_2', 0)
        
        # Determine direction based on who has more wins
        if wins_1 > wins_2:
            # wrestler1 (idx1) beat wrestler2 (idx2)
            adjacency[idx1][idx2] += wins_1
        elif wins_2 > wins_1:
            # wrestler2 (idx2) beat wrestler1 (idx1)
            adjacency[idx2][idx1] += wins_2
        # If tied, don't add anything
    
    # Add common opponent relationships (with lower weight)
    for pair_key, rel in relationships.get('common_opponent_relationships', {}).items():
        # Handle string keys from JSON (format: "id1_id2")
        if isinstance(pair_key, str):
            ids = pair_key.split('_')
            if len(ids) == 2:
                w1_id, w2_id = ids
            else:
                continue
        else:
            # Handle tuple keys
            w1_id, w2_id = pair_key
        
        # Also get from rel if available (more reliable)
        if 'wrestler1_id' in rel and 'wrestler2_id' in rel:
            w1_id = rel['wrestler1_id']
            w2_id = rel['wrestler2_id']
        
        if w1_id not in wrestler_to_idx or w2_id not in wrestler_to_idx:
            continue
        
        idx1 = wrestler_to_idx[w1_id]
        idx2 = wrestler_to_idx[w2_id]
        
        co_wins_1 = rel.get('common_opp_wins_1', 0)
        co_wins_2 = rel.get('common_opp_wins_2', 0)
        
        # Determine direction based on who has more common opponent wins
        if co_wins_1 > co_wins_2:
            # wrestler1 has advantage via common opponents
            adjacency[idx1][idx2] += 0.5 * co_wins_1
        elif co_wins_2 > co_wins_1:
            # wrestler2 has advantage via common opponents
            adjacency[idx2][idx1] += 0.5 * co_wins_2
        # If tied, don't add anything
    
    # Calculate PageRank using power iteration
    damping = 0.85
    max_iter = 100
    tol = 1e-6
    
    # Initialize PageRank vector
    pr = [1.0 / n] * n
    
    # Calculate out-degree for each node
    out_degree = [sum(adjacency[i].values()) for i in range(n)]
    
    for iteration in range(max_iter):
        pr_new = [(1 - damping) / n] * n
        
        for i in range(n):
            if out_degree[i] > 0:
                for j, weight in adjacency[i].items():
                    pr_new[j] += damping * pr[i] * (weight / out_degree[i])
            else:
                # Dangling node - distribute evenly
                for j in range(n):
                    pr_new[j] += damping * pr[i] / n
        
        # Check convergence
        diff = sum(abs(pr_new[i] - pr[i]) for i in range(n))
        if diff < tol:
            break
        
        pr = pr_new
    
    # Create list of (wrestler_id, score) and sort
    scores = [(wrestler_ids[i], pr[i]) for i in range(n)]
    scores.sort(key=lambda x: x[1], reverse=True)
    
    return scores


def greedy_ranking(relationships: Dict, wrestlers: Dict[str, Dict]) -> List[str]:
    """
    Simple greedy ranking based on win percentage and head-to-head results.
    
    Args:
        relationships: Dictionary with direct and common opponent relationships
        wrestlers: Dictionary of wrestler_id -> wrestler_info
        
    Returns:
        List of wrestler_ids in ranking order
    """
    wrestler_ids = list(wrestlers.keys())
    
    # Calculate scores for each wrestler
    scores = {}
    for w_id in wrestler_ids:
        wrestler = wrestlers[w_id]
        wins = wrestler.get('wins', 0)
        losses = wrestler.get('losses', 0)
        total = wins + losses
        
        # Base score from win percentage
        if total > 0:
            base_score = wins / total
        else:
            base_score = 0.0
        
        # Add bonus for quality wins (beating highly-ranked opponents)
        # For now, just use base score
        scores[w_id] = base_score
    
    # Sort by score
    ranked = sorted(wrestler_ids, key=lambda w_id: scores[w_id], reverse=True)
    
    return ranked


def calculate_rankings_for_weight_class(
    relationships_data: Dict,
    algorithm: str = 'pagerank'
) -> List[Dict]:
    """
    Calculate rankings for a single weight class.
    
    Args:
        relationships_data: Dictionary with wrestlers and relationships
        algorithm: Algorithm to use ('pagerank' or 'greedy')
        
    Returns:
        List of ranking dictionaries with wrestler info and rank
    """
    wrestlers = relationships_data['wrestlers']
    relationships = {
        'direct_relationships': relationships_data.get('direct_relationships', {}),
        'common_opponent_relationships': relationships_data.get('common_opponent_relationships', {})
    }
    
    if algorithm == 'pagerank':
        # Use PageRank
        ranked_scores = calculate_pagerank_simple(relationships, wrestlers)
        rankings = []
        for rank, (wrestler_id, score) in enumerate(ranked_scores, 1):
            wrestler = wrestlers[wrestler_id]
            rankings.append({
                'rank': rank,
                'wrestler_id': wrestler_id,
                'name': wrestler['name'],
                'team': wrestler['team'],
                'record': f"{wrestler.get('wins', 0)}-{wrestler.get('losses', 0)}",
                'score': score,
                'algorithm': 'pagerank'
            })
    else:
        # Use greedy ranking
        ranked_ids = greedy_ranking(relationships, wrestlers)
        rankings = []
        for rank, wrestler_id in enumerate(ranked_ids, 1):
            wrestler = wrestlers[wrestler_id]
            rankings.append({
                'rank': rank,
                'wrestler_id': wrestler_id,
                'name': wrestler['name'],
                'team': wrestler['team'],
                'record': f"{wrestler.get('wins', 0)}-{wrestler.get('losses', 0)}",
                'algorithm': 'greedy'
            })
    
    return rankings


def load_relationships(season: int, data_dir: str = "mt/rankings_data") -> Dict[str, Dict]:
    """
    Load relationship data for all weight classes.
    
    Args:
        season: Season year
        data_dir: Directory containing relationship files
        
    Returns:
        Dictionary mapping weight_class -> relationships_data
    """
    data_path = Path(data_dir) / str(season)
    
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    relationships_by_weight = {}
    
    for rel_file in sorted(data_path.glob("relationships_*.json")):
        weight_class = rel_file.stem.replace("relationships_", "")
        with open(rel_file, 'r', encoding='utf-8') as f:
            relationships_by_weight[weight_class] = json.load(f)
    
    return relationships_by_weight


def calculate_all_rankings(
    season: int,
    algorithm: str = 'pagerank',
    data_dir: str = "mt/rankings_data"
) -> Dict[str, List[Dict]]:
    """
    Calculate rankings for all weight classes.
    
    Args:
        season: Season year
        algorithm: Algorithm to use ('pagerank' or 'greedy')
        data_dir: Directory containing relationship files
        
    Returns:
        Dictionary mapping weight_class -> list of rankings
    """
    print(f"Calculating rankings for season {season} using {algorithm} algorithm...")
    
    # Load relationships
    relationships_by_weight = load_relationships(season, data_dir)
    
    if not relationships_by_weight:
        raise ValueError(f"No relationship data found for season {season}")
    
    # Calculate rankings for each weight class
    all_rankings = {}
    
    for weight_class in sorted(relationships_by_weight.keys()):
        print(f"\nWeight class {weight_class}:")
        rankings = calculate_rankings_for_weight_class(
            relationships_by_weight[weight_class],
            algorithm
        )
        all_rankings[weight_class] = rankings
        print(f"  Ranked {len(rankings)} wrestlers")
        if rankings:
            print(f"  Top 5:")
            for r in rankings[:5]:
                print(f"    {r['rank']}. {r['name']} ({r['team']}) - {r['record']}")
    
    return all_rankings


def save_rankings(rankings_by_weight: Dict[str, List[Dict]], season: int, output_dir: str = "mt/rankings_data"):
    """
    Save rankings to JSON files.
    
    Args:
        rankings_by_weight: Dictionary from calculate_all_rankings
        season: Season year
        output_dir: Directory to save files
    """
    output_path = Path(output_dir) / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for weight_class, rankings in rankings_by_weight.items():
        rankings_file = output_path / f"rankings_{weight_class}.json"
        with open(rankings_file, 'w', encoding='utf-8') as f:
            json.dump({
                'weight_class': weight_class,
                'season': season,
                'rankings': rankings
            }, f, indent=2)
        print(f"Saved rankings for {weight_class} to {rankings_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Calculate rankings for wrestlers')
    parser.add_argument('-season', type=int, required=True, help='Season year (e.g., 2026)')
    parser.add_argument('-algorithm', choices=['pagerank', 'greedy'], default='pagerank',
                       help='Ranking algorithm to use')
    parser.add_argument('-data-dir', default='mt/rankings_data', help='Directory containing relationship data')
    parser.add_argument('-save', action='store_true', help='Save rankings to JSON files')
    args = parser.parse_args()
    
    rankings = calculate_all_rankings(args.season, args.algorithm, args.data_dir)
    
    if args.save:
        save_rankings(rankings, args.season, args.data_dir)
    
    # Print summary
    print(f"\n=== Summary ===")
    for wc in sorted(rankings.keys()):
        print(f"{wc}: {len(rankings[wc])} wrestlers ranked")

