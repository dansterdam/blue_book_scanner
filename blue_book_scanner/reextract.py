#!/usr/bin/env python3
"""
Re-extract flagged suspect cases using Claude vision, writing per-page .txt files
directly into the scanned/ directory tree — same layout as vision.py, so the
normal combine_pages → full_case_set pipeline picks them up automatically.

Output path per page:
    {scanned_root}/{decade}_scanned/{casename}.pdf{N}.txt

Where decade is derived from the case filename year (e.g. "1950s").

Idempotent by default: skips pages whose output file already exists.
Pass --overwrite to force re-extraction.

Usage:
    python reextract.py \\
        --keyfile api_key.json \\
        --pdf-root /Volumes/Expansion/data \\
        --scanned-root /path/to/blue_book_scanner/data/scanned \\
        --min-score 3

    python reextract.py --keyfile api_key.json --only 1962-07-8681154-WestoverAFB-Massachusetts.txt
"""
import argparse
import base64
import concurrent.futures
import csv
import io
import json
import os
import re
from pathlib import Path
from time import sleep

import anthropic
import PyPDF2
from pdf2image import convert_from_path
from PIL import Image

from prompts import OCR_PROMPT

REPO = Path(__file__).parent.parent
DEFAULT_SUSPECTS = REPO / "suspect_cases.csv"
DEFAULT_PDF_ROOT = Path("/Volumes/Expansion/data")
DEFAULT_SCANNED_ROOT = REPO / "data" / "scanned"


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

def encode_pdf_page(pdf_path: Path, page_number: int, dpi: int = 150, max_width: int = 2048) -> str:
    """Convert a single PDF page to a base64-encoded JPEG."""
    pages = convert_from_path(str(pdf_path), first_page=page_number, last_page=page_number, dpi=dpi)
    img = pages[0]
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def page_count(pdf_path: Path) -> int:
    with open(pdf_path, "rb") as f:
        return len(PyPDF2.PdfReader(f).pages)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def call_with_retry(fn, *, max_retries: int = 4, base_delay: float = 4.0):
    for attempt in range(max_retries):
        try:
            return fn()
        except anthropic.RateLimitError:
            sleep(base_delay * (2 ** attempt))
        except anthropic.APIStatusError as e:
            if e.status_code in (500, 502, 503, 529):
                sleep(base_delay * (2 ** attempt))
            else:
                raise
    raise RuntimeError("exceeded retries")


def ocr_page(client, model: str, b64_image: str, filename_hint: str) -> str:
    """Send one page image to the API and return the transcribed text."""
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=4000,
            system=[{"type": "text", "text": OCR_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_image},
                    },
                    {
                        "type": "text",
                        "text": f"Filename (for context only): {filename_hint}",
                    },
                ],
            }],
        )
    resp = call_with_retry(_call)
    return resp.content[0].text.strip()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def decade_for(casename: str) -> str:
    """Return e.g. '1950s' from a case filename like '1952-04-...'."""
    year_str = casename.split("-", 1)[0]
    try:
        decade = f"{year_str[:3]}0s"
        if decade[0].isdigit():
            return decade
    except Exception:
        pass
    return "19XXs"


def scanned_subdir(scanned_root: Path, casename: str) -> Path:
    """Return the decade subdir, falling back to 19XXs if it doesn't exist."""
    decade = decade_for(casename)
    candidate = scanned_root / f"{decade}_scanned"
    if candidate.exists():
        return candidate
    fallback = scanned_root / "19XXs_scanned"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def pdf_path_for(casename: str, pdf_root: Path) -> Path | None:
    """Locate the source PDF under pdf_root."""
    stem = casename.replace(".txt", "")
    decade = decade_for(stem)
    candidate = pdf_root / decade / f"{stem}.pdf"
    if candidate.exists():
        return candidate
    for d in ("1940s", "1950s", "1960s", "19XXs"):
        c = pdf_root / d / f"{stem}.pdf"
        if c.exists():
            return c
    return None


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def reextract_case(case_fname: str, pdf_path: Path, client, model: str,
                   scanned_root: Path, overwrite: bool = True,
                   dpi: int = 150) -> dict:
    """
    Re-extract one case: one API call per page, write to scanned/<decade>_scanned/.
    Returns a status dict.
    """
    stem = case_fname.replace(".txt", "")
    out_dir = scanned_subdir(scanned_root, stem)

    if not pdf_path.exists():
        return {"case": case_fname, "status": f"missing pdf: {pdf_path}"}

    n_pages = page_count(pdf_path)

    def _do_page(page_num):
        """Process a single page; returns (page_num, status_str)."""
        out_file = out_dir / f"{stem}.pdf{page_num}.txt"
        if out_file.exists() and not overwrite:
            return page_num, "skipped"
        try:
            b64 = encode_pdf_page(pdf_path, page_num, dpi=dpi)
            text = ocr_page(client, model, b64, f"{stem}.pdf{page_num}.txt")
            out_file.write_text(text, encoding="utf-8")
            return page_num, "ok"
        except Exception as e:
            return page_num, f"error: {e}"

    # Process pages in parallel (inner pool, 3 threads per case)
    page_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_do_page, p): p for p in range(1, n_pages + 1)}
        for fut in concurrent.futures.as_completed(futures):
            page_num, status = fut.result()
            page_results[page_num] = status

    errors = [f"p{p}:{s}" for p, s in sorted(page_results.items()) if s.startswith("error")]
    skipped = sum(1 for s in page_results.values() if s == "skipped")
    done = sum(1 for s in page_results.values() if s == "ok")

    overall = "ok"
    if errors:
        overall = "partial" if done > 0 else "error"
    elif skipped == n_pages:
        overall = "skipped (all pages exist)"

    return {
        "case": case_fname,
        "status": overall,
        "pages": n_pages,
        "done": done,
        "skipped": skipped,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_suspects(csv_path: Path, min_score: int, only: str | None, limit: int | None):
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    if only:
        rows = [r for r in rows if r["case"] == only]
    else:
        rows = [r for r in rows if int(r["score"]) >= min_score]
    rows = [r for r in rows if r.get("pdf", "")]
    if limit:
        rows = rows[:limit]
    return rows


def build_skip_set(skip_dirs: list[Path]) -> set[str]:
    """Return set of case filenames already present in any of the given dirs."""
    done = set()
    for d in skip_dirs:
        if d.exists():
            done.update(os.listdir(d))
    return done


def main():
    p = argparse.ArgumentParser(
        description="Re-extract Blue Book suspects; overwrites scanned/ per-page txts."
    )
    p.add_argument("--keyfile", required=True, type=Path, help="JSON file with API key")
    p.add_argument("--suspects", type=Path, default=DEFAULT_SUSPECTS)
    p.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT,
                   help="Root dir containing 1940s/, 1950s/, etc. subdirs with PDFs")
    p.add_argument("--scanned-root", type=Path, default=DEFAULT_SCANNED_ROOT,
                   help="Root dir containing 1940s_scanned/, etc. subdirs")
    p.add_argument("--skip-if-in", nargs="+", type=Path, metavar="DIR",
                   help="Skip cases whose filename already appears in these dirs "
                        "(e.g. reextracted_claude/txt or a --done-dir). Can pass multiple dirs.")
    p.add_argument("--done-dir", type=Path, metavar="DIR",
                   help="After each successful case, write a marker file here so future "
                        "runs can skip it via --skip-if-in. Created automatically if needed.")
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--dpi", type=int, default=150,
                   help="DPI for PDF→image conversion (150 is safe; 300 may OOM)")
    p.add_argument("--min-score", type=int, default=3)
    p.add_argument("--only", help="Process only this specific case filename")
    p.add_argument("--limit", type=int, help="Cap number of cases")
    p.add_argument("--workers", type=int, default=2, help="Parallel cases")
    p.add_argument("--overwrite", action="store_true", default=True,
                   help="Overwrite existing page files (default: True for re-extraction)")
    p.add_argument("--no-overwrite", dest="overwrite", action="store_false",
                   help="Skip pages that already have output files")
    args = p.parse_args()

    keys = json.loads(args.keyfile.read_text())
    # Support both field names
    api_key = keys.get("dontuse") or keys.get("anthropic_api_key")
    if not api_key:
        raise ValueError(f"No API key found in {args.keyfile} (tried 'dontuse', 'anthropic_api_key')")
    client = anthropic.Anthropic(api_key=api_key)

    # Set up done-dir if requested
    done_dir = args.done_dir
    if done_dir:
        done_dir.mkdir(parents=True, exist_ok=True)
        # Auto-include done_dir in the skip set
        skip_dirs = list(args.skip_if_in or []) + [done_dir]
    else:
        skip_dirs = list(args.skip_if_in or [])

    # Build skip set from any --skip-if-in dirs (+ done_dir)
    already_done = build_skip_set(skip_dirs)
    if already_done:
        print(f"Skipping {len(already_done)} cases already found in: "
              f"{[str(d) for d in skip_dirs]}")

    suspects = load_suspects(args.suspects, args.min_score, args.only, args.limit)

    # Filter out already-done cases BEFORE applying --limit so limit means "N new cases"
    if already_done:
        before = len(suspects)
        suspects = [r for r in suspects if r["case"] not in already_done]
        print(f"  {before - len(suspects)} skipped, {len(suspects)} remaining")

    print(f"Re-extracting {len(suspects)} cases → {args.scanned_root}")
    print(f"Model: {args.model}  DPI: {args.dpi}  Workers: {args.workers}  Overwrite: {args.overwrite}")
    print()

    # Resolve PDF paths at load time
    cases = []
    for r in suspects:
        pdf = pdf_path_for(r["case"], args.pdf_root)
        if pdf is None:
            print(f"  [skip] no PDF found for {r['case']}")
            continue
        cases.append((r["case"], pdf))

    print(f"  {len(cases)} cases with PDFs found\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                reextract_case,
                case_fname, pdf, client, args.model,
                args.scanned_root, args.overwrite, args.dpi
            ): case_fname
            for case_fname, pdf in cases
        }
        done_count = 0
        for fut in concurrent.futures.as_completed(futures):
            case_fname = futures[fut]
            try:
                result = fut.result()
                done_count += 1
                errs = f"  ERRORS: {result['errors']}" if result.get("errors") else ""
                print(f"[{done_count:>3}/{len(cases)}] {result['status']:30s} {case_fname}{errs}")
                # Write marker so future runs can skip this case
                if done_dir and not result.get("errors"):
                    (done_dir / case_fname).write_text("")
            except Exception as e:
                print(f"[ERR] {case_fname}: {e}")

    print(f"\nDone. Output in {args.scanned_root}")


if __name__ == "__main__":
    main()
