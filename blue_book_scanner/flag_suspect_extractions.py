#!/usr/bin/env python3
"""
Flag cases where the LLM-extracted text or JSON metadata likely disagrees
with the source PDF. Produces a ranked CSV of suspects for re-extraction.

Signals:
  A  witness count outlier (>=1000)
  B  JSON witness count not groundable in text_content
  C  duration mismatch between summary/JSON and ATIC form line
  D  very short text_content (truncated extraction)
  E  heavy LLM hedging / uncertainty markers
  F  JSON location disagrees with filename location
  G  sighted_object contradicts NUMBER OF OBJECTS line
"""
import argparse
import csv
import json
import re
from pathlib import Path

DEFAULT_TXT_DIR = Path("/Users/foster/git/blue_book_searcher/casefiles/txt")
DEFAULT_JSON_DIR = Path("/Users/foster/git/blue_book_searcher/casefiles/json")
DEFAULT_PDF_ROOT = Path("/Volumes/Expansion/data")
DEFAULT_OUT = Path(__file__).parent.parent / "suspect_cases.csv"

HEDGE_PATTERNS = [
    r"\bI cannot\b", r"\billegible\b", r"\bunclear\b", r"\bhard to read\b",
    r"\bappears to be\b", r"\bseems to\b", r"\blikely\b",
    r"\b\[illegible\]\b", r"\b\?{2,}\b",
]
HEDGE_RE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)


def pdf_path_for(fname: str, pdf_root: Path) -> str:
    """Resolve filename like 1962-07-8681154-WestoverAFB-Massachusetts.txt to pdf path."""
    stem = fname.replace(".txt", "")
    year = stem.split("-", 1)[0]
    try:
        decade = f"{year[:3]}0s"
    except Exception:
        decade = "19XXs"
    candidate = pdf_root / decade / f"{stem}.pdf"
    if candidate.exists():
        return str(candidate)
    for d in ("1940s", "1950s", "1960s", "19XXs"):
        c = pdf_root / d / f"{stem}.pdf"
        if c.exists():
            return str(c)
    return ""


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
    except Exception:
        pass
    return {}


def extract_duration_seconds(s: str) -> float | None:
    """Find first duration phrase and convert to seconds."""
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(sec|second|min|minute|hour|hr)s?\b",
                  s, re.IGNORECASE)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("sec"):
        return n
    if unit.startswith("min"):
        return n * 60
    return n * 3600


def witness_groundable(count: int, text: str) -> bool:
    """Does the witness number appear near a witness-y word in the text?"""
    variants = {str(count), f"{count:,}"}
    if count >= 1000:
        variants.add(f"{count // 1000},{count % 1000:03d}")
    for v in variants:
        if v in text:
            return True
    return False


def score_case(fname: str, text: str, meta: dict) -> tuple[int, list[str]]:
    reasons = []
    score = 0

    # A: witness outlier
    w = meta.get("number of confirmed witnesses")
    if isinstance(w, str):
        m = re.search(r"\d+", w)
        w = int(m.group()) if m else None
    if isinstance(w, int) and w >= 1000:
        score += 2
        reasons.append(f"A:witnesses={w}")

    # B: witness count not groundable in text
    if isinstance(w, int) and w >= 10 and not witness_groundable(w, text):
        score += 3
        reasons.append(f"B:witnesses_{w}_not_in_text")

    # C: duration mismatch between summary and form line
    summary = meta.get("main event", "") + " " + meta.get("interesting points", "")
    meta_dur = extract_duration_seconds(summary)
    form_match = re.search(
        r"LENGTH OF OBSERVATION[:\s]*([^\n]+)", text, re.IGNORECASE
    )
    form_dur = extract_duration_seconds(form_match.group(1)) if form_match else None
    if meta_dur and form_dur and max(meta_dur, form_dur) / max(min(meta_dur, form_dur), 0.1) >= 5:
        score += 2
        reasons.append(f"C:dur_meta={meta_dur}s_vs_form={form_dur}s")

    # D: short text
    if len(text) < 400:
        score += 2
        reasons.append(f"D:text_len={len(text)}")

    # E: heavy hedging
    hedges = len(HEDGE_RE.findall(text))
    if hedges >= 6:
        score += 1
        reasons.append(f"E:hedges={hedges}")

    # F: filename location vs JSON location
    parts = fname.replace(".txt", "").split("-")
    fn_loc = " ".join(p for p in parts[3:] if p and not p.isdigit()).lower()
    json_loc = (meta.get("location") or "").lower()
    if fn_loc and json_loc:
        fn_tokens = {t for t in re.findall(r"[a-z]+", fn_loc) if len(t) >= 4}
        if fn_tokens and not any(t in json_loc for t in fn_tokens):
            score += 1
            reasons.append("F:location_mismatch")

    # G: sighted_object vs NUMBER OF OBJECTS line
    obj = (meta.get("sighted object") or "").lower()
    num_match = re.search(r"NUMBER OF OBJECTS[:\s]*([^\n]+)", text, re.IGNORECASE)
    if obj and num_match:
        form_num = num_match.group(1).strip().lower()
        if "one" in form_num and re.search(r"\b(two|three|four|many|multiple|several)\b", obj):
            score += 2
            reasons.append(f"G:form='one'_vs_obj='{obj[:40]}'")

    return score, reasons


def main():
    parser = argparse.ArgumentParser(description="Flag suspect LLM extractions.")
    parser.add_argument("--txt-dir", type=Path, default=DEFAULT_TXT_DIR)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-score", type=int, default=1)
    args = parser.parse_args()

    rows = []
    for txt_file in sorted(args.txt_dir.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8", errors="replace")
        meta = load_json(args.json_dir / (txt_file.name + ".json"))
        score, reasons = score_case(txt_file.name, text, meta)
        if score >= args.min_score:
            rows.append({
                "score": score,
                "case": txt_file.name,
                "reasons": "; ".join(reasons),
                "pdf": pdf_path_for(txt_file.name, args.pdf_root),
            })

    rows.sort(key=lambda r: (-r["score"], r["case"]))

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["score", "case", "reasons", "pdf"])
        w.writeheader()
        w.writerows(rows)

    print(f"Total flagged: {len(rows)}")
    print("Score distribution:")
    from collections import Counter
    for s, n in sorted(Counter(r["score"] for r in rows).items(), reverse=True):
        print(f"  score {s}: {n}")
    print("\nTop 10 suspects:")
    for r in rows[:10]:
        print(f"  [{r['score']}] {r['case']}")
        print(f"       {r['reasons']}")
    print(f"\nWritten: {args.out}")


if __name__ == "__main__":
    main()
