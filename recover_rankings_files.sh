#!/bin/bash
# Recovery script for rankings release files that were overwritten
# This will restore files from the last git commit before the mistake

echo "Recovering rankings release files from git..."
echo ""

# Get the list of modified files related to girls 2026 rankings
FILES_TO_RECOVER=(
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/100.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/107.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/114.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/120.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/126.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/132.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/138.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/145.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/152.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/165.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/185.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/235.json"
    "frontend/hs-ky-ui/public/data/rankings/girls/2026/2026-01-07/meta.json"
)

# Check if index.json exists in git history
if git cat-file -e HEAD:frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json 2>/dev/null; then
    echo "✓ Found index.json in git history"
else
    echo "⚠ Warning: index.json not found in current HEAD. Checking previous commits..."
    # Try to find it in recent commits
    COMMIT=$(git log --oneline --all -20 -- "frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json" | head -1 | cut -d' ' -f1)
    if [ -n "$COMMIT" ]; then
        echo "  Found in commit: $COMMIT"
        echo "  Use: git checkout $COMMIT -- frontend/hs-ky-ui/public/data/rankings/girls/2026/index.json"
    fi
fi

echo ""
echo "Files to recover:"
for file in "${FILES_TO_RECOVER[@]}"; do
    if [ -f "$file" ]; then
        if git diff --quiet HEAD -- "$file" 2>/dev/null; then
            echo "  ✓ $file (unchanged)"
        else
            echo "  M $file (modified - will restore)"
        fi
    else
        echo "  ? $file (not found)"
    fi
done

echo ""
read -p "Do you want to restore these files from HEAD? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Restoring files from git HEAD..."
    for file in "${FILES_TO_RECOVER[@]}"; do
        if git cat-file -e HEAD:"$file" 2>/dev/null; then
            git checkout HEAD -- "$file"
            echo "  ✓ Restored: $file"
        else
            echo "  ⚠ Not found in HEAD: $file"
        fi
    done
    echo ""
    echo "✓ Recovery complete!"
    echo ""
    echo "Next steps:"
    echo "1. Verify the index.json has the correct drop history"
    echo "2. Re-run the rankings release script with the CORRECT drop-id"
    echo "3. Check that movement indicators are calculated correctly"
else
    echo "Recovery cancelled."
fi

