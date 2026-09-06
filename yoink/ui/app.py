from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from yoink.config import load_settings, save_settings
from yoink.core.engine import DownloadEngine
from yoink.core.models import DownloadJob, JobStatus
from yoink.core.presets import PRESETS
from yoink.themes.manager import ThemeManager


class YoinkApp(ctk.CTk):
    def __init__(self):
        self.settings = load_settings()
        self.themes = ThemeManager()
        self.theme = self.themes.load(self.settings.theme)
        ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
        ctk.set_default_color_theme("dark-blue")
        super().__init__()
        self.title("YOINK")
        self.geometry(self.settings.window_geometry)
        self.minsize(760, 540)
        self.configure(fg_color=self.theme["bg"])
        self.engine = DownloadEngine(_ffmpeg_path(), self.settings.workers)
        self.jobs: list[DownloadJob] = []
        self.rows: dict[str, tuple] = {}
        self._build()
        self.after(250, self._refresh)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(24, 10), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="YOINK",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=self.theme["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="media, neatly gathered", text_color=self.theme["text_muted"]
        ).grid(row=1, column=0, sticky="w")
        self.theme_menu = ctk.CTkOptionMenu(
            header,
            values=self.themes.available(),
            command=self._change_theme,
            fg_color=self.theme["surface_alt"],
            button_color=self.theme["accent"],
            button_hover_color=self.theme["accent_hover"],
        )
        self.theme_menu.set(self.settings.theme)
        self.theme_menu.grid(row=0, column=2, rowspan=2, padx=(12, 0))

        add = ctk.CTkFrame(self, fg_color=self.theme["surface"], corner_radius=14)
        add.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        add.grid_columnconfigure(0, weight=1)
        self.url_box = ctk.CTkTextbox(
            add,
            height=76,
            border_width=1,
            border_color=self.theme["border"],
            fg_color=self.theme["surface_alt"],
        )
        self.url_box.grid(row=0, column=0, padx=14, pady=14, sticky="ew")
        self.url_box.insert("1.0", "Paste one or more media URLs, one per line")
        self.url_box.bind("<FocusIn>", self._clear_placeholder)
        ctk.CTkButton(
            add,
            text="Add to queue",
            command=self._add_jobs,
            width=130,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
        ).grid(row=0, column=1, padx=(0, 14), pady=14)

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=2, column=0, padx=28, pady=(2, 0), sticky="ew")
        ctk.CTkLabel(options, text="Preset", text_color=self.theme["text_muted"]).pack(
            side="left", padx=(0, 8)
        )
        self.preset_menu = ctk.CTkOptionMenu(
            options,
            values=list(PRESETS),
            command=self._set_preset,
            fg_color=self.theme["surface_alt"],
            button_color=self.theme["accent"],
            button_hover_color=self.theme["accent_hover"],
        )
        self.preset_menu.set(self.settings.preset)
        self.preset_menu.pack(side="left")
        self.clip_start = ctk.CTkEntry(options, width=100, placeholder_text="Start")
        self.clip_start.pack(side="left", padx=(20, 5))
        self.clip_end = ctk.CTkEntry(options, width=100, placeholder_text="End")
        self.clip_end.pack(side="left")
        ctk.CTkButton(
            options,
            text="Output folder",
            command=self._choose_output,
            width=115,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="right")
        ctk.CTkButton(
            options,
            text="Settings",
            command=self._settings_dialog,
            width=85,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="right", padx=5)

        self.queue = ctk.CTkScrollableFrame(
            self,
            label_text="DOWNLOAD QUEUE",
            label_text_color=self.theme["text_muted"],
            fg_color=self.theme["bg"],
        )
        self.queue.grid(row=3, column=0, padx=22, pady=(8, 0), sticky="nsew")
        self.grid_rowconfigure(3, weight=1)
        self.status_label = ctk.CTkLabel(
            self, text="Ready", anchor="w", text_color=self.theme["text_muted"]
        )
        self.status_label.grid(row=4, column=0, padx=28, pady=12, sticky="ew")

    def _clear_placeholder(self, _event):
        if self.url_box.get("1.0", "end").strip().startswith("Paste one or more"):
            self.url_box.delete("1.0", "end")

    def _add_jobs(self):
        urls = [
            line.strip()
            for line in self.url_box.get("1.0", "end").splitlines()
            if line.strip() and not line.startswith("Paste one or more")
        ]
        if not urls:
            messagebox.showwarning("YOINK", "Paste at least one URL first.")
            return
        Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        for url in urls:
            job = DownloadJob(
                url,
                self.settings.output_dir,
                self.preset_menu.get(),
                start=self.clip_start.get() or None,
                end=self.clip_end.get() or None,
                cookies_path=self.settings.cookies_path or None,
                recode_mp4=self.settings.recode_mp4,
            )
            self.jobs.append(job)
            self.engine.submit(job)
            self._add_row(job)
        self.url_box.delete("1.0", "end")
        self.status_label.configure(text=f"Queued {len(urls)} item(s)")

    def _set_preset(self, name):
        self.settings.preset = name
        save_settings(self.settings)

    def _choose_output(self):
        selected = filedialog.askdirectory(initialdir=self.settings.output_dir)
        if selected:
            self.settings.output_dir = selected
            save_settings(self.settings)
            self.status_label.configure(text=f"Output: {selected}")

    def _settings_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("YOINK Settings")
        dialog.geometry("520x230")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Cookies file (Netscape format)", anchor="w").pack(
            fill="x", padx=20, pady=(20, 4)
        )
        line = ctk.CTkFrame(dialog, fg_color="transparent")
        line.pack(fill="x", padx=20)
        entry = ctk.CTkEntry(line)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, self.settings.cookies_path)

        def choose_cookies():
            selected = filedialog.askopenfilename(
                filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")]
            )
            if selected:
                entry.delete(0, "end")
                entry.insert(0, selected)

        ctk.CTkButton(line, text="Browse", width=80, command=choose_cookies).pack(
            side="left", padx=(8, 0)
        )
        recode = tk.BooleanVar(value=self.settings.recode_mp4)
        ctk.CTkCheckBox(
            dialog,
            text="Force full MP4 re-encode (slow, maximum compatibility)",
            variable=recode,
        ).pack(anchor="w", padx=20, pady=18)

        def save():
            self.settings.cookies_path = entry.get().strip()
            self.settings.recode_mp4 = recode.get()
            save_settings(self.settings)
            dialog.destroy()

        ctk.CTkButton(
            dialog,
            text="Save settings",
            command=save,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
        ).pack(anchor="e", padx=20)

    def _add_row(self, job):
        row = ctk.CTkFrame(self.queue, fg_color=self.theme["surface"], corner_radius=10)
        row.pack(fill="x", padx=4, pady=5)
        row.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            row, text=job.url, anchor="w", text_color=self.theme["text"]
        )
        title.grid(row=0, column=0, padx=14, pady=(10, 2), sticky="ew")
        detail = ctk.CTkLabel(
            row, text="Queued", anchor="w", text_color=self.theme["text_muted"]
        )
        detail.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        progress = ctk.CTkProgressBar(
            row,
            progress_color=self.theme["progress_fill"],
            fg_color=self.theme["progress_track"],
        )
        progress.set(0)
        progress.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")
        cancel = ctk.CTkButton(
            row,
            text="Cancel",
            width=74,
            fg_color=self.theme["danger"],
            hover_color="#8F4D49",
            command=job.cancel,
        )
        cancel.grid(row=0, column=1, rowspan=3, padx=14)
        self.rows[job.id] = (title, detail, progress, cancel)

    def _refresh(self):
        for job in self.jobs:
            title, detail, progress, cancel = self.rows[job.id]
            snap = job.snapshot()
            status = snap["status"]
            title.configure(
                text=snap["title"]
                if snap["title"] != "Waiting for media information"
                else job.url
            )
            label = status.value.title()
            if snap["speed"]:
                label += f"  •  {snap['speed']}  •  ETA {snap['eta'] or '-'}"
            if snap["error"]:
                label = snap["error"]
            detail.configure(
                text=label,
                text_color=self.theme["danger"]
                if status == JobStatus.FAILED
                else self.theme["text_muted"],
            )
            progress.set(snap["percent"] / 100)
            cancel.configure(
                state="disabled"
                if status in {JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED}
                else "normal"
            )
        self.after(250, self._refresh)

    def _change_theme(self, name):
        try:
            self.theme = self.themes.load(name)
            self.settings.theme = name
            save_settings(self.settings)
            ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
            self._rebuild()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Theme error", str(exc))

    def _rebuild(self):
        for child in self.winfo_children():
            child.destroy()
        self.rows.clear()
        self._build()
        for job in self.jobs:
            self._add_row(job)

    def _close(self):
        self.settings.window_geometry = str(self.geometry())
        save_settings(self.settings)
        self.engine.shutdown()
        self.destroy()


def _ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which("ffmpeg")


def run():
    YoinkApp().mainloop()
