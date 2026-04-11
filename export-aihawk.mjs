#!/usr/bin/env node
/**
 * career-ops → AIHawk Export Adapter
 *
 * Reads career-ops' data/applications.md, filters approved jobs
 * (score ≥ threshold AND status in STATUS_FILTER), then writes
 * aihawk-queue.json for bridge.py to consume.
 *
 * Usage:
 *   node export-aihawk.mjs
 *   SCORE_THRESHOLD=3.8 node export-aihawk.mjs
 *   CAREER_OPS_DIR=/path/to/career-ops node export-aihawk.mjs
 *
 * Env vars:
 *   CAREER_OPS_DIR    Path to career-ops project (default: ../career-ops)
 *   SCORE_THRESHOLD   Minimum score to export (default: 4.0)
 *   STATUS_FILTER     Comma-separated statuses to include (default: "Evaluated")
 *   OUTPUT_FILE       Output path for the queue JSON (default: ./aihawk-queue.json)
 */

import { readFileSync, writeFileSync, existsSync } from "fs";
import { resolve, dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────
const CAREER_OPS_DIR   = process.env.CAREER_OPS_DIR   || resolve(__dirname, "../career-ops");
const SCORE_THRESHOLD  = parseFloat(process.env.SCORE_THRESHOLD || "4.0");
const STATUS_FILTER    = (process.env.STATUS_FILTER || "Evaluated").split(",").map(s => s.trim());
const OUTPUT_FILE      = process.env.OUTPUT_FILE      || resolve(__dirname, "aihawk-queue.json");

const TRACKER_PATH     = join(CAREER_OPS_DIR, "data/applications.md");
const OUTPUT_DIR       = join(CAREER_OPS_DIR, "output");
const REPORTS_DIR      = join(CAREER_OPS_DIR, "reports");

// ── Parser ────────────────────────────────────────────────────────────────────
/**
 * Parse career-ops applications.md markdown table.
 *
 * Column order (applications.md):
 *   # | Date | Company | Role | Score | Status | PDF | Report | Notes
 *
 * Returns array of job objects.
 */
function parseTracker(content) {
  const jobs = [];

  for (const line of content.split("\n")) {
    // Skip header, separator, and non-table lines
    if (!line.startsWith("|"))              continue;
    if (line.includes("| # |"))            continue;
    if (/^\|[-| ]+\|$/.test(line.trim()))  continue;

    const cols = line.split("|").map(c => c.trim()).filter(Boolean);
    if (cols.length < 8) continue;

    const [num, date, company, role, score, status, pdf, report, ...notesParts] = cols;
    const notes = notesParts.join(" | ").trim();

    const scoreNum = parseFloat(score);
    if (isNaN(scoreNum)) continue;

    // Extract relative report path from markdown link [N](reports/...)
    const reportRelMatch = report?.match(/\[.*?\]\((.*?)\)/);
    const reportPath = reportRelMatch
      ? join(CAREER_OPS_DIR, reportRelMatch[1])
      : null;

    // Try to find the tailored PDF by common naming patterns
    const slug = company.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const pdfCandidates = [
      join(OUTPUT_DIR, `${num.padStart(3, "0")}-${slug}.pdf`),
      join(OUTPUT_DIR, `${num}-${slug}.pdf`),
      join(OUTPUT_DIR, `${slug}.pdf`),
    ];
    const pdfPath = pdfCandidates.find(p => existsSync(p)) || null;

    // Extract job URL from report file (**URL:** field)
    let jobUrl = null;
    if (reportPath && existsSync(reportPath)) {
      const reportContent = readFileSync(reportPath, "utf-8");
      const urlMatch = reportContent.match(/\*\*URL:\*\*\s*(https?:\/\/\S+)/);
      if (urlMatch) jobUrl = urlMatch[1].replace(/[.,)>]+$/, ""); // strip trailing punctuation
    }

    jobs.push({
      id:         num.trim().padStart(3, "0"),
      date:       date.trim(),
      company:    company.trim(),
      role:       role.trim(),
      score:      scoreNum,
      status:     status.trim(),
      hasPdf:     pdf.trim() === "✅",
      pdfPath,
      reportPath,
      jobUrl,
      notes:      notes.trim(),
    });
  }

  return jobs;
}

// ── Main ──────────────────────────────────────────────────────────────────────
function main() {
  if (!existsSync(TRACKER_PATH)) {
    console.error(`❌  Tracker not found: ${TRACKER_PATH}`);
    console.error(`    Set CAREER_OPS_DIR to point to your career-ops directory.`);
    process.exit(1);
  }

  const content  = readFileSync(TRACKER_PATH, "utf-8");
  const all      = parseTracker(content);
  const approved = all.filter(
    job => job.score >= SCORE_THRESHOLD && STATUS_FILTER.includes(job.status)
  );

  console.log(`📊 career-ops tracker: ${all.length} total entries`);
  console.log(`🎯 Filter: score ≥ ${SCORE_THRESHOLD}, status in [${STATUS_FILTER.join(", ")}]`);
  console.log(`✅ Approved: ${approved.length} job(s)\n`);

  if (approved.length === 0) {
    console.log("   Nothing to export. Adjust SCORE_THRESHOLD or STATUS_FILTER.");
    process.exit(0);
  }

  const queue = {
    schema_version:  "1.0",
    exported_at:     new Date().toISOString(),
    score_threshold: SCORE_THRESHOLD,
    status_filter:   STATUS_FILTER,
    career_ops_dir:  CAREER_OPS_DIR,
    jobs:            approved,
  };

  writeFileSync(OUTPUT_FILE, JSON.stringify(queue, null, 2));
  console.log(`📤 Wrote queue → ${OUTPUT_FILE}\n`);

  for (const j of approved) {
    const pdf = j.pdfPath  ? `✅ PDF`          : "❌ no PDF";
    const url = j.jobUrl   ? j.jobUrl.slice(0, 60) + (j.jobUrl.length > 60 ? "…" : "")
                            : "⚠️  URL not found in report";
    console.log(`  [${j.id}] ${j.company.padEnd(20)} ${j.role.padEnd(35)} ${j.score}/5  ${pdf}`);
    console.log(`         ${url}`);
  }

  console.log(`\n▶  Next step: python bridge.py --queue ${OUTPUT_FILE}`);
}

main();
