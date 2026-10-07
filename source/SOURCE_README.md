# Job Agent automated source

This source bundle is intentionally free of the user's name, email, phone,
gender and CV file.

Personal data is stored locally by Job Agent Desktop in:

`~/Library/Application Support/Job Agent/settings.json`

The GitHub Actions release pipeline builds a generic application from this
source bundle.

The user completes the local Profile tab and selects a CV once. Future updates
keep those local settings.

Discovery sources in Desktop 2.7 include Jobs.cz, Prace.cz, StartupJobs.cz and
Indeed.cz. StartupJobs.cz and Indeed.cz are discovery-only in 2.7: vacancies
can be scored, deduplicated, reviewed and opened from Dashboard, but they do not
enter the automated application-preparation queue.
