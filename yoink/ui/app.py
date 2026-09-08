import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from glob import escape as glob_escape

from yoink.config import AUDIO_QUALITIES, VIDEO_QUALITIES, load_settings, save_settings
from yoink.core.codecs import CODECS
from yoink.core.engine import DownloadEngine
from yoink.core.inspection import inspect_urls
from yoink.core.models import DownloadJob, JobStatus
from yoink.themes.manager import ThemeManager
from yoink.ui.assets import ThumbnailCache, asset_path, local_image, placeholder
from yoink.ui.design import SPACE, card, fonts
from yoink.ui.widgets import TimeEntry

APP_VERSION = "v1.1"
APP_AUTHOR = "Astartes7"
APP_AUTHOR_URL = "https://github.com/Astartes7"

MEDIA_VIEWS = ("List", "Grid", "Sources")
QUEUE_VIEWS = ("List", "Grid")
THUMB_SIZE = (112, 64)
GRID_THUMB_SIZE = (150, 84)
DEFAULT_GEOMETRY = "640x360"
MIN_WINDOW = (640, 360)
_MEDIA_SUFFIXES = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".flv",
    ".ts",
    ".mp3",
    ".m4a",
    ".opus",
    ".ogg",
    ".wav",
    ".aac",
    ".flac",
}
_IGNORE_SUFFIXES = {
    ".part",
    ".ytdl",
    ".tmp",
    ".crdownload",
    ".webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".url",
    ".json",
}

ACTIVE_STATES = {
    JobStatus.CHECKING,
    JobStatus.PREPARING,
    JobStatus.DOWNLOADING,
    JobStatus.PROCESSING,
    JobStatus.MERGING,
    JobStatus.CONVERTING,
}
DETAIL_COLOR_ROLES = {
    JobStatus.QUEUED: "text_muted",
    JobStatus.CHECKING: "text_muted",
    JobStatus.PREPARING: "text_muted",
    JobStatus.DOWNLOADING: "secondary",
    JobStatus.PROCESSING: "media",
    JobStatus.MERGING: "media",
    JobStatus.CONVERTING: "media",
    JobStatus.COMPLETE: "success",
    JobStatus.FAILED: "danger",
    JobStatus.CANCELLED: "text_muted",
}


class YoinkApp(ctk.CTk):
    def __init__(self):
        self.settings = load_settings()
        self.themes = ThemeManager()
        self.theme = self.themes.load(self.settings.theme)
        ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
        ctk.set_default_color_theme("dark-blue")
        super().__init__()
        self.title(f"YOINK {APP_VERSION}")
        self.geometry(self._initial_geometry())
        self.minsize(*MIN_WINDOW)
        if self.settings.window_maximized:
            self._maximize_window()
            # CTk's startup titlebar redraw withdraws and restores the
            # window, which drops the zoomed state set during __init__;
            # re-apply once after that dance settles.
            self.after(300, self._reassert_maximized)
        self._last_state = self.state()
        self.configure(fg_color=self.theme["bg"])
        _apply_window_icon(self)
        self.engine = DownloadEngine(_ffmpeg_path(), self.settings.workers)
        self.jobs: list[DownloadJob] = []
        self.media: list[dict] = []
        self.selected: dict[str, tk.BooleanVar] = {}
        self.rows: dict[str, dict] = {}
        self.media_view = "List"
        self.queue_view = "List"
        self._queue_empty = None
        self._background = None
        self._thumbnail_cache = ThumbnailCache()
        self._fonts = fonts()
        self._build()
        self._render_queue()
        self._load_background()
        self.after(250, self._refresh)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------- layout

    def _initial_geometry(self) -> str:
        """Windowed mode is always 640x360; keep only the saved position."""
        stored = (self.settings.window_geometry or "").strip()
        match = re.search(r"([+-]\d+[+-]\d+)$", stored)
        return DEFAULT_GEOMETRY + (match.group(1) if match else "")

    def _maximize_window(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def _reassert_maximized(self):
        """Re-apply the launch fullscreen state; only runs 300ms after
        startup, long before any user interaction could restore it."""
        if not self.settings.window_maximized:
            return
        self._maximize_window()
        self._last_state = self.state()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.page = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.page.grid(row=0, column=0, sticky="nsew")
        _auto_hide_scrollbar(self.page)
        self.page.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_add_media()
        self._build_options()
        self._build_media_section()
        self._build_queue_section()
        self.status_label = ctk.CTkLabel(
            self,
            text="Ready to yoink.",
            anchor="w",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        self.status_label.grid(
            row=1, column=0, padx=20, pady=(SPACE.xs, SPACE.sm), sticky="ew"
        )

    def _build_header(self):
        header = ctk.CTkFrame(self.page, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(SPACE.lg, SPACE.sm), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        logo = local_image(asset_path("icons", "main-icon-nobg.png"), (46, 46))
        ctk.CTkLabel(
            header,
            text="☾" if logo is None else "",
            font=ctk.CTkFont(size=26),
            text_color=self.theme["accent"],
            image=logo,
        ).grid(row=0, column=0, rowspan=2, padx=(0, SPACE.md))
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=1, rowspan=2, sticky="w")
        ctk.CTkLabel(
            brand,
            text="YOINK",
            font=self._fonts["brand"],
            text_color=self.theme["accent"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="media, neatly gathered.",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Settings",
            width=92,
            command=self._settings_dialog,
            font=self._fonts["small"],
            fg_color=self._dark_control_color(),
            hover_color=self._blend(self.theme["surface_alt"], 0.2),
            text_color=self.theme["text"],
        ).grid(row=0, column=2, rowspan=2)

    def _dark_control_color(self) -> str:
        """Quiet fill for chrome buttons: surface_alt deepened toward bg."""
        return self._blend(self.theme["surface_alt"], 0.5)

    def _build_add_media(self):
        add = card(self.page, self.theme)
        add.grid(row=1, column=0, padx=20, pady=(SPACE.sm, 0), sticky="ew")
        add.grid_columnconfigure(0, weight=1)
        title_row = ctk.CTkFrame(add, fg_color="transparent")
        title_row.grid(row=0, column=0, padx=SPACE.lg, pady=(SPACE.md, 0), sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            title_row,
            text="Add Media",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_row,
            text="Paste one or more media links to get started.",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).grid(row=0, column=1, sticky="e")
        input_row = ctk.CTkFrame(add, fg_color="transparent")
        input_row.grid(
            row=1, column=0, padx=SPACE.lg, pady=(SPACE.sm, SPACE.md), sticky="ew"
        )
        input_row.grid_columnconfigure(0, weight=1)
        self.url_box = ctk.CTkTextbox(
            input_row,
            height=64,
            border_width=1,
            border_color=self.theme["border"],
            fg_color=self.theme["surface_alt"],
        )
        self.url_box.grid(row=0, column=0, sticky="ew")
        self.url_box.insert("1.0", "Paste a video, playlist, or media URL...")
        self.url_box.bind("<FocusIn>", self._clear_placeholder)
        self.url_box.bind("<Control-Return>", lambda _event: self._inspect())
        self.inspect_button = ctk.CTkButton(
            input_row,
            text="Inspect",
            command=self._inspect,
            width=105,
            font=self._fonts["small"],
            fg_color=self._blend(
                self.theme.get("secondary", self.theme["accent"]), 0.72
            ),
            hover_color=self._blend(
                self.theme.get("secondary", self.theme["accent"]), 0.58
            ),
            text_color=self.theme["text"],
        )
        self.inspect_button.grid(row=0, column=1, padx=(SPACE.md, 0))

    # ----------------------------------------------------- style helpers

    def _blend(self, base: str, weight: float) -> str:
        """Mix a color toward this theme's background (weight = bg share).

        0.0 keeps the base, 1.0 is the background itself. Used to derive
        muted control colors that stay close to the window tone on every
        theme, dark or light.
        """
        return _mix(base, self.theme["bg"], weight)

    def _make_segmented(self, parent, values, command, **kwargs):
        return ctk.CTkSegmentedButton(
            parent,
            values=list(values),
            command=command,
            font=self._fonts["small"],
            selected_color=self._blend(self.theme["accent"], 0.55),
            selected_hover_color=self._blend(self.theme["accent"], 0.42),
            unselected_color=self.theme["surface_alt"],
            unselected_hover_color=_mix(
                self.theme["surface_alt"], self.theme["text"], 0.12
            ),
            text_color=self.theme["text"],
            **kwargs,
        )

    def _make_action_button(self, parent, text, command, width=None, **kwargs):
        """Queue/media action button in the same quiet ghost style as Remove:
        surface_alt background with a border-tone hover."""
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            **({"width": width} if width else {}),
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
            font=self._fonts["small"],
            text_color=self.theme["text"],
            **kwargs,
        )

    def _make_option_menu(self, parent, values, width=150, command=None):
        return ctk.CTkOptionMenu(
            parent,
            values=list(values),
            width=width,
            font=self._fonts["small"],
            fg_color=self.theme["surface_alt"],
            button_color=self._blend(self.theme["accent"], 0.68),
            button_hover_color=self._blend(self.theme["accent"], 0.55),
            text_color=self.theme["text"],
            dropdown_fg_color=self.theme["surface"],
            dropdown_hover_color=self._blend(self.theme["accent"], 0.62),
            dropdown_text_color=self.theme["text"],
            command=command,
        )

    def _build_options(self):
        self.options_card = options = card(self.page, self.theme)
        options.grid(row=2, column=0, padx=20, pady=SPACE.sm, sticky="ew")
        options.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            options,
            text="Download Options",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, padx=SPACE.lg, pady=(SPACE.md, SPACE.xs), sticky="w")

        self.fmt_row = fmt_row = ctk.CTkFrame(options, fg_color="transparent")
        fmt_row.grid(row=1, column=0, padx=SPACE.md, pady=SPACE.xs, sticky="ew")
        ctk.CTkLabel(
            fmt_row,
            text="Format",
            width=46,
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        self.format_var = tk.StringVar(value=self.settings.default_format)
        self.format_button = self._make_segmented(
            fmt_row, ["Video", "Audio"], self._format_changed, variable=self.format_var
        )
        self.format_button.pack(side="left", padx=(SPACE.xs, SPACE.sm))
        ctk.CTkLabel(
            fmt_row,
            text="Quality",
            width=42,
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        self.quality_menu = self._make_option_menu(
            fmt_row, self._quality_values(), width=126, command=self._set_quality
        )
        self.quality_menu.set(self._current_quality())
        self.quality_menu.pack(side="left")

        codec_row = ctk.CTkFrame(options, fg_color="transparent")
        codec_row.grid(row=2, column=0, padx=SPACE.md, pady=SPACE.xs, sticky="ew")
        ctk.CTkLabel(
            codec_row,
            text="Codec",
            width=46,
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        self.codec_menu = self._make_option_menu(
            codec_row, list(CODECS), width=180, command=self._set_codec
        )
        self.codec_menu.set(self.settings.codec)
        self.codec_menu.pack(side="left")

        trim_row = ctk.CTkFrame(options, fg_color="transparent")
        trim_row.grid(row=3, column=0, padx=SPACE.md, pady=SPACE.xs, sticky="ew")
        ctk.CTkLabel(
            trim_row,
            text="Trim (optional)",
            width=96,
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        self.clip_start = TimeEntry(trim_row, self.theme)
        self.clip_start.pack(side="left", padx=(SPACE.sm, SPACE.md))
        ctk.CTkLabel(
            trim_row,
            text="to",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        self.clip_end = TimeEntry(trim_row, self.theme)
        self.clip_end.pack(side="left", padx=(SPACE.md, 0))
        self.trim_reset_button = self._make_action_button(
            trim_row, "Reset", self._reset_trim, width=64
        )
        self.trim_reset_button.pack(side="left", padx=(SPACE.md, 0))

        save_row = ctk.CTkFrame(options, fg_color="transparent")
        save_row.grid(
            row=4, column=0, padx=SPACE.md, pady=(SPACE.xs, SPACE.md), sticky="ew"
        )
        save_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            save_row,
            text="Save to",
            width=96,
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).grid(row=0, column=0, sticky="w")
        self.output_label = ctk.CTkLabel(
            save_row,
            text=self._output_text(),
            anchor="w",
            justify="left",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        _bind_wrap(self.output_label)
        self.output_label.grid(row=0, column=1, padx=(SPACE.sm, SPACE.md), sticky="ew")
        ctk.CTkButton(
            save_row,
            text="Browse",
            width=80,
            command=self._choose_output,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).grid(row=0, column=2)

    def _build_media_section(self):
        # Not gridded here: the section stays hidden until an inspection
        # actually finds media (see _show_media / _grid_media_section).
        self.media_section = card(self.page, self.theme)
        section = self.media_section
        section.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(section, fg_color="transparent")
        header.grid(
            row=0, column=0, padx=SPACE.lg, pady=(SPACE.md, SPACE.xs), sticky="ew"
        )
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Detected Media",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, sticky="w")
        self.media_count_label = ctk.CTkLabel(
            header,
            text="",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        self.media_count_label.grid(row=0, column=1, padx=SPACE.md, sticky="w")
        self._make_segmented(header, MEDIA_VIEWS, self._set_media_view).grid(
            row=0, column=2, sticky="e"
        )
        self.media_content = ctk.CTkFrame(
            section, fg_color=self.theme["surface"], corner_radius=8
        )
        self.media_content.grid(
            row=1, column=0, padx=SPACE.sm, pady=(0, SPACE.md), sticky="ew"
        )

    def _grid_media_section(self):
        self.media_section.grid(
            row=3, column=0, padx=20, pady=(0, SPACE.sm), sticky="ew"
        )

    def _hide_media_section(self):
        self.media_section.grid_remove()

    def _build_queue_section(self):
        section = card(self.page, self.theme)
        section.grid(row=4, column=0, padx=20, pady=(0, SPACE.sm), sticky="ew")
        section.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(section, fg_color="transparent")
        header.grid(
            row=0, column=0, padx=SPACE.lg, pady=(SPACE.md, SPACE.xs), sticky="ew"
        )
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Download Queue",
            font=self._fonts["section"],
            text_color=self.theme["text"],
        ).grid(row=0, column=0, sticky="w")
        self.clear_done_button = ctk.CTkButton(
            header,
            text="Clear Completed",
            width=118,
            command=self._clear_completed,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
            font=self._fonts["small"],
        )
        self.clear_done_button.grid(row=0, column=1, padx=SPACE.md, sticky="w")
        self.clear_done_button.configure(state="disabled")
        self._make_segmented(header, QUEUE_VIEWS, self._set_queue_view).grid(
            row=0, column=2, sticky="e"
        )
        self.queue_content = ctk.CTkFrame(
            section, fg_color=self.theme["surface"], corner_radius=8
        )
        self.queue_content.grid(
            row=1, column=0, padx=SPACE.sm, pady=(0, SPACE.md), sticky="ew"
        )

    # ------------------------------------------------------- media panel

    def _set_media_view(self, value):
        self.media_view = value
        self._render_media()

    def _render_media(self):
        if not hasattr(self, "media_content"):
            return
        for child in self.media_content.winfo_children():
            child.destroy()
        items = self.media
        self.media_count_label.configure(text=f"{len(items)} item(s)" if items else "")
        if not items:
            empty = ctk.CTkFrame(self.media_content, fg_color="transparent")
            empty.pack(fill="both", expand=True)
            moon = local_image(asset_path("icons", "main-icon-nobg.png"), (56, 56))
            ctk.CTkLabel(
                empty,
                text="☾" if moon is None else "",
                font=ctk.CTkFont(size=24),
                text_color=self.theme.get("moon", self.theme["accent"]),
                image=moon,
            ).pack(side="left", expand=True, pady=(SPACE.md, SPACE.lg))
            ctk.CTkLabel(
                empty,
                text="Paste a link to find some media.",
                font=self._fonts["body"],
                text_color=self.theme["text_muted"],
            ).pack(side="left", expand=True, pady=(SPACE.md, SPACE.lg))
            self._render_media_controls()
            return
        items_frame = ctk.CTkFrame(self.media_content, fg_color="transparent")
        items_frame.pack(fill="both", expand=True)
        if self.media_view == "Grid":
            columns = 3
            for column in range(columns):
                items_frame.grid_columnconfigure(column, weight=1, uniform="media")
            for index, item in enumerate(items):
                self._media_grid_card(items_frame, item, index, columns)
        elif self.media_view == "Sources":
            groups: dict[str, list[dict]] = {}
            for item in items:
                groups.setdefault(item["source"], []).append(item)
            for source, entries in groups.items():
                group = ctk.CTkFrame(items_frame, fg_color="transparent")
                group.pack(fill="x", pady=(SPACE.xs, SPACE.sm))
                ctk.CTkLabel(
                    group,
                    text=f"{source} ({len(entries)})",
                    font=self._fonts["title"],
                    text_color=self.theme.get(
                        "text_secondary", self.theme["text_muted"]
                    ),
                ).pack(anchor="w", pady=(0, SPACE.xs))
                for item in entries:
                    self._media_list_row(group, item)
        else:
            for item in items:
                self._media_list_row(items_frame, item)
        self._render_media_controls()

    def _render_media_controls(self):
        controls = ctk.CTkFrame(self.media_content, fg_color="transparent")
        controls.pack(fill="x", pady=(SPACE.md, SPACE.xs))
        self.select_all_button = ctk.CTkButton(
            controls,
            text="Select All",
            width=104,
            command=self._toggle_select_all,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        )
        self.select_all_button.pack(side="left")
        ctk.CTkButton(
            controls,
            text="Clear",
            width=74,
            command=self._clear_media,
            fg_color=self.theme["surface_alt"],
            hover_color=self.theme["border"],
        ).pack(side="left", padx=SPACE.sm)
        self.selection_label = ctk.CTkLabel(
            controls,
            text="0 selected",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        self.selection_label.pack(side="left", padx=SPACE.md)
        self.download_selected_button = self._make_action_button(
            controls,
            "Download Selected (0)",
            self._download_selected,
            height=30,
        )
        self.download_selected_button.pack(side="right")
        self._update_selection()

    def _media_list_row(self, parent, item):
        key = item["id"] or item["url"]
        var = self.selected.setdefault(key, tk.BooleanVar(value=True))
        row = card(parent, self.theme)
        row.pack(fill="x", padx=2, pady=SPACE.xs)
        row.grid_columnconfigure(2, weight=1)
        ctk.CTkCheckBox(
            row, text="", variable=var, width=24, command=self._update_selection
        ).grid(row=0, column=0, rowspan=2, padx=(SPACE.md, SPACE.sm))
        thumb = self._thumbnail_label(row, THUMB_SIZE, item)
        thumb.grid(row=0, column=1, rowspan=2, padx=(0, SPACE.md), pady=SPACE.md)
        title = ctk.CTkLabel(
            row,
            text=item["title"],
            anchor="w",
            font=self._fonts["title"],
            text_color=self.theme["text"],
        )
        _bind_wrap(title)
        title.grid(row=0, column=2, padx=SPACE.xs, pady=(SPACE.md, 0), sticky="ew")
        metadata = ctk.CTkLabel(
            row,
            text=f"{item['uploader']}  •  {item['duration']}  •  {item['source']}",
            anchor="w",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        _bind_wrap(metadata)
        metadata.grid(row=1, column=2, padx=SPACE.xs, pady=(0, SPACE.md), sticky="ew")
        self._make_action_button(
            row, "Download", lambda value=item: self._download_media([value]), width=92
        ).grid(row=0, column=3, rowspan=2, padx=SPACE.md)
        var.trace_add(
            "write",
            lambda *_a, frame=row, variable=var: self._tint_card(frame, variable.get()),
        )

    def _media_grid_card(self, parent, item, index, columns):
        key = item["id"] or item["url"]
        var = self.selected.setdefault(key, tk.BooleanVar(value=True))
        cell = card(parent, self.theme)
        cell.grid(
            row=index // columns,
            column=index % columns,
            sticky="nsew",
            padx=SPACE.sm,
            pady=SPACE.xs,
        )
        thumb = self._thumbnail_label(cell, GRID_THUMB_SIZE, item)
        thumb.pack(padx=SPACE.md, pady=(SPACE.md, SPACE.xs))
        grid_title = ctk.CTkLabel(
            cell,
            text=item["title"],
            anchor="w",
            justify="left",
            font=self._fonts["title"],
            text_color=self.theme["text"],
        )
        _bind_wrap(grid_title)
        grid_title.pack(fill="x", padx=SPACE.md)
        grid_meta = ctk.CTkLabel(
            cell,
            text=f"{item['uploader']}  •  {item['duration']}",
            anchor="w",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        _bind_wrap(grid_meta)
        grid_meta.pack(fill="x", padx=SPACE.md, pady=(2, SPACE.sm))
        bottom = ctk.CTkFrame(cell, fg_color="transparent")
        bottom.pack(fill="x", padx=SPACE.md, pady=(0, SPACE.md))
        ctk.CTkCheckBox(
            bottom, text="", variable=var, width=24, command=self._update_selection
        ).pack(side="left")
        self._make_action_button(
            bottom,
            "Download",
            lambda value=item: self._download_media([value]),
            width=88,
        ).pack(side="right")
        var.trace_add(
            "write",
            lambda *_a, frame=cell, variable=var: self._tint_card(
                frame, variable.get()
            ),
        )

    def _thumbnail_label(self, parent, size, item):
        ph = placeholder(
            size,
            self.theme["surface_alt"],
            self.theme.get("moon", self.theme["accent"]),
        )
        if ph is None:
            return ctk.CTkLabel(
                parent,
                text=" media ",
                font=self._fonts["small"],
                text_color=self.theme["text_muted"],
            )
        label = ctk.CTkLabel(parent, text="", image=ph)
        if item.get("thumbnail"):
            self._thumbnail_cache.load(
                self,
                item["thumbnail"],
                size,
                ph,
                lambda image, target=label: target.configure(image=image),
            )
        return label

    def _tint_card(self, frame, selected):
        try:
            frame.configure(
                border_color=self.theme.get("border_active", self.theme["border"])
                if selected
                else self.theme["border"]
            )
        except tk.TclError:
            pass

    def _toggle_select_all(self):
        values = list(self.selected.values())
        if not values:
            return
        target = not all(variable.get() for variable in values)
        for variable in values:
            variable.set(target)
        self._update_selection()

    def _clear_media(self):
        self.media = []
        self.selected = {}
        self._hide_media_section()
        self.status_label.configure(text="Ready to yoink.")

    def _update_selection(self):
        widgets = ("select_all_button", "selection_label", "download_selected_button")
        if not all(hasattr(self, name) for name in widgets):
            return
        if not self.selection_label.winfo_exists():
            return
        count = sum(variable.get() for variable in self.selected.values())
        all_selected = bool(self.selected) and all(
            v.get() for v in self.selected.values()
        )
        self.select_all_button.configure(
            text="Deselect All" if all_selected else "Select All"
        )
        self.selection_label.configure(text=f"{count} selected")
        self.download_selected_button.configure(
            text=f"Download Selected ({count})", state="normal" if count else "disabled"
        )

    def _reset_trim(self):
        self.clip_start.reset()
        self.clip_end.reset()

    # ------------------------------------------------------ inspection

    def _clear_placeholder(self, _event):
        if self.url_box.get("1.0", "end").strip().startswith("Paste a video"):
            self.url_box.delete("1.0", "end")

    def _inspect(self):
        urls = list(
            dict.fromkeys(
                line.strip()
                for line in self.url_box.get("1.0", "end").splitlines()
                if line.strip() and not line.startswith("Paste a video")
            )
        )
        if not urls:
            messagebox.showwarning("YOINK", "Paste at least one URL first.")
            return
        self.inspect_button.configure(state="disabled", text="Inspecting...")
        self.status_label.configure(text=f"Inspecting {len(urls)} URL(s)...")
        threading.Thread(target=self._inspect_worker, args=(urls,), daemon=True).start()

    def _inspect_worker(self, urls):
        try:
            media = inspect_urls(urls, self.settings.cookies_path)
            self.after(0, lambda: self._show_media(media))
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI thread
            message = _friendly_error(exc)
            self.after(
                0,
                lambda: self.status_label.configure(
                    text=f"Inspection failed: {message}"
                ),
            )
        finally:
            self.after(0, self._inspect_finished)

    def _inspect_finished(self):
        if self.inspect_button.winfo_exists():
            self.inspect_button.configure(state="normal", text="Inspect")

    def _show_media(self, media):
        self.media = media
        self.selected = {
            (item["id"] or item["url"]): tk.BooleanVar(value=True) for item in media
        }
        if media:
            self._grid_media_section()
            self._render_media()
            self.status_label.configure(text=f"Detected {len(media)} item(s)")
        else:
            self.status_label.configure(text="No media found.")

    # -------------------------------------------------------- downloads

    def _quality_values(self):
        return VIDEO_QUALITIES if self.format_var.get() == "Video" else AUDIO_QUALITIES

    def _current_quality(self):
        values = self._quality_values()
        current = self.settings.default_quality
        return current if current in values else values[0]

    def _format_changed(self, _value):
        self.quality_menu.configure(values=self._quality_values())
        self.quality_menu.set(self._quality_values()[0])
        self.settings.default_format = self.format_var.get()
        self.settings.default_quality = self.quality_menu.get()
        save_settings(self.settings)

    def _set_quality(self, value):
        self.settings.default_quality = value
        save_settings(self.settings)

    def _set_codec(self, value):
        self.settings.codec = value
        save_settings(self.settings)

    def _download_selected(self):
        selected = [
            item
            for item in self.media
            if self.selected.get(item["id"] or item["url"], tk.BooleanVar()).get()
        ]
        self._download_media(selected)

    def _download_media(self, media):
        if not media:
            return
        duplicates = [
            item for item in media if any(job.url == item["url"] for job in self.jobs)
        ]
        duplicate_urls = {item["url"] for item in duplicates}
        fresh = [item for item in media if item["url"] not in duplicate_urls]
        if duplicates and not fresh:
            messagebox.showwarning(
                "Already in queue",
                "The selected media is already in your download queue or has been downloaded.\n"
                "It will not be queued again.",
            )
            return
        start_text = self.clip_start.get()
        end_text = self.clip_end.get()
        for item in fresh:
            error = _trim_error(start_text, end_text, item.get("duration_seconds"))
            if error:
                messagebox.showwarning(
                    "Invalid trim", f"{error}\n\nApplies to: {item['title']}"
                )
                return
        if self.format_var.get() == "Audio" and not self.engine.ffmpeg_location:
            messagebox.showerror(
                "FFmpeg required",
                "MP3 conversion requires FFmpeg. Configure or install FFmpeg before downloading.",
            )
            return
        if duplicates:
            messagebox.showwarning(
                "Duplicates skipped",
                f"{len(duplicates)} item(s) already queued or downloaded were skipped.",
            )
        Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        start = _time_seconds(start_text) or None
        end = _time_seconds(end_text) or None
        for item in fresh:
            job = DownloadJob(
                item["url"],
                self.settings.output_dir,
                codec=self.codec_menu.get(),
                start=str(start) if start else None,
                end=str(end) if end else None,
                cookies_path=self.settings.cookies_path or None,
                recode_mp4=self.settings.recode_mp4,
                kind="video" if self.format_var.get() == "Video" else "audio",
                quality=self.quality_menu.get(),
                title=item["title"],
                uploader=item["uploader"],
                source=item["source"],
                thumbnail=item["thumbnail"],
                filename_template=self.settings.filename_template,
                embed_metadata=self.settings.embed_metadata,
                embed_thumbnail=self.settings.embed_thumbnail,
                subtitles=self.settings.subtitles,
                duration=item.get("duration_seconds"),
            )
            self.jobs.append(job)
            self.engine.submit(job)
            self._make_queue_card(job, len(self.jobs) - 1)
        self._update_footer()

    # ---------------------------------------------------------- queue

    def _set_queue_view(self, value):
        self.queue_view = value
        self._render_queue()

    def _render_queue(self):
        if not hasattr(self, "queue_content"):
            return
        for child in self.queue_content.winfo_children():
            child.destroy()
        self.rows.clear()
        self._queue_empty = None
        if not self.jobs:
            self._queue_empty = self._build_queue_empty()
            return
        for index, job in enumerate(self.jobs):
            self._make_queue_card(job, index)

    def _build_queue_empty(self):
        empty = ctk.CTkFrame(self.queue_content, fg_color="transparent")
        empty.pack(fill="both", expand=True, pady=24)
        art = local_image(asset_path("icons", "not-available.png"), (76, 76))
        ctk.CTkLabel(
            empty,
            text="☾" if art is None else "",
            font=ctk.CTkFont(size=30),
            text_color=self.theme.get("moon", self.theme["accent"]),
            image=art,
        ).pack(pady=(SPACE.lg, SPACE.xs))
        ctk.CTkLabel(
            empty,
            text="Nothing yoinked yet.",
            font=self._fonts["title"],
            text_color=self.theme["text"],
        ).pack()
        ctk.CTkLabel(
            empty,
            text="Your downloads will appear here.",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(pady=SPACE.xs)
        return empty

    def _make_queue_card(self, job, index=0):
        if self._queue_empty is not None and self._queue_empty.winfo_exists():
            self._queue_empty.destroy()
        self._queue_empty = None
        compact = self.queue_view == "Grid"
        row = card(self.queue_content, self.theme)
        if compact:
            for column in (0, 1):
                self.queue_content.grid_columnconfigure(
                    column, weight=1, uniform="queue"
                )
            row.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=SPACE.sm,
                pady=SPACE.xs,
            )
        else:
            row.pack(fill="x", padx=2, pady=SPACE.xs)
            row.grid_columnconfigure(0, weight=1)
        if compact:
            title = ctk.CTkLabel(
                row,
                text=job.title,
                anchor="w",
                font=self._fonts["title"],
                text_color=self.theme["text"],
            )
            _bind_wrap(title)
            title.pack(fill="x", padx=SPACE.md, pady=(SPACE.md, 0))
            detail = ctk.CTkLabel(
                row,
                text="",
                anchor="w",
                font=self._fonts["small"],
                text_color=self.theme["text_muted"],
            )
            _bind_wrap(detail)
            detail.pack(fill="x", padx=SPACE.md)
            progress = ctk.CTkProgressBar(
                row,
                progress_color=self.theme["progress_fill"],
                fg_color=self.theme["progress_track"],
            )
            progress.set(0)
            progress.pack(fill="x", padx=SPACE.md, pady=(SPACE.xs, 0))
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(fill="x", padx=SPACE.md, pady=(SPACE.xs, SPACE.md))
        else:
            title = ctk.CTkLabel(
                row,
                text=job.title,
                anchor="w",
                font=self._fonts["title"],
                text_color=self.theme["text"],
            )
            _bind_wrap(title)
            title.grid(row=0, column=0, padx=SPACE.md, pady=(SPACE.md, 0), sticky="ew")
            detail = ctk.CTkLabel(
                row,
                text="",
                anchor="w",
                font=self._fonts["small"],
                text_color=self.theme["text_muted"],
            )
            _bind_wrap(detail)
            detail.grid(row=1, column=0, padx=SPACE.md, sticky="ew")
            progress = ctk.CTkProgressBar(
                row,
                progress_color=self.theme["progress_fill"],
                fg_color=self.theme["progress_track"],
            )
            progress.set(0)
            progress.grid(
                row=2, column=0, padx=SPACE.md, pady=(SPACE.xs, SPACE.md), sticky="ew"
            )
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=1, rowspan=3, padx=(0, SPACE.md))
        self.rows[job.id] = {
            "card": row,
            "title": title,
            "detail": detail,
            "progress": progress,
            "actions": actions,
            "status": None,
        }
        self._update_row_actions(job)

    def _update_row(self, job):
        widgets = self.rows.get(job.id)
        if not widgets or not widgets["card"].winfo_exists():
            return
        snap = job.snapshot()
        status = snap["status"]
        widgets["title"].configure(text=snap["title"])
        label = f"{snap['kind'].upper()} • {snap['quality']} • {status.value.title()}"
        if snap["speed"]:
            label += f"  •  {snap['speed']}  •  ETA {snap['eta'] or '-'}"
        color_role = DETAIL_COLOR_ROLES.get(status, "text_muted")
        color = self.theme.get(
            color_role, self.theme.get("accent", self.theme["text_muted"])
        )
        if snap["error"]:
            label = _friendly_error(snap["error"])
            color = self.theme["danger"]
        widgets["detail"].configure(text=label, text_color=color)
        widgets["progress"].set(snap["percent"] / 100)
        if widgets["status"] != status:
            widgets["status"] = status
            self._update_row_actions(job)
            try:
                if status == JobStatus.COMPLETE:
                    border = self.theme.get("success", self.theme["accent"])
                elif status == JobStatus.FAILED:
                    border = self.theme["danger"]
                else:
                    border = self.theme["border"]
                widgets["card"].configure(border_color=border)
            except tk.TclError:
                pass

    def _update_row_actions(self, job):
        widgets = self.rows.get(job.id)
        if not widgets or not widgets["actions"].winfo_exists():
            return
        actions = widgets["actions"]
        for child in actions.winfo_children():
            child.destroy()
        compact = self.queue_view == "Grid"
        width = 62 if compact else 78

        def add(text, command, kind):
            colors = {
                "primary": (self.theme["accent"], self.theme["accent_hover"]),
                "ghost": (self.theme["surface_alt"], self.theme["border"]),
                "danger": (
                    self.theme["danger"],
                    self.theme.get("danger_hover", self.theme["danger"]),
                ),
            }
            fg, hover = colors[kind]
            ctk.CTkButton(
                actions,
                text=text,
                width=width,
                command=command,
                fg_color=fg,
                hover_color=hover,
                font=self._fonts["small"],
                text_color=self.theme["text"],
            ).pack(side="left", padx=(0, SPACE.xs))

        status = job.snapshot()["status"]
        if status == JobStatus.COMPLETE:
            add("Open File", lambda j=job: self._open_job_file(j), "ghost")
            add("Open Folder", lambda j=job: self._open_job_folder(j), "ghost")
            add("Remove", lambda j=job: self._remove_job(j), "ghost")
        elif status == JobStatus.FAILED:
            add("Retry", lambda j=job: self._retry_job(j), "ghost")
            add("Remove", lambda j=job: self._remove_job(j), "ghost")
        elif status == JobStatus.CANCELLED:
            add("Remove", lambda j=job: self._remove_job(j), "ghost")
        else:
            add("Cancel", lambda j=job: self._confirm_cancel(j), "danger")

    def _confirm_cancel(self, job):
        if messagebox.askyesno("Cancel download", f"Cancel '{job.title}'?"):
            job.cancel()

    def _open_job_file(self, job):
        path = job.snapshot().get("filename")
        if path and Path(path).is_file():
            _open_path(path)
        else:
            located = _locate_media_file(job)
            if located:
                job.update(filename=located)
                _open_path(located)
            else:
                messagebox.showinfo(
                    "File not found",
                    "The saved file could not be located. It may have been moved, "
                    "renamed, or deleted.\n\nChecked:\n"
                    f"{path or job.output_dir}",
                )

    def _open_job_folder(self, job):
        path = job.snapshot().get("filename")
        if not (path and Path(path).is_file()):
            path = _locate_media_file(job)
            if path:
                job.update(filename=path)
        folder = Path(path).parent if path else Path(job.output_dir)
        if sys.platform == "win32" and path:
            # Single-string form: quoting inside the argument is what
            # explorer parses correctly; the list form misquotes paths
            # with spaces and explorer then opens its default folder.
            subprocess.Popen(f'explorer /select,"{path}"')
        elif folder.is_dir():
            _open_path(str(folder))
        else:
            messagebox.showinfo(
                "Folder not found", "The output folder could not be located."
            )

    def _remove_job(self, job):
        path = job.snapshot().get("filename")
        delete_file = False
        if job.status == JobStatus.COMPLETE and path and Path(path).is_file():
            answer = messagebox.askyesnocancel(
                "Remove download",
                f"Remove '{job.title}' from the queue?\n\n"
                "Yes — remove from queue, keep the file\n"
                "No — remove from queue and delete the file\n"
                "Cancel — keep everything",
            )
            if answer is None:
                return
            delete_file = not answer
        widgets = self.rows.pop(job.id, None)
        if widgets and widgets["card"].winfo_exists():
            widgets["card"].destroy()
        if job in self.jobs:
            self.jobs.remove(job)
        if delete_file and path:
            try:
                Path(path).unlink()
            except OSError:
                messagebox.showwarning("Delete failed", f"Could not delete:\n{path}")
        if not self.jobs:
            self._render_queue()
        self._update_footer()

    def _retry_job(self, job):
        job.cancel_requested.clear()
        job.update(
            status=JobStatus.QUEUED,
            percent=0.0,
            error="",
            speed="",
            eta="",
            filename="",
        )
        self.engine.submit(job)
        widgets = self.rows.get(job.id)
        if widgets:
            widgets["status"] = None
        self._update_footer()

    def _clear_completed(self):
        for job in [job for job in self.jobs if job.status == JobStatus.COMPLETE]:
            widgets = self.rows.pop(job.id, None)
            if widgets and widgets["card"].winfo_exists():
                widgets["card"].destroy()
            self.jobs.remove(job)
        if not self.jobs:
            self._render_queue()
        self._update_footer()

    def _refresh(self):
        self._watch_window_state()
        for job in list(self.jobs):
            self._update_row(job)
        self._update_footer()
        self.after(250, self._refresh)

    def _watch_window_state(self):
        """Keep the windowed size pinned at 640x360 when leaving maximized."""
        try:
            state = self.state()
        except tk.TclError:
            return
        if self._last_state == "zoomed" and state == "normal":
            self.geometry(DEFAULT_GEOMETRY)
        self._last_state = state

    def _update_footer(self):
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(text=self._counts())
        if hasattr(self, "clear_done_button") and self.clear_done_button.winfo_exists():
            has_completed = any(job.status == JobStatus.COMPLETE for job in self.jobs)
            self.clear_done_button.configure(
                state="normal" if has_completed else "disabled"
            )

    def _counts(self) -> str:
        active = sum(1 for job in self.jobs if job.status in ACTIVE_STATES)
        queued = sum(1 for job in self.jobs if job.status == JobStatus.QUEUED)
        completed = sum(1 for job in self.jobs if job.status == JobStatus.COMPLETE)
        failed = sum(1 for job in self.jobs if job.status == JobStatus.FAILED)
        parts = [f"{active} active"]
        if queued:
            parts.append(f"{queued} queued")
        parts.append(f"{completed} completed")
        if failed:
            parts.append(f"{failed} failed")
        return " • ".join(parts)

    # -------------------------------------------------------- settings

    def _output_text(self):
        return f"Save to: {self.settings.output_dir}"

    def _choose_output(self):
        selected = filedialog.askdirectory(initialdir=self.settings.output_dir)
        if selected:
            self.settings.output_dir = selected
            save_settings(self.settings)
            self.output_label.configure(text=self._output_text())

    def _settings_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("YOINK Settings")
        dialog.geometry("560x560")
        dialog.transient(self)
        dialog.grab_set()
        _apply_window_icon(dialog)
        header = ctk.CTkFrame(dialog, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))
        logo = local_image(asset_path("icons", "main-icon-nobg.png"), (52, 52))
        ctk.CTkLabel(header, text="", image=logo).pack(side="left", padx=(0, SPACE.md))
        ctk.CTkLabel(
            header, text="Settings", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            dialog, text="General", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=24, pady=(12, 4))
        ctk.CTkLabel(dialog, text="Cookies file (Netscape format)").pack(
            anchor="w", padx=24
        )
        line = ctk.CTkFrame(dialog, fg_color="transparent")
        line.pack(fill="x", padx=24)
        entry = ctk.CTkEntry(line)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, self.settings.cookies_path)
        ctk.CTkButton(
            line, text="Browse", width=80, command=lambda: self._browse_cookie(entry)
        ).pack(side="left", padx=8)
        recode = tk.BooleanVar(value=self.settings.recode_mp4)
        ctk.CTkCheckBox(dialog, text="Force full MP4 re-encode", variable=recode).pack(
            anchor="w", padx=24, pady=10
        )

        ctk.CTkLabel(
            dialog, text="Appearance", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=24, pady=(10, 4))
        theme = self._make_option_menu(
            dialog, self.themes.available(), width=220, command=self._change_theme
        )
        theme.set(self.settings.theme)
        theme.pack(anchor="w", padx=24)
        ctk.CTkLabel(
            dialog,
            text="Background selection is automatic when assets/background contains images.",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(anchor="w", padx=24, pady=8)

        def save():
            self.settings.cookies_path = entry.get().strip()
            self.settings.recode_mp4 = recode.get()
            save_settings(self.settings)
            dialog.destroy()

        footer = ctk.CTkFrame(dialog, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(16, 20))
        ctk.CTkButton(
            footer,
            text="About",
            width=90,
            command=self._about_dialog,
            font=self._fonts["small"],
            fg_color=self._dark_control_color(),
            hover_color=self._blend(self.theme["surface_alt"], 0.2),
            text_color=self.theme["text"],
        ).pack(side="left")
        ctk.CTkButton(
            footer,
            text="Save settings",
            command=save,
            font=self._fonts["small"],
            fg_color=self._blend(self.theme["accent"], 0.72),
            hover_color=self._blend(self.theme["accent"], 0.58),
            text_color=self.theme["text"],
        ).pack(side="right")

    def _about_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("About YOINK")
        dialog.geometry("480x470")
        dialog.transient(self)
        dialog.grab_set()
        _apply_window_icon(dialog)
        victory = local_image(asset_path("icons", "victory.png"), (150, 150))
        ctk.CTkLabel(
            dialog,
            text="✦" if victory is None else "",
            font=ctk.CTkFont(size=26),
            text_color=self.theme.get("moon", self.theme["accent"]),
            image=victory,
        ).pack(pady=(28, 10))
        ctk.CTkLabel(
            dialog,
            text="YOINK",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.theme["accent"],
        ).pack()
        tagline = ctk.CTkLabel(
            dialog,
            text="For Yoinkers from Yoinker. Made with ❤️ By Astartes7 and Luna 💚",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        )
        _bind_wrap(tagline)
        tagline.pack(pady=3, padx=SPACE.xl, fill="x")
        ctk.CTkLabel(
            dialog,
            text=f"Version {APP_VERSION} • Powered by yt-dlp",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(pady=(10, 2))
        credit = ctk.CTkFrame(dialog, fg_color="transparent")
        credit.pack(pady=(2, 4))
        ctk.CTkLabel(
            credit,
            text="Developed by",
            font=self._fonts["small"],
            text_color=self.theme["text_muted"],
        ).pack(side="left")
        dev = ctk.CTkLabel(
            credit,
            text=APP_AUTHOR,
            font=self._fonts["link"],
            text_color=self.theme.get("secondary", self.theme["accent"]),
            cursor="hand2",
        )
        dev.pack(side="left", padx=(SPACE.xs, 0))
        dev.bind("<Button-1>", lambda _event: webbrowser.open(APP_AUTHOR_URL))
        ctk.CTkButton(
            dialog,
            text="Close",
            width=90,
            command=dialog.destroy,
            font=self._fonts["small"],
            fg_color=self._blend(self.theme["accent"], 0.72),
            hover_color=self._blend(self.theme["accent"], 0.58),
            text_color=self.theme["text"],
        ).pack(pady=(16, 20))

    def _browse_cookie(self, entry):
        selected = filedialog.askopenfilename(
            filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")]
        )
        if selected:
            entry.delete(0, "end")
            entry.insert(0, selected)

    def _change_theme(self, name):
        try:
            self.theme = self.themes.load(name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Theme error", str(exc))
            return
        self.settings.theme = name
        save_settings(self.settings)
        ctk.set_appearance_mode(self.theme.get("appearance", "dark"))
        self._rebuild()

    def _rebuild(self):
        for child in self.winfo_children():
            child.destroy()
        self.rows.clear()
        self._queue_empty = None
        self._background = None
        self._build()
        self._load_background()
        if self.media:
            self._grid_media_section()
        self._render_media()
        self._render_queue()

    # ----------------------------------------------------- background

    def _load_background(self):
        if self.settings.background_mode == "off":
            return
        try:
            from PIL import Image
        except ImportError:
            return
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
        if not images:
            return
        selected = (
            Path(self.settings.background_path)
            if self.settings.background_mode == "selected"
            and self.settings.background_path
            else random.choice(images)
        )
        if not selected.is_file():
            return
        try:
            image = Image.open(selected).convert("RGB")
            image.thumbnail((1600, 1000))
            dim = min(100, max(0, self.settings.background_dim)) / 100
            overlay = Image.new("RGB", image.size, _hex_rgb(self.theme["bg"]))
            image = Image.blend(image, overlay, dim)
            self._background = ctk.CTkImage(
                light_image=image, dark_image=image, size=image.size
            )
            label = ctk.CTkLabel(self, text="", image=self._background)
            label.place(relx=0, rely=0, relwidth=1, relheight=1)
            label.lower()
        except (OSError, ValueError):
            return

    def _close(self):
        try:
            maximized = self.state() == "zoomed"
        except tk.TclError:
            maximized = False
        self.settings.window_maximized = maximized
        self.settings.window_geometry = (
            DEFAULT_GEOMETRY if maximized else str(self.geometry())
        )
        save_settings(self.settings)
        self.engine.shutdown()
        self.destroy()


def _bind_wrap(label: ctk.CTkLabel) -> None:
    """Wrap the label's text at its actual width so long titles and paths
    never force the page wider than the window."""
    label.configure(wraplength=220)

    def wrap(event):
        label.configure(wraplength=max(60, event.width - 4))

    label.bind("<Configure>", wrap)


def _auto_hide_scrollbar(container: ctk.CTkScrollableFrame) -> None:
    """Hide the scrollbar while the content fits; restore it when needed."""
    try:
        scrollbar = container._scrollbar
        canvas = container._parent_canvas
        original_set = scrollbar.set

        def _set(first, last):
            original_set(first, last)
            try:
                if float(first) <= 0.0 and float(last) >= 1.0:
                    scrollbar.grid_remove()
                else:
                    scrollbar.grid()
            except tk.TclError:
                pass

        canvas.configure(yscrollcommand=_set)
    except (AttributeError, tk.TclError):
        pass


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


def _valid_timestamp(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    parts = text.split(":")
    if len(parts) > 3:
        return False
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return False
    if not all(math.isfinite(number) for number in numbers):
        return False
    if not all(number >= 0 for number in numbers):
        return False
    return all(number < 60 for number in numbers[1:])


def _time_seconds(text):
    if not text:
        return 0.0
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def _clock(seconds):
    total = int(seconds)
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def _trim_error(start, end, duration):
    start_seconds = _time_seconds(start)
    end_seconds = _time_seconds(end)
    if start_seconds is None or end_seconds is None:
        return "Trim times must use HH:MM:SS digits."
    if start_seconds and end_seconds and end_seconds <= start_seconds:
        return "End time must be later than the start time."
    if duration:
        if start_seconds and start_seconds >= duration:
            return f"Start time is beyond the media duration ({_clock(duration)})."
        if end_seconds and end_seconds > duration:
            return f"End time exceeds the media duration ({_clock(duration)})."
    return None


def _core_stem(path: Path) -> str:
    """Stem with yt-dlp format-fragment suffixes removed (name.f137)."""
    return re.sub(r"\.f\d+$", "", path.stem)


def _locate_media_file(job) -> str:
    """Fallback lookup for a finished job's file in its output folder."""
    filename = job.snapshot().get("filename") or ""
    folder = Path(job.output_dir)
    if not folder.is_dir() or not filename:
        return ""
    path = Path(filename)
    candidates = [path, folder / path.name]
    core = _core_stem(path)
    if core:
        candidates.extend(
            p
            for p in folder.glob(glob_escape(core) + ".*")
            if p.suffix.lower() in _MEDIA_SUFFIXES
        )
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() not in _IGNORE_SUFFIXES:
            return str(candidate)
    return ""


def _mix(hex_a: str, hex_b: str, b_weight: float) -> str:
    """Linear blend of two hex colors; b_weight is the share of hex_b."""
    a = _hex_rgb(hex_a)
    b = _hex_rgb(hex_b)
    mixed = tuple(round(a[i] + (b[i] - a[i]) * b_weight) for i in range(3))
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    digits = hex_color.lstrip("#")
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def _apply_window_icon(widget):
    icon = asset_path("icons", "luna.ico")
    try:
        widget.iconbitmap(str(icon))
    except (tk.TclError, OSError):
        pass


def _open_path(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


def _ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which("ffmpeg")


def run():
    YoinkApp().mainloop()
