#!/usr/bin/env python3
"""
Process Suspect Links - Wrestler Database Management Tool

This script processes the suspect_links JSON files that are generated during the season data
upload process. These files contain wrestlers that may need manual review for one of two reasons:

1. Non-Freshman New Career: Wrestlers who are not freshmen (FR or RSFR) but were assigned a new 
   career_id because no match was found. Since non-freshmen should have wrestled in a previous 
   season, these might be wrestlers who were missed in the matching process.

2. Borderline Match Confidence: Wrestlers who were matched to an existing career with a confidence 
   score between 0.7 and 0.85, which is not confident enough for automatic acceptance but 
   high enough to warrant review.

The script allows the user to:
- Link a season_wrestler to the suggested career_id
- Create a new career_id (confirming the wrestler is truly new)
- Link to a different manually specified career_id
- Search for other potential matches before deciding
- Process perfect heavyweight matches automatically

After a decision is made, the script updates:
- season_wrestler table: Updates the career_id field and status
- career_wrestler table: Adds the name as a new variant if needed
- career_link table: Records the linking decision with manual_override flag

This ensures that all wrestler data is properly linked across seasons, maintaining the 
integrity of career statistics and historical data.
"""

import json
import os
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import argparse
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# Load name variations from JSON file
def load_name_variations() -> Dict[str, List[str]]:
    """Load name variations from data/name_variations.json and create lookup dictionary."""
    try:
        with open('data/name_variations.json', 'r') as f:
            data = json.load(f)
            
        # Create lookup from any variant to all variants in its group
        variant_to_variants = {}
        for group_data in data['name_groups'].values():
            variants = group_data['variants']
            # Add each variant as a key that maps to the full set of variants
            for variant in variants:
                variant_to_variants[variant.lower()] = set(v.lower() for v in variants)
                
        return variant_to_variants
    except Exception as e:
        print(f"❌ Error loading name variations from data/name_variations.json: {e}")
        sys.exit(1)  # Exit if we can't load name variations

# Load name variations at startup
NAME_VARIATIONS = load_name_variations()

# Setup DynamoDB connection
db = boto3.resource('dynamodb', endpoint_url='http://localhost:8001')
career_table = db.Table('career_wrestler')
season_table = db.Table('season_wrestler')
link_table = db.Table('career_link')

def parse_args():
    parser = argparse.ArgumentParser(description='Process suspect wrestler links for manual review')
    parser.add_argument('--file', type=str, required=True, help='Path to suspect_links JSON file')
    parser.add_argument('--season', type=int, help='Season year for processing (e.g., 2023)')
    parser.add_argument('--batch', action='store_true', help='Run in batch mode (no interactive prompts)')
    return parser.parse_args()

def load_suspect_links(file_path: str) -> List[Dict]:
    """Load suspect links from the specified JSON file."""
    try:
        with open(file_path, 'r') as f:
            links = json.load(f)
        print(f"✅ Loaded {len(links)} suspect links from {file_path}")
        return links
    except Exception as e:
        print(f"❌ Error loading suspect links: {e}")
        return []

def search_career_wrestlers(search_term: str) -> List[Dict]:
    """Search for career wrestlers by name."""
    try:
        # Search in career_wrestler table using name_variants
        results = []
        
        # Scan the career_wrestler table
        response = career_table.scan()
        items = response['Items']
        
        # Filter items that have the search term in any name variant
        for item in items:
            name_variants = item.get('name_variants', [])
            for name in name_variants:
                if search_term.lower() in name.lower():
                    results.append(item)
                    break
        
        return results
    except Exception as e:
        print(f"❌ Error searching career wrestlers: {e}")
        return []

def get_career_wrestler(career_id: str) -> Optional[Dict]:
    """Get a career wrestler by ID."""
    try:
        response = career_table.get_item(Key={'career_id': career_id})
        return response.get('Item')
    except ClientError as e:
        print(f"❌ Error getting career wrestler {career_id}: {e}")
        return None

def get_season_wrestlers_by_career(career_id: str) -> List[Dict]:
    """Get all season wrestlers linked to a specific career ID."""
    try:
        # Query using the GSI on career_id
        response = season_table.query(
            IndexName='career_id-index',
            KeyConditionExpression=Key('career_id').eq(career_id)
        )
        return response.get('Items', [])
    except ClientError as e:
        print(f"❌ Error getting season wrestlers for career {career_id}: {e}")
        return []

def update_season_wrestler(season_wrestler_id: str, career_id: str, status: str = 'linked_to_career') -> bool:
    """Update a season wrestler with the specified career ID."""
    try:
        season_table.update_item(
            Key={'season_wrestler_id': season_wrestler_id},
            UpdateExpression="SET career_id = :career_id, #status = :status",
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':career_id': career_id,
                ':status': status
            }
        )
        return True
    except ClientError as e:
        print(f"❌ Error updating season wrestler {season_wrestler_id}: {e}")
        return False

def add_name_variant_to_career(career_id: str, name: str) -> bool:
    """Add a new name variant to a career wrestler if it doesn't already exist."""
    try:
        # Get the current career wrestler data
        career_wrestler = get_career_wrestler(career_id)
        if not career_wrestler:
            print(f"⚠️ Career {career_id} not found in database")
            return False
        
        # Check if the name is already in the variants
        name_variants = career_wrestler.get('name_variants', [])
        if name in name_variants:
            # Name already exists, no update needed
            return True
        
        # Add the new name variant
        name_variants.append(name)
        
        # Update the career wrestler with the new name_variants
        career_table.update_item(
            Key={'career_id': career_id},
            UpdateExpression="SET name_variants = :name_variants",
            ExpressionAttributeValues={
                ':name_variants': name_variants
            }
        )
        return True
    except ClientError as e:
        print(f"❌ Error adding name variant to career {career_id}: {e}")
        return False

def create_new_career(name: str) -> Optional[str]:
    """Create a new career wrestler entry."""
    try:
        # Get the next available career ID
        response = career_table.scan(ProjectionExpression='career_id')
        existing_ids = [int(i['career_id'].split('_')[1]) for i in response['Items'] if i['career_id'].startswith('career_')]
        next_id = max(existing_ids) + 1 if existing_ids else 1
        
        # Create the new career ID
        career_id = f"career_{str(next_id).zfill(5)}"
        
        # Create the new career entry
        career_table.put_item(Item={
            'career_id': career_id,
            'name_variants': [name]
        })
        
        print(f"✅ Created new career {career_id} for {name}")
        return career_id
    except ClientError as e:
        print(f"❌ Error creating new career: {e}")
        return None

def update_career_link(season_wrestler_id: str, career_id: str, confidence: float, match_type: str, manual_override: bool) -> bool:
    """Create or update a career link entry."""
    try:
        link_table.put_item(Item={
            'season_wrestler_id': season_wrestler_id,
            'linked_career_id': career_id,
            'confidence_score': Decimal(str(confidence)),
            'match_type': match_type,
            'manual_override': manual_override
        })
        return True
    except ClientError as e:
        print(f"❌ Error updating career link: {e}")
        return False

def display_wrestler_info(wrestler: Dict) -> None:
    """Display formatted information about a wrestler."""
    print("\n" + "—" * 65)
    # Format current wrestler info in a single line with pipe separators
    # Map team to team_id for consistency with database records
    team_id = wrestler.get('team_id', wrestler.get('team', 'Unknown'))
    print(f"{wrestler.get('name', 'Unknown'):<20} | {team_id:<10} | "
          f"{wrestler.get('weight_class', 'Unknown'):<5} | {wrestler.get('class_year', 'Unknown'):<5} | "
          f"{wrestler.get('season', 'Unknown'):<6} | {wrestler.get('season_wrestler_id', 'Unknown')}")
    print("—" * 65)
    
    # Display suggested match information if available
    suggested_match = wrestler.get('suggested_match')
    if suggested_match:
        print(f"\nSuggested Match - Confidence {suggested_match.get('confidence', 0)}")
        print("—" * 65)
        
        # If there's a career ID, display career info
        career_id = suggested_match.get('career_id')
        if career_id:
            career = get_career_wrestler(career_id)
            if career:
                # Get all seasons for this career and display them
                seasons = get_season_wrestlers_by_career(career_id)
                for season in sorted(seasons, key=lambda x: x.get('season', 0)):
                    print(f"{season.get('name', 'Unknown'):<20} | {season.get('team_id', 'Unknown'):<10} | "
                          f"{season.get('weight_class', 'Unknown'):<5} | {season.get('class_year', 'Unknown'):<5} | "
                          f"{season.get('season', 'Unknown'):<6} | {career_id}")
        print("—" * 65)

def display_career_info(career_id: str) -> None:
    """Display information about a career wrestler and their seasons."""
    career = get_career_wrestler(career_id)
    if not career:
        print(f"  Career details not found for {career_id}")
        return
    
    # Display career data
    print(f"  Name Variants: {', '.join(career.get('name_variants', []))}")
    
    # Get and display all seasons for this career
    seasons = get_season_wrestlers_by_career(career_id)
    if seasons:
        print(f"  Seasons ({len(seasons)}):")
        for s in seasons:
            print(f"    {s.get('season', 'Unknown')} - {s.get('team_id', 'Unknown')} - {s.get('name', 'Unknown')} ({s.get('weight_class', 'Unknown')})")
    else:
        print("  No season data found")

def display_search_results(results: List[Dict]) -> None:
    """Display search results in a numbered list."""
    if not results:
        print("No matching career wrestlers found.")
        return
    
    print("\n=== Search Results ===")
    print("—" * 75)
    
    # Get all seasons for each career and calculate confidence scores
    formatted_results = []
    for career in results:
        seasons = get_season_wrestlers_by_career(career.get('career_id'))
        for season in sorted(seasons, key=lambda x: x.get('season', 0)):
            match_info = {
                'name': season.get('name'),
                'season': season.get('season'),
                'team_id': season.get('team_id'),
                'team_name': season.get('team_name', 'Unknown'),
                'weight_class': season.get('weight_class', 'Unknown'),
                'class_year': season.get('class_year', 'Unknown'),
                'career_id': career.get('career_id'),
                'conf_score': calculate_confidence_score(
                    {'name': season.get('name'), 'team_id': season.get('team_id'), 'weight_class': season.get('weight_class')},
                    season
                )
            }
            formatted_results.append(match_info)
    
    # Sort results by confidence score
    formatted_results.sort(key=lambda x: (-x['conf_score'], x['name']))
    
    # Display results in the same format as last name matches
    for i, result in enumerate(formatted_results, 1):
        print(f"{i}. {result['name']:<17} | {result['team_id']:<10} | "
              f"{result['weight_class']:<5} | {result['class_year']:<5} | "
              f"{result['season']:<6} | {result['career_id']:<12} | {result['conf_score']:.2f}")
    print("—" * 75)

def calculate_confidence_score(wrestler: Dict, match: Dict) -> float:
    """Calculate a simple confidence score between two wrestlers."""
    score = 0.0
    
    # Check first name (including variants) - 0.5 points
    wrestler_first = wrestler.get('name', '').split()[0].lower()
    match_first = match.get('name', '').split()[0].lower()
    
    # Use the existing NAME_VARIATIONS dictionary and get_name_variants function
    wrestler_variants = set()
    if wrestler_first in NAME_VARIATIONS:
        wrestler_variants.update(NAME_VARIATIONS[wrestler_first])
    else:
        wrestler_variants.add(wrestler_first)
        
    match_variants = set()
    if match_first in NAME_VARIATIONS:
        match_variants.update(NAME_VARIATIONS[match_first])
    else:
        match_variants.add(match_first)
    
    if wrestler_variants & match_variants:
        score += 0.5
        
    # Check team - 0.25 points
    if wrestler.get('team_id') == match.get('team_id'):
        score += 0.25
        
    # Check weight class - 0.25 points
    try:
        w1 = int(''.join(filter(str.isdigit, wrestler.get('weight_class', '0'))))
        w2 = int(''.join(filter(str.isdigit, match.get('weight_class', '0'))))
        if abs(w1 - w2) <= 20:
            score += 0.25
    except ValueError:
        pass  # Invalid weight format, skip weight comparison
        
    return score

def find_identical_last_names(name: str) -> List[Dict]:
    """Find wrestlers with identical last names, prioritizing those with same first names or name variants."""
    try:
        # Split the name into parts
        parts = name.lower().split()
        if len(parts) < 2:
            print("⚠️ Name must include both first and last name")
            return []
            
        first_name = parts[0]
        first_initial = first_name[0]  # Get first initial for sorting
        last_name = parts[-1]  # Take last part as last name
        
        results = []
        exact_name_matches = []  # For tracking exact name matches (including variants)
        
        # Get all variants of the current first name
        current_variants = set()
        if first_name in NAME_VARIATIONS:
            current_variants.update(NAME_VARIATIONS[first_name])
        else:
            current_variants.add(first_name)
        
        # Scan the season_wrestler table
        response = season_table.scan()
        items = response['Items']
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = season_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        # Process each wrestler
        for item in items:
            other_name = item.get('name', '').lower()
            other_parts = other_name.split()
            
            if len(other_parts) < 2:
                continue
                
            other_first = other_parts[0]
            other_last = other_parts[-1]
            
            # Get variants of the other first name
            other_variants = set()
            if other_first in NAME_VARIATIONS:
                other_variants.update(NAME_VARIATIONS[other_first])
            else:
                other_variants.add(other_first)
            
            # Check if last names match
            if other_last == last_name:
                match_info = {
                    'name': item.get('name'),
                    'season': item.get('season'),
                    'team_id': item.get('team_id'),
                    'team_name': item.get('team_name', 'Unknown'),
                    'weight_class': item.get('weight_class', 'Unknown'),
                    'class_year': item.get('class_year', 'Unknown'),
                    'career_id': item.get('career_id', 'Unknown'),
                    'first_initial_match': other_first.startswith(first_initial)  # Add flag for first initial match
                }
                
                # Calculate confidence score
                match_info['conf_score'] = calculate_confidence_score(
                    {'name': name, 'team_id': item.get('team_id'), 'weight_class': item.get('weight_class')},
                    match_info
                )
                
                # Check if first names match exactly or through variants
                if current_variants & other_variants:
                    exact_name_matches.append(match_info)
                else:
                    results.append(match_info)
        
        # Sort both lists by confidence score, then by first initial match, then by name
        exact_name_matches.sort(key=lambda x: (-x['conf_score'], not x['first_initial_match'], x['name']))
        results.sort(key=lambda x: (-x['conf_score'], not x['first_initial_match'], x['name']))
        
        # Combine lists with exact matches first
        return exact_name_matches + results
        
    except Exception as e:
        print(f"❌ Error searching for identical last names: {e}")
        return []

def display_last_name_matches(matches: List[Dict]) -> None:
    """Display matches grouped by exact name matches and last name only matches."""
    if not matches:
        print("No matching last names found.")
        return
        
    # Split matches into exact and non-exact based on their order
    exact_matches = []
    last_name_matches = []
    
    # Split matches into exact and non-exact based on their order
    for match in matches:
        if match in matches[:matches.index(match) + 1]:  # If it's in the first part of the list
            exact_matches.append(match)
        else:
            last_name_matches.append(match)
    
    if exact_matches:
        print("\n=== Exact Name Matches ===")
        print("—" * 75)
        for i, match in enumerate(exact_matches, 1):
            print(f"{i}. {match['name']:<17} | {match['team_id']:<10} | "
                  f"{match['weight_class']:<5} | {match['class_year']:<5} | "
                  f"{match['season']:<6} | {match['career_id']:<12} | {match['conf_score']:.2f}")
    
    if last_name_matches:
        print("\n=== Same Last Name, Different First Name ===")
        print("—" * 75)
        start_index = len(exact_matches) + 1
        for i, match in enumerate(last_name_matches, start_index):
            print(f"{i}. {match['name']:<17} | {match['team_id']:<10} | "
                  f"{match['weight_class']:<5} | {match['class_year']:<5} | "
                  f"{match['season']:<6} | {match['career_id']:<12} | {match['conf_score']:.2f}")
    print("—" * 75)

def process_suspect_link(link: Dict) -> bool:
    """Process a single suspect link with user interaction.
    Returns True if the link was processed, False if skipped."""
    display_wrestler_info(link)
    
    while True:
        print("\nOptions:")
        print("1. Accept suggested match")
        print("2. Create new career (confirm wrestler is new)")
        print("3. Link to a different career ID")
        print("4. Search for potential matches")
        print("5. List identical last names")
        print("6. Skip this wrestler")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        if choice == '1':
            # Accept suggested match
            suggested_match = link.get('suggested_match')
            if not suggested_match or not suggested_match.get('career_id'):
                print("⚠️ No suggested match available for this wrestler.")
                continue
            
            career_id = suggested_match.get('career_id')
            confidence = suggested_match.get('confidence', 0)
            
            # Update the season wrestler entry
            success = update_season_wrestler(link['season_wrestler_id'], career_id)
            if success:
                # Add name as a variant if it's new
                add_name_variant_to_career(career_id, link['name'])
                
                # Update the career link
                update_career_link(
                    link['season_wrestler_id'], 
                    career_id, 
                    confidence, 
                    'manual_confirm', 
                    True
                )
                print(f"✅ Linked {link['name']} to career {career_id}")
            return True
                
        elif choice == '2':
            # Create new career
            career_id = create_new_career(link['name'])
            if career_id:
                # Update the season wrestler entry
                update_season_wrestler(link['season_wrestler_id'], career_id)
                
                # Update the career link
                update_career_link(
                    link['season_wrestler_id'], 
                    career_id, 
                    1.0,  # 100% confidence for manual creation
                    'manual_new', 
                    True
                )
                print(f"✅ Created new career {career_id} for {link['name']}")
            return True
                
        elif choice == '3':
            # Link to a different career ID
            career_id = input("Enter the career ID to link to: ").strip()
            if not career_id:
                continue
            
            # Verify the career ID exists
            career = get_career_wrestler(career_id)
            if not career:
                print(f"⚠️ Career ID {career_id} not found in the database.")
                continue
            
            # Display career info for confirmation
            display_career_info(career_id)
            confirm = input(f"Confirm linking {link['name']} to this career? (y/n): ").lower()
            if confirm != 'y':
                continue
                
            # Update the season wrestler entry
            success = update_season_wrestler(link['season_wrestler_id'], career_id)
            if success:
                # Add name as a variant if it's new
                add_name_variant_to_career(career_id, link['name'])
                
                # Update the career link
                update_career_link(
                    link['season_wrestler_id'], 
                    career_id, 
                    1.0,  # 100% confidence for manual link
                    'manual_override', 
                    True
                )
                print(f"✅ Linked {link['name']} to career {career_id}")
            return True
                
        elif choice == '4':
            # Search for potential matches
            search_term = input("Enter search term (name): ").strip()
            if not search_term:
                continue
                
            results = search_career_wrestlers(search_term)
            display_search_results(results)
            
            if results:
                use_result = input("Link to one of these careers? Enter number or 'n' to cancel: ").strip()
                if use_result.isdigit() and 1 <= int(use_result) <= len(results):
                    selected = results[int(use_result) - 1]
                    career_id = selected.get('career_id')
                    
                    # Update the season wrestler entry
                    success = update_season_wrestler(link['season_wrestler_id'], career_id)
                    if success:
                        # Add name as a variant if it's new
                        add_name_variant_to_career(career_id, link['name'])
                        
                        # Update the career link
                        update_career_link(
                            link['season_wrestler_id'], 
                            career_id, 
                            1.0,  # 100% confidence for manual selection
                            'manual_search', 
                            True
                        )
                        print(f"✅ Linked {link['name']} to career {career_id}")
                        return True
            
        elif choice == '5':
            # Search for identical last names
            matches = find_identical_last_names(link['name'])
            display_last_name_matches(matches)
            
            if matches:
                use_result = input("\nLink to one of these careers? Enter number or 'n' to cancel: ").strip()
                if use_result.isdigit():
                    idx = int(use_result) - 1
                    if 0 <= idx < len(matches):
                        selected = matches[idx]
                        career_id = selected.get('career_id')
                        if career_id and career_id != 'Unknown':
                            # Update the season wrestler entry
                            success = update_season_wrestler(link['season_wrestler_id'], career_id)
                            if success:
                                # Add name as a variant if it's new
                                add_name_variant_to_career(career_id, link['name'])
                                
                                # Update the career link
                                update_career_link(
                                    link['season_wrestler_id'], 
                                    career_id, 
                                    1.0,  # 100% confidence for manual selection
                                    'manual_last_name_match', 
                                    True
                                )
                                print(f"✅ Linked {link['name']} to career {career_id}")
                                return True
            
        elif choice == '6':
            # Skip this wrestler
            print(f"⏭️ Skipping {link['name']}")
            return False
            
        else:
            print("Invalid choice. Please enter a number from 1-6.")

def batch_process_links(links: List[Dict]) -> List[Dict]:
    """Process all links in batch mode using suggested matches.
    Returns list of links that were skipped (no suggested match)."""
    skipped_links = []
    
    for link in links:
        suggested_match = link.get('suggested_match')
        if not suggested_match or not suggested_match.get('career_id'):
            print(f"⚠️ Skipping {link['name']} - no suggested match")
            skipped_links.append(link)
            continue
        
        career_id = suggested_match.get('career_id')
        confidence = suggested_match.get('confidence', 0)
        
        # Update the season wrestler entry
        success = update_season_wrestler(link['season_wrestler_id'], career_id)
        if success:
            # Add name as a variant if it's new
            add_name_variant_to_career(career_id, link['name'])
            
            # Update the career link
            update_career_link(
                link['season_wrestler_id'], 
                career_id, 
                confidence, 
                'batch_confirm', 
                True
            )
            print(f"✅ Linked {link['name']} to career {career_id}")
            
    return skipped_links

def process_suspect_links(file_path: str, batch_mode: bool = False) -> None:
    """Process all suspect links in the specified file."""
    links = load_suspect_links(file_path)
    if not links:
        print("No suspect links to process.")
        return
    
    # Create a backup of the original file
    backup_path = f"{file_path}.backup"
    try:
        with open(file_path, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())
        print(f"✅ Created backup at {backup_path}")
    except Exception as e:
        print(f"⚠️ Warning: Could not create backup: {e}")
    
    if batch_mode:
        print(f"Processing {len(links)} links in batch mode...")
        skipped_links = batch_process_links(links)
        
        # Save skipped links back to the file
        if skipped_links:
            try:
                with open(file_path, 'w') as f:
                    json.dump(skipped_links, f, indent=2)
                print(f"✅ Saved {len(skipped_links)} remaining links back to {file_path}")
            except Exception as e:
                print(f"❌ Error saving file: {e}")
                print(f"Your data is backed up at {backup_path}")
        else:
            # If no links are skipped, create an empty file
            try:
                with open(file_path, 'w') as f:
                    json.dump([], f)
                print(f"✅ All links processed. Cleared {file_path}")
            except Exception as e:
                print(f"❌ Error saving file: {e}")
        return
    
    # Process links one by one with user interaction
    remaining_links = links.copy()  # Make a copy to avoid modifying the original list during iteration
    processed_count = 0
    processed_links = []  # Keep track of processed links for potential recovery
    
    for i, link in enumerate(links, 1):
        print(f"\n[{i}/{len(links)}] Processing {link['name']}...")
        try:
            processed = process_suspect_link(link)
            
            if processed:
                processed_count += 1
                processed_links.append(link)
                remaining_links.remove(link)  # Remove from our working copy
            
            # Save progress after each wrestler, with error handling
            try:
                with open(file_path, 'w') as f:
                    json.dump(remaining_links, f, indent=2)
            except Exception as e:
                print(f"❌ Error saving progress: {e}")
                print(f"Will try again after next wrestler. Your data is backed up at {backup_path}")
        except Exception as e:
            print(f"❌ Error processing wrestler: {e}")
            print("Continuing with next wrestler...")
    
    # Final save with explicit error handling
    try:
        with open(file_path, 'w') as f:
            json.dump(remaining_links, f, indent=2)
            
        if processed_count == len(links):
            print(f"\n✅ All {processed_count} wrestlers processed!")
        else:
            print(f"\n✅ Processed {processed_count} wrestlers. {len(remaining_links)} remaining.")
            print(f"✅ Progress saved to {file_path}")
    except Exception as e:
        print(f"❌ Error saving final progress: {e}")
        print(f"Your data is backed up at {backup_path}")
        
        # Try to create a recovery file with the remaining links
        try:
            recovery_path = f"{file_path}.recovery"
            with open(recovery_path, 'w') as f:
                json.dump(remaining_links, f, indent=2)
            print(f"✅ Created recovery file at {recovery_path}")
        except Exception as recovery_error:
            print(f"❌ Error creating recovery file: {recovery_error}")

def normalize(name: str) -> str:
    """Normalize name by lowercasing and stripping whitespace."""
    return name.lower().strip()

def class_to_num(cls: str) -> int:
    """Convert class year string to a numeric representation."""
    return {
        "FR": 1, "RSFR": 1, "Fr.": 1,
        "SO": 2, "RSSO": 2, "So.": 2,
        "JR": 3, "RSJR": 3, "Jr.": 3,
        "SR": 4, "RSSR": 4, "Sr.": 4
    }.get(str(cls).upper(), 0)

def save_suspect_links(file_path: str, links: List[Dict]) -> None:
    """Save the modified list of suspect links back to the file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(links, f, indent=2)
        print(f"✅ Saved {len(links)} remaining suspect links to {file_path}")
    except Exception as e:
        print(f"❌ Error saving suspect links: {e}")

def run_normal_processing(file_path: str, batch_mode: bool = False) -> None:
    """Run the normal interactive processing of suspect links."""
    # This simply calls the existing process_suspect_links function
    process_suspect_links(file_path, batch_mode)

def process_perfect_heavyweights(file_path: str) -> None:
    """
    Process heavyweight wrestlers with perfect match criteria:
    1. One wrestler has weight class 285
    2. Weight difference <= 110 lbs
    3. Names are identical (normalized)
    4. Teams are identical
    5. Grade progression is valid (same or +1)
    """
    # Load all suspect links
    links = load_suspect_links(file_path)
    print(f"DEBUG: Loaded {len(links)} total suspect links")
    if not links:
        print("No suspect links to process.")
        return
    
    # Lists to track matches and display data
    heavyweight_matches = []
    display_data = []
    validation_failed = 0
    weight_criteria_failed = 0
    name_match_failed = 0
    team_match_failed = 0
    grade_failed = 0
    data_not_found = 0
    
    print("\n--- Processing Perfect Heavyweight Matches ---")
    
    # Process each suspect link to identify heavyweight matches
    for i, link in enumerate(links):
        # Print details for a sample of links for debugging
        debug_this_link = (i < 5)  # Debug the first 5 links
        
        # In the actual file, the link itself has the current wrestler info
        current_wrestler = link
        current_weight = 0
        
        # The suggested_match only contains confidence and career_id
        suggested_match_info = link.get('suggested_match', {})
        suggested_weight = 0
        
        # Get full suggested match info from DB
        suggested_career_id = suggested_match_info.get('career_id')
        
        if debug_this_link:
            print(f"\nDEBUG LINK #{i+1}:")
            print(f"  Current: {link.get('name', 'Unknown')} - {link.get('weight_class', 'Unknown')} - {link.get('team', 'Unknown')} - {link.get('class_year', 'Unknown')} - {link.get('season', 'Unknown')}")
            print(f"  Suggested match career_id: {suggested_career_id}")
        
        # Basic validation - skip if any required field is missing
        if not all([
            'name' in current_wrestler,
            'team' in current_wrestler,
            'weight_class' in current_wrestler,
            'class_year' in current_wrestler,
            'season' in current_wrestler,
            'season_wrestler_id' in current_wrestler,
            suggested_career_id is not None
        ]):
            if debug_this_link:
                print("  VALIDATION FAILED: Missing required fields in link")
                for field in ['name', 'team', 'weight_class', 'class_year', 'season', 'season_wrestler_id']:
                    if field not in current_wrestler:
                        print(f"    - Missing link['{field}']")
                if suggested_career_id is None:
                    print("    - Missing suggested_match['career_id']")
            validation_failed += 1
            continue
        
        # Get previous season wrestler data from the DB using career_id
        career = get_career_wrestler(suggested_career_id)
        if not career:
            if debug_this_link:
                print(f"  VALIDATION FAILED: Career {suggested_career_id} not found in database")
            validation_failed += 1
            continue
        
        # Get all seasons for this career from the DB
        seasons = get_season_wrestlers_by_career(suggested_career_id)
        if not seasons:
            if debug_this_link:
                print(f"  VALIDATION FAILED: No seasons found for career {suggested_career_id}")
            validation_failed += 1
            continue
        
        # Find the most recent season before current_wrestler's season
        prior_seasons = [s for s in seasons if s.get('season', 0) < current_wrestler['season']]
        if not prior_seasons:
            if debug_this_link:
                print(f"  VALIDATION FAILED: No prior seasons found for career {suggested_career_id}")
            validation_failed += 1
            continue
        
        # Sort by season descending and take the most recent one
        prior_seasons.sort(key=lambda x: x.get('season', 0), reverse=True)
        previous_season = prior_seasons[0]
        
        # Now we have both current and previous season data
        try:
            # Check weight criteria
            current_weight = int(current_wrestler['weight_class'])
            previous_weight = int(previous_season.get('weight_class', 0))
            is_heavyweight = (current_weight == 285 or previous_weight == 285)
            weight_diff_ok = abs(current_weight - previous_weight) <= 110
            
            # Check name, team, and grade criteria using previous season data
            name_match = normalize(current_wrestler['name']) == normalize(previous_season.get('name', ''))
            
            # Team field in current wrestler, team_id in previous season data
            team_match = current_wrestler['team'] == previous_season.get('team_id', '')
            
            # Determine newer and older for grade progression
            if current_wrestler['season'] > previous_season.get('season', 0):
                newer_grade = class_to_num(current_wrestler['class_year'])
                older_grade = class_to_num(previous_season.get('class_year', ''))
            else:
                newer_grade = class_to_num(previous_season.get('class_year', ''))
                older_grade = class_to_num(current_wrestler['class_year'])
            
            grade_progression_ok = newer_grade - older_grade in {0, 1}
            
            if debug_this_link:
                print("  CRITERIA EVALUATION:")
                print(f"    - Is heavyweight (285): {is_heavyweight} ({current_weight} vs {previous_weight})")
                print(f"    - Weight diff ≤ 110: {weight_diff_ok} (diff: {abs(current_weight - previous_weight)})")
                print(f"    - Name match: {name_match} ('{normalize(current_wrestler['name'])}' vs '{normalize(previous_season.get('name', ''))}')")
                print(f"    - Team match: {team_match} ('{current_wrestler['team']}' vs '{previous_season.get('team_id', '')}')")
                print(f"    - Grade progression OK: {grade_progression_ok} (newer: {newer_grade}, older: {older_grade})")
            
            # Count failures for debugging
            if not is_heavyweight or not weight_diff_ok:
                weight_criteria_failed += 1
            if not name_match:
                name_match_failed += 1
            if not team_match:
                team_match_failed += 1
            if not grade_progression_ok:
                grade_failed += 1
            
            # If all criteria are met, add to matches
            if is_heavyweight and weight_diff_ok and name_match and team_match and grade_progression_ok:
                heavyweight_matches.append(link)
                
                # Format display string: YYYY Name (Team) WT CL || YYYY Name (Team) WT CL
                display_str = (f"{current_wrestler['season']} {current_wrestler['name']} "
                              f"({current_wrestler['team']}) {current_wrestler['weight_class']} "
                              f"{current_wrestler['class_year']} || {previous_season.get('season', 'Unknown')} "
                              f"{previous_season.get('name', 'Unknown')} ({previous_season.get('team_id', 'Unknown')}) "
                              f"{previous_season.get('weight_class', 'Unknown')} {previous_season.get('class_year', 'Unknown')}")
                display_data.append(display_str)
                if debug_this_link:
                    print("  RESULT: MATCH FOUND! ✓")
            elif debug_this_link:
                print("  RESULT: No match ✗")
                
        except (ValueError, TypeError, KeyError) as e:
            if debug_this_link:
                print(f"  ERROR: Exception during processing: {type(e).__name__}: {e}")
            data_not_found += 1
            continue
    
    # Print summary statistics
    print(f"\nDEBUG SUMMARY:")
    print(f"  Total links: {len(links)}")
    print(f"  Failed validation: {validation_failed}")
    print(f"  Data not found: {data_not_found}")
    print(f"  Failed criteria counts:")
    print(f"    - Weight criteria: {weight_criteria_failed}")
    print(f"    - Name match: {name_match_failed}")
    print(f"    - Team match: {team_match_failed}")
    print(f"    - Grade progression: {grade_failed}")
    print(f"  Matches found: {len(heavyweight_matches)}")
    
    # Display results and prompt for action
    if not heavyweight_matches:
        print("No perfect heavyweight matches found in the suspect list.")
        return
    
    print(f"\nFound {len(heavyweight_matches)} potential perfect heavyweight matches:")
    print("—" * 80)
    for display_str in display_data:
        print(display_str)
    print("—" * 80)
    
    action = input("To link all of these wrestlers automatically, press (y). To return to main menu, press (b): ").lower().strip()
    
    if action == 'y':
        # Process all heavyweight matches
        processed_count = 0
        processed_ids = set()
        
        for link in heavyweight_matches:
            season_wrestler_id = link['season_wrestler_id']
            career_id = link['suggested_match']['career_id']
            confidence = link['suggested_match'].get('confidence', 0.8)  # Default to 0.8 if not specified
            
            try:
                # Update the season wrestler entry
                if update_season_wrestler(season_wrestler_id, career_id):
                    # Add name as a variant if it's new
                    add_name_variant_to_career(career_id, link['name'])
                    
                    # Update the career link
                    update_career_link(
                        season_wrestler_id, 
                        career_id, 
                        confidence, 
                        'auto_hwt_match', 
                        True
                    )
                    processed_count += 1
                    processed_ids.add(season_wrestler_id)
                    print(f"✅ Linked {link['name']} to career {career_id}")
            except Exception as e:
                print(f"❌ Error processing {link['name']}: {e}")
        
        # Filter out processed links and save remaining ones
        remaining_links = [link for link in links if link['season_wrestler_id'] not in processed_ids]
        
        # Save the remaining links
        try:
            save_suspect_links(file_path, remaining_links)
            print(f"\n✅ Successfully processed {processed_count} of {len(heavyweight_matches)} heavyweight matches.")
            print(f"✅ {len(remaining_links)} suspect links remaining.")
        except Exception as e:
            print(f"❌ Error saving remaining links: {e}")
    else:
        print("No changes made. Returning to main menu.")

def process_low_confidence_links(file_path: str) -> None:
    """
    Process low confidence suspect links that meet these criteria:
    1. Suggested match confidence is at or below user-selected threshold (0.3, 0.4, or 0.5)
    2. Only one match found when searching by last name (themselves)
    """
    # Prompt user to select confidence threshold
    print("\n--- Auto Processing Low Confidence Links ---")
    print("Select confidence threshold:")
    print("1. 0.3 (Recommended)")
    print("2. 0.4")
    print("3. 0.5")
    
    threshold_choice = input("Enter choice (1-3): ").strip()
    
    # Set threshold based on user input
    if threshold_choice == '2':
        confidence_threshold = 0.4
    elif threshold_choice == '3':
        confidence_threshold = 0.5
    else:
        confidence_threshold = 0.3  # Default to recommended value
    
    print(f"\nUsing confidence threshold: {confidence_threshold}")
    
    # Load all suspect links
    links = load_suspect_links(file_path)
    print(f"DEBUG: Loaded {len(links)} total suspect links")
    if not links:
        print("No suspect links to process.")
        return
    
    # Lists to track matches and display data
    auto_process_links = []
    display_data = []
    high_confidence_skipped = 0
    multiple_matches_skipped = 0
    validation_failed = 0
    
    # Process each suspect link
    for i, link in enumerate(links):
        # Get suggested match confidence
        suggested_match_info = link.get('suggested_match', {})
        suggested_confidence = suggested_match_info.get('confidence', 1.0)
        suggested_career_id = suggested_match_info.get('career_id')
        
        # Debug display
        print(f"\nChecking link #{i+1}: {link.get('name', 'Unknown')} - Confidence: {suggested_confidence}")
        
        # Skip if confidence is > threshold
        if suggested_confidence > confidence_threshold:
            print(f"  Skipping - Confidence {suggested_confidence} > {confidence_threshold}")
            high_confidence_skipped += 1
            continue
        
        # Basic validation - skip if any required field is missing
        if not all([
            'name' in link,
            'season_wrestler_id' in link
        ]):
            print(f"  Skipping - Missing required fields")
            validation_failed += 1
            continue
        
        # Find matches with identical last names
        name = link.get('name', '')
        last_name_matches = find_identical_last_names(name)
        
        # If there's exactly one match (the wrestler themselves), process it
        if len(last_name_matches) == 1:
            match = last_name_matches[0]
            career_id = match.get('career_id')
            
            # Get the suggested match career info from the original link
            suggested_career_id = suggested_match_info.get('career_id')
            suggested_career_name = "Unknown"
            
            if suggested_career_id:
                suggested_career = get_career_wrestler(suggested_career_id)
                if suggested_career and 'name_variants' in suggested_career and suggested_career['name_variants']:
                    suggested_career_name = suggested_career['name_variants'][0]
            
            # Add to auto-process list
            auto_process_links.append({
                'link': link,
                'match': match,
                'suggested_career_name': suggested_career_name,
                'suggested_career_id': suggested_career_id
            })
            
            # Format display string to include the original wrestler and the suggested match name
            display_str = (f"{link.get('name', 'Unknown')} — "
                          f"({suggested_career_name}) — "
                          f"({link.get('team', 'Unknown')}) {link.get('weight_class', 'Unknown')} "
                          f"{link.get('class_year', 'Unknown')} - Career: {career_id}")
            display_data.append(display_str)
            print(f"  Found single exact match - will process")
        else:
            print(f"  Skipping - Found {len(last_name_matches)} last name matches")
            multiple_matches_skipped += 1
    
    # Print summary statistics
    print(f"\nDEBUG SUMMARY:")
    print(f"  Total links: {len(links)}")
    print(f"  Confidence threshold: {confidence_threshold}")
    print(f"  Skipped due to high confidence: {high_confidence_skipped}")
    print(f"  Skipped due to multiple matches: {multiple_matches_skipped}")
    print(f"  Validation failed: {validation_failed}")
    print(f"  Auto-processable links found: {len(auto_process_links)}")
    
    # Display results and prompt for action
    if not auto_process_links:
        print(f"No low confidence links (≤ {confidence_threshold}) with single exact matches found.")
        return
    
    print(f"\nFound {len(auto_process_links)} links to auto-process:")
    print("—" * 80)
    for display_str in display_data:
        print(display_str)
    print("—" * 80)
    
    action = input("To process these wrestlers automatically, press (y). To return to main menu, press (b): ").lower().strip()
    
    if action == 'y':
        # Process all matching links
        processed_count = 0
        processed_ids = set()
        
        for item in auto_process_links:
            link = item['link']
            match = item['match']
            
            season_wrestler_id = link['season_wrestler_id']
            career_id = match['career_id']
            
            # Display info and prompt for confirmation (temporary, will be removed later)
            print(f"\nProcessing: {link.get('name', 'Unknown')} -> {career_id}")
            print("—" * 80)
            print(f"Current: {link.get('name', 'Unknown')} - {link.get('team', 'Unknown')} - {link.get('weight_class', 'Unknown')} - {link.get('class_year', 'Unknown')} - {link.get('season', 'Unknown')}")
            
            # Get and display the suggested match info from the link
            suggested_career_id = item.get('suggested_career_id')
            suggested_name = item.get('suggested_career_name', 'Unknown')
            suggested_confidence = link.get('suggested_match', {}).get('confidence', 'Unknown')
            print(f"Suggested Match: {suggested_name} - Career ID: {suggested_career_id} - Confidence: {suggested_confidence}")
            
            # Display the match that was found by last name
            print(f"Exact Match: {match.get('name', 'Unknown')} - {match.get('team_id', 'Unknown')} - {match.get('weight_class', 'Unknown')} - {match.get('class_year', 'Unknown')} - {match.get('season', 'Unknown')}")
            print("—" * 80)
            
            # Add pause for confirmation - this will be removed once the function is confirmed working
            confirm = input("Press Enter to continue, or 'q' to quit: ")
            if confirm.lower() == 'q':
                print("Stopping auto-processing.")
                break
            
            try:
                # Update the season wrestler entry
                if update_season_wrestler(season_wrestler_id, career_id):
                    # Add name as a variant if it's new
                    add_name_variant_to_career(career_id, link['name'])
                    
                    # Update the career link
                    update_career_link(
                        season_wrestler_id, 
                        career_id, 
                        1.0,  # 100% confidence for exact name match
                        'auto_low_conf_exact_match', 
                        True
                    )
                    processed_count += 1
                    processed_ids.add(season_wrestler_id)
                    print(f"✅ Linked {link['name']} to career {career_id}")
            except Exception as e:
                print(f"❌ Error processing {link['name']}: {e}")
        
        # Filter out processed links and save remaining ones
        remaining_links = [link for link in links if link['season_wrestler_id'] not in processed_ids]
        
        # Save the remaining links
        try:
            save_suspect_links(file_path, remaining_links)
            print(f"\n✅ Successfully processed {processed_count} of {len(auto_process_links)} links.")
            print(f"✅ {len(remaining_links)} suspect links remaining.")
        except Exception as e:
            print(f"❌ Error saving remaining links: {e}")
    else:
        print("No changes made. Returning to main menu.")

def main():
    """Main entry point with menu options."""
    # Parse command line arguments for backward compatibility
    parser = argparse.ArgumentParser(description='Process suspect wrestler links for manual review')
    parser.add_argument('--file', type=str, help='Path to suspect_links JSON file')
    parser.add_argument('--season', type=int, help='Season year for processing (e.g., 2023)')
    parser.add_argument('--batch', action='store_true', help='Run in batch mode (no interactive prompts)')
    args = parser.parse_args()
    
    # Default file path
    default_file_path = 'data/suspect_links.json'
    file_path = args.file if args.file else default_file_path
    
    # If args are provided, run in legacy mode for backward compatibility
 #   if args.file:
 #       run_normal_processing(file_path, args.batch)
 #       return
    
    # Interactive menu mode
    while True:
        print("\n--- Suspect Link Processor Menu ---")
        print("1. Run Normal Interactive Processing")
        print("2. Process Perfect Heavyweight Matches")
        print("3. Auto Process Low Confidence Links")
        print("q. Quit")
        
        choice = input("Enter choice: ").lower().strip()
        
        if choice == '1':
            run_normal_processing(file_path)
        elif choice == '2':
            process_perfect_heavyweights(file_path)
        elif choice == '3':
            process_low_confidence_links(file_path)
        elif choice == 'q':
            print("Exiting program.")
            break
        else:
            print("Invalid choice. Please try again.")

# Use the new main function if the script is run directly
if __name__ == "__main__":
    main() 