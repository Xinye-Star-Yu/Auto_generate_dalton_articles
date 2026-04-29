"""
Minimal Tkinter GUI for article scheduling.

Run with:
    python scheduler_gui.py
"""

from __future__ import annotations

import csv
import queue
import sys
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from auto_generate_dalton_articles import scheduler as article_scheduler

DEFAULT_RUN_TIME = "09:00"
LOG_PREVIEW_LINES = 120


class SchedulerGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Article Scheduler")
        self.minsize(960, 520)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.interval_var = tk.StringVar()
        self.article_count_var = tk.StringVar()
        self.new_doi_var = tk.StringVar()
        self.new_date_var = tk.StringVar(value=date.today().isoformat())
        self.doi_rows: list[dict[str, str]] = []

        self._build_ui()
        self._load_config()
        self._refresh_doi_csv()
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

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        log_frame = ttk.Frame(notebook)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        notebook.add(log_frame, text="Logs")

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        doi_frame = ttk.Frame(notebook)
        doi_frame.columnconfigure(0, weight=1)
        doi_frame.rowconfigure(2, weight=1)
        notebook.add(doi_frame, text="DOI History")

        doi_actions = ttk.Frame(doi_frame)
        doi_actions.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        doi_actions.columnconfigure(0, weight=1)
        self.doi_status_var = tk.StringVar(value="Loaded 0 DOI rows.")
        ttk.Label(doi_actions, textvariable=self.doi_status_var).grid(row=0, column=0, sticky="w")
        self.delete_doi_button = ttk.Button(doi_actions, text="Delete Selected", command=self._delete_selected_doi_rows)
        self.delete_doi_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.refresh_doi_button = ttk.Button(doi_actions, text="Refresh", command=self._refresh_doi_csv)
        self.refresh_doi_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

        add_frame = ttk.Frame(doi_frame)
        add_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
        add_frame.columnconfigure(1, weight=3)
        add_frame.columnconfigure(3, weight=1)
        ttk.Label(add_frame, text="DOI").grid(row=0, column=0, sticky="w")
        ttk.Entry(add_frame, textvariable=self.new_doi_var).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(add_frame, text="Date").grid(row=0, column=2, sticky="w")
        ttk.Entry(add_frame, textvariable=self.new_date_var, width=12).grid(row=0, column=3, sticky="ew", padx=(6, 12))
        self.add_doi_button = ttk.Button(add_frame, text="Add Row", command=self._add_doi_row)
        self.add_doi_button.grid(row=0, column=4, sticky="e")

        columns = ("doi_norm", "date")
        self.doi_tree = ttk.Treeview(doi_frame, columns=columns, show="headings")
        for column in columns:
            self.doi_tree.heading(column, text=column)
        self.doi_tree.column("doi_norm", width=360, minwidth=240, stretch=True)
        self.doi_tree.column("date", width=120, minwidth=90, stretch=False)
        self.doi_tree.grid(row=2, column=0, sticky="nsew", padx=(10, 0), pady=10)

        doi_y_scrollbar = ttk.Scrollbar(doi_frame, orient="vertical", command=self.doi_tree.yview)
        doi_y_scrollbar.grid(row=2, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.doi_tree.configure(yscrollcommand=doi_y_scrollbar.set)

        doi_x_scrollbar = ttk.Scrollbar(doi_frame, orient="horizontal", command=self.doi_tree.xview)
        doi_x_scrollbar.grid(row=3, column=0, sticky="ew", padx=(10, 0), pady=(0, 10))
        self.doi_tree.configure(xscrollcommand=doi_x_scrollbar.set)

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

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.start_button.configure(state=state)
        self.refresh_doi_button.configure(state=state)
        self.add_doi_button.configure(state=state)
        self.delete_doi_button.configure(state=state)

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
                self._refresh_doi_csv()
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

    def _refresh_doi_csv(self) -> None:
        csv_path = article_scheduler.duplication_csv_path()
        for item in self.doi_tree.get_children():
            self.doi_tree.delete(item)
        self.doi_rows = []

        if not csv_path.exists():
            self.doi_status_var.set("DOI history file was not found.")
            return

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
                rows = list(csv.DictReader(csv_file))
        except Exception as exc:
            self.doi_status_var.set(f"Could not read DOI history: {exc}")
            return

        self.doi_rows = [
            {
                "doi_norm": row.get("doi_norm", ""),
                "date": row.get("date", ""),
            }
            for row in rows
        ]
        for index, row in enumerate(self.doi_rows):
            self.doi_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row.get("doi_norm", ""),
                    row.get("date", ""),
                ),
            )
        self.doi_status_var.set(f"Loaded {len(rows)} DOI row(s) from {csv_path.name}.")

    def _write_doi_rows(self, rows: list[dict[str, str]]) -> None:
        csv_path = article_scheduler.duplication_csv_path()
        with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["doi_norm", "date"])
            writer.writeheader()
            writer.writerows(rows)
        self._refresh_doi_csv()

    def _add_doi_row(self) -> None:
        doi = self.new_doi_var.get().strip().lower()
        row_date = self.new_date_var.get().strip() or date.today().isoformat()

        if not doi:
            messagebox.showerror("Missing DOI", "Enter a DOI before adding a row.")
            return

        if any(row.get("doi_norm", "").lower() == doi for row in self.doi_rows):
            should_add = messagebox.askyesno(
                "Duplicate DOI",
                "This DOI is already in the history. Add it anyway?",
            )
            if not should_add:
                return

        rows = list(self.doi_rows)
        rows.append({"doi_norm": doi, "date": row_date})
        try:
            self._write_doi_rows(rows)
        except Exception as exc:
            messagebox.showerror("Could Not Add Row", str(exc))
            return

        self.new_doi_var.set("")
        self.doi_status_var.set(f"Added DOI row. Loaded {len(rows)} DOI row(s).")

    def _delete_selected_doi_rows(self) -> None:
        selected = self.doi_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Select one or more DOI rows to delete.")
            return

        should_delete = messagebox.askyesno(
            "Delete DOI Rows",
            f"Delete {len(selected)} selected DOI row(s)?",
        )
        if not should_delete:
            return

        selected_indexes = {int(item) for item in selected}
        rows = [row for index, row in enumerate(self.doi_rows) if index not in selected_indexes]
        try:
            self._write_doi_rows(rows)
        except Exception as exc:
            messagebox.showerror("Could Not Delete Rows", str(exc))
            return

        self.doi_status_var.set(f"Deleted {len(selected)} row(s). Loaded {len(rows)} DOI row(s).")


def main() -> None:
    if "--generate-now" in sys.argv[1:]:
        from auto_generate_dalton_articles import generate

        raise SystemExit(generate.main() or 0)

    if len(sys.argv) > 1:
        raise SystemExit(article_scheduler.main(sys.argv[1:]))

    app = SchedulerGui()
    app.mainloop()


if __name__ == "__main__":
    main()
