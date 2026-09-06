import math
import random
import re
import shutil
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from yoink.config import (
    AUDIO_QUALITIES,
    VIDEO_QUALITIES,
    load_settings,
    save_settings,
)
from yoink.core.codecs import CODECS, get_codec
from yoink.core.engine import DownloadEngine
from yoink.core.inspection import inspect_urls
from yoink.core.models import DownloadJob, JobStatus
from yoink.themes.manager import ThemeManager
from yoink.ui.assets import ThumbnailCache, asset_path, local_image, placeholder
from yoink.ui.design import card, fonts

FINISHED = {JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED}
APP_VERSION = "v1.1"
DEFAULT_GEOMETRY = "720x480"
MIN_SIZE = (720, 480)
_BACKGROUND_CHOICES = {
    "off": "Off",
    "random": "Random from bundled art",
    "selected": "Custom image…",
}


class YoinkApp(ctk.CTk):
    def __init__(self):
        self.settings = load_settings()
        self.themes = ThemeManager()
        self.theme = self.themes.load(self.settings.theme)
        ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
        ctk.set_default_color_theme("dark-blue")
        super().__init__()
        self.title("YOINK")
        try:
            self.iconbitmap(str(asset_path("icons", "luna.ico")))
        except tk.TclError:
            # Some Tk builds cannot load ICO files; the in-app PNG remains available.
            pass
        self._apply_geometry(self.settings.window_geometry)
        self.minsize(*MIN_SIZE)
        self.configure(fg_color=self.theme["bg"])
        self.engine = DownloadEngine(_ffmpeg_path(), self.settings.workers)
        self.jobs: list[DownloadJob] = []
        self.media: list[dict] = []
        self.selected: dict[str, tk.BooleanVar] = {}
        self.rows: dict[str, tuple] = {}
        self._background = None
        self._background_label = None
        self._thumbnail_cache = ThumbnailCache()
        self._fonts = fonts()
        self._queue_empty = None
        self._status_transient: tuple[str, float] | None = None
        self._build()
        self._load_background()
        self.after(200, self._ensure_on_screen)
        self.after(250, self._refresh)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_geometry(self, geometry: str) -> None:
        if re.fullmatch(r"\d+x\d+(?:[+-]\d+){0,2}", geometry or ""):
            self.geometry(geometry)
        else:
            self.geometry(DEFAULT_GEOMETRY)

    def _ensure_on_screen(self) -> None:
        bounds = _virtual_screen_bounds()
        if bounds is None:
            return
        left, top, width, height = bounds
        x, y = self.winfo_x(), self.winfo_y()
        window_width, window_height = self.winfo_width(), self.winfo_height()
        visible = (
            x < left + width - 80
            and x + window_width > left + 80
            and y < top + height - 40
            and y + window_height > top + 40
        )
        if visible:
            return
        new_width = min(window_width, width)
        new_height = min(window_height, height - 40)
        new_x = min(max(left, x), left + width - new_width)
        new_y = min(max(top, y), top + height - new_height)
        tk.Tk.geometry(self, f"{new_width}x{new_height}+{new_x}+{new_y}")

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(22, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        logo = local_image(asset_path("icons", "main-icon-nobg.png"), (46, 46))
        ctk.CTkLabel(header, text="", image=logo).grid(
            row=0, column=0, rowspan=2, padx=(0, 10)
        )
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=1, rowspan=2, sticky="w")
        brand_title = ctk.CTkLabel(
            brand,
            text="YOINK",
            font=self._fonts["brand"],
            text_color=self.theme["accent"],
            cursor="hand2",
        )
        brand_title.grid(row=0, column=0, sticky="w")
        brand_title.bind("<Button-1>", lambda _event: self._about_dialog())
        brand_title.bind(
            "<Enter>",
            lambda _event: brand_title.configure(text_color=self.theme["accent_hover"]),
        )
        brand_title.bind(
            "<Leave>",
            lambda _event: brand_title.configure(text_color=self.theme["accent"]),
        )
        ctk.CTkLabel(
            brand,
            text="Multi-media Yoinkers, made with ♡ by Astartes.",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        ).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Settings",
            width=92,
            command=self._settings_dialog,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).grid(row=0, column=2, rowspan=2)

        add = ctk.CTkFrame(
            self,
            fg_color=self.theme["surface"],
            border_width=1,
            border_color=self.theme["border"],
            corner_radius=14,
        )
        add.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        add.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            add,
            text="Add URL(s)",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, padx=16, pady=(13, 0), sticky="w")
        self.url_box = ctk.CTkTextbox(
            add,
            height=70,
            border_width=1,
            border_color=self.theme["border"],
            fg_color=self.theme["surface_alt"],
        )
        self.url_box.grid(row=1, column=0, padx=14, pady=(7, 14), sticky="ew")
        self.url_box.insert("1.0", "Paste a video, playlist, or media URL...")
        self.url_box.bind("<FocusIn>", self._clear_placeholder)
        self.url_box.bind("<Control-Return>", lambda _: self._inspect())
        actions = ctk.CTkFrame(add, fg_color="transparent")
        actions.grid(
            row=0, column=1, rowspan=2, padx=(10, 14), pady=(13, 14), sticky="e"
        )
        ctk.CTkLabel(
            actions,
            text="Paste one or more media links to get started.",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        ).pack(anchor="e", pady=(0, 8))
        ctk.CTkButton(
            actions,
            text="Inspect",
            command=self._inspect,
            width=105,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme.get("accent_text", self.theme["bg"]),
        ).pack(anchor="e")
        ctk.CTkButton(
            actions,
            text="Download",
            command=self._blind_download,
            width=105,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme.get("accent_text", self.theme["bg"]),
        ).pack(anchor="e", pady=(6, 0))

        self.content = ctk.CTkScrollableFrame(
            self,
            fg_color=self.theme["bg"],
        )
        self.content.grid(row=2, column=0, padx=28, pady=(8, 0), sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.workspace = ctk.CTkFrame(self.content, fg_color="transparent")
        self.workspace.grid(row=0, column=0, sticky="ew")
        self.workspace.grid_columnconfigure(0, weight=1)
        self.media_header = ctk.CTkLabel(
            self.workspace,
            text="Detected Media",
            text_color=self.theme["text_muted"],
            anchor="w",
        )
        self.media_header.grid(row=0, column=0, padx=4, pady=(0, 4), sticky="ew")
        self.media_list = ctk.CTkFrame(self.workspace, fg_color="transparent")
        self.media_list.grid(row=1, column=0, sticky="ew")
        self.media_list.grid_columnconfigure(0, weight=1)
        self._set_media_pane_visible(False)
        self._build_options()
        self._build_queue()
        self.status_label = ctk.CTkLabel(
            self,
            text=self._status_text(),
            anchor="w",
            text_color=self.theme["text_muted"],
        )
        self.status_label.grid(row=3, column=0, padx=28, pady=10, sticky="ew")

    def _set_media_pane_visible(self, visible: bool) -> None:
        if visible:
            self.workspace.grid()
            self.content.grid_rowconfigure(0, weight=0)
        else:
            self.workspace.grid_remove()
            self.content.grid_rowconfigure(0, weight=0)

    def _load_background(self):
        if self._background_label is not None and self._background_label.winfo_exists():
            self._background_label.destroy()
        self._background_label = None
        directory = asset_path("background")
        images = (
            [
                path
                for path in directory.iterdir()
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            if directory.is_dir()
            else []
        )
        if not images or self.settings.background_mode == "off":
            return
        if self.settings.background_mode == "selected":
            selected = Path(self.settings.background_path)
        else:
            selected = images[0]
            if self.settings.background_mode == "random":
                selected = random.choice(images)
        if not selected.is_file():
            return
        try:
            from PIL import Image

            image = Image.open(selected)
            image.thumbnail((1600, 1000))
            image = image.convert("RGB")
            dim = min(100, max(0, int(self.settings.background_dim)))
            if dim < 100:
                overlay = Image.new("RGB", image.size, (0, 0, 0))
                image = Image.blend(image, overlay, (100 - dim) / 100)
            self._background = ctk.CTkImage(
                light_image=image, dark_image=image, size=image.size
            )
            label = ctk.CTkLabel(self, text="", image=self._background)
            label.place(relx=0, rely=0, relwidth=1, relheight=1)
            label.lower()
            self._background_label = label
        except (OSError, ImportError):
            return

    def _apply_background(self) -> None:
        self._load_background()

    def _build_options(self):
        options = ctk.CTkFrame(
            self.content,
            fg_color=self.theme["surface"],
            border_width=1,
            border_color=self.theme["border"],
            corner_radius=12,
        )
        options.grid(row=1, column=0, padx=0, pady=(12, 8), sticky="ew")
        options.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            options,
            text="Download Settings",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, columnspan=4, padx=14, pady=(12, 0), sticky="w")
        self.options_hint = ctk.CTkLabel(
            options,
            text=self._options_hint(),
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        )
        self.options_hint.grid(
            row=1, column=0, columnspan=4, padx=14, pady=(2, 0), sticky="w"
        )
        for column, text in enumerate(("Format", "Quality", "Codec")):
            ctk.CTkLabel(
                options,
                text=text,
                text_color=self.theme["text_muted"],
                font=self._fonts["small"],
            ).grid(row=2, column=column, padx=14, pady=(14, 2), sticky="w")
        self.format_var = tk.StringVar(value=self.settings.default_format)
        ctk.CTkSegmentedButton(
            options,
            values=["Video", "Audio"],
            variable=self.format_var,
            command=self._format_changed,
            fg_color=self.theme["surface"],
            selected_color=self.theme.get("border_active", self.theme["border"]),
            selected_hover_color=self.theme.get("border_active", self.theme["border"]),
            unselected_color=self.theme["surface_alt"],
            unselected_hover_color=self.theme["border"],
            text_color=self.theme["text"],
        ).grid(row=3, column=0, padx=14, pady=(0, 12), sticky="w")
        self.quality_menu = ctk.CTkOptionMenu(
            options,
            values=self._quality_values(),
            command=self._set_quality,
            fg_color=self.theme["surface_alt"],
            button_color=self.theme["accent"],
            button_hover_color=self.theme["accent_hover"],
        )
        self.quality_menu.set(self.settings.default_quality)
        self.quality_menu.grid(row=3, column=1, padx=14, pady=(0, 12), sticky="w")
        self.codec_menu = ctk.CTkOptionMenu(
            options,
            values=list(CODECS),
            command=self._set_codec,
            fg_color=self.theme["surface_alt"],
            button_color=self.theme["accent"],
            button_hover_color=self.theme["accent_hover"],
        )
        self.codec_menu.set(self.settings.codec)
        self.codec_menu.grid(row=3, column=2, padx=14, pady=(0, 12), sticky="w")
        if self.format_var.get() == "Audio":
            self.codec_menu.configure(state="disabled")
        trim = ctk.CTkFrame(options, fg_color="transparent")
        trim.grid(row=4, column=0, columnspan=4, padx=14, pady=(0, 10), sticky="ew")
        ctk.CTkLabel(
            trim,
            text="Trim",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        ).pack(side="left")
        self.clip_start = ctk.CTkEntry(
            trim,
            width=110,
            placeholder_text="Start 00:00:00",
            border_color=self.theme["border"],
        )
        self.clip_start.pack(side="left", padx=(10, 6))
        ctk.CTkLabel(
            trim,
            text="to",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        ).pack(side="left")
        self.clip_end = ctk.CTkEntry(
            trim,
            width=110,
            placeholder_text="End 00:00:00",
            border_color=self.theme["border"],
        )
        self.clip_end.pack(side="left", padx=6)
        self.trim_hint = ctk.CTkLabel(
            trim,
            text="",
            text_color=self.theme["danger"],
            font=self._fonts["small"],
        )
        self.trim_hint.pack(side="left", padx=(10, 0))
        save = ctk.CTkFrame(
            options,
            fg_color=self.theme["surface_alt"],
            border_width=1,
            border_color=self.theme.get("border_active", self.theme["border"]),
            corner_radius=8,
        )
        save.grid(row=5, column=0, columnspan=4, padx=14, pady=(0, 14), sticky="ew")
        self.output_label = ctk.CTkLabel(
            save,
            text=self._output_text(),
            text_color=self.theme.get("text_secondary", self.theme["text"]),
            anchor="w",
            font=self._fonts["small"],
        )
        self.output_label.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=6)
        ctk.CTkButton(
            save,
            text="Browse",
            width=75,
            command=self._choose_output,
            fg_color=self.theme["surface"],
            hover_color=self.theme["border"],
        ).pack(side="right", padx=(0, 10), pady=6)
        self.clip_start.bind("<KeyRelease>", self._validate_trim)
        self.clip_end.bind("<KeyRelease>", self._validate_trim)

    def _build_queue(self):
        wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap.grid(row=2, column=0, pady=(8, 0), sticky="ew")
        wrap.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(wrap, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(
            bar,
            text="Download Queue",
            text_color=self.theme["text_muted"],
            anchor="w",
        ).pack(side="left", padx=4)
        self.clear_completed_button = ctk.CTkButton(
            bar,
            text="Clear Completed",
            width=120,
            state="disabled",
            command=self._clear_completed,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        )
        self.clear_completed_button.pack(side="right")
        self.queue = ctk.CTkFrame(wrap, fg_color="transparent")
        self.queue.grid(row=1, column=0, sticky="ew")
        self.queue.grid_columnconfigure(0, weight=1)
        self._queue_empty = None
        if not self.jobs:
            self._show_queue_empty()

    def _show_queue_empty(self):
        self._queue_empty = ctk.CTkFrame(self.queue, fg_color="transparent")
        self._queue_empty.pack(fill="both", expand=True, pady=28)
        unavailable = local_image(asset_path("icons", "not-available.png"), (72, 72))
        ctk.CTkLabel(self._queue_empty, text="", image=unavailable).pack(pady=(20, 6))
        ctk.CTkLabel(
            self._queue_empty,
            text="Nothing yoinked yet.",
            font=self._fonts["title"],
            text_color=self.theme["text"],
        ).pack()
        ctk.CTkLabel(
            self._queue_empty,
            text="Your downloads will appear here.",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(pady=3)

    def _quality_values(self, format_value: str | None = None):
        if format_value is None:
            format_value = self.format_var.get()
        return VIDEO_QUALITIES if format_value == "Video" else AUDIO_QUALITIES

    def _options_hint(self) -> str:
        if self.settings.default_format == "Audio":
            container = "MP3 audio"
        else:
            container = f"{get_codec(self.settings.codec).container.upper()} output"
        return f"Applies to new downloads · {container}"

    def _refresh_options_hint(self) -> None:
        if hasattr(self, "options_hint"):
            self.options_hint.configure(text=self._options_hint())

    def _format_changed(self, value):
        self.settings.default_format = value
        self.quality_menu.configure(values=self._quality_values(value))
        self.quality_menu.set("Best Available")
        self.settings.default_quality = "Best Available"
        self.codec_menu.configure(state="normal" if value == "Video" else "disabled")
        self._refresh_options_hint()
        save_settings(self.settings)

    def _set_codec(self, name):
        self.settings.codec = name
        self._refresh_options_hint()
        save_settings(self.settings)

    def _set_quality(self, value):
        self.settings.default_quality = value
        save_settings(self.settings)

    def _validate_trim(self, _event=None):
        valid = _valid_timestamp(self.clip_start.get()) and _valid_timestamp(
            self.clip_end.get()
        )
        border = self.theme["border"] if valid else self.theme["danger"]
        self.clip_start.configure(border_color=border)
        self.clip_end.configure(border_color=border)
        self.trim_hint.configure(
            text="" if valid else "Use seconds, MM:SS, or HH:MM:SS"
        )

    def _set_status(self, text: str, seconds: float = 4) -> None:
        self._status_transient = (text, time.monotonic() + seconds)
        if hasattr(self, "status_label"):
            self.status_label.configure(text=text)

    def _status_text(self) -> str:
        transient = self._status_transient
        if transient is not None:
            if time.monotonic() < transient[1]:
                return transient[0]
            self._status_transient = None
        if self.jobs:
            return f"Queue: {self._counts()}"
        return "Ready to yoink."

    def _clear_placeholder(self, _event):
        if self.url_box.get("1.0", "end").strip().startswith("Paste a video"):
            self.url_box.delete("1.0", "end")

    def _current_urls(self) -> str:
        if not hasattr(self, "url_box"):
            return ""
        text = self.url_box.get("1.0", "end").strip()
        return "" if text.startswith("Paste a video") else text

    def _inspect(self):
        urls = list(
            dict.fromkeys(
                line.strip()
                for line in self.url_box.get("1.0", "end").splitlines()
                if line.strip() and not line.startswith("Paste a video")
            )
        )
        if not urls:
            messagebox.showwarning(
                "YOINK", "Paste at least one URL first.", parent=self
            )
            return
        self._set_status(f"Inspecting {len(urls)} URL(s)...", seconds=60)
        threading.Thread(target=self._inspect_worker, args=(urls,), daemon=True).start()

    def _blind_download(self):
        urls = list(
            dict.fromkeys(
                line.strip()
                for line in self.url_box.get("1.0", "end").splitlines()
                if line.strip() and not line.startswith("Paste a video")
            )
        )
        if not urls:
            messagebox.showwarning(
                "YOINK", "Paste at least one URL first.", parent=self
            )
            return
        self._download_media(
            [
                {
                    "id": "",
                    "url": url,
                    "title": url,
                    "uploader": "Unknown uploader",
                    "duration": "Duration unavailable",
                    "source": "Direct URL",
                    "thumbnail": "",
                }
                for url in urls
            ]
        )

    def _inspect_worker(self, urls):
        try:
            media = inspect_urls(urls, self.settings.cookies_path)
        except Exception as exc:  # noqa: BLE001 - inspection errors must surface
            message = f"Inspection failed: {_friendly_error(exc)}"
            self.after(0, lambda: self._set_status(message, seconds=10))
            return
        self.after(0, lambda: self._show_media(media))

    def _show_media(self, media):
        for child in self.media_list.winfo_children():
            child.destroy()
        self.media = media
        self.selected = {}
        if not media:
            self._set_media_pane_visible(False)
            self._set_status("No media found at those links.", seconds=6)
            return
        self._set_media_pane_visible(True)
        for item in media:
            key = item["id"] or item["url"]
            self.selected[key] = tk.BooleanVar(value=True)
            row = card(self.media_list, self.theme)
            row.pack(fill="x", padx=3, pady=4)
            row.grid_columnconfigure(2, weight=1)
            ctk.CTkCheckBox(
                row,
                text="",
                variable=self.selected[key],
                width=25,
                command=self._update_selection,
            ).grid(row=0, column=0, rowspan=2, padx=10)
            thumb = ctk.CTkLabel(
                row,
                text="Media" if not item["thumbnail"] else "",
                image=placeholder(
                    (112, 64),
                    self.theme["surface_alt"],
                    self.theme.get("moon", self.theme["accent"]),
                ),
            )
            thumb.grid(row=0, column=1, rowspan=2, padx=(0, 10), pady=10)
            ctk.CTkLabel(
                row,
                text=item["title"],
                anchor="w",
                font=self._fonts["title"],
                text_color=self.theme["text"],
            ).grid(row=0, column=2, padx=4, pady=(9, 1), sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"{item['uploader']}  •  {item['duration']}  •  {item['source']}",
                anchor="w",
                text_color=self.theme["text_muted"],
            ).grid(row=1, column=2, padx=4, pady=(0, 9), sticky="ew")
            self._thumbnail_cache.load(
                self,
                item["thumbnail"],
                (112, 64),
                thumb.cget("image"),
                lambda image, widget=thumb: _set_thumbnail(widget, image),
            )
            ctk.CTkButton(
                row,
                text="Download",
                width=92,
                command=lambda value=item: self._download_media([value]),
                fg_color=self.theme["accent"],
                hover_color=self.theme["accent_hover"],
                text_color=self.theme.get("accent_text", self.theme["bg"]),
            ).grid(row=0, column=3, rowspan=2, padx=10)
        controls = ctk.CTkFrame(self.media_list, fg_color="transparent")
        controls.pack(fill="x", pady=8)
        ctk.CTkButton(
            controls,
            text="Select All",
            width=90,
            command=lambda: self._select_all(True),
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="left")
        ctk.CTkButton(
            controls,
            text="Clear",
            width=70,
            command=lambda: self._select_all(False),
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="left", padx=6)
        self.selection_label = ctk.CTkLabel(
            controls,
            text="0 selected",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        )
        self.selection_label.pack(side="left", padx=12)
        self.download_selected_button = ctk.CTkButton(
            controls,
            text="Download Selected (0)",
            command=self._download_selected,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme.get("accent_text", self.theme["bg"]),
        )
        self.download_selected_button.pack(side="right")
        self._update_selection()
        self._set_status(f"Detected Media ({len(media)})", seconds=4)

    def _select_all(self, value):
        for variable in self.selected.values():
            variable.set(value)
        self._update_selection()

    def _update_selection(self):
        count = sum(variable.get() for variable in self.selected.values())
        if hasattr(self, "selection_label"):
            self.selection_label.configure(text=f"{count} selected")
            self.download_selected_button.configure(
                text=f"Download Selected ({count})",
                state="normal" if count else "disabled",
            )

    def _download_selected(self):
        selected = [
            item
            for item in self.media
            if self.selected.get(item["id"] or item["url"], tk.BooleanVar()).get()
        ]
        self._download_media(selected)

    def _needs_ffmpeg(self) -> bool:
        if self.format_var.get() == "Audio":
            return True
        if self.clip_start.get().strip() or self.clip_end.get().strip():
            return True
        if self.codec_menu.get() != "Auto (Best)":
            return True
        if self.quality_menu.get() != "Best Available":
            return True
        return (
            self.settings.embed_metadata
            or self.settings.embed_thumbnail
            or self.settings.subtitles
        )

    def _download_media(self, media):
        if not media:
            return
        if not _valid_timestamp(self.clip_start.get()) or not _valid_timestamp(
            self.clip_end.get()
        ):
            self._validate_trim()
            self._set_status(
                "Invalid trim times. Use seconds, MM:SS, or HH:MM:SS.", seconds=6
            )
            return
        if self._needs_ffmpeg() and not self.engine.ffmpeg_location:
            messagebox.showerror(
                "FFmpeg required",
                "This download needs FFmpeg (audio conversion, trimming, quality or "
                "codec selection, or embedding options). Install FFmpeg or reinstall "
                "YOINK so its bundled dependency is available.",
                parent=self,
            )
            return
        Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        codec = self.codec_menu.get()
        queued = 0
        skipped = 0
        for item in media:
            if any(
                job.url == item["url"] and job.status not in FINISHED
                for job in self.jobs
            ):
                skipped += 1
                continue
            job = DownloadJob(
                item["url"],
                self.settings.output_dir,
                codec,
                start=self.clip_start.get() or None,
                end=self.clip_end.get() or None,
                cookies_path=self.settings.cookies_path or None,
                recode_mp4=self.settings.recode_mp4,
                kind="audio" if self.format_var.get() == "Audio" else "video",
                quality=self.quality_menu.get(),
                title=item["title"],
                uploader=item["uploader"],
                source=item["source"],
                thumbnail=item["thumbnail"],
                filename_template=self.settings.filename_template,
                embed_metadata=self.settings.embed_metadata,
                embed_thumbnail=self.settings.embed_thumbnail,
                subtitles=self.settings.subtitles,
            )
            self.jobs.append(job)
            self.engine.submit(job)
            self._add_row(job)
            queued += 1
        message = f"Queued {queued} download(s)"
        if skipped:
            message += f" · skipped {skipped} already in queue"
        self._set_status(f"{message}.", seconds=4)

    def _add_row(self, job):
        if self._queue_empty is not None:
            self._queue_empty.destroy()
            self._queue_empty = None
        row = card(self.queue, self.theme)
        row.pack(fill="x", padx=4, pady=5)
        row.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            row, text=job.title, anchor="w", text_color=self.theme["text"]
        )
        title.grid(row=0, column=0, padx=14, pady=(10, 1), sticky="ew")
        detail = ctk.CTkLabel(
            row,
            text=f"{_format_label(job.kind)} • {job.quality} • {job.codec} • Queued",
            anchor="w",
            text_color=self.theme["text_muted"],
        )
        detail.grid(row=1, column=0, padx=14, pady=(0, 5), sticky="ew")
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
            hover_color=self.theme.get("danger_hover", "#8F4D49"),
            command=job.cancel,
        )
        cancel.grid(row=0, column=1, rowspan=3, padx=14)
        self.rows[job.id] = (row, title, detail, progress, cancel)

    def _clear_completed(self):
        finished = [job for job in self.jobs if job.status in FINISHED]
        if not finished:
            return
        for job in finished:
            row = self.rows.pop(job.id, None)
            if row is not None:
                row[0].destroy()
        self.jobs = [job for job in self.jobs if job.status not in FINISHED]
        if not self.jobs and self._queue_empty is None:
            self._show_queue_empty()
        self._set_status(f"Cleared {len(finished)} finished download(s).", seconds=4)

    def _refresh(self):
        for job in self.jobs:
            row = self.rows.get(job.id)
            if row is None:
                continue
            _card, title, detail, progress, cancel = row
            snap = job.snapshot()
            status = snap["status"]
            title.configure(text=snap["title"])
            label = f"{_format_label(snap['kind'])} • {snap['quality']} • {job.codec} • {status.value.title()}"
            if snap["speed"]:
                label += f"  •  {snap['speed']}  •  ETA {snap['eta'] or '-'}"
            if snap["error"]:
                label = _friendly_error(snap["error"])
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
        if hasattr(self, "status_label"):
            self.status_label.configure(text=self._status_text())
        if hasattr(self, "clear_completed_button"):
            self.clear_completed_button.configure(
                state="normal"
                if any(job.status in FINISHED for job in self.jobs)
                else "disabled"
            )
        self.after(250, self._refresh)

    def _counts(self):
        return f"{sum(j.status not in FINISHED for j in self.jobs)} active, {sum(j.status == JobStatus.COMPLETE for j in self.jobs)} completed"

    def _output_text(self):
        return f"Save to: {self.settings.output_dir}"

    def _choose_output(self):
        selected = filedialog.askdirectory(
            parent=self, initialdir=self.settings.output_dir
        )
        if selected:
            self.settings.output_dir = selected
            save_settings(self.settings)
            self.output_label.configure(text=self._output_text())

    def _about_dialog(self):
        dialog = ctk.CTkToplevel(self, fg_color=self.theme["bg"])
        dialog.title("About YOINK")
        dialog.geometry("360x240")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        icon = local_image(asset_path("icons", "main-icon-nobg.png"), (40, 40))
        ctk.CTkLabel(dialog, text="", image=icon).pack(pady=(10, 2))
        ctk.CTkLabel(
            dialog,
            text="YOINK",
            font=self._fonts["section"],
            text_color=self.theme["accent"],
        ).pack()
        ctk.CTkLabel(
            dialog,
            text="Multi-media Yoinkers, made with ♡ by Astartes.",
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
        ).pack(pady=(0, 2))
        info = ctk.CTkFrame(dialog, fg_color="transparent")
        info.pack()

        def info_row(label_text, value_text, link=False):
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack()
            ctk.CTkLabel(
                row,
                text=label_text,
                text_color=self.theme["text_muted"],
                font=self._fonts["small"],
                width=90,
                anchor="w",
            ).pack(side="left")
            value = (
                _link_label(row, value_text, self.theme, self._fonts)
                if link
                else ctk.CTkLabel(
                    row,
                    text=value_text,
                    text_color=self.theme["text"],
                    font=self._fonts["body"],
                )
            )
            value.pack(side="left")

        info_row("Version", APP_VERSION)
        info_row("Mascot", "Luna", link=True)
        info_row("Developer", "Astartes", link=True)
        ctk.CTkButton(
            dialog,
            text="Close",
            command=dialog.destroy,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme.get("accent_text", self.theme["text"]),
        ).pack(pady=(6, 8))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _settings_dialog(self):
        dialog = ctk.CTkToplevel(self, fg_color=self.theme["bg"])
        dialog.title("YOINK Settings")
        dialog.geometry("620x640")
        dialog.transient(self)
        dialog.grab_set()
        body = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True)

        def themed_entry(parent, **kwargs):
            return ctk.CTkEntry(
                parent,
                fg_color=self.theme["surface_alt"],
                border_color=self.theme["border"],
                text_color=self.theme["text"],
                **kwargs,
            )

        def themed_menu(parent, **kwargs):
            return ctk.CTkOptionMenu(
                parent,
                fg_color=self.theme["surface_alt"],
                button_color=self.theme["accent"],
                button_hover_color=self.theme["accent_hover"],
                text_color=self.theme["text"],
                dropdown_fg_color=self.theme["surface"],
                dropdown_hover_color=self.theme["surface_alt"],
                dropdown_text_color=self.theme["text"],
                **kwargs,
            )

        def themed_checkbox(parent, text, variable):
            return ctk.CTkCheckBox(
                parent,
                text=text,
                variable=variable,
                fg_color=self.theme["accent"],
                hover_color=self.theme["accent_hover"],
                border_color=self.theme["border"],
                checkmark_color=self.theme.get("accent_text", self.theme["text"]),
                text_color=self.theme["text"],
            )

        def section(text):
            ctk.CTkLabel(
                body,
                text=text,
                font=self._fonts["section"],
                text_color=self.theme["text"],
            ).pack(anchor="w", padx=24, pady=(18, 4))

        def line():
            frame = ctk.CTkFrame(body, fg_color="transparent")
            frame.pack(fill="x", padx=24, pady=3)
            return frame

        section("General")
        cookies_line = line()
        ctk.CTkLabel(
            cookies_line,
            text="Cookies file (Netscape format)",
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        cookies = themed_entry(cookies_line, placeholder_text="Optional")
        cookies.pack(side="left", fill="x", expand=True, padx=(10, 0))
        cookies.insert(0, self.settings.cookies_path)
        ctk.CTkButton(
            cookies_line,
            text="Browse",
            width=80,
            command=lambda: self._browse_cookie(cookies),
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="left", padx=(8, 0))

        workers_line = line()
        ctk.CTkLabel(
            workers_line,
            text="Concurrent downloads",
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        workers = themed_menu(workers_line, values=["1", "2", "3", "4"], width=84)
        workers.set(str(min(4, max(1, self.settings.workers))))
        workers.pack(side="left", padx=(10, 0))

        template_line = line()
        ctk.CTkLabel(
            template_line, text="Filename template", text_color=self.theme["text_muted"]
        ).pack(side="left")
        template = themed_entry(template_line)
        template.pack(side="left", fill="x", expand=True, padx=(10, 0))
        template.insert(0, self.settings.filename_template)

        embed_metadata = tk.BooleanVar(value=self.settings.embed_metadata)
        embed_thumbnail = tk.BooleanVar(value=self.settings.embed_thumbnail)
        subtitles = tk.BooleanVar(value=self.settings.subtitles)
        themed_checkbox(body, "Embed metadata (FFmpeg)", embed_metadata).pack(
            anchor="w", padx=24, pady=(8, 0)
        )
        themed_checkbox(body, "Embed thumbnail (FFmpeg)", embed_thumbnail).pack(
            anchor="w", padx=24
        )
        themed_checkbox(body, "Download and embed subtitles (FFmpeg)", subtitles).pack(
            anchor="w", padx=24
        )

        section("Appearance")
        theme_line = line()
        ctk.CTkLabel(
            theme_line, text="Theme", text_color=self.theme["text_muted"]
        ).pack(side="left")
        theme_menu = themed_menu(
            theme_line, values=self.themes.available(), command=self._change_theme
        )
        theme_menu.set(self.settings.theme)
        theme_menu.pack(side="left", padx=(10, 0))

        background_line = line()
        ctk.CTkLabel(
            background_line, text="Background", text_color=self.theme["text_muted"]
        ).pack(side="left")
        background_menu = themed_menu(
            background_line, values=list(_BACKGROUND_CHOICES.values()), width=190
        )
        background_menu.set(
            _BACKGROUND_CHOICES.get(self.settings.background_mode, "Off")
        )
        background_menu.pack(side="left", padx=(10, 0))
        background_path_state = {
            "path": (
                self.settings.background_path
                if self.settings.background_mode == "selected"
                else ""
            )
        }
        browse_background_button = ctk.CTkButton(
            background_line,
            text="Browse",
            width=80,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        )

        def browse_background():
            selected = filedialog.askopenfilename(
                parent=dialog,
                filetypes=[
                    ("Images", "*.png *.jpg *.jpeg *.webp"),
                    ("All files", "*.*"),
                ],
            )
            if selected:
                background_path_state["path"] = selected
                background_path_label.configure(text=selected)

        browse_background_button.configure(command=browse_background)
        browse_background_button.pack(side="left", padx=(8, 0))
        background_path_label = ctk.CTkLabel(
            body,
            text=background_path_state["path"],
            text_color=self.theme["text_muted"],
            font=self._fonts["small"],
            anchor="w",
        )
        background_path_label.pack(anchor="w", padx=24)

        def background_changed(value):
            browse_background_button.configure(
                state="normal" if value == "Custom image…" else "disabled"
            )

        background_menu.configure(command=background_changed)
        background_changed(background_menu.get())

        dim_line = line()
        ctk.CTkLabel(
            dim_line, text="Background dim", text_color=self.theme["text_muted"]
        ).pack(side="left")
        dim_value = ctk.CTkLabel(
            dim_line,
            text=f"{self.settings.background_dim}%",
            text_color=self.theme["text"],
        )
        dim_slider = ctk.CTkSlider(
            dim_line,
            from_=20,
            to=100,
            number_of_steps=80,
            width=180,
            fg_color=self.theme["progress_track"],
            progress_color=self.theme["progress_fill"],
            button_color=self.theme["accent"],
            button_hover_color=self.theme["accent_hover"],
            command=lambda value: dim_value.configure(text=f"{int(value)}%"),
        )
        dim_slider.set(self.settings.background_dim)
        dim_slider.pack(side="left", padx=(10, 8))
        dim_value.pack(side="left")

        section("Output")
        recode = tk.BooleanVar(value=self.settings.recode_mp4)
        themed_checkbox(
            body,
            "Force full MP4 re-encode (slow, maximum compatibility)",
            recode,
        ).pack(anchor="w", padx=24)

        def save():
            self.settings.cookies_path = cookies.get().strip()
            self.settings.filename_template = (
                template.get().strip() or "%(title)s [%(id)s].%(ext)s"
            )
            self.settings.embed_metadata = embed_metadata.get()
            self.settings.embed_thumbnail = embed_thumbnail.get()
            self.settings.subtitles = subtitles.get()
            self.settings.recode_mp4 = recode.get()
            self.settings.background_dim = int(dim_slider.get())
            modes = {value: key for key, value in _BACKGROUND_CHOICES.items()}
            mode = modes.get(background_menu.get(), "off")
            if mode == "selected":
                if background_path_state["path"]:
                    self.settings.background_path = background_path_state["path"]
                elif not self.settings.background_path:
                    mode = "off"
            self.settings.background_mode = mode
            new_workers = max(1, min(4, int(workers.get())))
            if new_workers != self.settings.workers:
                self.settings.workers = new_workers
                if all(job.status in FINISHED for job in self.jobs):
                    self.engine.shutdown()
                    self.engine = DownloadEngine(_ffmpeg_path(), new_workers)
            save_settings(self.settings)
            self._apply_background()
            dialog.destroy()

        ctk.CTkButton(
            body,
            text="Save settings",
            command=save,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
        ).pack(anchor="e", padx=24, pady=20)

    def _browse_cookie(self, entry):
        selected = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")],
        )
        if selected:
            entry.delete(0, "end")
            entry.insert(0, selected)

    def _change_theme(self, name):
        self.settings.theme = name
        save_settings(self.settings)
        self.theme = self.themes.load(name)
        ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
        self._rebuild()

    def _rebuild(self):
        media = self.media[:]
        selected = {key: variable.get() for key, variable in self.selected.items()}
        urls = self._current_urls()
        for child in self.winfo_children():
            child.destroy()
        self.rows.clear()
        self._background_label = None
        self._build()
        self._load_background()
        if urls:
            self.url_box.delete("1.0", "end")
            self.url_box.insert("1.0", urls)
        if media:
            self._show_media(media)
            for key, value in selected.items():
                if key in self.selected:
                    self.selected[key].set(value)
            self._update_selection()
        for job in self.jobs:
            self._add_row(job)

    def _close(self):
        self.settings.window_geometry = str(self.geometry())
        save_settings(self.settings)
        self.engine.shutdown()
        self.destroy()


def _friendly_error(error):
    text = str(error).lower()
    for phrase, message in (
        ("ffmpeg", "FFmpeg is required for this conversion"),
        ("unsupported", "Unsupported website or URL"),
        ("private", "This media is private"),
        ("login", "Login is required for this media"),
        ("network", "Network error while contacting the source"),
        ("unavailable", "Media is unavailable"),
    ):
        if phrase in text:
            return message
    return "Inspection/download failed. Open details in logs for the technical error."


def _format_label(kind):
    return {"video": "Video", "audio": "Audio"}.get(kind, kind.title())


def _link_label(parent, text, theme, fonts):
    label = ctk.CTkLabel(
        parent,
        text=text,
        text_color=theme.get("secondary", theme["accent"]),
        font=fonts["link"],
        cursor="hand2",
    )
    label.bind(
        "<Button-1>", lambda _event: webbrowser.open("https://github.com/Astartes7")
    )
    return label


def _set_thumbnail(widget, image):
    try:
        if widget.winfo_exists():
            widget.configure(image=image)
    except tk.TclError:
        pass


def _valid_timestamp(value):
    value = value.strip()
    if not value:
        return True
    parts = value.split(":")
    if len(parts) > 3:
        return False
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return False
    return (
        all(math.isfinite(number) for number in numbers)
        and all(number >= 0 for number in numbers)
        and all(number < 60 for number in numbers[1:])
    )


def _virtual_screen_bounds() -> tuple[int, int, int, int] | None:
    try:
        import ctypes

        metrics = ctypes.windll.user32.GetSystemMetrics
        width, height = metrics(78), metrics(79)
        if width and height:
            return metrics(76), metrics(77), width, height
    except (AttributeError, ImportError, OSError):
        pass
    return None


def _ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which("ffmpeg")


def run():
    YoinkApp().mainloop()
