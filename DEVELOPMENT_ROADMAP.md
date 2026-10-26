# Job Agent product roadmap (October 2026)

## Product objective

Find **new, credible entry-level IT opportunities in Prague or fully remote**
and help the user prepare accurate applications without duplicate submissions,
misrepresenting their skills, or uploading private applicant data to GitHub.

## Verified baseline

- Latest published beta: **3.0.15**.
- Main source version when roadmap was established: **3.0.16** (merged
  cross-portal Alma ID deduplication with CI success, unpublished).
- Observed macOS 3.0.15 run: 180 discovery results, 108 detail enrichments,
  105 post-dedup scoring results, 18 REVIEW and 0 APPLY.
  These numbers are **one run**, not a claim about long-term quality.
- Supported search sources: Jobs.cz, Prace.cz, StartupJobs.cz.
  StartupJobs is discovery/review only, not application preparation.

## Workstreams, in dependency order

### P0 — Safe release and observability foundation (this PR)
1. Aggregate the **whole scored pool**, not just Dashboard shortlist.
2. Distinguish primary blocker (one per non-APPLY vacancy) from all
   contributing blockers (may overlap); segment by Data/BI, IT Support, QA.
3. Show funnel stages, zero-APPLY explanation and local last-run report.
4. Ship unit and Qt offscreen tests for missing data, privacy and persistence.
5. Run GitHub Actions. Publish the next beta only when both PR and main CI pass.

Acceptance: report totals reconcile with scored counts; no changes to
APPLY/REVIEW/SKIP outcomes; zero CV, contact, raw vacancy text or URLs
stored in the aggregate report; no form submission side effects.

### P1 — Evidence-grounded Fit Intelligence
- Distinguish employer requirements from benefits, related jobs, nav/footer
  and third-party excerpts, with bounded vacancy-specific evidence.
- Trace each hard requirement and matched skill to a literal source excerpt;
  retain explicit "unknown" for insufficient evidence.
- Compare Data/BI and Support/QA against separate verified CV skill profiles.
- Add an offline fixture-based audit: graduate/student role, mandatory 1–2
  years, mandatory 3+ years, advanced technology, optional requirements,
  truncated/blocked pages, mixed language, missing location.

Acceptance: known required experience remains a blocker and weak evidence
never promotes a job to APPLY. Review known 0-APPLY cases using a reproducible
offline test corpus before **any** threshold change.

### P1 — Smart Discovery / source health
- Measure source yield by query: new vs seen, details fetched, weak/strong,
  broken pages, duplicates, location unknown and conversion to REVIEW/APPLY.
- Improve StartupJobs error classification and safe read-only browser
  fallback; no CAPTCHA bypass, no guessed hidden data.
- Use observed yields to rebalance the existing HTTP/browser budgets. Keep
  global caps explicit and retain source fairness.
- Avoid re-enriching closed/rejected or already confirmed submissions.

Acceptance: same budgets, higher *verified new relevant* yield on saved
source fixtures, no unintended increase in requests or retries.

### P2 — Application preparation and CV intelligence
- Validate CV routing across Data/BI vs IT Support/QA and explain the choice.
- Recommend employer-specific cover letters based strictly on confirmed CV
  skills and vacancy facts; allow preview/edit before using.
- Record form-preparation evidence and missing required fields safely.

Acceptance: no fabrication of skills, no unsolicited form submission, no
automatic confirmation of sent status, no personal data in public repository.

### P2 — Employer response intelligence
- Keep Gmail access opt-in and read-only until user confirms a stage.
- Improve conservative correspondence matching to a *confirmed* application,
  and highlight ambiguous matches.
- Build an actionable follow-up queue, local deadlines, response/interview
  conversion funnel (not raw send counts alone).

Acceptance: no email can autonomously mark a vacancy submitted/rejected; no
false recruiter statuses inferred from application technical events.

### P3 — Reliability and product operations
- Add anonymized offline fixtures, schema/version guards for local state,
  failure-safe atomic writes and backup/restore tooling.
- Publish auditable CI results and release notes, keep beta/stable
  channels explicit; validate on real macOS before stable promotion.
- Report actual workflow outcomes rather than assuming deployment success.

## Release and safety rules

1. Work in feature branches; use draft PR + CI before merging.
2. Never change application safety gates as part of diagnostics-only work.
3. Manual final Submit stays manual; never mark sent without verified human
   completion.
4. Public GitHub receives **sanitized source and tests only**; personal CVs,
   addresses, contacts, emails, job application messages and local runtime
   state stay on the user's Mac.
5. Treat counts from one run as diagnostic evidence, not a statistical
   guarantee. Collect reproducible comparisons before tuning thresholds.
