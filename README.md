# Job Scraper

Small CLI tool that pulls open roles from several sources, keeps only listings that look like **software / ML / AI** work at **intern or entry level**, and highlights **new** postings since your last run.

Sources:

- **Greenhouse** and **Lever** — official JSON APIs per company board
- **Indeed** — RSS for a search query (`q` / optional `l`); see limitations below
- **LinkedIn** — public guest job-search endpoint that returns HTML snippets (no login)

## Requirements

- Python 3.10 or newer (the code uses `dataclass(slots=True)`)
- Network access when you run the script

## Setup

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## How to run

**Default:** print only jobs that were **not** in the previous run (uses a saved list of IDs):

```bash
python -m job_scraper
```

**Print every matching job** on this run (ignore “new since last time” for display):

```bash
python -m job_scraper --all
```

**Custom paths** for board list or state file:

```bash
python -m job_scraper --config ./config/boards.json --state ./data/seen_jobs.json
```

**Do not write snapshot files** (only update `seen_jobs.json` and print to the terminal):

```bash
python -m job_scraper --no-save
```

**Custom snapshot paths** (defaults: `data/output/jobs_latest.json`, `data/output/jobs.md`):

```bash
python -m job_scraper --json-out ./data/output/custom.json --md-out ./data/output/custom.md
```

**Help:**

```bash
python -m job_scraper --help
```

### Where results go

| Output | What it is |
|--------|------------|
| **Terminal** | By default, only rows that are **new** since the last run (same as before). With `--all`, every match from this fetch is printed. |
| `data/seen_jobs.json` | List of **fingerprints** (source + board + id) so the tool knows what you have already seen. Not full job text. |
| `data/output/jobs_latest.json` | **Full snapshot** of every job that matched filters on this run (structured JSON with metadata). Overwritten each run unless you use `--no-save`. |
| `data/output/jobs.md` | Same snapshot as a **Markdown table** so GitHub can render it when you browse the file in the repo. |

Snapshots live under **`data/output/`** so they stay separate from state (`seen_jobs.json` in `data/`).

Putting scraped listings **inside `README.md` itself** is uncommon: the README is meant to describe the project, and auto-updated listings cause noisy diffs and merge conflicts. Many repos instead commit files under `data/output/` (or similar)—GitHub renders Markdown the same way—and link to it from the README, e.g. [data/output/jobs.md](data/output/jobs.md) after your first run.

## Configuration

Edit `config/boards.json`:

- **`greenhouse`:** string array of board tokens from `https://job-boards.greenhouse.io/{token}`.
- **`lever`:** string array of company slugs from `https://jobs.lever.co/{company}`.
- **`indeed`:** array of objects:
  - **`q`** (required): search string.
  - **`l`** (optional): location, same as on the Indeed site.
  - **`label`** (optional): short name for logs and output; defaults from `q`.
- **`linkedin`:** array of objects:
  - **`keywords`** (required): search string (you can use the same syntax LinkedIn’s search box supports).
  - **`location`** (optional): e.g. `"United States"`, or `""`.
  - **`label`** (optional): short name for output.
  - **`pages`** (optional): how many result pages to pull (25 jobs per page); default `2`, max `10` in code.

Omit `indeed` or `linkedin` or use `[]` if you do not want those sources.

### Which roles and levels count as a match

Rules live in `job_scraper/filters.py` (`ROLE_KEYWORDS` and `LEVEL_KEYWORDS`). A job must match **at least one** pattern from each group in the title (and description when the source provides one). Tweak the regexes there for broader or stricter matching.

## Automation

The tool does not schedule itself. To poll regularly, use **cron**, a **macOS LaunchAgent**, or a **CI scheduled job** that activates your venv and runs `python -m job_scraper`, optionally redirecting output to a log file.

## Limitations

- **Indeed** often serves **Cloudflare** or other challenges to scripted clients. The RSS integration is best-effort: it may work from a normal home network and fail from a datacenter or VPN. If you always get warnings, rely on other sources or run less often from a residential IP.
- **LinkedIn** uses an **undocumented guest** endpoint. It can change, throttle, or block aggressive use. Keep **`pages`** small and runs infrequent. Automated access may not match [LinkedIn’s terms](https://www.linkedin.com/legal/user-agreement); use at your own risk.
- Only the implemented sources are supported; many employers use **Workday, Ashby, iCIMS**, etc.
- Matching is keyword-based; occasional false positives or misses are normal.
