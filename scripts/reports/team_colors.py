#!/usr/bin/env python3
"""
Official primary color + nickname per NCAA D1 wrestling program we track,
keyed by the same non-collapsing slug build_wrestler_profiles.py uses for
by_team/roster directories (see build_transfer_dpg_report.py's slugify()
docstring).

`stroke: true` marks colors light enough (gold, pale blue, etc.) that a
disc needs a dark outline to read against the report's cream background --
mirrors Iowa's gold+black-stroke treatment in the reference design.

`nickname` is the school's official athletics nickname/mascot (e.g. "Penn
State" -> "Nittany Lions"), used alongside `name` on the mobile schedule
matchup card (frontend/wrestledata-ui/public/schedule.js) so it can show
"Penn State / Nittany Lions" instead of the school name alone. Cross-checked
against https://www.trucolor.net/college-colors-nicknames/ where the site's
alphabetical-by-nickname index made a given school easy to verify.

Best-effort from official athletics brand colors; not guaranteed pixel-
perfect for every program, but chosen for the trueest single "identity"
color per school rather than a generic accent.
"""

TEAM_COLORS = {
    "air_force":            {"name": "Air Force",          "nickname": "Falcons",         "hex": "#003087", "stroke": False},
    "american":              {"name": "American",           "nickname": "Eagles",          "hex": "#A6192E", "stroke": False},
    "appalachian_state":     {"name": "Appalachian State",  "nickname": "Mountaineers",    "hex": "#000000", "stroke": False},
    "arizona_state":         {"name": "Arizona State",      "nickname": "Sun Devils",      "hex": "#8C1D40", "stroke": False},
    "army_west_point":       {"name": "Army West Point",    "nickname": "Black Knights",   "hex": "#000000", "stroke": False},
    "bellarmine":            {"name": "Bellarmine",         "nickname": "Knights",         "hex": "#A6192E", "stroke": False},
    "binghamton":            {"name": "Binghamton",         "nickname": "Bearcats",        "hex": "#005A43", "stroke": False},
    "bloomsburg":             {"name": "Bloomsburg",         "nickname": "Huskies",         "hex": "#6F263D", "stroke": False},
    "brown":                 {"name": "Brown",              "nickname": "Bears",           "hex": "#4E3629", "stroke": False},
    "bucknell":              {"name": "Bucknell",           "nickname": "Bison",           "hex": "#FF7F00", "stroke": False},
    "buffalo":               {"name": "Buffalo",            "nickname": "Bulls",           "hex": "#005BBB", "stroke": False},
    "csu_bakersfield":       {"name": "CSU Bakersfield",    "nickname": "Roadrunners",     "hex": "#003DA5", "stroke": False},
    "cal_poly":              {"name": "Cal Poly",           "nickname": "Mustangs",        "hex": "#154734", "stroke": False},
    "california_baptist":    {"name": "California Baptist", "nickname": "Lancers",        "hex": "#C41230", "stroke": False},
    "campbell":              {"name": "Campbell",           "nickname": "Fighting Camels", "hex": "#F58025", "stroke": False},
    "central_michigan":      {"name": "Central Michigan",   "nickname": "Chippewas",       "hex": "#6A0032", "stroke": False},
    "chattanooga":           {"name": "Chattanooga",        "nickname": "Mocs",            "hex": "#00386B", "stroke": False},
    "clarion":               {"name": "Clarion",            "nickname": "Golden Eagles",   "hex": "#002D62", "stroke": False},
    "columbia":              {"name": "Columbia",           "nickname": "Lions",           "hex": "#B9D9EB", "stroke": True},
    "cornell":               {"name": "Cornell",            "nickname": "Big Red",         "hex": "#B31B1B", "stroke": False},
    "davidson":              {"name": "Davidson",           "nickname": "Wildcats",        "hex": "#A6192E", "stroke": False},
    "drexel":                {"name": "Drexel",             "nickname": "Dragons",         "hex": "#07294D", "stroke": False},
    "duke":                  {"name": "Duke",               "nickname": "Blue Devils",     "hex": "#00539B", "stroke": False},
    "edinboro":              {"name": "Edinboro",           "nickname": "Fighting Scots",  "hex": "#C8102E", "stroke": False},
    "franklin__marshall":    {"name": "Franklin & Marshall","nickname": "Diplomats",       "hex": "#00205B", "stroke": False},
    "gardnerwebb":           {"name": "Gardner-Webb",       "nickname": "Bulldogs",        "hex": "#BA0C2F", "stroke": False},
    "george_mason":          {"name": "George Mason",       "nickname": "Patriots",        "hex": "#006633", "stroke": False},
    "harvard":               {"name": "Harvard",            "nickname": "Crimson",         "hex": "#A51C30", "stroke": False},
    "hofstra":               {"name": "Hofstra",            "nickname": "Pride",           "hex": "#0033A0", "stroke": False},
    "illinois":              {"name": "Illinois",           "nickname": "Fighting Illini", "hex": "#E84A27", "stroke": False},
    "indiana":               {"name": "Indiana",            "nickname": "Hoosiers",        "hex": "#990000", "stroke": False},
    "iowa":                  {"name": "Iowa",               "nickname": "Hawkeyes",        "hex": "#FFCD00", "stroke": True},
    "iowa_state":            {"name": "Iowa State",         "nickname": "Cyclones",        "hex": "#C8102E", "stroke": False},
    "kent_state":            {"name": "Kent State",         "nickname": "Golden Flashes",  "hex": "#002664", "stroke": False},
    "liu":                   {"name": "LIU",                "nickname": "Sharks",          "hex": "#002F6C", "stroke": False},
    "lehigh":                {"name": "Lehigh",             "nickname": "Mountain Hawks",  "hex": "#532E1F", "stroke": False},
    "little_rock":           {"name": "Little Rock",        "nickname": "Trojans",         "hex": "#B71234", "stroke": False},
    "lock_haven":            {"name": "Lock Haven",         "nickname": "Bald Eagles",     "hex": "#00573F", "stroke": False},
    "maryland":              {"name": "Maryland",           "nickname": "Terrapins",       "hex": "#E21833", "stroke": False},
    "mercyhurst":            {"name": "Mercyhurst",         "nickname": "Lakers",          "hex": "#00563F", "stroke": False},
    "michigan":              {"name": "Michigan",           "nickname": "Wolverines",      "hex": "#00274C", "stroke": False},
    "michigan_state":        {"name": "Michigan State",     "nickname": "Spartans",        "hex": "#18453B", "stroke": False},
    "minnesota":             {"name": "Minnesota",          "nickname": "Golden Gophers",  "hex": "#7A0019", "stroke": False},
    "missouri":              {"name": "Missouri",           "nickname": "Tigers",          "hex": "#000000", "stroke": False},
    "morgan_state":          {"name": "Morgan State",       "nickname": "Bears",           "hex": "#002147", "stroke": False},
    "navy":                  {"name": "Navy",               "nickname": "Midshipmen",      "hex": "#00205B", "stroke": False},
    "nc_state":              {"name": "NC State",           "nickname": "Wolfpack",        "hex": "#CC0000", "stroke": False},
    "nebraska":              {"name": "Nebraska",           "nickname": "Cornhuskers",     "hex": "#D00000", "stroke": False},
    "north_carolina":        {"name": "North Carolina",     "nickname": "Tar Heels",       "hex": "#7BAFD4", "stroke": True},
    "north_dakota_state":    {"name": "North Dakota State", "nickname": "Bison",           "hex": "#005643", "stroke": False},
    "northern_colorado":     {"name": "Northern Colorado",  "nickname": "Bears",           "hex": "#002554", "stroke": False},
    "northern_illinois":     {"name": "Northern Illinois",  "nickname": "Huskies",         "hex": "#C8102E", "stroke": False},
    "northern_iowa":         {"name": "Northern Iowa",      "nickname": "Panthers",        "hex": "#500778", "stroke": False},
    "northwestern":          {"name": "Northwestern",       "nickname": "Wildcats",        "hex": "#4E2A84", "stroke": False},
    "ohio":                  {"name": "Ohio",               "nickname": "Bobcats",         "hex": "#00694E", "stroke": False},
    "ohio_state":            {"name": "Ohio State",         "nickname": "Buckeyes",        "hex": "#BB0000", "stroke": False},
    "oklahoma":              {"name": "Oklahoma",           "nickname": "Sooners",         "hex": "#841617", "stroke": False},
    "oklahoma_state":        {"name": "Oklahoma State",     "nickname": "Cowboys",         "hex": "#FF7300", "stroke": False},
    "oregon_state":          {"name": "Oregon State",       "nickname": "Beavers",         "hex": "#DC4405", "stroke": False},
    "penn":                  {"name": "Penn",               "nickname": "Quakers",         "hex": "#990000", "stroke": False},
    "penn_state":            {"name": "Penn State",         "nickname": "Nittany Lions",   "hex": "#1E407C", "stroke": False},
    "pittsburgh":            {"name": "Pittsburgh",         "nickname": "Panthers",        "hex": "#003594", "stroke": False},
    "presbyterian":          {"name": "Presbyterian",       "nickname": "Blue Hose",       "hex": "#002D72", "stroke": False},
    "princeton":             {"name": "Princeton",          "nickname": "Tigers",          "hex": "#FF6700", "stroke": False},
    "purdue":                {"name": "Purdue",             "nickname": "Boilermakers",    "hex": "#000000", "stroke": False},
    "rider":                 {"name": "Rider",              "nickname": "Broncs",          "hex": "#C8102E", "stroke": False},
    "rutgers":               {"name": "Rutgers",            "nickname": "Scarlet Knights", "hex": "#CC0033", "stroke": False},
    "siu_edwardsville":      {"name": "SIU Edwardsville",   "nickname": "Cougars",         "hex": "#A6192E", "stroke": False},
    "sacred_heart":          {"name": "Sacred Heart",       "nickname": "Pioneers",        "hex": "#A6192E", "stroke": False},
    "south_dakota_state":    {"name": "South Dakota State", "nickname": "Jackrabbits",     "hex": "#FFD100", "stroke": True},
    "stanford":              {"name": "Stanford",           "nickname": "Cardinal",        "hex": "#8C1515", "stroke": False},
    "the_citadel":           {"name": "The Citadel",        "nickname": "Bulldogs",        "hex": "#003876", "stroke": False},
    "utah_valley":           {"name": "Utah Valley",        "nickname": "Wolverines",      "hex": "#00534C", "stroke": False},
    "vmi":                   {"name": "VMI",                "nickname": "Keydets",         "hex": "#C41230", "stroke": False},
    "virginia":              {"name": "Virginia",           "nickname": "Cavaliers",       "hex": "#232D4B", "stroke": False},
    "virginia_tech":         {"name": "Virginia Tech",      "nickname": "Hokies",          "hex": "#630031", "stroke": False},
    "west_virginia":         {"name": "West Virginia",      "nickname": "Mountaineers",    "hex": "#002855", "stroke": False},
    "wisconsin":             {"name": "Wisconsin",          "nickname": "Badgers",         "hex": "#C5050C", "stroke": False},
    "wyoming":               {"name": "Wyoming",            "nickname": "Cowboys",         "hex": "#492F24", "stroke": False},
}

DEFAULT_COLOR = {"hex": "#6b6153", "stroke": False}  # muted neutral fallback for any untracked slug
