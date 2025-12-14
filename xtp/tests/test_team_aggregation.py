"""
Tests for team xTP aggregation.

Tests aggregation logic, validation, and sorting.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.xtp.run_team_xtp import aggregate_team_xtp, validate_team_data


def create_test_weight_data(season: int, weight: int, data_dir: Path):
    """Create test xTP data for a weight class."""
    test_data = [
        {
            "wrestler_id": f"test_{weight}_1",
            "name": f"Wrestler {weight}-1",
            "team": "Team A",
            "weight": weight,
            "rank": 1,
            "xTP_A": 2.0,
            "xTP_P": 5.0,
            "xTP_B": 1.0,
            "xTP": 8.0,
        },
        {
            "wrestler_id": f"test_{weight}_2",
            "name": f"Wrestler {weight}-2",
            "team": "Team B",
            "weight": weight,
            "rank": 2,
            "xTP_A": 1.5,
            "xTP_P": 4.0,
            "xTP_B": 0.5,
            "xTP": 6.0,
        },
    ]
    
    output_path = data_dir / str(season)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"xtp_weight_{season}_{weight}.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2)


def test_team_component_sum():
    """Test that team_xTP equals sum of components."""
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data" / "xtp"
        season = 2026
        
        # Create test data for 2 weights
        create_test_weight_data(season, 125, data_dir)
        create_test_weight_data(season, 133, data_dir)
        
        # Aggregate
        teams = aggregate_team_xtp(season, str(data_dir))
        
        # Validate
        assert validate_team_data(teams), "Team data validation failed"
        
        # Check sums
        for team_name, team_data in teams.items():
            xTP_A = team_data["team_xTP_A"]
            xTP_P = team_data["team_xTP_P"]
            xTP_B = team_data["team_xTP_B"]
            xTP = team_data["team_xTP"]
            
            expected = xTP_A + xTP_P + xTP_B
            assert abs(xTP - expected) < 0.01, f"Sum mismatch for {team_name}: {xTP} != {expected}"
        
        print("✓ test_team_component_sum passed")


def test_missing_weight_handled():
    """Test that missing weights are handled gracefully."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data" / "xtp"
        season = 2026
        
        # Create test data for only 1 weight
        create_test_weight_data(season, 125, data_dir)
        
        # Aggregate (should handle missing weights)
        teams = aggregate_team_xtp(season, str(data_dir))
        
        # Should still have teams
        assert len(teams) > 0, "No teams found"
        
        # Teams should only have data for weight 125
        for team_name, team_data in teams.items():
            weights = team_data.get("weights", {})
            assert "125" in weights, f"Team {team_name} missing weight 125"
            assert len(weights) == 1, f"Team {team_name} should only have 1 weight"
        
        print("✓ test_missing_weight_handled passed")


def test_sorted_descending():
    """Test that teams are sorted correctly."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data" / "xtp"
        season = 2026
        
        # Create test data with different totals
        test_data_125 = [
            {
                "wrestler_id": "test_125_1",
                "name": "Wrestler 125-1",
                "team": "Team High",
                "weight": 125,
                "rank": 1,
                "xTP_A": 3.0,
                "xTP_P": 10.0,
                "xTP_B": 2.0,
                "xTP": 15.0,
            },
            {
                "wrestler_id": "test_125_2",
                "name": "Wrestler 125-2",
                "team": "Team Low",
                "weight": 125,
                "rank": 2,
                "xTP_A": 1.0,
                "xTP_P": 2.0,
                "xTP_B": 0.5,
                "xTP": 3.5,
            },
        ]
        
        output_path = data_dir / str(season)
        output_path.mkdir(parents=True, exist_ok=True)
        
        output_file = output_path / f"xtp_weight_{season}_125.json"
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(test_data_125, f, indent=2)
        
        # Aggregate
        teams = aggregate_team_xtp(season, str(data_dir))
        
        # Convert to sorted list
        teams_list = list(teams.values())
        teams_list.sort(key=lambda t: (-t["team_xTP"], -t["team_xTP_P"], -t["team_xTP_A"], t["team"]))
        
        # Check sorting
        assert teams_list[0]["team"] == "Team High", "Highest xTP team should be first"
        assert teams_list[0]["team_xTP"] == 15.0, "Team High should have 15.0 xTP"
        assert teams_list[1]["team"] == "Team Low", "Lowest xTP team should be second"
        assert teams_list[1]["team_xTP"] == 3.5, "Team Low should have 3.5 xTP"
        
        print("✓ test_sorted_descending passed")


if __name__ == "__main__":
    print("Running team aggregation tests...\n")
    
    test_team_component_sum()
    test_missing_weight_handled()
    test_sorted_descending()
    
    print("\n" + "=" * 50)
    print("All tests passed!")

