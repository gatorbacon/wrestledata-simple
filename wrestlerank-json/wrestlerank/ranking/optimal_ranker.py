"""
Optimal Ranking Algorithm for WrestleRank.

This module adapts the advanced ranking algorithms from the legacy system
to work with the new database-driven framework. It uses sophisticated
optimization techniques including PageRank, MFAS, Simulated Annealing,
and Local Search to minimize ranking anomalies.
"""

import os
import time
import random
from datetime import datetime
import sqlite3

# Try importing optional dependencies
try:
    import numpy as np
    import tqdm
    from concurrent.futures import ProcessPoolExecutor
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

from wrestlerank.db import sqlite_db

# Constants for optimization
INITIAL_TEMPERATURE = 10.0  # Starting temperature for simulated annealing
COOLING_RATE = 0.9999      # Rate at which temperature decreases
MIN_TEMPERATURE = 0.01     # Minimum temperature for simulated annealing
MAX_ITERATIONS = 100000    # Maximum iterations for simulated annealing
PARALLEL_RUNS = 4          # Number of parallel simulated annealing runs

class OptimalRanker:
    """
    Generates optimal rankings for wrestlers by minimizing anomalies.
    
    This class implements the same advanced optimization techniques from
    the legacy system, but adapted to work with database input instead of
    HTML matrix files.
    """
    
    def __init__(self, weight_class):
        """
        Initialize the ranker for a specific weight class.
        
        Args:
            weight_class: Weight class to generate rankings for
        """
        if not DEPS_AVAILABLE:
            raise ImportError(
                "Required dependencies not available. Please run: "
                "python install_deps.py"
            )
            
        self.weight_class = weight_class
        self.wrestlers = []  # List of wrestler information
        self.wrestler_id_to_index = {}  # Mapping from wrestler ID to index
        self.adjacency_matrix = None  # Will be initialized when data is loaded
        self.best_ordering = None  # Best ordering found during optimization
        self.best_score = None  # Score (anomaly count) of the best ordering
    
    def load_data_from_db(self):
        """
        Load wrestler data and match results from the database.
        
        This replaces the parse_matrix_file method from the legacy system.
        """
        print(f"Loading data for weight class {self.weight_class} from database...")
        
        # Initialize database connection
        sqlite_db.init_db()
        cursor = sqlite_db.conn.cursor()
        
        try:
            # Get active wrestlers for this weight class
            cursor.execute("""
                SELECT id, external_id, name, team_id, team_name, wins, losses
                FROM wrestlers 
                WHERE weight_class = ? AND active_team = 1
                ORDER BY win_percentage DESC
            """, (self.weight_class,))
            
            wrestler_rows = cursor.fetchall()
            
            if not wrestler_rows:
                print(f"No active wrestlers found for weight class {self.weight_class}")
                return False
            
            # Build the wrestlers list and index mapping
            for i, wrestler in enumerate(wrestler_rows):
                self.wrestlers.append({
                    'id': wrestler['external_id'],  # Store external_id as 'id'
                    'db_id': wrestler['id'],        # Store database ID as 'db_id'
                    'external_id': wrestler['external_id'],  # Also store as 'external_id' for clarity
                    'name': wrestler['name'],
                    'team': wrestler['team_name'],
                    'record': f"{wrestler['wins']}-{wrestler['losses']}"
                })
                self.wrestler_id_to_index[wrestler['external_id']] = i
            
            n = len(self.wrestlers)
            self.adjacency_matrix = np.zeros((n, n), dtype=float)
            
            # Now load direct relationships from database
            print("Loading direct match relationships...")
            cursor.execute("""
                SELECT wrestler1_id, wrestler2_id, direct_wins, direct_losses 
                FROM wrestler_relationships
                WHERE weight_class = ? AND (direct_wins > 0 OR direct_losses > 0)
            """, (self.weight_class,))
            
            direct_relationships = cursor.fetchall()
            
            # Build adjacency matrix from relationships
            for rel in direct_relationships:
                w1 = rel['wrestler1_id']
                w2 = rel['wrestler2_id']
                direct_wins = rel['direct_wins']
                
                # Only if both wrestlers are in our active set
                if w1 in self.wrestler_id_to_index and w2 in self.wrestler_id_to_index:
                    idx1 = self.wrestler_id_to_index[w1]
                    idx2 = self.wrestler_id_to_index[w2]
                    
                    # Add weight 1.0 for each direct win
                    self.adjacency_matrix[idx1, idx2] = float(direct_wins)
            
            # Also load common opponent relationships
            print("Loading common opponent relationships...")
            cursor.execute("""
                SELECT wrestler1_id, wrestler2_id, common_opp_wins, common_opp_losses 
                FROM wrestler_relationships
                WHERE weight_class = ? AND (common_opp_wins > 0 OR common_opp_losses > 0)
            """, (self.weight_class,))
            
            co_relationships = cursor.fetchall()
            
            # Add common opponent relationships with lower weight
            for rel in co_relationships:
                w1 = rel['wrestler1_id']
                w2 = rel['wrestler2_id']
                co_wins = rel['common_opp_wins']
                
                # Only if both wrestlers are in our active set
                if w1 in self.wrestler_id_to_index and w2 in self.wrestler_id_to_index:
                    idx1 = self.wrestler_id_to_index[w1]
                    idx2 = self.wrestler_id_to_index[w2]
                    
                    # Add weight 0.5 for each common opponent win
                    # Only add if there's no direct relationship or add to it
                    if self.adjacency_matrix[idx1, idx2] == 0:
                        self.adjacency_matrix[idx1, idx2] = 0.5 * float(co_wins)
                    else:
                        # If there's already a direct relationship, just add a smaller bonus
                        self.adjacency_matrix[idx1, idx2] += 0.1 * float(co_wins)
            
            print(f"Loaded {len(self.wrestlers)} wrestlers and their relationships")
            return True
            
        finally:
            sqlite_db.close_db()
    
    def calculate_pagerank(self, damping=0.85, max_iter=100, tol=1e-6):
        """Calculate PageRank scores for initial ranking."""
        n = len(self.wrestlers)
        
        # Create a copy of the adjacency matrix with float values
        M = self.adjacency_matrix.astype(float)
        
        # Normalize by column
        col_sums = M.sum(axis=0)
        # Avoid division by zero
        col_sums[col_sums == 0] = 1
        M = M / col_sums
        
        # Initialize PageRank vector
        v = np.ones(n) / n
        
        # Power iteration
        for _ in range(max_iter):
            v_prev = v.copy()
            v = damping * M.dot(v) + (1 - damping) / n
            
            # Check for convergence
            if np.linalg.norm(v - v_prev, 1) < tol:
                break
        
        # Create initial ordering based on PageRank
        ordering = np.argsort(-v)
        return ordering
    
    def greedy_mfas(self):
        """Greedy approximation for Minimum Feedback Arc Set problem."""
        n = len(self.wrestlers)
        remaining = set(range(n))
        ordering = []
        
        while remaining:
            best_score = float('-inf')
            best_node = None
            
            for node in remaining:
                # Calculate score: outgoing - incoming edges
                outgoing = sum(self.adjacency_matrix[node, j] for j in remaining if j != node)
                incoming = sum(self.adjacency_matrix[j, node] for j in remaining if j != node)
                score = outgoing - incoming
                
                if score > best_score:
                    best_score = score
                    best_node = node
            
            ordering.append(best_node)
            remaining.remove(best_node)
        
        # Reverse to get correct ordering (highest score first)
        return ordering[::-1]
    
    def count_anomalies(self, ordering):
        """Count the number of anomalies in a given ordering."""
        n = len(ordering)
        anomalies = 0
        
        # Check for each pair of wrestlers
        for i in range(n):
            for j in range(i+1, n):
                # If lower-ranked wrestler beat higher-ranked wrestler
                if self.adjacency_matrix[ordering[j], ordering[i]] > 0:
                    anomalies += self.adjacency_matrix[ordering[j], ordering[i]]
        
        return anomalies
    
    def calculate_swap_delta(self, ordering, i, j):
        """Calculate change in anomalies if wrestlers at positions i and j are swapped."""
        n = len(ordering)
        if i < 0 or j < 0 or i >= n or j >= n or i == j:
            return 0
        
        # Ensure i < j for simplicity
        if i > j:
            i, j = j, i
        
        # Only need to recalculate anomalies for pairs involving i or j
        wrestler_i = ordering[i]
        wrestler_j = ordering[j]
        
        # Calculate current anomalies involving these wrestlers
        current_anomalies = 0
        
        # Check all wrestlers between i and j
        for k in range(i+1, j):
            wrestler_k = ordering[k]
            
            # Anomalies involving wrestler i
            if self.adjacency_matrix[wrestler_k, wrestler_i] > 0:
                current_anomalies += self.adjacency_matrix[wrestler_k, wrestler_i]
            
            # Anomalies involving wrestler j
            if self.adjacency_matrix[wrestler_j, wrestler_k] > 0:
                current_anomalies += self.adjacency_matrix[wrestler_j, wrestler_k]
        
        # Direct anomaly between i and j
        if self.adjacency_matrix[wrestler_j, wrestler_i] > 0:
            current_anomalies += self.adjacency_matrix[wrestler_j, wrestler_i]
        
        # Calculate new anomalies after swap
        new_anomalies = 0
        
        # Check all wrestlers between i and j
        for k in range(i+1, j):
            wrestler_k = ordering[k]
            
            # Anomalies involving wrestler j (now at position i)
            if self.adjacency_matrix[wrestler_k, wrestler_j] > 0:
                new_anomalies += self.adjacency_matrix[wrestler_k, wrestler_j]
            
            # Anomalies involving wrestler i (now at position j)
            if self.adjacency_matrix[wrestler_i, wrestler_k] > 0:
                new_anomalies += self.adjacency_matrix[wrestler_i, wrestler_k]
        
        # Direct anomaly between j and i after swap
        if self.adjacency_matrix[wrestler_i, wrestler_j] > 0:
            new_anomalies += self.adjacency_matrix[wrestler_i, wrestler_j]
        
        return new_anomalies - current_anomalies
    
    def simulated_annealing(self, initial_ordering, seed=42):
        """Run simulated annealing to minimize anomalies."""
        random.seed(seed)
        
        n = len(initial_ordering)
        current_ordering = initial_ordering.copy()
        current_score = self.count_anomalies(current_ordering)
        
        best_ordering = current_ordering.copy()
        best_score = current_score
        
        temp = INITIAL_TEMPERATURE
        iterations = 0
        
        while temp > MIN_TEMPERATURE and iterations < MAX_ITERATIONS:
            # Randomly select two positions to swap
            i = random.randint(0, n-1)
            j = random.randint(0, n-1)
            
            if i != j:
                # Calculate score change for the swap
                delta = self.calculate_swap_delta(current_ordering, i, j)
                
                # Accept if better or with probability based on temperature
                if delta < 0 or random.random() < np.exp(-delta / temp):
                    # Perform the swap
                    current_ordering[i], current_ordering[j] = current_ordering[j], current_ordering[i]
                    current_score += delta
                    
                    # Update best solution if needed
                    if current_score < best_score:
                        best_ordering = current_ordering.copy()
                        best_score = current_score
            
            # Cool down
            temp *= COOLING_RATE
            iterations += 1
        
        return best_ordering, best_score
    
    def local_search(self, initial_ordering, max_iterations=10000):
        """Perform local search to further minimize anomalies."""
        n = len(initial_ordering)
        current_ordering = initial_ordering.copy()
        current_score = self.count_anomalies(current_ordering)
        
        iterations = 0
        improved = True
        
        while improved and iterations < max_iterations:
            improved = False
            
            # Try swapping all pairs of wrestlers
            for i in range(n):
                for j in range(i+1, n):
                    # Calculate score change for the swap
                    delta = self.calculate_swap_delta(current_ordering, i, j)
                    
                    # Accept if better
                    if delta < 0:
                        # Perform the swap
                        current_ordering[i], current_ordering[j] = current_ordering[j], current_ordering[i]
                        current_score += delta
                        improved = True
                        break
                
                if improved:
                    break
            
            iterations += 1
        
        return current_ordering, current_score
    
    def run_optimization(self):
        """Run the complete optimization process."""
        print("Starting optimization process...")
        
        # Debug the wrestler data structure
        self.debug_wrestler_data()
        
        # Get initial ordering from PageRank
        print("Calculating PageRank ordering...")
        pagerank_ordering = self.calculate_pagerank()
        pagerank_score = self.count_anomalies(pagerank_ordering)
        print(f"PageRank ordering score: {pagerank_score}")
        
        # Print top 20 wrestlers by PageRank
        print("\nTop 20 wrestlers by PageRank:")
        for rank, idx in enumerate(pagerank_ordering[:20], 1):
            wrestler = self.wrestlers[idx]
            print(f"{rank}. {wrestler['name']} (ID: {wrestler['db_id']})")
        
        # Get greedy MFAS ordering
        print("Calculating Greedy MFAS ordering...")
        mfas_ordering = self.greedy_mfas()
        mfas_score = self.count_anomalies(mfas_ordering)
        print(f"Greedy MFAS ordering score: {mfas_score}")
        
        # Print top 20 wrestlers by MFAS
        print("\nTop 20 wrestlers by MFAS:")
        for rank, idx in enumerate(mfas_ordering[:20], 1):
            wrestler = self.wrestlers[idx]
            print(f"{rank}. {wrestler['name']} (ID: {wrestler['db_id']})")
        
        # Compare initial orderings
        print(f"Initial ordering comparison: PageRank={pagerank_score}, MFAS={mfas_score}")
        
        # Run simulated annealing in parallel with different seeds
        print(f"Running {PARALLEL_RUNS} parallel simulated annealing processes...")
        
        with ProcessPoolExecutor(max_workers=PARALLEL_RUNS) as executor:
            futures = []
            
            # Start with PageRank ordering
            print("Submitting SA job with PageRank initial ordering (seed 42)...")
            futures.append(executor.submit(self.simulated_annealing, pagerank_ordering, seed=42))
            
            # Start with MFAS ordering
            print("Submitting SA job with MFAS initial ordering (seed 43)...")
            futures.append(executor.submit(self.simulated_annealing, mfas_ordering, seed=43))
            
            # Start with random permutations
            for i in range(PARALLEL_RUNS - 2):
                random_ordering = np.random.permutation(len(self.wrestlers))
                random_score = self.count_anomalies(random_ordering)
                print(f"Submitting SA job with random initial ordering (seed {44+i}): score = {random_score}")
                futures.append(executor.submit(self.simulated_annealing, random_ordering, seed=44+i))
            
            # Collect results with progress tracking
            print("Waiting for SA processes to complete...")
            results = []
            completed = 0
            
            for future in futures:
                ordering, score = future.result()
                results.append((ordering, score))
                completed += 1
                print(f"SA process {completed}/{len(futures)} completed: score = {score}")
        
        # Select the best result
        best_ordering, best_score = min(results, key=lambda x: x[1])
        print(f"Best SA result: score = {best_score}")
        
        # Further improve with local search
        print("Starting local search optimization...")
        final_ordering, final_score = self.local_search(best_ordering)
        
        # Calculate improvement statistics
        initial_best = min(pagerank_score, mfas_score)
        sa_improvement = initial_best - best_score
        ls_improvement = best_score - final_score
        total_improvement = initial_best - final_score
        
        print(f"Optimization summary:")
        print(f"  Initial best score (PageRank/MFAS): {initial_best}")
        print(f"  After simulated annealing: {best_score} (improved by {sa_improvement})")
        print(f"  After local search: {final_score} (improved by {ls_improvement})")
        print(f"  Total improvement: {total_improvement} ({(total_improvement/initial_best)*100:.1f}%)")
        
        # Print top 20 wrestlers after optimization
        print("\nTop 20 wrestlers after optimization:")
        for rank, idx in enumerate(final_ordering[:20], 1):
            wrestler = self.wrestlers[idx]
            print(f"{rank}. {wrestler['name']} (ID: {wrestler['db_id']})")
        
        self.best_ordering = final_ordering
        self.best_score = final_score
        
        return final_ordering
    
    def save_rankings_to_db(self, algorithm_name="optimal"):
        """
        Save the optimized rankings to the database.
        
        Args:
            algorithm_name: Name of the algorithm used
            
        Returns:
            bool: True if successful
        """
        if self.best_ordering is None:
            raise ValueError("Must run optimization before saving rankings")
        
        # Initialize database connection
        sqlite_db.init_db()
        cursor = sqlite_db.conn.cursor()
        
        try:
            # Generate ranking data
            rankings = []
            for rank, idx in enumerate(self.best_ordering, 1):
                wrestler = self.wrestlers[idx]
                
                # Check which ID key is available in the wrestler dictionary
                # The key might be 'id', 'external_id', or 'db_id' depending on how it was loaded
                wrestler_id = None
                if 'id' in wrestler:
                    wrestler_id = wrestler['id']
                elif 'external_id' in wrestler:
                    wrestler_id = wrestler['external_id']
                elif 'db_id' in wrestler:
                    wrestler_id = wrestler['db_id']
                else:
                    # Print the available keys for debugging
                    print(f"Available keys in wrestler dictionary: {list(wrestler.keys())}")
                    raise ValueError(f"Could not find ID key in wrestler dictionary: {wrestler}")
                
                rankings.append({
                    'wrestler_id': wrestler_id,
                    'name': wrestler['name'],
                    'rank': rank
                })
            
            # Get the current date in desired format
            today = datetime.now().strftime('%m%d%y')  # Format as MMDDYY
            date_str = f"{today}-{algorithm_name}"  # Format as MMDDYY-optimal
            
            # Get the current timestamp for last_updated
            now = datetime.now().isoformat()
            
            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Delete any existing rankings for this weight class and date
            cursor.execute(
                "DELETE FROM wrestler_rankings WHERE weight_class = ? AND date = ?",
                (self.weight_class, date_str)
            )
            
            # Insert new rankings
            for ranking in rankings:
                cursor.execute(
                    """
                    INSERT INTO wrestler_rankings
                    (wrestler_id, weight_class, rank, date, last_updated, algorithm)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ranking['wrestler_id'], self.weight_class, ranking['rank'], 
                     date_str, now, algorithm_name)
                )
            
            # Commit transaction
            cursor.execute("COMMIT")
            
            print(f"Saved {len(rankings)} rankings to database with date {date_str}")
            return True
            
        except Exception as e:
            print(f"Error saving rankings to database: {e}")
            # Only rollback if a transaction is active
            try:
                cursor.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass  # Ignore "no transaction is active" error
            return False
            
        finally:
            sqlite_db.close_db()
    
    def debug_wrestler_data(self):
        """Print debug information about the wrestler data structure."""
        if not self.wrestlers:
            print("No wrestlers loaded.")
            return
        
        # Print the first wrestler as an example
        print("\nWrestler data structure example:")
        first_wrestler = self.wrestlers[0]
        print(f"Keys: {list(first_wrestler.keys())}")
        
        # Print each key-value pair
        for key, value in first_wrestler.items():
            print(f"  {key}: {value}")
        
        # Check if we have the necessary keys
        required_keys = ['id', 'name']
        missing_keys = [key for key in required_keys if key not in first_wrestler]
        
        if missing_keys:
            print(f"\nWARNING: Missing required keys: {missing_keys}")
        else:
            print("\nAll required keys are present.")
        
        # Print the ID mapping
        print("\nWrestler ID mapping example:")
        for wrestler_id, idx in list(self.wrestler_id_to_index.items())[:5]:
            print(f"  {wrestler_id} -> {idx}")
        
        print(f"\nTotal wrestlers: {len(self.wrestlers)}")
        print(f"Total ID mappings: {len(self.wrestler_id_to_index)}")
        
        # Check if the number of wrestlers matches the number of ID mappings
        if len(self.wrestlers) != len(self.wrestler_id_to_index):
            print("WARNING: Number of wrestlers doesn't match number of ID mappings!")
        
        print("\n")