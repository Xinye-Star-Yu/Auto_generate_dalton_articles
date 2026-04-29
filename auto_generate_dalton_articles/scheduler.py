"""
Persistent scheduler support for generate.py.

The OS task runs this file once per day at the configured time. This module
then checks scheduler_config.json to decide whether the article generator is
actually due based on the requested day interval.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterable


def app_base_dir() -> Path:
    """Directory used for writable runtime files and article outputs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_base_dir() -> Path:
    """Directory used for bundled read-only files in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_base_dir()))
    return app_base_dir()


BASE_DIR = app_base_dir()
RESOURCE_DIR = resource_base_dir()
CONFIG_PATH = BASE_DIR / "scheduler_config.json"
LOG_PATH = BASE_DIR / "scheduler.log"
GENERATOR_PATH = BASE_DIR / "generate.py"
DUP_CSV_PATH = BASE_DIR / "Duplication_Check_Dalton.csv"
TASK_NAME = "AutoGenerateArticleScheduler"
CRON_BEGIN = "# BEGIN AutoGenerateArticleScheduler"
CRON_END = "# END AutoGenerateArticleScheduler"

DEFAULT_CONFIG = {
    "enabled": True,
    "interval_days": 7,
    "articles_per_run": 1,
    "run_time": "09:00",
    "next_run_at": None,
    "last_run_at": None,
    "last_status": "Never run",
    "last_output_dir": None,
    "last_output_dirs": [],
}


LogCallback = Callable[[str], None]


def ensure_runtime_file(filename: str) -> Path:
    target = BASE_DIR / filename
    source = RESOURCE_DIR / filename
    if not target.exists() and source.exists() and source != target:
        shutil.copy2(source, target)
    return target


def duplication_csv_path() -> Path:
    path = ensure_runtime_file("Duplication_Check_Dalton.csv")
    normalize_duplication_csv(path)
    return path


def normalize_duplication_csv(path: Path) -> None:
    """Keep the DOI history CSV limited to doi_norm,date columns."""
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["doi_norm", "date"])
        return

    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = [
            {
                "doi_norm": (row.get("doi_norm") or "").strip(),
                "date": (row.get("date") or "").strip(),
            }
            for row in reader
            if (row.get("doi_norm") or "").strip()
        ]
        if reader.fieldnames == ["doi_norm", "date"]:
            return

    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["doi_norm", "date"])
        writer.writeheader()
        writer.writerows(rows)


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def append_log(message: str) -> None:
    timestamp = _now().isoformat(sep=" ", timespec="seconds")
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message.rstrip()}\n")


def parse_run_time(value: str) -> time:
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
    if not match:
        raise ValueError("Run time must be in HH:MM 24-hour format.")
    return time(hour=int(match.group(1)), minute=int(match.group(2)))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as config_file:
            saved = json.load(config_file)
        config.update(saved)
    config["interval_days"] = max(0, int(config["interval_days"]))
    config["articles_per_run"] = max(1, int(config.get("articles_per_run", 1)))
    if config["interval_days"] == 0:
        config["enabled"] = False
        config["next_run_at"] = None
    elif not config.get("next_run_at") and config.get("enabled", True):
        config["next_run_at"] = next_run_after(_now(), config["interval_days"], config["run_time"]).isoformat()
    return config


def save_config(config: dict) -> dict:
    normalized = dict(DEFAULT_CONFIG)
    normalized.update(config)
    normalized["interval_days"] = max(0, int(normalized["interval_days"]))
    normalized["articles_per_run"] = max(1, int(normalized.get("articles_per_run", 1)))
    parse_run_time(normalized["run_time"])
    if normalized["interval_days"] == 0:
        normalized["enabled"] = False
        normalized["next_run_at"] = None
    CONFIG_PATH.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def next_run_after(reference: datetime, interval_days: int, run_time: str) -> datetime:
    run_at = parse_run_time(run_time)
    interval = max(1, int(interval_days))
    candidate = datetime.combine(reference.date(), run_at)
    while candidate <= reference:
        candidate += timedelta(days=interval)
    return candidate


def next_run_after_immediate_run(reference: datetime, interval_days: int, run_time: str) -> datetime:
    run_at = parse_run_time(run_time)
    interval = max(1, int(interval_days))
    candidate = datetime.combine(reference.date() + timedelta(days=interval), run_at)
    while candidate <= reference:
        candidate += timedelta(days=interval)
    return candidate


def update_schedule(
    interval_days: int,
    run_time: str,
    articles_per_run: int = 1,
    enabled: bool = True,
    immediate_run_at: datetime | None = None,
) -> dict:
    now = _now()
    interval = max(0, int(interval_days))
    article_count = max(1, int(articles_per_run))
    if interval == 0:
        config = load_config()
        config.update(
            {
                "enabled": False,
                "interval_days": 0,
                "articles_per_run": article_count,
                "run_time": run_time.strip(),
                "next_run_at": None,
            }
        )
        save_config(config)
        append_log(
            f"One-time run configured for {article_count} article(s); "
            "no recurring schedule will be installed."
        )
        return config

    if immediate_run_at is not None:
        candidate = next_run_after_immediate_run(immediate_run_at, interval, run_time)
    else:
        candidate = next_run_after(now, interval, run_time)

    config = load_config()
    config.update(
        {
            "enabled": enabled,
            "interval_days": interval,
            "articles_per_run": article_count,
            "run_time": run_time.strip(),
            "next_run_at": candidate.isoformat(),
        }
    )
    save_config(config)
    append_log(
        f"Schedule saved: {config['articles_per_run']} article(s) every "
        f"{config['interval_days']} day(s) at {config['run_time']}; "
        f"next run {config['next_run_at']}"
    )
    return config


def emit(message: str, callback: LogCallback | None = None) -> None:
    append_log(message)
    if callback:
        callback(message)


def iter_process_lines(process: subprocess.Popen) -> Iterable[str]:
    assert process.stdout is not None
    for line in process.stdout:
        yield line.rstrip("\n")


def run_generation(callback: LogCallback | None = None) -> tuple[int, str | None]:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--generate-now"]
    else:
        command = [sys.executable, str(GENERATOR_PATH)]

    if not getattr(sys, "frozen", False) and not GENERATOR_PATH.exists():
        raise FileNotFoundError(f"Cannot find generator script: {GENERATOR_PATH}")

    emit(f"Starting article generation with: {' '.join(command)}", callback)

    output_dir = None
    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in iter_process_lines(process):
        append_log(line)
        if callback:
            callback(line)
        if line.startswith("Output folder:"):
            output_dir = line.split(":", 1)[1].strip()

    return_code = process.wait()
    emit(f"Article generation finished with exit code {return_code}", callback)
    return return_code, output_dir


def run_generation_batch(
    article_count: int,
    callback: LogCallback | None = None,
) -> tuple[int, list[str]]:
    count = max(1, int(article_count))
    output_dirs: list[str] = []
    failures = 0
    first_failure_code = 0

    for index in range(count):
        if count > 1:
            emit(f"Starting article {index + 1} of {count}.", callback)
        return_code, output_dir = run_generation(callback)
        if output_dir:
            output_dirs.append(output_dir)
        if return_code != 0:
            failures += 1
            if first_failure_code == 0:
                first_failure_code = return_code

    if failures:
        emit(f"Batch finished with {count - failures}/{count} article(s) successful.", callback)
        return first_failure_code or 1, output_dirs

    emit(f"Batch finished successfully: {count}/{count} article(s).", callback)
    return 0, output_dirs


def batch_status(return_code: int, article_count: int) -> str:
    count = max(1, int(article_count))
    if return_code == 0:
        return f"Success ({count}/{count} articles)"
    return f"Failed with exit code {return_code}"


def run_manual_generation(
    callback: LogCallback | None = None,
    article_count: int = 1,
) -> tuple[int, list[str]]:
    started_at = _now()
    return_code, output_dirs = run_generation_batch(article_count, callback)
    config = load_config()
    config.update(
        {
            "last_run_at": started_at.isoformat(),
            "last_status": batch_status(return_code, article_count),
            "last_output_dir": output_dirs[-1] if output_dirs else None,
            "last_output_dirs": output_dirs,
        }
    )
    save_config(config)
    return return_code, output_dirs


def run_due_generation(callback: LogCallback | None = None) -> bool:
    config = load_config()
    now = _now()
    next_run_at = parse_datetime(config.get("next_run_at"))
    article_count = max(1, int(config.get("articles_per_run", 1)))

    if not config.get("enabled", True):
        emit("Scheduler is disabled; no article generated.", callback)
        return False

    if next_run_at and now < next_run_at:
        emit(f"No article due. Next run is {next_run_at.isoformat(sep=' ', timespec='minutes')}.", callback)
        return False

    emit(f"Schedule is due; launching {article_count} article(s).", callback)
    return_code, output_dirs = run_generation_batch(article_count, callback)

    config.update(
        {
            "last_run_at": now.isoformat(),
            "last_status": batch_status(return_code, article_count),
            "last_output_dir": output_dirs[-1] if output_dirs else None,
            "last_output_dirs": output_dirs,
            "next_run_at": next_run_after(now, config["interval_days"], config["run_time"]).isoformat(),
        }
    )
    save_config(config)
    emit(f"Next scheduled run: {config['next_run_at']}", callback)
    return return_code == 0


def build_task_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --run-due'
    return f'"{sys.executable}" "{BASE_DIR / "article_scheduler.py"}" --run-due'


def install_windows_task(run_time: str) -> subprocess.CompletedProcess:
    parse_run_time(run_time)
    return subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/SC",
            "DAILY",
            "/ST",
            run_time,
            "/TR",
            build_task_command(),
            "/F",
        ],
        text=True,
        capture_output=True,
    )


def remove_windows_task() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        text=True,
        capture_output=True,
    )


def _without_cron_block(crontab: str) -> str:
    pattern = re.compile(
        rf"{re.escape(CRON_BEGIN)}.*?{re.escape(CRON_END)}\s*",
        flags=re.DOTALL,
    )
    return pattern.sub("", crontab).rstrip() + "\n"


def install_cron(run_time: str) -> subprocess.CompletedProcess:
    run_at = parse_run_time(run_time)
    current = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    existing = current.stdout if current.returncode == 0 else ""
    cleaned = _without_cron_block(existing)
    command = (
        f'{run_at.minute} {run_at.hour} * * * cd "{BASE_DIR}" && '
        f'{build_task_command()} >> "{BASE_DIR / "scheduler_cron.log"}" 2>&1'
    )
    updated = f"{cleaned}{CRON_BEGIN}\n{command}\n{CRON_END}\n"
    return subprocess.run(["crontab", "-"], input=updated, text=True, capture_output=True)


def remove_cron() -> subprocess.CompletedProcess:
    current = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    existing = current.stdout if current.returncode == 0 else ""
    updated = _without_cron_block(existing)
    return subprocess.run(["crontab", "-"], input=updated, text=True, capture_output=True)


def install_os_schedule(
    interval_days: int,
    run_time: str,
    immediate_run_at: datetime | None = None,
    articles_per_run: int = 1,
) -> subprocess.CompletedProcess:
    if int(interval_days) <= 0:
        update_schedule(0, run_time, articles_per_run=articles_per_run, enabled=False)
        if platform.system().lower().startswith("win"):
            remove_windows_task()
        else:
            remove_cron()
        result = subprocess.CompletedProcess(
            args=["no-recurring-schedule"],
            returncode=0,
            stdout="One-time run selected; no recurring schedule installed.\n",
            stderr="",
        )
        append_log(result.stdout.strip())
        return result

    update_schedule(
        interval_days,
        run_time,
        articles_per_run=articles_per_run,
        enabled=True,
        immediate_run_at=immediate_run_at,
    )
    if platform.system().lower().startswith("win"):
        result = install_windows_task(run_time)
    else:
        result = install_cron(run_time)

    append_log(result.stdout.strip() or result.stderr.strip() or f"Install returned {result.returncode}")
    return result


def remove_os_schedule() -> subprocess.CompletedProcess:
    config = load_config()
    config["enabled"] = False
    save_config(config)

    if platform.system().lower().startswith("win"):
        result = remove_windows_task()
    else:
        result = remove_cron()

    append_log(result.stdout.strip() or result.stderr.strip() or f"Remove returned {result.returncode}")
    return result


def format_status(config: dict | None = None) -> str:
    config = config or load_config()
    fields = [
        f"Enabled: {config.get('enabled')}",
        f"Interval days: {config.get('interval_days')}",
        f"Articles per run: {config.get('articles_per_run')}",
        f"Run time: {config.get('run_time')}",
        f"Next run: {config.get('next_run_at')}",
        f"Last run: {config.get('last_run_at') or 'Never'}",
        f"Last status: {config.get('last_status') or 'Unknown'}",
    ]
    if config.get("last_output_dir"):
        fields.append(f"Last output: {config['last_output_dir']}")
    return "\n".join(fields)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Schedule or run Auto_generate_article.")
    parser.add_argument("--run-due", action="store_true", help="Run generate.py only if the saved schedule is due.")
    parser.add_argument("--run-now", action="store_true", help="Run generate.py immediately.")
    parser.add_argument("--install", action="store_true", help="Install the OS scheduled task or cron entry.")
    parser.add_argument("--remove", action="store_true", help="Remove the OS scheduled task or cron entry.")
    parser.add_argument("--status", action="store_true", help="Print saved schedule status.")
    parser.add_argument("--interval-days", type=int, default=None, help="Number of days between generated articles.")
    parser.add_argument("--article-count", type=int, default=None, help="Number of articles to generate per run.")
    parser.add_argument("--run-time", default=None, help="Daily check time in HH:MM 24-hour format.")
    args = parser.parse_args(argv)

    if args.interval_days is not None or args.run_time is not None or args.article_count is not None:
        config = load_config()
        update_schedule(
            args.interval_days if args.interval_days is not None else int(config["interval_days"]),
            args.run_time if args.run_time is not None else str(config["run_time"]),
            articles_per_run=(
                args.article_count if args.article_count is not None else int(config["articles_per_run"])
            ),
            enabled=bool(config.get("enabled", True)),
        )

    if args.install:
        config = load_config()
        result = install_os_schedule(
            int(config["interval_days"]),
            str(config["run_time"]),
            articles_per_run=int(config["articles_per_run"]),
        )
        print(result.stdout or result.stderr, end="")
        return result.returncode

    if args.remove:
        result = remove_os_schedule()
        print(result.stdout or result.stderr, end="")
        return result.returncode

    if args.run_now:
        config = load_config()
        article_count = args.article_count if args.article_count is not None else int(config["articles_per_run"])
        return_code, _ = run_manual_generation(print, article_count=article_count)
        return return_code

    if args.run_due:
        return 0 if run_due_generation(print) else 0

    if args.status:
        print(format_status())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
