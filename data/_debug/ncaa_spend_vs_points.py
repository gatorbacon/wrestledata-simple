import json

# Load expenses
with open('ncaa_wrestling_expenses_2025.json') as f:
    expenses = json.load(f)

# Load tournament points
with open('../../../frontend/wrestledata-ui/public/data/2026/simulation_replay.json') as f:
    sim = json.load(f)
points = sim['current_projection']

# Name mapping: common_name in expenses -> tournament name in sim data
name_map = {
    "Army": "Army West Point",
}

# Build combined records
records = []
for e in expenses:
    cname = e['common_name']
    lookup = name_map.get(cname, cname)
    pts = points.get(lookup, 0)
    cost_per_pt = round(e['expenses_2025'] / pts, 0) if pts > 0 else None
    records.append({
        "team": cname,
        "expenses": e['expenses_2025'],
        "points": pts,
        "cost_per_point": cost_per_pt,
    })

# Sort by points desc for table
records_sorted = sorted(records, key=lambda x: -x['points'])

# Save combined JSON
with open('ncaa_spend_vs_points.json', 'w') as f:
    json.dump(records_sorted, f, indent=2)
print("Saved ncaa_spend_vs_points.json")

# Teams that scored but aren't in expenses list
expense_teams = {e['common_name'] for e in expenses}
expense_teams.add("Army West Point")  # mapped
for team, pts in sorted(points.items(), key=lambda x: -x[1]):
    if pts > 0 and team not in expense_teams:
        print(f"  No expense data: {team} ({pts} pts)")
