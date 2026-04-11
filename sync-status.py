#!/usr/bin/env python3
"""
AIHawk → career-ops Status Sync
================================
Reads AIHawk's data_folder/career_ops_queue.json (or an arbitrary results JSON),
then writes TSV tracker-addition files back into career-ops' pipeline.

Run `node merge-tracker.mjs` inside career-ops after this script to apply changes.

Usage:
    python sync-status.py --status Applied
    python sync-status.py --status Responded --queue-file data_folder/career_ops_queue.json
    python sync-status.py --results-file aihawk_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


VALID_STATUSES = [
    "Evaluated", "Applied", "Responded", "Interview",
    "Offer", "Rejected", "Discarded", "SKIP",
]


def write_tracker_tsv(job: dict, career_ops_dir: Path, status: str, note_override: str = "") -> Path:
    """
    Write a single TSV line to career-ops' batch/tracker-additions/.

    Column order (per career-ops CLAUDE.md):
        num  date  company  role  status  score  pdf  report  notes
    """
    tsv_dir = career_ops_dir / "batch" / "tracker-additions"
    tsv_dir.mkdir(parents=True, exist_ok=True)

    today     = date.today().strftime("%Y-%m-%d")
    num       = job.get("_career_ops_id") or job.get("id", "???")
    company   = job.get("company", "Unknown")
    role      = job.get("role", "Unknown")
    job_date  = job.get("_date") or job.get("date") or today
    slug      = company.lower().replace(" ", "-")
    score_raw = job.get("_score") or job.get("score", "")
    score_str = f"{score_raw}/5" if score_raw else "?"
    pdf_emoji = "✅" if job.get("hasPdf") else "❌"
    report    = f"[{num}](reports/{num}-{slug}-{job_date}.md)"
    note      = note_override or f"Status updated via AIHawk bridge sync on {today}"

    row = "\t".join([num, today, company, role, status, score_str, pdf_emoji, report, note])

    tsv_path = tsv_dir / f"{num}-{slug}-aihawk-sync.tsv"
    tsv_path.write_text(row + "\n", encoding="utf-8")
    return tsv_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync AIHawk results back to career-ops tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Mark all queued jobs as Applied:
  python sync-status.py --status Applied

  # Read AIHawk output results and update per-job status:
  python sync-status.py --results-file aihawk_results.json

  # Custom career-ops path:
  python sync-status.py --career-ops-dir ~/repos/career-ops --status Applied
""",
    )
    parser.add_argument("--queue-file",     default="aihawk-queue.json",
                        help="career-ops queue JSON  (default: aihawk-queue.json)")
    parser.add_argument("--results-file",   default=None,
                        help="AIHawk results JSON (optional — use if AIHawk writes per-job outcomes)")
    parser.add_argument("--career-ops-dir", default="../career-ops",
                        help="Path to career-ops repo root")
    parser.add_argument("--status",         default="Applied",
                        choices=VALID_STATUSES,
                        help="Status to write back for all jobs  (default: Applied)")
    parser.add_argument("--dry-run",        action="store_true",
                        help="Print what would be written without touching files")
    args = parser.parse_args()

    career_ops_dir = Path(args.career_ops_dir).expanduser().resolve()

    # ── Load job list ──────────────────────────────────────────────────────────
    # Priority: results_file > queue_file
    if args.results_file:
        results_path = Path(args.results_file)
        if not results_path.exists():
            print(f"❌  Results file not found: {results_path}")
            sys.exit(1)
        with open(results_path) as f:
            data = json.load(f)
        jobs = data.get("jobs", [])
        print(f"📄  Loaded results from: {results_path}  ({len(jobs)} jobs)")
    else:
        queue_path = Path(args.queue_file)
        if not queue_path.exists():
            print(f"❌  Queue file not found: {queue_path}")
            print("    Run `node export-aihawk.mjs` to generate it.")
            sys.exit(1)
        with open(queue_path) as f:
            data = json.load(f)
        jobs = data.get("jobs", [])
        print(f"📄  Loaded queue from: {queue_path}  ({len(jobs)} jobs)")

    if not jobs:
        print("⚠️  No jobs found. Nothing to sync.")
        sys.exit(0)

    print(f"📁  career-ops dir: {career_ops_dir}")
    print(f"✏️   Status:         {args.status}\n")

    # ── Write TSV per job ──────────────────────────────────────────────────────
    written = []
    for job in jobs:
        # If results file provides per-job status, use it; else use the --status arg
        job_status = job.get("_applied_status") or args.status
        note       = job.get("_applied_note") or ""

        company = job.get("company", "?")
        role    = job.get("role",    "?")
        jid     = job.get("_career_ops_id") or job.get("id", "?")

        if args.dry_run:
            print(f"  [dry-run] Would write TSV: [{jid}] {company} — {role}  →  {job_status}")
            continue

        tsv_path = write_tracker_tsv(job, career_ops_dir, job_status, note_override=note)
        written.append(tsv_path)
        print(f"  ✅  [{jid}] {company} — {role}  →  {job_status}")
        print(f"       {tsv_path}")

    if not args.dry_run and written:
        print(f"\n✅  Wrote {len(written)} TSV file(s) to {career_ops_dir}/batch/tracker-additions/")
        print("\n▶  Now run inside career-ops:")
        print("       node merge-tracker.mjs")


if __name__ == "__main__":
    main()
