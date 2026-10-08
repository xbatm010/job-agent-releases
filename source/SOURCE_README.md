# Job Agent automated source

This source bundle is intentionally free of the user's name, email, phone,
gender and CV file.

Personal data is stored locally by Job Agent Desktop in:

`~/Library/Application Support/Job Agent/settings.json`

The GitHub Actions release pipeline builds a generic application from this
source bundle.

The user completes the local Profile tab and selects a CV once. Future updates
keep those local settings.

Discovery sources in Desktop 2.8 are Jobs.cz, Prace.cz and StartupJobs.cz.
StartupJobs.cz is discovery-only: vacancies can be scored, deduplicated,
reviewed and opened from Dashboard, but they do not enter the automated
application-preparation queue. Indeed is intentionally not integrated and is
reviewed manually outside Job Agent.

In 2.8.2, expanded roles with an explicit entry title (Junior, Student, Intern,
Trainee, Graduate or the existing Czech equivalents) use a skills-fit floor of
10 instead of 12. Regular specialist/operations titles still require 12.
The expanded APPLY score remains 70. Strong evidence, at least three independent
data signals, a central data signal, experience checks and the location gate
remain required; Operations/CRM roles still need one extra data signal.
Part-time alone and entry wording only in a description do not qualify.

The ranking log and Dashboard details show skills fit, the applicable floor
and failed expanded APPLY checks. New local snapshots retain these fields;
old history remains readable. CSV reasons retain the complete scoring and
location explanations. Final employer Submit remains manual in Desktop.

Desktop 2.9.0 introduces the light workspace: sidebar navigation, vacancy
table and detail inspector, score explanations, favorites and source-health
badges. Settings and updates are in a separate window. Narrow windows place
the detail inspector below the table. Existing local profiles/history remain
readable; thresholds and contact data are preserved.

Desktop defaults to **search only** on the first 2.9.0 launch. Uncheck
"Только поиск" to search and prepare forms in one run, or use the selected
vacancy's "Подготовить отклик" action. Search-only needs no contact profile or
CV; explicit preparation still validates both. The runtime receives
SEARCH_ONLY=true and stores eligible results as READY_TO_PREPARE before
returning without opening any application forms. The CLI default stays false
when the variable is absent; the example environment enables search-only.

discovery_status.json in STATE_DIR records the last search's source counts,
empty/error/partial outcomes and diagnostic details. StartupJobs records HTTP
status, parsed count, vacancy-link count and browser-fallback outcome. Zero
parsed results are shown as needing review, not proof that no vacancies exist.
Location-only employer names such as Prague are rejected. Explicit entry
roles get priority in the limited browser-evidence pass.

Run offline regression tests (including real Qt widgets) with:

`QT_QPA_PLATFORM=offscreen python -m unittest discover -s source/tests -v`


Desktop 2.9.1 refines the selected light concept with inline header metrics,
vector navigation icons, a single source-health strip, counted filter tabs,
three-line vacancy rows, source marks, score/status pills, a native detail
card with match checks and skill tags, and a run journal below the table.
The detail description remains available through a disclosure control.
Source and extra decision filters are in the filter menu; saved vacancies,
queue actions, letters and updates remain accessible. Remote vacancy text
is always plain text in native labels. Unknown locations are explained
without changing scoring or preparation gates. The offline suite includes
33 tests covering the new controls and responsive layout.
