"""
JSON data import utilities for WrestleRank.

This module imports teams, wrestlers, and matches from the new JSON data
format into the SQLite database schema used by the app.
"""

import json
import os
import re
import datetime
from typing import Dict, Optional, Tuple

from wrestlerank.db import sqlite_db
from wrestlerank.matrix import relationship_manager


def _parse_team_id_from_url(url: str) -> Optional[str]:
	"""Extract teamId query parameter from a TrackWrestling team URL."""
	if not url:
		return None
	match = re.search(r"[?&]teamId=([^&]+)", url)
	return match.group(1) if match else None


def import_teams_json(json_path: str) -> Dict[str, int]:
	"""
	Import teams from a JSON file (array of team objects).
	Expected fields: name, state, abbreviation, url (contains teamId).
	Returns mapping of team name -> DB team id.
	"""
	if not os.path.exists(json_path):
		raise FileNotFoundError(json_path)

	with open(json_path, "r", encoding="utf-8") as f:
		data = json.load(f)

	if not isinstance(data, list):
		raise ValueError("Teams JSON must be a list of team objects")

	sqlite_db.init_db()
	team_map: Dict[str, int] = {}
	try:
		for item in data:
			name = (item.get("name") or "").strip()
			if not name:
				continue
			state = (item.get("state") or "").strip() or None
			short_name = (item.get("abbreviation") or "").strip() or None
			external_id = _parse_team_id_from_url(item.get("url") or "") or None

			# Try to find existing by external_id, else by name
			existing = None
			if external_id:
				existing = sqlite_db.get_team_by_external_id(external_id)
			if not existing:
				existing = sqlite_db.get_team_by_name(name)

			if existing:
				team_map[name] = existing["id"]
			else:
				team_id = sqlite_db.add_team(
					name=name,
					external_id=external_id,
					short_name=short_name,
					state=state
				)
				team_map[name] = team_id
	finally:
		sqlite_db.close_db()

	return team_map


def _ensure_team_id_for_name(team_name: str) -> Optional[int]:
	"""Best-effort lookup of team id by exact name or LIKE."""
	if not team_name:
		return None
	cursor = sqlite_db.conn.cursor()
	# Try exact
	cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
	row = cursor.fetchone()
	if row:
		return row["id"]
	# Try LIKE
	cursor.execute("SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",))
	row = cursor.fetchone()
	return row["id"] if row else None


def _get_or_create_wrestler(external_id: str, name: str, team_name: str, weight_class: Optional[str]) -> Dict:
	"""Ensure a wrestler exists; create if missing. Returns DB row as dict-like Row."""
	w = sqlite_db.get_wrestler_by_external_id(external_id)
	if w:
		return w

	team_id = _ensure_team_id_for_name(team_name)
	wrestler_db_id = sqlite_db.add_wrestler(
		name=name,
		external_id=external_id,
		team_id=team_id,
		team_name=team_name,
		weight_class=weight_class,
		active_team=True,
		wins=0,
		losses=0,
		matches=0
	)
	cursor = sqlite_db.conn.cursor()
	cursor.execute("SELECT * FROM wrestlers WHERE id = ?", (wrestler_db_id,))
	return cursor.fetchone()


_RESULT_PATTERN = re.compile(
	r"""(?P<winner>[^()]+?)\s*\((?P<winner_team>[^()]+?)\)\s*over\s*(?P<loser>[^()]+?)\s*\((?P<loser_team>[^()]+?)\)\s*\((?P<result>[^)]+)\)""",
	re.IGNORECASE,
)

_LEADING_PREFIX = re.compile(r"^\s*[^-]+-\s*")  # e.g., "Varsity - ", "Cons. Round 1 - ", etc.


def _parse_match_summary(summary: str) -> Optional[Tuple[str, str, str, str, str]]:
	"""
	Parse a summary like:
	"Varsity - Winner Name (Team) over Loser Name (Team) (Dec 4-0)"
	Returns (winner_name, winner_team, loser_name, loser_team, result) or None if not a completed match.
	"""
	if not summary or "over" not in summary.lower():
		return None
	# Strip leading labels like "Varsity - ", "Cons. Round 1 - ", "Quarterfinals - ", etc.
	clean = _LEADING_PREFIX.sub("", summary.strip())
	m = _RESULT_PATTERN.search(clean)
	if not m:
		return None
	return (
		m.group("winner").strip(),
		m.group("winner_team").strip(),
		m.group("loser").strip(),
		m.group("loser_team").strip(),
		m.group("result").strip(),
	)


def _is_bye_or_unscheduled(summary: str) -> bool:
	s = (summary or "").lower()
	if "received a bye" in s:
		return True
	# Examples like "vs. Presbyterian) vs. Nick Gonzalez" have no "over"
	if " vs. " in s and "over" not in s:
		return True
	return False


def _to_iso_date(mmddyyyy: str) -> str:
	try:
		d = datetime.datetime.strptime(mmddyyyy, "%m/%d/%Y")
		return d.strftime("%Y-%m-%d")
	except Exception:
		# Fallback to today if format unexpected
		return datetime.date.today().isoformat()


def _update_wrestler_stats_after_match(winner_row: Dict, loser_row: Dict) -> None:
	"""Increment wins/losses/matches and recompute win% for both wrestlers."""
	# Winner
	new_wins = (winner_row["wins"] or 0) + 1
	new_matches = (winner_row["matches"] or 0) + 1
	win_pct = (new_wins / new_matches) * 100 if new_matches > 0 else 0
	sqlite_db.update_wrestler_stats(
		winner_row["id"],
		wins=new_wins,
		matches=new_matches,
		win_percentage=win_pct,
	)
	# Loser
	new_losses = (loser_row["losses"] or 0) + 1
	new_matches = (loser_row["matches"] or 0) + 1
	win_pct = ((loser_row["wins"] or 0) / new_matches) * 100 if new_matches > 0 else 0
	sqlite_db.update_wrestler_stats(
		loser_row["id"],
		losses=new_losses,
		matches=new_matches,
		win_percentage=win_pct,
	)


def import_team_matches_json(json_path: str, update_relationships: bool = True) -> int:
	"""
	Import a single team's roster and matches JSON.
	Creates wrestlers for all roster entries; imports completed matches and updates relationships.
	Returns number of matches imported.
	"""
	if not os.path.exists(json_path):
		raise FileNotFoundError(json_path)

	with open(json_path, "r", encoding="utf-8") as f:
		data = json.load(f)

	team_name = data.get("team_name") or data.get("name") or ""
	abbr = data.get("abbreviation") or ""
	season = data.get("season")
	roster = data.get("roster") or []

	sqlite_db.init_db()
	imported = 0
	try:
		for athlete in roster:
			wrestler_ext_id = str(athlete.get("season_wrestler_id") or "").strip()
			wrestler_name = (athlete.get("name") or "").strip()
			wc = (athlete.get("weight_class") or "").strip() or None
			grade = athlete.get("grade")  # unused but available

			if not wrestler_ext_id or not wrestler_name:
				continue

			# Ensure wrestler exists (active on team)
			home_wrestler = _get_or_create_wrestler(wrestler_ext_id, wrestler_name, team_name, wc)

			for match in athlete.get("matches") or []:
				date_src = match.get("date") or ""
				event = match.get("event") or ""
				match_weight = (match.get("weight") or "").strip()
				summary = match.get("summary") or ""
				opponent_ext_id = match.get("opponent_id")

				# Skip bye/unscheduled
				if _is_bye_or_unscheduled(summary):
					continue

				parsed = _parse_match_summary(summary)
				if not parsed:
					# Not a completed match we can parse; skip
					continue

				win_name, win_team, lose_name, lose_team, result = parsed

				# Require opponent_id to avoid creating duplicate placeholder wrestlers
				if not opponent_ext_id:
					# Skip matches without a stable opponent id to prevent duplicates
					continue
				opp_external_id = str(opponent_ext_id)

				# Ensure opponent exists
				opponent_row = _get_or_create_wrestler(
					opp_external_id,
					lose_name if wrestler_name == win_name else win_name,
					lose_team if wrestler_name == win_name else win_team,
					match_weight or wc,
				)

				# Decide winner/loser external IDs in our schema
				if wrestler_name == win_name:
					winner_id = wrestler_ext_id
					loser_id = opponent_row["external_id"]
				elif wrestler_name == lose_name:
					winner_id = opponent_row["external_id"]
					loser_id = wrestler_ext_id
				else:
					# Names didn't align (format variance). With stable opponent_id present,
					# resolve by assuming rostered athlete is home; decide winner by string equality fallback.
					# If still ambiguous, leave as opponent as winner only when summary indicates so.
					# Heuristic: if home name appears at start of clean summary, assume 'winner' is home.
					clean_summary = _LEADING_PREFIX.sub("", summary.strip())
					if clean_summary.startswith(wrestler_name):
						winner_id = wrestler_ext_id
						loser_id = opponent_row["external_id"]
					else:
						# Default to opponent as winner to keep consistency with summary
						winner_id = opponent_row["external_id"]
						loser_id = wrestler_ext_id

				# Build fields
				date_iso = _to_iso_date(date_src) if date_src else datetime.date.today().isoformat()
				weight_class = match_weight or wc
				if not weight_class:
					# If entirely missing, skip to avoid polluting data
					continue

				# Unique match external ID
				match_uid = f"{date_iso.replace('-', '')}-{winner_id}-{loser_id}"

				# Skip if match already exists
				existing = sqlite_db.get_match_by_external_id(match_uid)
				if existing:
					continue

				# Add match
				sqlite_db.add_match(
					external_id=match_uid,
					date=date_iso,
					weight_class=weight_class,
					wrestler1_id=winner_id,
					wrestler2_id=loser_id,
					winner_id=winner_id,
					result=result,
				)
				imported += 1

				# Update stats
				winner_row = sqlite_db.get_wrestler_by_external_id(winner_id)
				loser_row = sqlite_db.get_wrestler_by_external_id(loser_id)
				if winner_row and loser_row:
					_update_wrestler_stats_after_match(winner_row, loser_row)

				# Update relationships
				if update_relationships:
					relationship_manager.update_direct_relationship(
						winner_id, loser_id, weight_class, match_uid, existing_connection=True
					)
		sqlite_db.conn.commit()
	finally:
		sqlite_db.close_db()

	return imported


def import_matches_json(path: str, update_relationships: bool = True) -> int:
	"""
	Import matches from a JSON file or all JSON files in a directory.
	Returns the total number of matches imported.
	"""
	total = 0
	if os.path.isdir(path):
		for name in os.listdir(path):
			if not name.lower().endswith(".json"):
				continue
			total += import_team_matches_json(os.path.join(path, name), update_relationships=update_relationships)
	else:
		total = import_team_matches_json(path, update_relationships=update_relationships)
	return total


