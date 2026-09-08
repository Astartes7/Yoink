import tkinter as tk

import customtkinter as ctk


class TimeEntry(ctk.CTkFrame):
    """Masked HH:MM:SS entry: colons are fixed and segments default to 00.

    Clicking a segment selects it so typing replaces the digits; only digits
    are accepted and empty segments fall back to 00, so the mask never
    disappears.
    """

    def __init__(self, master, theme: dict, **kwargs):
        super().__init__(
            master,
            fg_color=theme["surface_alt"],
            corner_radius=8,
            border_width=1,
            border_color=theme["border"],
            **kwargs,
        )
        self._segments: list[ctk.CTkEntry] = []
        for index in range(3):
            if index:
                ctk.CTkLabel(
                    self, text=":", width=8, text_color=theme["text_muted"]
                ).pack(side="left")
            entry = ctk.CTkEntry(
                self,
                width=36,
                justify="center",
                border_width=0,
                fg_color="transparent",
                font=ctk.CTkFont(size=12),
            )
            vcmd = (self.register(self._validate), "%P")
            try:
                entry.configure(validate="key", validatecommand=vcmd)
            except tk.TclError:
                entry._entry.configure(validate="key", validatecommand=vcmd)
            entry.insert(0, "00")
            entry.bind(
                "<FocusIn>", lambda _e, widget=entry: self._select_segment(widget)
            )
            entry.bind(
                "<FocusOut>", lambda _e, widget=entry: self._restore_segment(widget)
            )
            entry.pack(side="left")
            self._segments.append(entry)

    @staticmethod
    def _validate(proposed: str) -> bool:
        return proposed == "" or (proposed.isdigit() and len(proposed) <= 2)

    def _select_segment(self, widget):
        widget.focus_set()
        try:
            widget.select_range(0, "end")
        except (AttributeError, tk.TclError):
            try:
                widget._entry.select_range(0, tk.END)
            except (AttributeError, tk.TclError):
                pass

    def _restore_segment(self, widget):
        if not widget.get():
            widget.delete(0, "end")
            widget.insert(0, "00")

    def reset(self) -> None:
        """Restore every segment to 00 (no trim)."""
        for segment in self._segments:
            segment.delete(0, "end")
            segment.insert(0, "00")

    def get(self) -> str:
        values = []
        for segment in self._segments:
            text = segment.get().strip()
            values.append(text.zfill(2) if text.isdigit() and text else "00")
        if all(value == "00" for value in values):
            return ""
        return ":".join(values)

    def seconds(self) -> float:
        text = self.get()
        if not text:
            return 0.0
        hours, minutes, secs = (int(part) for part in text.split(":"))
        return hours * 3600 + minutes * 60 + secs
