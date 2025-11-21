import os
import json
import argparse

def strip_result(text):
    text = text.strip()
    if not text.endswith(")"):
        return text, ""
    index = len(text) - 1
    depth = 1
    while index > 0:
        index -= 1
        if text[index] == ")":
            depth += 1
        elif text[index] == "(":
            depth -= 1
            if depth == 0:
                result = text[index + 1:-1].strip()
                rest = text[:index].strip()
                return rest, result
    return text, ""

def parse_name_team(segment):
    segment = segment.strip()
    if not segment.endswith(")"):
        return segment or "Unknown", "Unknown"
    index = len(segment) - 1
    depth = 1
    while index > 0:
        index -= 1
        if segment[index] == ")":
            depth += 1
        elif segment[index] == "(":
            depth -= 1
            if depth == 0:
                team = segment[index + 1:-1].strip()
                name = segment[:index].strip()
                return name or "Unknown", team or "Unknown"
    return segment or "Unknown", "Unknown"

def clean_winner_name(raw):
    raw = raw.strip()
    if raw.endswith("-"):
        return "Unknown"
    parts = [p.strip() for p in raw.split(" - ") if p.strip()]
    return parts[-1] if parts else "Unknown"

def update_alias_file(canonical_name, variant_name, team_name, season):
    """Add a new entry to the alias file."""
    alias_file_path = "mt/name_alias.json"
    
    try:
        # Load the current alias file
        with open(alias_file_path, "r") as f:
            alias_data = json.load(f)
    except FileNotFoundError:
        # Create new structure if file doesn't exist
        alias_data = {"aliases": []}
    
    # Create the new alias entry
    new_alias = {
        "canonical_name": canonical_name,
        "name_variants": [variant_name],
        "conditions": {
            "season": season,
            "team": team_name
        },
        "notes": ""
    }
    
    # Add to aliases list
    alias_data["aliases"].append(new_alias)
    
    # Write back to file with nice formatting
    with open(alias_file_path, "w") as f:
        json.dump(alias_data, f, indent=2)
    
    print(f"✅ Added alias: {variant_name} → {canonical_name} for {team_name} in {season}")

def process_match(summary, wrestler_name, team_name=None, season=None):
    summary = summary.strip()
    
    # Check for aliases if team_name and season are provided
    current_variants = [wrestler_name]
    if team_name and season:
        # Load existing aliases
        alias_file_path = "mt/name_alias.json"
        try:
            with open(alias_file_path, "r") as f:
                alias_data = json.load(f)
                # Find variants for this wrestler/team/season
                for alias in alias_data.get("aliases", []):
                    if (alias.get("conditions", {}).get("team") == team_name and 
                        alias.get("conditions", {}).get("season") == season and
                        alias.get("canonical_name") == wrestler_name):
                        current_variants.extend(alias.get("name_variants", []))
        except FileNotFoundError:
            pass
    
    # Check if any variant of the name is in the summary
    name_found = False
    matching_alias = None
    for variant in current_variants:
        if variant in summary:
            name_found = True
            if variant != wrestler_name:
                matching_alias = variant
            break
    
    if not name_found:
        error_msg = f"❌ SCRAPER_ERROR: '{wrestler_name}' not found in match summary: '{summary}'"
        print(error_msg)
        
        # If team_name and season are provided, offer to update alias
        if team_name and season:
            add_alias = input("Would you like to add an alias for this wrestler? (y/n): ").strip().lower()
            if add_alias == 'y' or add_alias == 'yes':
                variant_name = input(f"Enter the variant name for '{wrestler_name}' in this match summary: ").strip()
                if variant_name:
                    update_alias_file(wrestler_name, variant_name, team_name, season)
        
        return {"result": "SCRAPER_ERROR"}
    
    # If match passed using an alias, print message
    if matching_alias:
        print(f"✅ Match passed using alias '{matching_alias}' for '{wrestler_name}': {summary}")
    
    if "received a bye" in summary.lower():
        lparen = summary.find("(")
        rparen = summary.find(")")
        if lparen != -1 and rparen != -1 and rparen > lparen:
            winner_team = summary[lparen + 1:rparen].strip()
        else:
            winner_team = "Unknown"
        return {
            "winner_name": wrestler_name,
            "winner_team": winner_team,
            "loser_name": "Unknown",
            "loser_team": "Unknown",
            "result": "BYE"
        }
    if " vs. " in summary:
        return {
            "winner_name": "Unknown",
            "winner_team": "Unknown",
            "loser_name": "Unknown",
            "loser_team": "Unknown",
            "result": "NoResult"
        }
    if " over " not in summary:
        return {"result": "PARSE_ERROR"}
    try:
        before, after = summary.split(" over ", 1)
        after, result = strip_result(after)
        loser_name, loser_team = parse_name_team(after)
        winner_raw, winner_team = parse_name_team(before)
        winner_name = clean_winner_name(winner_raw)
        return {
            "winner_name": winner_name,
            "winner_team": winner_team,
            "loser_name": loser_name,
            "loser_team": loser_team,
            "result": result or "Unknown"
        }
    except:
        return {"result": "PARSE_ERROR"}

def process_file(input_path, output_path, season):
    with open(input_path, "r") as f:
        data = json.load(f)

    scraper_errors = 0
    parse_errors = 0
    total_matches = 0
    team_name = data.get("team_name", "Unknown")
    
    # Load existing aliases
    alias_file_path = "mt/name_alias.json"
    try:
        with open(alias_file_path, "r") as f:
            alias_data = json.load(f)
    except FileNotFoundError:
        alias_data = {"aliases": []}
    
    # Create a mapping of canonical names to their variants for this team/season
    name_variants = {}
    for alias in alias_data.get("aliases", []):
        if (alias.get("conditions", {}).get("team") == team_name and 
            alias.get("conditions", {}).get("season") == season):
            canonical_name = alias.get("canonical_name")
            if canonical_name not in name_variants:
                name_variants[canonical_name] = []
            name_variants[canonical_name].extend(alias.get("name_variants", []))

    for wrestler in data.get("roster", []):
        name = wrestler.get("name", "")
        current_variants = [name]  # Start with original name
        if name in name_variants:
            current_variants.extend(name_variants[name])
        
        # Process matches
        for match in wrestler.get("matches", []):
            total_matches += 1
            # Pass team_name and season to process_match
            parsed = process_match(match.get("summary", ""), name, team_name, season)
            if parsed.get("result") == "SCRAPER_ERROR":
                scraper_errors += 1
            elif parsed.get("result") == "PARSE_ERROR":
                parse_errors += 1
            match.update(parsed)

    # Print a summary of errors for the file
    file_name = os.path.basename(input_path)
    print(f"File: {file_name} - Processed {total_matches} matches")
    if scraper_errors > 0:
        print(f"   ❌ Found {scraper_errors} SCRAPER_ERRORS")
    if parse_errors > 0:
        print(f"   ⚠️ Found {parse_errors} PARSE_ERRORS")
    if scraper_errors == 0 and parse_errors == 0:
        print(f"   ✅ No errors found")

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
        
    # Return error counts for overall summary
    return total_matches, scraper_errors, parse_errors

def main(season):
    in_dir = os.path.join("mt", "data_alias", season)
    out_dir = os.path.join("mt", "processed_data", season)
    os.makedirs(out_dir, exist_ok=True)

    total_files = 0
    total_matches = 0
    total_scraper_errors = 0
    total_parse_errors = 0

    for filename in os.listdir(in_dir):
        if filename.endswith(".json"):
            total_files += 1
            input_path = os.path.join(in_dir, filename)
            output_path = os.path.join(out_dir, filename)
            matches, scraper_errors, parse_errors = process_file(input_path, output_path, season)
            
            total_matches += matches
            total_scraper_errors += scraper_errors
            total_parse_errors += parse_errors
    
    # Print overall summary
    print("\n========== SEASON SUMMARY ==========")
    print(f"Processed {total_files} files with {total_matches} total matches")
    if total_scraper_errors > 0:
        print(f"❌ Total SCRAPER_ERRORS: {total_scraper_errors}")
    if total_parse_errors > 0:
        print(f"⚠️ Total PARSE_ERRORS: {total_parse_errors}")
    
    if total_scraper_errors == 0 and total_parse_errors == 0:
        print("✅ No errors found in any files!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-season", required=True, help="Season folder name (e.g., 2014)")
    args = parser.parse_args()
    main(args.season)
