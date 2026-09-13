#!/usr/bin/env python3
"""
new_note.py

Scaffolds a new MatSavant Note draft: creates
frontend/wrestledata-ui/notes_drafts/<slug>/note.md with a frontmatter
template, then opens it in Obsidian (paste a screenshot from the
clipboard and Obsidian auto-saves it into the same draft folder and
inserts the markdown image reference for you).

Requires frontend/wrestledata-ui/notes_drafts/ to be opened in Obsidian
as its own vault (not nested in a subfolder) with:
  Settings -> Files & Links -> "New attachment location" = Same folder as current file
  Settings -> Files & Links -> "Use [[Wikilinks]]" = off

OBSIDIAN_VAULT below must exactly match the vault name shown in
Obsidian's vault switcher (bottom-left corner) -- update it if it
doesn't say "notes_drafts".

Usage:
    python scripts/notes/new_note.py "Oklahoma State has a 17% shot"
    python scripts/notes/new_note.py "My Title" --slug custom-slug
"""

import argparse
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DRAFTS_DIR = REPO_ROOT / "frontend/wrestledata-ui/notes_drafts"
OBSIDIAN_VAULT = "notes_drafts"

TEMPLATE = """---
title: {title}
hook: One sentence that sells the argument
tags: tag1, tag2
---

Write the note here. **Bold**, *italic*, `code`, and [links](https://example.com)
all work. Drop screenshots into this same folder and reference them like:

![Alt text describing the image](screenshot1.png)
*Optional caption shown under the image*

Leave a blank line between paragraphs and around images.
"""


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new MatSavant Note draft")
    parser.add_argument("title", help="Note title")
    parser.add_argument("--slug", help="Override the auto-generated slug")
    parser.add_argument("--no-open", action="store_true", help="Don't open Obsidian afterward")
    args = parser.parse_args()

    slug = args.slug or slugify(args.title)
    if not slug:
        print("Error: could not derive a slug from that title, pass --slug explicitly")
        sys.exit(1)

    draft_dir = DRAFTS_DIR / slug
    if draft_dir.exists():
        print(f"Error: draft already exists at {draft_dir}")
        sys.exit(1)

    draft_dir.mkdir(parents=True)
    note_path = draft_dir / "note.md"
    note_path.write_text(TEMPLATE.format(title=args.title))

    print(f"Created draft: {note_path}")
    print(f"Drop screenshots into: {draft_dir}")
    print(f"When it's ready: python scripts/notes/publish_note.py {slug}")

    if not args.no_open:
        vault_q = urllib.parse.quote(OBSIDIAN_VAULT)
        file_q = urllib.parse.quote(f"{slug}/note")
        uri = f"obsidian://open?vault={vault_q}&file={file_q}"
        try:
            subprocess.run(["open", uri], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"(Couldn't open Obsidian automatically — open manually: {note_path})")


if __name__ == "__main__":
    main()
