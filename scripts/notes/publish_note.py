#!/usr/bin/env python3
"""
publish_note.py

Converts a MatSavant Note draft (markdown + frontmatter, written in
MacDown, with screenshots dropped in the same folder) into the site's
Note format and publishes it:

  - Copies referenced images into
    frontend/wrestledata-ui/public/data/notes/images/<slug>/
  - Writes frontend/wrestledata-ui/public/data/notes/body/<slug>.json
  - Adds/updates the entry in frontend/wrestledata-ui/public/data/notes/notes.json
  - Regenerates sitemap.xml (skip with --no-sitemap)

Draft format (frontend/wrestledata-ui/notes_drafts/<slug>/note.md):

    ---
    title: Oklahoma State has a 17% shot
    hook: One sentence that sells the argument
    tags: ncaa, team-race
    ---

    Paragraph text. **Bold**, *italic*, `code`, and [links](https://x.com) work.

    ![Alt text](screenshot1.png)
    *Optional caption*

    Another paragraph.

Usage:
    python scripts/notes/publish_note.py <slug>
    python scripts/notes/publish_note.py <slug> --date 2026-09-13
    python scripts/notes/publish_note.py <slug> --draft path/to/other/note.md
    python scripts/notes/publish_note.py <slug> --no-sitemap
"""

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DRAFTS_DIR = REPO_ROOT / "frontend/wrestledata-ui/notes_drafts"
PUBLIC_DIR = REPO_ROOT / "frontend/wrestledata-ui/public"
NOTES_JSON = PUBLIC_DIR / "data/notes/notes.json"
BODY_DIR = PUBLIC_DIR / "data/notes/body"
IMAGES_ROOT = PUBLIC_DIR / "data/notes/images"

IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^\s)]+)\)\s*$")
CAPTION_LINE_RE = re.compile(r"^\*([^*].*)\*$")

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"\*(.+?)\*")
CODE_RE = re.compile(r"`([^`]+?)`")


def parse_frontmatter(raw: str):
    """Split leading '---' YAML-lite frontmatter from the markdown body."""
    if not raw.startswith("---"):
        raise ValueError("Draft must start with a '---' frontmatter block")
    end = raw.find("\n---", 3)
    if end == -1:
        raise ValueError("Frontmatter block is not closed with '---'")
    fm_raw = raw[3:end].strip("\n")
    body = raw[end + 4:].lstrip("\n")

    meta = {}
    for line in fm_raw.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()

    if "tags" in meta:
        meta["tags"] = [t.strip() for t in meta["tags"].split(",") if t.strip()]
    else:
        meta["tags"] = []

    return meta, body


def render_inline(text: str) -> str:
    """Escape then apply a small safe markdown-inline subset: links, bold, italic, code."""
    escaped = html_lib.escape(text, quote=False)
    escaped = LINK_RE.sub(r'<a href="\2">\1</a>', escaped)
    escaped = BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = ITALIC_RE.sub(r"<em>\1</em>", escaped)
    escaped = CODE_RE.sub(r"<code>\1</code>", escaped)
    return escaped


def parse_body(body: str, slug: str, draft_dir: Path):
    """Walk the markdown line by line; an image line (wherever it falls,
    even mid-paragraph with no blank line around it -- common in pasted
    X-thread text) always starts its own image block."""
    lines = body.splitlines()
    blocks = []
    all_images = []
    copied_images = []
    paragraph_buf = []

    def flush_paragraph():
        if paragraph_buf:
            text = " ".join(paragraph_buf)
            blocks.append({"type": "p", "html": render_inline(text)})
            paragraph_buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        img_match = IMG_LINE_RE.match(line) if line else None
        if img_match:
            flush_paragraph()
            alt, src_ref = img_match.groups()
            caption = None
            if i + 1 < len(lines):
                cap_match = CAPTION_LINE_RE.match(lines[i + 1].strip())
                if cap_match:
                    caption = cap_match.group(1).strip()
                    i += 1

            if src_ref.startswith(("http://", "https://", "/")):
                site_src = src_ref
            else:
                # Obsidian URL-encodes spaces etc. in the link even though the
                # actual filename on disk (e.g. "Pasted image ....png") isn't.
                local_name = urllib.parse.unquote(src_ref)
                src_path = draft_dir / local_name
                if not src_path.exists():
                    raise FileNotFoundError(
                        f"Image referenced in note.md not found: {src_path}"
                    )
                dest_dir = IMAGES_ROOT / slug
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / src_path.name
                shutil.copyfile(src_path, dest_path)
                site_src = f"/data/notes/images/{slug}/{urllib.parse.quote(src_path.name)}"
                copied_images.append(site_src)

            all_images.append(site_src)
            block = {"type": "img", "src": site_src, "alt": alt}
            if caption:
                block["caption"] = caption
            blocks.append(block)
        elif line:
            paragraph_buf.append(line)
        else:
            flush_paragraph()
        i += 1

    flush_paragraph()
    return blocks, all_images, copied_images


def load_notes_json():
    if NOTES_JSON.exists():
        return json.loads(NOTES_JSON.read_text())
    return []


def upsert_note_entry(entries, entry):
    for idx, existing in enumerate(entries):
        if existing.get("slug") == entry["slug"]:
            entries[idx] = entry
            return entries
    entries.append(entry)
    return entries


def main():
    parser = argparse.ArgumentParser(description="Publish a MatSavant Note draft")
    parser.add_argument("slug", help="Draft folder name / note slug")
    parser.add_argument("--draft", help="Path to note.md (default: notes_drafts/<slug>/note.md)")
    parser.add_argument("--date", help="Publish date YYYY-MM-DD (default: today)")
    parser.add_argument("--no-sitemap", action="store_true", help="Skip sitemap regeneration")
    args = parser.parse_args()

    slug = args.slug
    draft_path = Path(args.draft) if args.draft else DRAFTS_DIR / slug / "note.md"
    draft_dir = draft_path.parent

    if not draft_path.exists():
        print(f"Error: draft not found at {draft_path}")
        sys.exit(1)

    raw = draft_path.read_text()
    meta, body = parse_frontmatter(raw)

    if "title" not in meta:
        print("Error: frontmatter must include 'title'")
        sys.exit(1)

    publish_date = args.date or meta.get("date") or date.today().isoformat()

    blocks, all_images, copied_images = parse_body(body, slug, draft_dir)

    BODY_DIR.mkdir(parents=True, exist_ok=True)
    body_path = BODY_DIR / f"{slug}.json"
    body_path.write_text(json.dumps({"slug": slug, "blocks": blocks}, indent=2) + "\n")

    entries = load_notes_json()
    entry = {
        "slug": slug,
        "title": meta["title"],
        "hook": meta.get("hook", ""),
        "date": publish_date,
        "tags": meta["tags"],
        "images": all_images[:1],
    }
    entries = upsert_note_entry(entries, entry)
    NOTES_JSON.parent.mkdir(parents=True, exist_ok=True)
    NOTES_JSON.write_text(json.dumps(entries, indent=2) + "\n")

    print(f"Wrote {body_path.relative_to(REPO_ROOT)}")
    print(f"Updated {NOTES_JSON.relative_to(REPO_ROOT)}")
    if copied_images:
        print(f"Copied {len(copied_images)} image(s) into {IMAGES_ROOT / slug}")

    if not args.no_sitemap:
        sitemap_script = REPO_ROOT / "scripts/generate_matsavant_sitemap.py"
        if sitemap_script.exists():
            subprocess.run([sys.executable, str(sitemap_script)], check=True)
        else:
            print("(sitemap script not found, skipping)")

    print(f"\nPreview locally, then check in the changed files under frontend/wrestledata-ui/public/")
    print(f"Live URL once deployed: /notes/note.html?slug={slug}")


if __name__ == "__main__":
    main()
