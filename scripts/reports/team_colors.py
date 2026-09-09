#!/usr/bin/env python3
"""
Official primary color per NCAA D1 wrestling program we track, keyed by the
same non-collapsing slug build_wrestler_profiles.py uses for by_team/
roster directories (see build_transfer_dpg_report.py's slugify() docstring).

`stroke: true` marks colors light enough (gold, pale blue, etc.) that a
disc needs a dark outline to read against the report's cream background --
mirrors Iowa's gold+black-stroke treatment in the reference design.

Best-effort from official athletics brand colors; not guaranteed pixel-
perfect for every program, but chosen for the trueest single "identity"
color per school rather than a generic accent.
"""

TEAM_COLORS = {
    "air_force":            {"name": "Air Force",          "hex": "#003087", "stroke": False},
    "american":              {"name": "American",           "hex": "#A6192E", "stroke": False},
    "appalachian_state":     {"name": "Appalachian State",  "hex": "#000000", "stroke": False},
    "arizona_state":         {"name": "Arizona State",      "hex": "#8C1D40", "stroke": False},
    "army_west_point":       {"name": "Army West Point",    "hex": "#000000", "stroke": False},
    "bellarmine":            {"name": "Bellarmine",         "hex": "#A6192E", "stroke": False},
    "binghamton":            {"name": "Binghamton",         "hex": "#005A43", "stroke": False},
    "bloomsburg":             {"name": "Bloomsburg",         "hex": "#6F263D", "stroke": False},
    "brown":                 {"name": "Brown",              "hex": "#4E3629", "stroke": False},
    "bucknell":              {"name": "Bucknell",           "hex": "#FF7F00", "stroke": False},
    "buffalo":               {"name": "Buffalo",            "hex": "#005BBB", "stroke": False},
    "csu_bakersfield":       {"name": "CSU Bakersfield",    "hex": "#003DA5", "stroke": False},
    "cal_poly":              {"name": "Cal Poly",           "hex": "#154734", "stroke": False},
    "california_baptist":    {"name": "California Baptist", "hex": "#C41230", "stroke": False},
    "campbell":              {"name": "Campbell",           "hex": "#F58025", "stroke": False},
    "central_michigan":      {"name": "Central Michigan",   "hex": "#6A0032", "stroke": False},
    "chattanooga":           {"name": "Chattanooga",        "hex": "#00386B", "stroke": False},
    "clarion":               {"name": "Clarion",            "hex": "#002D62", "stroke": False},
    "columbia":              {"name": "Columbia",           "hex": "#B9D9EB", "stroke": True},
    "cornell":               {"name": "Cornell",            "hex": "#B31B1B", "stroke": False},
    "davidson":              {"name": "Davidson",           "hex": "#A6192E", "stroke": False},
    "drexel":                {"name": "Drexel",             "hex": "#07294D", "stroke": False},
    "duke":                  {"name": "Duke",               "hex": "#00539B", "stroke": False},
    "edinboro":              {"name": "Edinboro",           "hex": "#C8102E", "stroke": False},
    "franklin__marshall":    {"name": "Franklin & Marshall","hex": "#00205B", "stroke": False},
    "gardnerwebb":           {"name": "Gardner-Webb",       "hex": "#BA0C2F", "stroke": False},
    "george_mason":          {"name": "George Mason",       "hex": "#006633", "stroke": False},
    "harvard":               {"name": "Harvard",            "hex": "#A51C30", "stroke": False},
    "hofstra":               {"name": "Hofstra",            "hex": "#0033A0", "stroke": False},
    "illinois":              {"name": "Illinois",           "hex": "#E84A27", "stroke": False},
    "indiana":               {"name": "Indiana",            "hex": "#990000", "stroke": False},
    "iowa":                  {"name": "Iowa",               "hex": "#FFCD00", "stroke": True},
    "iowa_state":            {"name": "Iowa State",         "hex": "#C8102E", "stroke": False},
    "kent_state":            {"name": "Kent State",         "hex": "#002664", "stroke": False},
    "liu":                   {"name": "LIU",                "hex": "#002F6C", "stroke": False},
    "lehigh":                {"name": "Lehigh",             "hex": "#532E1F", "stroke": False},
    "little_rock":           {"name": "Little Rock",        "hex": "#B71234", "stroke": False},
    "lock_haven":            {"name": "Lock Haven",         "hex": "#00573F", "stroke": False},
    "maryland":              {"name": "Maryland",           "hex": "#E21833", "stroke": False},
    "mercyhurst":            {"name": "Mercyhurst",         "hex": "#00563F", "stroke": False},
    "michigan":              {"name": "Michigan",           "hex": "#00274C", "stroke": False},
    "michigan_state":        {"name": "Michigan State",     "hex": "#18453B", "stroke": False},
    "minnesota":             {"name": "Minnesota",          "hex": "#7A0019", "stroke": False},
    "missouri":              {"name": "Missouri",           "hex": "#000000", "stroke": False},
    "morgan_state":          {"name": "Morgan State",       "hex": "#002147", "stroke": False},
    "navy":                  {"name": "Navy",               "hex": "#00205B", "stroke": False},
    "nc_state":              {"name": "NC State",           "hex": "#CC0000", "stroke": False},
    "nebraska":              {"name": "Nebraska",           "hex": "#D00000", "stroke": False},
    "north_carolina":        {"name": "North Carolina",     "hex": "#7BAFD4", "stroke": True},
    "north_dakota_state":    {"name": "North Dakota State", "hex": "#005643", "stroke": False},
    "northern_colorado":     {"name": "Northern Colorado",  "hex": "#002554", "stroke": False},
    "northern_illinois":     {"name": "Northern Illinois",  "hex": "#C8102E", "stroke": False},
    "northern_iowa":         {"name": "Northern Iowa",      "hex": "#500778", "stroke": False},
    "northwestern":          {"name": "Northwestern",       "hex": "#4E2A84", "stroke": False},
    "ohio":                  {"name": "Ohio",               "hex": "#00694E", "stroke": False},
    "ohio_state":            {"name": "Ohio State",         "hex": "#BB0000", "stroke": False},
    "oklahoma":              {"name": "Oklahoma",           "hex": "#841617", "stroke": False},
    "oklahoma_state":        {"name": "Oklahoma State",     "hex": "#FF7300", "stroke": False},
    "oregon_state":          {"name": "Oregon State",       "hex": "#DC4405", "stroke": False},
    "penn":                  {"name": "Penn",               "hex": "#990000", "stroke": False},
    "penn_state":            {"name": "Penn State",         "hex": "#1E407C", "stroke": False},
    "pittsburgh":            {"name": "Pittsburgh",         "hex": "#003594", "stroke": False},
    "presbyterian":          {"name": "Presbyterian",       "hex": "#002D72", "stroke": False},
    "princeton":             {"name": "Princeton",          "hex": "#FF6700", "stroke": False},
    "purdue":                {"name": "Purdue",             "hex": "#000000", "stroke": False},
    "rider":                 {"name": "Rider",              "hex": "#C8102E", "stroke": False},
    "rutgers":               {"name": "Rutgers",            "hex": "#CC0033", "stroke": False},
    "siu_edwardsville":      {"name": "SIU Edwardsville",   "hex": "#A6192E", "stroke": False},
    "sacred_heart":          {"name": "Sacred Heart",       "hex": "#A6192E", "stroke": False},
    "south_dakota_state":    {"name": "South Dakota State", "hex": "#FFD100", "stroke": True},
    "stanford":              {"name": "Stanford",           "hex": "#8C1515", "stroke": False},
    "the_citadel":           {"name": "The Citadel",        "hex": "#003876", "stroke": False},
    "utah_valley":           {"name": "Utah Valley",        "hex": "#00534C", "stroke": False},
    "vmi":                   {"name": "VMI",                "hex": "#C41230", "stroke": False},
    "virginia":              {"name": "Virginia",           "hex": "#232D4B", "stroke": False},
    "virginia_tech":         {"name": "Virginia Tech",      "hex": "#630031", "stroke": False},
    "west_virginia":         {"name": "West Virginia",      "hex": "#002855", "stroke": False},
    "wisconsin":             {"name": "Wisconsin",          "hex": "#C5050C", "stroke": False},
    "wyoming":               {"name": "Wyoming",            "hex": "#492F24", "stroke": False},
}

DEFAULT_COLOR = {"hex": "#6b6153", "stroke": False}  # muted neutral fallback for any untracked slug
