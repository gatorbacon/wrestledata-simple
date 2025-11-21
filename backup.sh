#!/bin/bash

cd "$(dirname "$0")" || exit 1

read -p "📬 Enter commit message: " msg

if [ -z "$msg" ]; then
  echo "❌ Commit message cannot be empty."
  exit 1
fi

echo "📦 Backing up workspace..."

git add -A
git commit -m "$msg"
git push

echo "✅ Backup complete."

