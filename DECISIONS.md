# Decisions

Choices the code does not explain by itself, each with the reason it was
made. `SPEC.md` says what the project does; this says why the repository is
shaped the way it is. Everything here is checkable in the repository or in
the Actions history.

## Architecture

**The two API functions are Node, `api/health.mjs` and `api/place.mjs`.**
The pipeline is Python and the site is JavaScript, and these two sit on the
site's side of that line: `api/place` has to snap a latitude and longitude to
exactly the square the page's own `snap.js` snaps it to, and a test drives
both and compares them. They import nothing but `fetch` and node's own
`readFileSync`, so there is nothing to install, nothing to pin and no cold
start to pay for a framework.
`vercel.json` gives the pattern `api/*.mjs` a 10-second limit and the two
config files they read, and excludes everything else from their bundle.

**Feature branches, merged with normal merge commits, and history is never
rewritten.** Each group of work is a branch — `g3-map`, `g4-report-card`,
`hc-catchup`, `report-polish`, `dvh-fallback` — merged into `main` with a
real merge commit that says what it brought, so the five merges in
`git log --merges` are the five stages of the build and the branches are all
still there to read. `ux-plain`, the rewritten interface, is the sixth and is
not merged yet. Nothing is squashed, nothing is rebased onto `main`,
and `main` has never been force-pushed: the session log and the history have
to agree, and a rewritten history is a report nobody can check.

**`config/regions.json` is committed, not computed at request time.** It maps
every square of the 129 by 121 grid to one of the four IMD regions the track
record is grouped by, derived once from the India Meteorological Department's
own subdivision table and checked by a test. `api/place` reads it to tell a
reader which region their square is in, so the region in an answer and the
region in the report card are the same assignment; its SHA-256 is recorded in
`results/site_details.json`, so a changed file cannot quietly change what a
published score means.

**The workflow files are `forecast.yml` and `tests.yml`.** The names are the
two things they do, and they are the names `CLAUDE.md` fixes. The job inside
`forecast.yml` is called `live`, with its concurrency group also `live`, so
that two forecast runs can never publish at once; the file is named for the
product and the job for the thing it must not do twice.

**`config/features.json` does not exist, and nothing looks for it.** It was
planned as a flag file for work in progress and was never needed: unfinished
features are kept off the site by living on a branch that has not been
merged, which is a stronger guarantee than a flag. A flag that is off in
production is still code in production, and can be switched on by accident;
a branch cannot be. Time Machine is the case this was for, and it is parked
(below).

**`results/site_summary.json` gained `label_colours` after the `results-v1`
tag.** The tag froze the verification output; the key was added in commit
`3bf9f74`, which also added `results/site_details.json`. It carries SPEC
6.7's own table of which colour each of the three label names is drawn in,
so the key on the report card cannot invent a colour for a label no group
has. No score moved: the 60 groups in that file are identical before and
after, and `verification.json`, `verification_meta.json` and `labels.json`
are byte for byte the frozen ones. Display metadata may be added to a frozen
file; a number may not.

**Time Machine is parked on the `time-machine` branch and was never
merged.** It would have shown what the runs said on seven chosen past days
beside what the satellite then saw. The branch holds its day-selection rule
and the seven days it chose. It was dropped when the people who tested the
site could not work out where to start on the page that already existed:
a second view of the same data was worth less than making the first one
readable. The branch stays, unmerged, and `README.md` lists it under future
work.
