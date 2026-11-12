# CLAUDE.md

## Project

India precipitation forecast website.

- **Forecast source:** ECMWF AIFS ENS, 51 members, 00 UTC runs.
- **Observation source:** NASA IMERG Late V07C, daily.
- **Product:** model-run counts for 1, 10 and 50 mm thresholds over 5 days.
- **Commitment:** an honest, published track record.
- **Repository:** https://github.com/SumedhaKar/Precipitation-Forecast-App
- **Author:** Sumedha Kar
- **Context:** QUEST Lab Full Stack AI Pre-doctoral application, November 2026.

This folder is the project root. Do not create a nested `precipitation-forecast/` folder inside it.

## Rules

1. Show actual evidence before claiming something works.
2. Never invent data, numbers or test results.
3. Never put passwords, keys or tokens in code or chat.
4. Commit after each completed, tested step.
5. Follow SPEC.md once it exists. Don't change the structure without asking.
6. NASA data is a satellite estimate, never ground truth.
7. Ensemble counts are model-run counts, not calibrated probabilities.
8. Never publish an incomplete forecast.
9. Never delete or overwrite data without my approval.
10. Do not reuse practice code or data.
11. Never force-push main or overwrite its history. Any other force-push needs my approval first.
12. If a requirement is unclear, explain the uncertainty and ask before making assumptions.

## Working notes

- The user is a beginner. Explain each command briefly. Keep replies short.
- Create files only when their step starts, not in advance.
- `data/` is never committed.
- Commit email for this repository is the GitHub noreply address, set locally, not the personal address in the global git config.

## Fixed structure

```
CLAUDE.md, SPEC.md, DECISIONS.md, README.md, CREDITS.md
requirements.txt, .python-version, .gitignore, .env.example, vercel.json
config/features.json
.github/workflows/   forecast.yml, tests.yml
pipeline/            config, ecmwf_download, nasa_download, ecmwf_process,
                     nasa_process, india_mask, checks, verify, labels,
                     publish, run_live
scripts/             run_pile_a, run_pile_b, supervise, build_report_card,
                     freeze
scripts/publish/     package.json, package-lock.json, blob.mjs
tests/               sample/, test_lead_days, test_ecmwf_process, test_remap,
                     test_india_mask, test_nasa_process, test_connections,
                     test_counts_dots, test_verify, test_labels, test_publish,
                     test_run_selection, test_api_consistency
handchecks/
api/                 health, place
web/                 React + Vite + MapLibre
results/             frozen verification output
data/                never committed: raw/, india/ecmwf/, india/nasa/,
                     live/, publish/, logs/done/, logs/failures/
```
