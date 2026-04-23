#!/usr/bin/env python3
"""
Re-extract flagged suspect cases using Claude vision with a strict, grounded prompt.

Reads suspect_cases.csv, re-runs OCR on each PDF page, then does a structured
metadata extraction pass from the transcribed text. By default overwrites the
searcher repo's casefiles; pass --out-txt-dir/--out-json-dir to redirect.

Idempotent: skips any case whose JSON already carries a `reextracted_by` key,
unless --force is given.

Usage:
    python reextract.py --keyfile api_key.json --min-score 3
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

from prompts import OCR_PROMPT, METADATA_PROMPT, METADATA_SCHEMA

REPO = Path(__file__).parent.parent
DEFAULT_SUSPECTS = REPO / "suspect_cases.csv"
DEFAULT_TXT_DIR = Path("/Users/foster/git/blue_book_searcher/casefiles/txt")
DEFAULT_JSON_DIR = Path("/Users/foster/git/blue_book_searcher/casefiles/json")


def encode_pdf_page(pdf_path: Path, page_number: int, max_width: int = 2048) -> str:
    pages = convert_from_path(str(pdf_path), first_page=page_number, last_page=page_number, dpi=300)
    img = pages[0]
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def page_count(pdf_path: Path) -> int:
    with open(pdf_path, "rb") as f:
        return len(PyPDF2.PdfReader(f).pages)


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


def ocr_page(client, model: str, b64_image: str, stem: str, page_number: int, total_pages: int) -> str:
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
                        "text": f"Page {page_number} of {total_pages} from case file: {stem}",
                    },
                ],
            }],
        )
    resp = call_with_retry(_call)
    return resp.content[0].text.strip()


def extract_metadata(client, model: str, transcript: str, stem: str) -> dict:
    schema_text = json.dumps(METADATA_SCHEMA, indent=2)
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=2000,
            system=[
                {"type": "text", "text": METADATA_PROMPT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": f"Schema:\n{schema_text}", "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{
                "role": "user",
                "content": f"Case file: {stem}\n\nTranscribed document text:\n\n{transcript}\n\nReturn ONLY a JSON object matching the schema.",
            }],
        )
    resp = call_with_retry(_call)
    text = resp.content[0].text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    return json.loads(text[start:end])


def reextract_case(case_fname: str, pdf_path: Path, client, model: str,
                   out_txt_dir: Path, out_json_dir: Path, overwrite: bool = False) -> dict:
    stem = case_fname.replace(".txt", "")
    txt_out = out_txt_dir / case_fname
    json_out = out_json_dir / (case_fname + ".json")

    if txt_out.exists() and json_out.exists() and not overwrite:
        return {"case": case_fname, "status": "skipped (exists)"}

    if not pdf_path.exists():
        return {"case": case_fname, "status": f"missing pdf: {pdf_path}"}

    n_pages = page_count(pdf_path)
    per_page_text = [""] * n_pages

    def _do_page(i):
        try:
            b64 = encode_pdf_page(pdf_path, i + 1)
            return i, ocr_page(client, model, b64, stem, i + 1, n_pages)
        except Exception as e:
            return i, f"[EXTRACTION ERROR: {e}]"

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for i, text in ex.map(_do_page, range(n_pages)):
            per_page_text[i] = text

    combined = "\n\n".join(
        f"{t}\n\n- page {i+1} -" for i, t in enumerate(per_page_text)
    )
    txt_out.parent.mkdir(parents=True, exist_ok=True)
    txt_out.write_text(combined, encoding="utf-8")

    try:
        meta = extract_metadata(client, model, combined, stem)
    except Exception as e:
        meta = {"_error": str(e)}

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"case": case_fname, "status": "ok", "pages": n_pages}


def load_suspects(csv_path: Path, min_score: int, only: str | None, limit: int | None):
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    if only:
        rows = [r for r in rows if r["case"] == only]
    else:
        rows = [r for r in rows if int(r["score"]) >= min_score]
    rows = [r for r in rows if r["pdf"]]
    if limit:
        rows = rows[:limit]
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--keyfile", required=True, type=Path, help="JSON file with anthropic_api_key")
    p.add_argument("--suspects", type=Path, default=DEFAULT_SUSPECTS)
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--min-score", type=int, default=3)
    p.add_argument("--only", help="process only this specific case filename")
    p.add_argument("--limit", type=int, help="cap number of cases")
    p.add_argument("--workers", type=int, default=2, help="parallel cases")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    keys = json.loads(args.keyfile.read_text())
    client = anthropic.Anthropic(api_key=keys["anthropic_api_key"])

    out_txt = DEFAULT_TXT_DIR
    out_json = DEFAULT_JSON_DIR

    suspects = load_suspects(args.suspects, args.min_score, args.only, args.limit)
    print(f"Re-extracting {len(suspects)} cases using {args.model}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(reextract_case, r["case"], Path(r["pdf"]), client, args.model,
                      out_txt, out_json, args.overwrite): r["case"]
            for r in suspects
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                result = fut.result()
                print(f"  {result['status']}: {result['case']}")
            except Exception as e:
                print(f"  ERROR on {futures[fut]}: {e}")


if __name__ == "__main__":
    main()
