from dataclasses import dataclass

import customtkinter as ctk


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


SPACE = Spacing()
CARD_RADIUS = 14


def fonts() -> dict[str, ctk.CTkFont]:
    return {
        "brand": ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
        "section": ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        "title": ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        "body": ctk.CTkFont(family="Segoe UI", size=13),
        "small": ctk.CTkFont(family="Segoe UI", size=12),
        "link": ctk.CTkFont(family="Segoe UI", size=13, underline=True),
    }


def card(parent, theme, **kwargs):
    return ctk.CTkFrame(
        parent,
        fg_color=theme["surface"],
        border_width=1,
        border_color=theme["border"],
        corner_radius=CARD_RADIUS,
        **kwargs,
    )
