# Job Scraper

Small CLI tool that pulls open roles from several sources, keeps only listings that look like **software / ML / AI** work at **intern or entry level**, and highlights **new** postings since your last run.

Sources:

- **Greenhouse** and **Lever** — official JSON APIs per company board
- **Indeed** — RSS for a search query (`q` / optional `l`); see limitations below
- **LinkedIn** — public guest job-search endpoint that returns HTML snippets (no login)
- **Gemini** (optional) — Google AI suggests a small JSON digest (not live scraping); needs `GEMINI_API_KEY` and `"gemini": { "enabled": true }` in config. When it runs you will see **`Gemini: calling API…`** and counts in the terminal; rows also appear with **Source** `gemini` in `data/output/jobs.md` / JSON.

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

**Gemini API key (optional):** Copy `.env.example` to `.env` in the **project root** (next to this README). Set `GEMINI_API_KEY=your_key_here`. `.env` is gitignored. You can also `export GEMINI_API_KEY=...` in the terminal instead.

## How to run

From the project root, with the venv activated (or use `.venv/bin/python` as below):

```bash
python -m job_scraper
python -m job_scraper --all
python -m job_scraper --help
```

**Without** activating the venv each time, you can still call the project interpreter directly:

```bash
.venv/bin/python -m job_scraper
```

**Optional:** add to `~/.zshrc` (adjust the path) so one short command `cd`s into the repo and runs the scraper:

```bash
alias run-jobs='cd /path/to/Job-Scraper && .venv/bin/python -m job_scraper'
```

Then use `run-jobs`, `run-jobs --all`, etc. No extra files in the repo are required.

### Where results go

| Output | What it is |
|--------|------------|
| **Terminal** | By default, only rows that are **new vs the previous run** (fingerprints not in last run’s state). With `--all`, every match from this fetch is printed. |
| `data/seen_jobs.json` | After each run this file is **replaced** with fingerprints **only for jobs found in that run**. Closed or missing listings drop off automatically; nothing historical accumulates. Used to compute “new” on the **next** run. |
| `data/output/jobs_latest.json` | **Full replace** every run: **`company`**, **`salary`** (when known), grouped into **`intern`**, **`new_grad`**, and **`other`**. Skipped with `--no-save`. |
| `data/output/jobs.md` | **Full replace** every run: sortable-style tables (**Company, Title, Location, Salary, Source,** link). Skipped with `--no-save`. |

Snapshots live under **`data/output/`** so they stay separate from state (`seen_jobs.json` in `data/`).

Putting scraped listings **inside `README.md` itself** is uncommon: the README is meant to describe the project, and auto-updated listings cause noisy diffs and merge conflicts. Many repos instead commit files under `data/output/` (or similar)—GitHub renders Markdown the same way—and link to it from the README, e.g. [data/output/jobs.md](data/output/jobs.md) after your first run.

## Configuration

Edit `config/boards.json`:

- **`location_filter`** (optional): string array. A job passes if **any** substring appears in **company, location, title, team, or salary** fields combined (case-insensitive), **or** if `remote_germany` applies (see below). Omit or use `[]` if you only rely on remote-Germany matching.
- **`gemini`** (optional): object with **`enabled`** (boolean), **`model`** (e.g. `gemini-2.0-flash`), and optional **`prompt_extra`**. The key is read from **`GEMINI_API_KEY`** in the environment or from a **`.env`** file in the project root (see setup above). With `enabled: false`, Gemini is skipped.
- **`remote_germany`** (optional, boolean, default `false`): if `true`, also keep jobs whose text looks like **remote / hybrid / WFH** *and* **Germany-related** (e.g. Germany, Deutschland, Berlin, Brandenburg, DACH, common Bundesländer hints). This is meant to include roles like “Remote (Germany)” without letting in generic worldwide remote spam.
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

### Intern vs new grad in output

After region filtering, listings are **classified from the job title** (`job_scraper/career_tier.py`):

- **Internships** — internship / intern / co-op / Praktikum / Werkstudent, etc.
- **New grad / entry level** — new grad, entry level, junior, associate engineer, graduate engineer, early career, etc. (intern keywords win if both could match.)
- **Other matches** — matched your role/level filters but did not fit the two buckets (tune patterns if you want fewer here).

Terminal output and `data/output/jobs.md` use these **section headers**; `jobs_latest.json` exposes **`intern`**, **`new_grad`**, and **`other`** arrays.

## Automation

The tool does not schedule itself. To poll regularly, use **cron**, a **macOS LaunchAgent**, or a **CI scheduled job** that activates your venv and runs `python -m job_scraper`, optionally redirecting output to a log file.

## Limitations

- **Gemini** does not browse the live web. It returns **suggested** roles from model knowledge; links and salaries can be **wrong or outdated**. Treat Gemini rows as leads and verify on the employer site. Empty `apply_url` from the model is replaced with a **Google search** link for convenience.
- **Indeed** often serves **Cloudflare** or other challenges to scripted clients. The RSS integration is best-effort: it may work from a normal home network and fail from a datacenter or VPN. If you always get warnings, rely on other sources or run less often from a residential IP.
- **LinkedIn** uses an **undocumented guest** endpoint. It can change, throttle, or block aggressive use. Keep **`pages`** small and runs infrequent. Automated access may not match [LinkedIn’s terms](https://www.linkedin.com/legal/user-agreement); use at your own risk.
- Only the implemented sources are supported; many employers use **Workday, Ashby, iCIMS**, etc.
- Matching is keyword-based; occasional false positives or misses are normal.
