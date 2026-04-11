---
description: Export approved jobs (score ≥ 4.0) to aihawk-queue.json for AIHawk submission
---

Export career-ops approved offers to the AIHawk bridge queue.

$ARGUMENTS

Steps:
1. Run `node export-aihawk.mjs` from the career-ops-aihawk-bridge directory
2. Review the generated `aihawk-queue.json` — verify job URLs and PDF paths
3. When ready: `python bridge.py --dry-run` to preview, then `python bridge.py` to run

If `$ARGUMENTS` contains a score threshold (e.g. "3.8"), set SCORE_THRESHOLD env var:
  SCORE_THRESHOLD=3.8 node export-aihawk.mjs

If `$ARGUMENTS` contains a status filter (e.g. "Evaluated,Applied"), set STATUS_FILTER:
  STATUS_FILTER=Evaluated,Applied node export-aihawk.mjs

After AIHawk runs, sync status back with:
  python sync-status.py --status Applied
  node merge-tracker.mjs    (run inside career-ops)
