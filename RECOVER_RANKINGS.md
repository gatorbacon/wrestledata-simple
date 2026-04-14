# Recovery Guide for Rankings Release Mistake

## Problem
You ran the rankings release script with the wrong drop-id, which may have overwritten files needed for tracking rankings movements between drops.

## Files That May Have Been Overwritten

### Critical Files (for movement tracking):
1. **`frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json`**
   - This file tracks all drops and determines which is the "previous" drop
   - If this is wrong, movement indicators won't calculate correctly

2. **`frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/*.json`**
   - All weight class files in the drop directory
   - These contain the movement data based on previous drop

3. **`frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/meta.json`**
   - Metadata about the drop

### Optional Files (graphics):
- `mt/graphics/2026/hs_rankings_girls_2026.pdf`
- `mt/graphics/2026/top40v1-girls_*.svg` and `.jpg` files

## Recovery Steps

### Step 1: Check What Was Actually Changed

```bash
# See all modified rankings files
git status --short | grep "rankings/girls/2026"

# See what changed in the critical index.json
git diff HEAD -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json

# Check if files exist in git history
git log --oneline -10 -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json
```

### Step 2: Restore Files from Git

**If you haven't committed the mistake yet:**
```bash
# Restore index.json (most critical)
git checkout HEAD -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json

# Restore all weight class files in the drop directory
git checkout HEAD -- frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/*.json

# Restore meta.json
git checkout HEAD -- frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/meta.json
```

**If you already committed the mistake:**
```bash
# Find the commit before the mistake (look for the last good rankings release)
git log --oneline -20

# Restore from that commit (replace COMMIT_HASH with actual hash)
git checkout COMMIT_HASH -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json
git checkout COMMIT_HASH -- frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/
```

**From the commit history, the last good commit appears to be:**
```bash
git checkout 69b294968 -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json
git checkout 69b294968 -- frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/
```

### Step 3: Verify the Recovery

```bash
# Check that index.json has correct drop history
cat frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json

# Should show both drops:
# - 2026-01-07 (most recent)
# - 2026-01-02 (previous, for movement calculations)
```

### Step 4: Re-run with Correct Drop-ID

Once files are recovered, re-run the rankings release script with the **CORRECT** drop-id:

```bash
python scripts/rankings/create_rankings_release.py \
    -season 2026 \
    -gender girls \
    -drop-id 2026-01-14 \
    --archive \
    --pdf \
    --jpg
```

(Replace `2026-01-14` with the actual correct drop date)

## Quick Recovery Script

You can also use the provided recovery script:

```bash
./recover_rankings_files.sh
```

This will:
1. Show you which files need recovery
2. Ask for confirmation
3. Restore all affected files from git HEAD

## Important Notes

- The `index.json` file is **critical** - it determines which drop is used as the "previous" drop for calculating movement indicators
- If the wrong drop-id was used, the movement calculations in the weight class JSON files will be incorrect
- Always verify the `index.json` has the correct drop history before re-running the script

