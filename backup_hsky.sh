#!/bin/bash

cd "$(dirname "$0")" || exit 1

current_branch=$(git branch --show-current)

if [ "$current_branch" != "hsky-dev" ]; then
  echo "❌ You are on '$current_branch'. Switch to 'hsky-dev' to run this backup."
  exit 1
fi

read -p "📬 Enter HS commit message: " msg

if [ -z "$msg" ]; then
  echo "❌ Commit message cannot be empty."
  exit 1
fi

echo "📦 Backing up HSKY workspace..."

git add -A
git commit -m "$msg"
git push origin hsky-dev

echo "✅ HSKY backup complete."