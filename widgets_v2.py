# -*- coding: utf-8 -*-
"""
IntermitDoc — Composants UI réutilisables (refonte Soft UI).

S'appuie sur customtkinter + theme_v2.
Fournit : Card, KPICard, boutons préstylés, et 3 loaders animés
(anneau, trois points, fondu/pulse) recréés sur Canvas Tkinter.
"""
from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk

import theme_v2 as TH2


# ---------------------------------------------------------------------------
# Conteneurs
# ---------------------------------------------------------------------------

class Card(ctk.CTkFrame):
    """Carte à surface ivoire, bordure fine, coins arrondis (élévation douce)."""
    def __init__(self, master, radius: int = TH2.RADIUS_LG, **kwargs):
        super().__init__(
            master,
            corner_radius=radius,
            fg_color=TH2.C.SURFACE,
            border_color=TH2.C.BORDER,
            border_width=1,
            **kwargs,
        )


class KPICard(ctk.CTkFrame):
    """Carte compteur : petit label en capitales + grande valeur."""
    def __init__(self, master, label: str, value: str = "—",
                 value_color: str | None = None, **kwargs):
        super().__init__(
            master,
            corner_radius=TH2.RADIUS_MD,
            fg_color=TH2.C.SURFACE,
            border_color=TH2.C.BORDER,
            border_width=1,
            **kwargs,
        )
        self._lbl = ctk.CTkLabel(
            self, text=label.upper(), font=TH2.FONT_CAPS,
            text_color=TH2.C.TEXT_3, anchor="w",
        )
        self._lbl.pack(fill="x", padx=14, pady=(11, 0))
        self._val = ctk.CTkLabel(
            self, text=value, font=TH2.FONT_KPI,
            text_color=value_color or TH2.C.PRIMARY, anchor="w",
        )
        self._val.pack(fill="x", padx=14, pady=(0, 11))

    def set_value(self, value: str, color: str | None = None) -> None:
        self._val.configure(text=value)
        if color:
            self._val.configure(text_color=color)


# ---------------------------------------------------------------------------
# Boutons préstylés
# ---------------------------------------------------------------------------

def bouton_primaire(master, text: str, command=None, icon: str = "", **kwargs):
    return ctk.CTkButton(
        master,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        corner_radius=TH2.RADIUS_MD,
        fg_color=TH2.C.PRIMARY,
        hover_color=TH2.C.PRIMARY_HOV,
        text_color=TH2.C.ON_PRIMARY,
        font=TH2.FONT_BODY,
        height=38,
        **kwargs,
    )


def bouton_secondaire(master, text: str, command=None, icon: str = "", **kwargs):
    return ctk.CTkButton(
        master,
        text=(f"{icon}  {text}" if icon else text),
        command=command,
        corner_radius=TH2.RADIUS_MD,
        fg_color="transparent",
        hover_color=TH2.C.SURFACE_2,
        text_color=TH2.C.PRIMARY,
        border_color=TH2.C.PRIMARY,
        border_width=1,
        font=TH2.FONT_BODY,
        height=38,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Loaders animés (Canvas) — pilotés par after(), s'arrêtent proprement
# ---------------------------------------------------------------------------

class _BaseLoader(ctk.CTkFrame):
    def __init__(self, master, size: int = 56, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._size = size
        self._bg = TH2.C.SURFACE
        self._canvas = tk.Canvas(
            self, width=size, height=size,
            bg=self._bg, highlightthickness=0, bd=0,
        )
        self._canvas.pack()
        self._job: str | None = None
        self._t = 0.0
        self._running = False

    def set_bg(self, color: str) -> None:
        self._bg = color
        self._canvas.configure(bg=color)

    def start(self, interval: int = 33) -> None:
        if self._running:
            return
        self._running = True
        self._interval = interval
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._canvas.delete("all")

    def _tick(self) -> None:
        if not self._running:
            return
        self._t += self._interval / 1000.0
        self._render()
        self._job = self.after(self._interval, self._tick)

    def _render(self) -> None:  # overridden
        raise NotImplementedError


class LoaderAnneau(_BaseLoader):
    """Anneau qui tourne (arc) — pour opérations courtes."""
    def __init__(self, master, size: int = 56,
                 color: str | None = None, track: str | None = None, **kwargs):
        super().__init__(master, size, **kwargs)
        self._color = color or TH2.C.PRIMARY
        self._track = track or TH2.C.BORDER
        self._width = max(4, size // 11)

    def _render(self) -> None:
        c = self._canvas
        c.delete("all")
        s, w = self._size, self._width
        pad = w + 2
        c.create_oval(pad, pad, s - pad, s - pad,
                      outline=self._track, width=w)
        start = (self._t * 320) % 360
        c.create_arc(pad, pad, s - pad, s - pad,
                     start=-start, extent=-100, style="arc",
                     outline=self._color, width=w)


class LoaderPoints(_BaseLoader):
    """Trois points qui pulsent en séquence — inline / discret."""
    def __init__(self, master, size: int = 56,
                 color: str | None = None, **kwargs):
        super().__init__(master, size, **kwargs)
        self._color = color or TH2.C.PRIMARY

    def _render(self) -> None:
        c = self._canvas
        c.delete("all")
        s = self._size
        cy = s / 2
        rmax = max(4, s // 9)
        gap = rmax * 2.6
        x0 = s / 2 - gap
        for i in range(3):
            phase = (self._t * 2.2) - i * 0.45
            scale = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(phase * math.pi))
            r = rmax * scale
            cx = x0 + i * gap
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=self._color, outline="")


class LoaderFondu(_BaseLoader):
    """Cercle en fondu/expansion (pulse) — loader principal de l'analyse IA."""
    def __init__(self, master, size: int = 56,
                 color: str | None = None, **kwargs):
        super().__init__(master, size, **kwargs)
        self._color = color or TH2.C.PRIMARY

    @staticmethod
    def _mix(hex_a: str, hex_b: str, t: float) -> str:
        a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
        m = [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
        return f"#{m[0]:02x}{m[1]:02x}{m[2]:02x}"

    def _render(self) -> None:
        c = self._canvas
        c.delete("all")
        s = self._size
        cx = cy = s / 2
        rmax = s / 2 - 2
        # deux ondes décalées pour un pulse continu
        for offset in (0.0, 0.5):
            p = ((self._t * 0.6) + offset) % 1.0
            r = rmax * (0.2 + 0.8 * p)
            fade = 1.0 - p
            col = self._mix(self._bg, self._color, max(0.0, fade))
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=col, outline="")
