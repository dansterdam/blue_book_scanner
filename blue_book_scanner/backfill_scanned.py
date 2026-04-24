#!/usr/bin/env python3
"""
Backfill scanned/ from already-reextracted combined txt files.

Reads combined case files from reextracted_claude/txt/ (and optionally other
reextracted dirs), splits them on their '- page N -' markers, and overwrites
the corresponding per-page files in scanned/{decade}_scanned/.

Handles marker variants:
  - page 5 -                  → writes page 5
  - pages 3 and 7 -           → writes pages 3 and 7
  - pages 14-18 -             → writes pages 14, 15, 16, 17, 18
  - page 1 (MISSING ...) -    → skipped (no content to write)

Usage:
    python backfill_scanned.py --scanned-root ../data/scanned
    python backfill_scanned.py --scanned-root ../data/scanned --dry-run
    python backfill_scanned.py --scanned-root ../data/scanned \\
        --reextracted-dirs ../data/reextracted_claude/txt
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
DEFAULT_SCANNED_ROOT = REPO / "data" / "scanned"
DEFAULT_REEXTRACTED_DIRS = [
    REPO / "data" / "reextracted_claude" / "txt",
]

# Matches any '- page(s) ... -' line (with optional trailing annotation)
PAGE_MARKER_RE = re.compile(r"^-\s+pages?\s+(.+?)\s+-\s*$", re.IGNORECASE)


def parse_page_numbers(marker_content: str) -> list[int]:
    """
    Extract all page numbers from a marker content string.
    Examples:
      '5'          → [5]
      '3 and 7'    → [3, 7]
      '14-18'      → [14, 15, 16, 17, 18]
      '2, 4'       → [2, 4]
      '1 (MISSING from file)'  → []  (skip missing)
    """
    # Skip markers that explicitly indicate missing/absent content
    if re.search(r"\b(missing|absent|not present|not in file)\b", marker_content, re.IGNORECASE):
        return []

    # Strip trailing annotations in parens: "2 (UNRELATED)" → "2"
    cleaned = re.sub(r"\(.*?\)", "", marker_content).strip()

    pages = []

    # Handle ranges: "14-18"
    range_m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", cleaned)
    if range_m:
        start, end = int(range_m.group(1)), int(range_m.group(2))
        return list(range(start, end + 1))

    # Handle "N and M" or "N, M" or just "N"
    for tok in re.split(r"[,\s]+(?:and\s+)?", cleaned):
        tok = tok.strip()
        if tok.isdigit():
            pages.append(int(tok))

    return pages


def decade_for(casename: str) -> str:
    year_str = casename.split("-", 1)[0]
    try:
        decade = f"{year_str[:3]}0s"
        if decade[0].isdigit():
            return decade
    except Exception:
        pass
    return "19XXs"


def scanned_subdir(scanned_root: Path, casename: str) -> Path | None:
    decade = decade_for(casename)
    candidate = scanned_root / f"{decade}_scanned"
    if candidate.exists():
        return candidate
    # Try fallback
    fallback = scanned_root / "19XXs_scanned"
    if fallback.exists():
        return fallback
    return None


def split_combined_file(text: str) -> list[tuple[list[int], str]]:
    """
    Split a combined case file into (page_numbers, content) pairs.
    Content comes *before* each marker, so we accumulate lines until a marker.
    Returns list of (page_list, content_str) — page_list may be empty for MISSING.
    """
    lines = text.splitlines()
    sections = []
    current_lines: list[str] = []

    for line in lines:
        m = PAGE_MARKER_RE.match(line.strip())
        if m:
            page_nums = parse_page_numbers(m.group(1))
            content = "\n".join(current_lines).strip()
            sections.append((page_nums, content))
            current_lines = []
        else:
            current_lines.append(line)

    # Trailing content after last marker (shouldn't normally exist, but handle it)
    trailing = "\n".join(current_lines).strip()
    if trailing:
        # Attach to last section's pages if possible, otherwise note it
        if sections:
            last_pages, last_content = sections[-1]
            sections[-1] = (last_pages, (last_content + "\n\n" + trailing).strip())
        else:
            sections.append(([], trailing))  # no marker at all — single-section file

    return sections


def backfill_case(combined_path: Path, scanned_root: Path, dry_run: bool) -> dict:
    casename = combined_path.name  # e.g. '1952-04-6313725-Fargo-NorthDakota.txt'
    stem = casename.replace(".txt", "")

    out_dir = scanned_subdir(scanned_root, stem)
    if out_dir is None:
        return {"case": casename, "status": "error: scanned subdir not found", "written": 0, "skipped": 0}

    text = combined_path.read_text(encoding="utf-8", errors="replace")
    sections = split_combined_file(text)

    written = 0
    skipped_missing = 0
    files_written = []

    for page_nums, content in sections:
        if not page_nums:
            skipped_missing += 1
            continue
        for pg in page_nums:
            out_file = out_dir / f"{stem}.pdf{pg}.txt"
            if not dry_run:
                out_file.write_text(content, encoding="utf-8")
            files_written.append(out_file.name)
            written += 1

    return {
        "case": casename,
        "status": "dry-run" if dry_run else "ok",
        "written": written,
        "skipped_missing": skipped_missing,
        "files": files_written,
    }


def main():
    p = argparse.ArgumentParser(
        description="Backfill scanned/ per-page txts from combined reextracted files."
    )
    p.add_argument(
        "--reextracted-dirs", nargs="+", type=Path,
        default=DEFAULT_REEXTRACTED_DIRS,
        help="One or more dirs containing combined case .txt files (default: reextracted_claude/txt)",
    )
    p.add_argument(
        "--scanned-root", type=Path, default=DEFAULT_SCANNED_ROOT,
        help="Root dir containing 1940s_scanned/, 1950s_scanned/, etc.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching any files",
    )
    p.add_argument(
        "--only", metavar="CASENAME",
        help="Process only this case filename",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print every file written",
    )
    args = p.parse_args()

    all_files: list[Path] = []
    for d in args.reextracted_dirs:
        if not d.exists():
            print(f"[warn] directory not found, skipping: {d}", file=sys.stderr)
            continue
        files = sorted(d.glob("*.txt"))
        if args.only:
            files = [f for f in files if f.name == args.only]
        all_files.extend(files)

    if not all_files:
        print("No files found. Check --reextracted-dirs.")
        sys.exit(1)

    print(f"Backfilling {len(all_files)} case(s) → {args.scanned_root}")
    if args.dry_run:
        print("  [DRY RUN — no files will be written]")
    print()

    total_written = 0
    total_skipped = 0

    for combined_path in all_files:
        result = backfill_case(combined_path, args.scanned_root, args.dry_run)
        total_written += result["written"]
        total_skipped += result["skipped_missing"]

        status_str = f"→ {result['written']} page files"
        if result["skipped_missing"]:
            status_str += f"  ({result['skipped_missing']} MISSING sections skipped)"
        print(f"  {result['status']:8s}  {result['case']}  {status_str}")

        if args.verbose and result.get("files"):
            for f in result["files"]:
                print(f"             {f}")

    print(f"\nTotal page files {'would write' if args.dry_run else 'written'}: {total_written}")
    if total_skipped:
        print(f"Total MISSING sections skipped: {total_skipped}")


if __name__ == "__main__":
    main()
