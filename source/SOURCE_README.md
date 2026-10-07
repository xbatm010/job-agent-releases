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

Run offline regression tests with:

`python -m unittest discover -s source/tests -v`

