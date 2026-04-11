#!/usr/bin/env python3
"""
career-ops → AIHawk Bridge
===========================
Reads aihawk-queue.json (produced by export-aihawk.mjs), sets up AIHawk's
data_folder with the tailored resume from career-ops, writes a consolidated
job queue for AIHawk plugins, and optionally invokes AIHawk's main.py.

After AIHawk runs, use --sync-back to write Applied status back to career-ops'
batch/tracker-additions/ directory (run `node merge-tracker.mjs` there to apply).

Usage:
    python bridge.py
    python bridge.py --queue aihawk-queue.json --aihawk-dir ../AIHawk --dry-run
    python bridge.py --sync-back

Required:
    pip install pyyaml
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path


# ── Schema version this bridge understands ────────────────────────────────────
SUPPORTED_SCHEMA = "1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_queue(queue_path: Path) -> dict:
    """Load and validate the aihawk-queue.json produced by export-aihawk.mjs."""
    if not queue_path.exists():
        print(f"❌  Queue not found: {queue_path}")
        print("    Run:  node export-aihawk.mjs")
        sys.exit(1)

    with open(queue_path) as f:
        queue = json.load(f)

    schema = queue.get("schema_version", "unknown")
    if schema != SUPPORTED_SCHEMA:
        print(f"⚠️  Schema version mismatch: queue={schema}, bridge={SUPPORTED_SCHEMA}")
        print("    Proceeding anyway — update bridge.py if issues arise.")

    return queue


def prepare_resume(job: dict, aihawk_dir: Path) -> Path | None:
    """
    Copy the career-ops tailored PDF into AIHawk's data_folder/output/.
    Returns the destination path, or None if no PDF is available.
    """
    data_folder = aihawk_dir / "data_folder"
    output_folder = data_folder / "output"
    output_folder.mkdir(parents=True, exist_ok=True)

    pdf_src = job.get("pdfPath")
    if pdf_src and Path(pdf_src).exists():
        slug = job["company"].lower().replace(" ", "_")
        dest = output_folder / f"resume_{job['id']}_{slug}.pdf"
        shutil.copy2(pdf_src, dest)
        return dest

    # Fallback: check if plain_text_resume.yaml exists in data_folder
    fallback = data_folder / "plain_text_resume.yaml"
    if fallback.exists():
        return fallback

    return None


def build_aihawk_job_entry(job: dict, resume_path: Path | None) -> dict:
    """
    Map a career-ops job dict to AIHawk's Job dataclass fields.

    career-ops field  →  AIHawk Job field
    ─────────────────────────────────────
    role              →  role
    company           →  company
    jobUrl            →  link
    (not available)   →  location      (left empty — AIHawk fills from listing)
    (not available)   →  apply_method  (set to "direct" for non-LinkedIn)
    pdfPath           →  resume_path
    notes             →  description   (brief stand-in until AIHawk scrapes full JD)
    """
    return {
        "id":           job["id"],
        "role":         job["role"],
        "company":      job["company"],
        "location":     "",                          # AIHawk scrapes this from the URL
        "link":         job.get("jobUrl") or "",
        "apply_method": "direct",                    # override to "linkedin" for Easy Apply jobs
        "description":  job.get("notes") or "",
        "resume_path":  str(resume_path) if resume_path else "",
        "cover_letter_path": "",                     # bridge doesn't generate cover letters
        # career-ops metadata (non-standard, for plugin use)
        "_score":       job["score"],
        "_date":        job["date"],
        "_career_ops_id": job["id"],
        "_report_path": job.get("reportPath") or "",
    }


def write_aihawk_queue(jobs_meta: list[dict], aihawk_dir: Path) -> Path:
    """
    Write career_ops_queue.json into AIHawk's data_folder.
    Custom AIHawk plugins/forks read this to drive form-filling.
    """
    out_path = aihawk_dir / "data_folder" / "career_ops_queue.json"
    payload = {
        "schema_version": SUPPORTED_SCHEMA,
        "generated_at":   datetime.utcnow().isoformat() + "Z",
        "total":          len(jobs_meta),
        "jobs":           jobs_meta,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def write_tracker_tsv(job: dict, career_ops_dir: Path, status: str = "Applied") -> Path:
    """
    Write a TSV tracker-addition file back into career-ops' pipeline.
    career-ops' merge-tracker.mjs will merge it into applications.md.

    TSV column order (per career-ops CLAUDE.md):
        num  date  company  role  status  score  pdf  report  notes
    """
    tsv_dir = career_ops_dir / "batch" / "tracker-additions"
    tsv_dir.mkdir(parents=True, exist_ok=True)

    today     = date.today().strftime("%Y-%m-%d")
    num       = job["id"]
    slug      = job["company"].lower().replace(" ", "-")
    score_str = f"{job['score']}/5"
    pdf_emoji = "✅" if job.get("hasPdf") else "❌"
    report    = f"[{num}](reports/{num}-{slug}-{job['date']}.md)"
    note      = f"Submitted via AIHawk bridge on {today}"

    row = "\t".join([num, today, job["company"], job["role"],
                     status, score_str, pdf_emoji, report, note])

    tsv_path = tsv_dir / f"{num}-{slug}-aihawk.tsv"
    tsv_path.write_text(row + "\n", encoding="utf-8")
    return tsv_path


def invoke_aihawk(aihawk_dir: Path, dry_run: bool = False) -> int:
    """Launch AIHawk's main.py as a subprocess."""
    cmd = [sys.executable, "main.py"]
    if dry_run:
        print(f"   [dry-run] Would run: {' '.join(cmd)}  (cwd={aihawk_dir})")
        return 0
    result = subprocess.run(cmd, cwd=str(aihawk_dir))
    return result.returncode


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="career-ops → AIHawk bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run (review step before submitting):
  python bridge.py --dry-run

  # Real run + write Applied status back to career-ops:
  python bridge.py --sync-back

  # Custom paths:
  python bridge.py --aihawk-dir ~/repos/AIHawk --career-ops-dir ~/repos/career-ops
""",
    )
    parser.add_argument("--queue",           default="aihawk-queue.json",
                        help="Path to aihawk-queue.json  (default: ./aihawk-queue.json)")
    parser.add_argument("--aihawk-dir",      default="../Jobs_Applier_AI_Agent_AIHawk",
                        help="Path to AIHawk repo root")
    parser.add_argument("--career-ops-dir",  default="../career-ops",
                        help="Path to career-ops repo root")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Set up files and print commands, but don't invoke AIHawk")
    parser.add_argument("--sync-back",       action="store_true",
                        help="Write Applied status back to career-ops after AIHawk runs")
    parser.add_argument("--status",          default="Applied",
                        help="Status to write back (default: Applied)")
    args = parser.parse_args()

    aihawk_dir     = Path(args.aihawk_dir).expanduser().resolve()
    career_ops_dir = Path(args.career_ops_dir).expanduser().resolve()
    queue_path     = Path(args.queue).resolve()

    # ── Validate ──────────────────────────────────────────────────────────────
    if not aihawk_dir.exists():
        print(f"❌  AIHawk directory not found: {aihawk_dir}")
        print("    Clone it: git clone https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk")
        sys.exit(1)

    queue  = load_queue(queue_path)
    jobs   = queue.get("jobs", [])

    if not jobs:
        print("⚠️  Queue is empty. Run `node export-aihawk.mjs` first.")
        sys.exit(0)

    print(f"📋  career-ops queue: {len(jobs)} job(s)  (exported {queue.get('exported_at', '?')})")
    print(f"📁  AIHawk dir:       {aihawk_dir}")
    print(f"📁  career-ops dir:   {career_ops_dir}\n")

    # ── Prepare each job ──────────────────────────────────────────────────────
    jobs_meta = []
    missing_urls = []

    for job in jobs:
        print(f"  → [{job['id']}] {job['company']} — {job['role']}  ({job['score']}/5)")

        resume_path = prepare_resume(job, aihawk_dir)
        if resume_path:
            print(f"       resume  : {resume_path.name}")
        else:
            print("       resume  : ⚠️  none found — AIHawk will need one in data_folder/")

        if job.get("jobUrl"):
            print(f"       job URL : {job['jobUrl']}")
        else:
            print("       job URL : ⚠️  not found in report — fill in manually")
            missing_urls.append(job)

        entry = build_aihawk_job_entry(job, resume_path)
        jobs_meta.append(entry)

    # ── Write consolidated queue for AIHawk ───────────────────────────────────
    queue_out = write_aihawk_queue(jobs_meta, aihawk_dir)
    print(f"\n✅  Wrote AIHawk queue → {queue_out}")

    if missing_urls:
        print(f"\n⚠️  {len(missing_urls)} job(s) missing URLs. Add them to the queue JSON or")
        print("    ensure reports contain a **URL:** field before running AIHawk.")

    # ── Invoke AIHawk ─────────────────────────────────────────────────────────
    print(f"\n{'🔍 Dry run — ' if args.dry_run else ''}🚀 Invoking AIHawk main.py ...")
    rc = invoke_aihawk(aihawk_dir, dry_run=args.dry_run)

    # ── Sync status back ──────────────────────────────────────────────────────
    if args.sync_back and not args.dry_run:
        if rc == 0:
            print(f"\n🔄  Syncing '{args.status}' status back to career-ops ...")
            for job in jobs:
                tsv = write_tracker_tsv(job, career_ops_dir, status=args.status)
                print(f"    wrote {tsv.name}")
            print("\n    Run in career-ops:  node merge-tracker.mjs")
        else:
            print(f"\n⚠️  AIHawk exited with code {rc} — skipping sync-back.")

    print(f"\n{'✅  Done' if rc == 0 else f'❌  AIHawk exited with code {rc}'}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
