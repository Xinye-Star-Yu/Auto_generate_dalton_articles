"""
Minimal Tkinter GUI for article scheduling.

Run with:
    python scheduler_gui.py
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import article_scheduler

DEFAULT_RUN_TIME = "09:00"
LOG_PREVIEW_LINES = 120


class SchedulerGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Article Scheduler")
        self.minsize(720, 420)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.interval_var = tk.StringVar()
        self.article_count_var = tk.StringVar()

        self._build_ui()
        self._load_config()
        self.after(150, self._drain_log_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        controls.columnconfigure(6, weight=1)

        ttk.Label(controls, text="Articles").grid(row=0, column=0, sticky="w")
        amount = ttk.Spinbox(controls, from_=1, to=25, textvariable=self.article_count_var, width=8)
        amount.grid(row=0, column=1, sticky="w", padx=(8, 16))

        ttk.Label(controls, text="Repeat every").grid(row=0, column=2, sticky="w")
        interval = ttk.Spinbox(controls, from_=0, to=365, textvariable=self.interval_var, width=8)
        interval.grid(row=0, column=3, sticky="w", padx=(8, 6))
        ttk.Label(controls, text="days").grid(row=0, column=4, sticky="w", padx=(0, 16))

        self.start_button = ttk.Button(controls, text="Start", command=self.start_schedule)
        self.start_button.grid(row=0, column=5, sticky="ew", padx=(0, 8))

        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop_schedule)
        self.stop_button.grid(row=0, column=6, sticky="w")

        log_frame = ttk.LabelFrame(self, text="Logs")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _load_config(self) -> None:
        config = article_scheduler.load_config()
        self.interval_var.set(str(config["interval_days"]))
        self.article_count_var.set(str(config.get("articles_per_run", 1)))
        self._append_log(
            f"Loaded schedule: {config.get('articles_per_run', 1)} article(s) "
            f"every {config['interval_days']} day(s)."
        )
        self._append_log(f"Last status: {config.get('last_status') or 'Never run'}")
        if config.get("next_run_at"):
            self._append_log(f"Next run: {config['next_run_at']}")
        self._append_recent_log()

    def _get_interval_days(self) -> int:
        try:
            interval_days = int(self.interval_var.get())
        except ValueError as exc:
            raise ValueError("Days must be a whole number.") from exc
        if interval_days < 0:
            raise ValueError("Days must be 0 or greater.")
        return interval_days

    def _get_article_count(self) -> int:
        try:
            article_count = int(self.article_count_var.get())
        except ValueError as exc:
            raise ValueError("Articles must be a whole number.") from exc
        if article_count < 1:
            raise ValueError("Articles must be at least 1.")
        return article_count

    def _run_time(self) -> str:
        config = article_scheduler.load_config()
        run_time = str(config.get("run_time") or DEFAULT_RUN_TIME)
        try:
            article_scheduler.parse_run_time(run_time)
        except ValueError:
            return DEFAULT_RUN_TIME
        return run_time

    def start_schedule(self) -> None:
        try:
            interval_days = self._get_interval_days()
            article_count = self._get_article_count()
        except Exception as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return

        def work() -> None:
            run_time = self._run_time()
            if interval_days == 0:
                result = article_scheduler.install_os_schedule(
                    0,
                    run_time,
                    articles_per_run=article_count,
                )
                output = (result.stdout or result.stderr or "").strip()
                self.log_queue.put(output)
                self.log_queue.put(f"Starting one-time generation for {article_count} article(s).")
                return_code, _ = article_scheduler.run_manual_generation(
                    self.log_queue.put,
                    article_count=article_count,
                )
                self.log_queue.put(f"One-time run finished with exit code {return_code}.")
                return

            immediate_run_at = datetime.now().replace(microsecond=0)
            result = article_scheduler.install_os_schedule(
                interval_days,
                run_time,
                immediate_run_at,
                articles_per_run=article_count,
            )
            output = (result.stdout or result.stderr or "").strip()
            self.log_queue.put(output or f"Scheduler started with exit code {result.returncode}.")
            config = article_scheduler.load_config()
            self.log_queue.put(
                f"Running {config['articles_per_run']} article(s) every "
                f"{config['interval_days']} day(s)."
            )
            self.log_queue.put(f"Next run: {config['next_run_at']}")
            self.log_queue.put(f"Starting immediate generation for {article_count} article(s).")
            return_code, _ = article_scheduler.run_manual_generation(
                self.log_queue.put,
                article_count=article_count,
            )
            self.log_queue.put(f"Immediate run finished with exit code {return_code}.")

        self._start_worker(work)

    def stop_schedule(self) -> None:
        def work() -> None:
            result = article_scheduler.remove_os_schedule()
            output = (result.stdout or result.stderr or "").strip()
            self.log_queue.put(output or f"Scheduler stopped with exit code {result.returncode}.")

        self._start_worker(work)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.start_button.configure(state=state)
        self.stop_button.configure(state=state)

    def _start_worker(self, target) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Busy", "The scheduler is already working.")
            return

        self._set_buttons_enabled(False)

        def guarded() -> None:
            try:
                target()
            except Exception as exc:
                self.log_queue.put(f"ERROR: {exc}")
            finally:
                self.log_queue.put("__DONE__")

        self.worker_thread = threading.Thread(target=guarded, daemon=True)
        self.worker_thread.start()

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if message == "__DONE__":
                self._set_buttons_enabled(True)
            else:
                self._append_log(message)

        self.after(150, self._drain_log_queue)

    def _append_log(self, message: str) -> None:
        if not message:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_recent_log(self) -> None:
        if not article_scheduler.LOG_PATH.exists():
            return
        lines = article_scheduler.LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = lines[-LOG_PREVIEW_LINES:]
        if not recent:
            return
        self._append_log("")
        self._append_log("Recent scheduler.log entries:")
        for line in recent:
            self._append_log(line)


def main() -> None:
    if "--generate-now" in sys.argv[1:]:
        import generate

        raise SystemExit(generate.main() or 0)

    if len(sys.argv) > 1:
        raise SystemExit(article_scheduler.main(sys.argv[1:]))

    app = SchedulerGui()
    app.mainloop()


if __name__ == "__main__":
    main()
