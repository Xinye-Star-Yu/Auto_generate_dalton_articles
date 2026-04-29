# Auto Generate Article

Generate Dalton Bioanalytics scientific summary articles with Claude Code, save the PDF and Figure 1 image in a dated output folder, and optionally schedule recurring runs from a small GUI.

## Requirements

- Python 3.10 or newer
- Claude Code CLI available as `claude` on your PATH
- A Claude Code session/account that can run `claude -p`
- Python package dependencies from `requirements.txt`
- Optional: Poppler `pdftotext` on your PATH for stricter PDF validation
- Optional: Windows Task Scheduler or Unix `cron` for persistent scheduling

`tkinter` is used for the GUI and is included with most Python installs on Windows.

## Setup

From this folder:

```powershell
cd Auto_generate_article
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Make sure the Claude CLI works before running the generator:

```powershell
claude --version
```

## Generate One Article

```powershell
python generate.py
```

The script creates the next available folder for the current date, such as `2026-04-29-1`, and writes:

- `article_output.pdf`
- Figure 1 image from the selected article

It also appends the selected DOI to `Duplication_Check_Dalton.csv`.

## Scheduler GUI

Run:

```powershell
python scheduler_gui.py
```

Use the GUI to:

- Set the number of days between generated articles
- Start or stop the OS schedule
- Watch scheduler logs

Clicking `Start` runs one article immediately. If the day value is greater than `0`, it also creates a recurring schedule for that many days later and continues on that interval. If the day value is `0`, it only runs once and does not install a recurring schedule.

On Windows, recurring runs use a Task Scheduler job named `AutoGenerateArticleScheduler`. The GUI keeps the schedule simple: you choose the day interval, and the backend uses the saved check time, defaulting to `09:00`. `article_scheduler.py` enforces the actual every-N-days interval.

Install the schedule while your intended virtual environment is active, because the task stores the current Python executable path.

## Scheduler CLI

You can use the scheduler without opening the GUI:

```powershell
python article_scheduler.py --interval-days 7 --run-time 09:00 --install
python article_scheduler.py --status
python article_scheduler.py --run-now
python article_scheduler.py --run-due
python article_scheduler.py --remove
```

Scheduler state is saved in `scheduler_config.json`. Runtime logs are written to `scheduler.log`.

## Important Files

- `generate.py`: main article generation workflow
- `scheduler_gui.py`: Tkinter scheduler interface
- `article_scheduler.py`: scheduler backend and OS task/cron installer
- `Duplication_Check_Dalton.csv`: DOI duplication history
- `template_output.pdf`: article template used when `template_article.pdf` is not present

## Notes

- The generator launches Claude Code with `--dangerously-skip-permissions`, matching the existing automation.
- Scheduled runs can take a long time because they perform article search, content generation, figure download, PDF creation, and validation.
- If validation says `pdftotext` is unavailable, PDF text validation is skipped, but PDF generation can still succeed.
