# career-ops-aihawk-bridge

Integration bridge between **[career-ops](https://github.com/santifer/career-ops)** (AI-powered job evaluation & CV generation) and **[AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk)** (automated job application submission).

```
career-ops                    →  bridge  →               AIHawk
──────────────────────────────────────────────────────────────────────
1. Scan 45+ company portals
2. Score offers A–F vs your CV
3. Generate tailored PDF per job
4. Filter: score ≥ 4.0/5        →  export-aihawk.mjs  →
                                 →  aihawk-queue.json  →
                                 →  bridge.py          →  5. Load tailored PDF
                                                          6. Fill application forms
                                                          7. Submit (LinkedIn etc.)
                                 ←  sync-status.py    ←  8. Return confirmation
9. Update tracker ("Applied") ←
```

---

## Repo layout

```
career-ops-aihawk-bridge/
├── export-aihawk.mjs               # Stage 1→2: reads career-ops tracker, writes queue JSON
├── bridge.py                       # Stage 2:   reads queue, sets up AIHawk, invokes it
├── sync-status.py                  # Stage 2→1: writes Applied status back to career-ops
├── config.example.yml              # Documented config reference (not read at runtime yet)
├── schemas/
│   └── aihawk-queue.schema.json   # JSON Schema for the handoff format
├── examples/
│   └── aihawk-queue.example.json  # Example queue for testing
└── career-ops-commands/
    └── career-ops-export-aihawk.md # OpenCode / Claude Code slash command
```

---

## Data schema mapping

### career-ops `data/applications.md` → `aihawk-queue.json`

| career-ops column | `aihawk-queue.json` field | AIHawk `Job` field | Notes |
|---|---|---|---|
| `#` (num) | `id` (zero-padded) | `_career_ops_id` | Preserved as metadata |
| `Date` | `date` | `_date` | Evaluation date |
| `Company` | `company` | `company` | Direct mapping |
| `Role` | `role` | `role` | Direct mapping |
| `Score` (e.g. `4.2/5`) | `score` (float 4.2) | `_score` | Float parsed from string |
| `Status` | `status` | _(filter only)_ | Only `Evaluated` exported by default |
| `PDF` (✅/❌) | `hasPdf` (bool) | _(routing)_ | Determines resume source |
| `Report` (markdown link) | `reportPath` (abs path) | `_report_path` | Used to extract job URL |
| `Notes` | `notes` | `description` | Stand-in until AIHawk scrapes full JD |
| _(extracted from report `**URL:**`)_ | `jobUrl` | `link` | Primary key for AIHawk |
| _(file: `output/{id}-{slug}.pdf`)_ | `pdfPath` (abs path) | `resume_path` | Tailored CV from career-ops |

### `aihawk-queue.json` → AIHawk `data_folder/career_ops_queue.json`

bridge.py maps each queue entry to AIHawk's `Job` dataclass fields:

| queue field | AIHawk `Job` field | Transform |
|---|---|---|
| `role` | `role` | Direct |
| `company` | `company` | Direct |
| `jobUrl` | `link` | Direct |
| `"direct"` (hardcoded) | `apply_method` | Override to `"linkedin"` for Easy Apply URLs |
| `notes` | `description` | Fallback until AIHawk scrapes the JD |
| `pdfPath` (copied to data_folder/output/) | `resume_path` | Absolute path after copy |
| `""` | `cover_letter_path` | Bridge doesn't generate cover letters |
| `""` | `location` | AIHawk scrapes this from the job URL |

### Status sync: AIHawk → career-ops `batch/tracker-additions/`

TSV column order (matches career-ops `merge-tracker.mjs` expectations):

```
num  date  company  role  status  score  pdf  report  notes
```

---

## Setup

### Prerequisites

```bash
# Python 3.11+ and Node.js 20+
pip install pyyaml
npm install  # inside career-ops (for merge-tracker.mjs)

# Clone all three repos side by side:
git clone https://github.com/santifer/career-ops
git clone https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk
git clone https://github.com/YOUR_USERNAME/career-ops-aihawk-bridge
```

### Directory structure assumed by defaults

```
repos/
├── career-ops/
├── Jobs_Applier_AI_Agent_AIHawk/
└── career-ops-aihawk-bridge/      ← you are here
```

If your layout differs, use `--career-ops-dir` / `--aihawk-dir` flags or set `CAREER_OPS_DIR` / `AIHAWK_DIR` env vars.

---

## Usage

### Step 1 — Run career-ops until you have evaluated jobs

```bash
cd career-ops
# Evaluate jobs, generate PDFs — the usual workflow
# Ensure reports have **URL:** lines and output/ has PDFs
```

### Step 2 — Export approved jobs

```bash
cd career-ops-aihawk-bridge
node export-aihawk.mjs
```

Optional env vars:
```bash
SCORE_THRESHOLD=3.8 STATUS_FILTER=Evaluated,Applied node export-aihawk.mjs
```

Review `aihawk-queue.json`. Check that `jobUrl` and `pdfPath` are populated for every job you intend to submit.

### Step 3 — Dry-run the bridge

```bash
python bridge.py --dry-run
```

This sets up `data_folder/` and prints what AIHawk would run — without actually launching it.

### Step 4 — Run the bridge

```bash
python bridge.py
```

AIHawk opens and processes jobs from `data_folder/career_ops_queue.json`.

> **Note:** AIHawk's provider plugins (LinkedIn Easy Apply, Greenhouse, etc.) were removed from the public repo due to copyright. You'll need to add your own plugin or use a fork. The bridge writes `career_ops_queue.json` in the format those plugins expect.

### Step 5 — Sync status back

```bash
# Option A: bridge handles it automatically
python bridge.py --sync-back

# Option B: manual sync after the fact
python sync-status.py --status Applied

# Apply back to career-ops tracker
cd ../career-ops && node merge-tracker.mjs
```

### OpenCode / Claude Code command

Copy `career-ops-commands/career-ops-export-aihawk.md` into your career-ops `.opencode/commands/` directory to add `/career-ops-export-aihawk` as a slash command.

---

## Key design decisions

**Why Node.js for export, Python for bridge?**  
career-ops is a Node.js project (`.mjs` scripts). Keeping the export script in the same language means it can be dropped directly into career-ops' toolchain. AIHawk is Python, so the bridge must be Python too.

**Why a JSON handoff file instead of a direct function call?**  
The two tools run in separate processes with different runtimes. A flat JSON file is auditable, pausable, and human-editable — you can review and trim `aihawk-queue.json` before committing to submit.

**Why does the bridge NOT auto-submit?**  
Respecting career-ops' philosophy: the human reviews the queue before anything is submitted. `--dry-run` is the safe default. You opt in to live submission explicitly.

**What about non-LinkedIn portals?**  
AIHawk's current public repo only supports resume/cover letter generation. For Greenhouse, Ashby, or Lever jobs from career-ops, you'll need to add provider plugins. The bridge's `career_ops_queue.json` is ready for any plugin to consume — `apply_method` is set to `"direct"` for non-LinkedIn URLs.

---

## Extending

### Adding a provider plugin

Create `plugins/{platform}_plugin.py` in AIHawk. On startup, read `data_folder/career_ops_queue.json`, iterate jobs, and dispatch by `apply_method` or by matching the URL domain.

### Making bridge.py config-file aware

```python
# TODO: load config.yml and merge with CLI args
import yaml
config = yaml.safe_load(open("config.yml")) if Path("config.yml").exists() else {}
```

### Adding a review UI

Between export and bridge, drop in a simple curses or rich-based TUI that lets you toggle jobs in/out of the queue before submission.

---

## License

MIT
