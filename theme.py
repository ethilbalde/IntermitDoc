# -*- coding: utf-8 -*-
"""
IntermitDoc — Design tokens + multi-theme support.

Usage:
    import theme as TH
    TH.apply_theme(root)           # first-run init (before widgets)
    TH.appliquer_theme(root, "sombre")  # switch at runtime
"""
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# Palette definitions — the only place to add/change color values
# ---------------------------------------------------------------------------

_PALETTES: dict[str, dict] = {
    "clair": {
        "SURFACE":        "#FFFFFF",
        "SURFACE_SUBTLE": "#F5F5F5",
        "BORDER":         "#E0E0E0",
        "TEXT_PRIMARY":   "#212121",
        "TEXT_SECONDARY": "#555555",
        "TEXT_MUTED":     "#888888",
        "TEXT_DISABLED":  "#9E9E9E",
        "BTN_SURFACE":    "#EEEEEE",
        "BTN_HOVER":      "#E0E0E0",
        "BTN_FG":         "#212121",
        "SV_TTK_THEME":   "light",
    },
    "medium": {
        "SURFACE":        "#F0F0F0",
        "SURFACE_SUBTLE": "#E4E4E4",
        "BORDER":         "#C8C8C8",
        "TEXT_PRIMARY":   "#1A1A1A",
        "TEXT_SECONDARY": "#444444",
        "TEXT_MUTED":     "#777777",
        "TEXT_DISABLED":  "#999999",
        "BTN_SURFACE":    "#D4D0C8",
        "BTN_HOVER":      "#C4C0B8",
        "BTN_FG":         "#1A1A1A",
        "SV_TTK_THEME":   "light",
    },
    "sombre": {
        "SURFACE":        "#2B2B2B",
        "SURFACE_SUBTLE": "#3C3C3C",
        "BORDER":         "#555555",
        "TEXT_PRIMARY":   "#E8E8E8",
        "TEXT_SECONDARY": "#AAAAAA",
        "TEXT_MUTED":     "#777777",
        "TEXT_DISABLED":  "#666666",
        "BTN_SURFACE":    "#4E4E4E",
        "BTN_HOVER":      "#5E5E5E",
        "BTN_FG":         "#E8E8E8",
        "SV_TTK_THEME":   "dark",
    },
    # --- Color combos from @design.deb batch 1 ---
    "bourgogne": {                         # Deep Burgundy + Golden Sand
        "SURFACE":        "#3D0A0E",
        "SURFACE_SUBTLE": "#5B0E14",
        "BORDER":         "#7A2020",
        "TEXT_PRIMARY":   "#F1E194",
        "TEXT_SECONDARY": "#D4C060",
        "TEXT_MUTED":     "#988840",
        "TEXT_DISABLED":  "#685E30",
        "BTN_SURFACE":    "#8A1A1A",
        "BTN_HOVER":      "#A82020",
        "BTN_FG":         "#F1E194",
        "SV_TTK_THEME":   "dark",
    },
    "violet": {                            # Lemon Chiffon + Ultra Violet
        "SURFACE":        "#FEFACD",
        "SURFACE_SUBTLE": "#F0EAA8",
        "BORDER":         "#C8BA50",
        "TEXT_PRIMARY":   "#3D2D6B",
        "TEXT_SECONDARY": "#5F4A8B",
        "TEXT_MUTED":     "#8070A8",
        "TEXT_DISABLED":  "#A898C0",
        "BTN_SURFACE":    "#6A50B8",
        "BTN_HOVER":      "#5A40A8",
        "BTN_FG":         "#FEFACD",
        "SV_TTK_THEME":   "light",
    },
    "citrouille": {                        # Pumpkin + Charcoal
        "SURFACE":        "#1A2E3A",
        "SURFACE_SUBTLE": "#233D4C",
        "BORDER":         "#3A5568",
        "TEXT_PRIMARY":   "#FDEEE0",
        "TEXT_SECONDARY": "#FDB07E",
        "TEXT_MUTED":     "#8AAABB",
        "TEXT_DISABLED":  "#4A6070",
        "BTN_SURFACE":    "#FD802E",
        "BTN_HOVER":      "#E87020",
        "BTN_FG":         "#1A2E3A",
        "SV_TTK_THEME":   "dark",
    },
    "ocean": {                             # Cloudy Sky + Ocean Blue
        "SURFACE":        "#CBDDE9",
        "SURFACE_SUBTLE": "#B8CDD8",
        "BORDER":         "#90B0C8",
        "TEXT_PRIMARY":   "#183048",
        "TEXT_SECONDARY": "#2872A1",
        "TEXT_MUTED":     "#5898B8",
        "TEXT_DISABLED":  "#90B0C8",
        "BTN_SURFACE":    "#2872A1",
        "BTN_HOVER":      "#186090",
        "BTN_FG":         "#FFFFFF",
        "SV_TTK_THEME":   "light",
    },
    # --- Color combos from @design.deb batch 2 ---
    "tiffany": {                           # Combo 01 — Dark Gray + Tiffany mint
        "SURFACE":        "#171717",
        "SURFACE_SUBTLE": "#252525",
        "BORDER":         "#2E4A3E",
        "TEXT_PRIMARY":   "#21F1A8",
        "TEXT_SECONDARY": "#18C888",
        "TEXT_MUTED":     "#10A060",
        "TEXT_DISABLED":  "#0A6040",
        "BTN_SURFACE":    "#1A5A42",
        "BTN_HOVER":      "#207050",
        "BTN_FG":         "#21F1A8",
        "SV_TTK_THEME":   "dark",
    },
    "corail": {                            # Combo 02 — Chill White + True Pink
        "SURFACE":        "#FFF9FA",
        "SURFACE_SUBTLE": "#FFE8ED",
        "BORDER":         "#FFB0C0",
        "TEXT_PRIMARY":   "#C00830",
        "TEXT_SECONDARY": "#A00828",
        "TEXT_MUTED":     "#B84060",
        "TEXT_DISABLED":  "#D88090",
        "BTN_SURFACE":    "#FD1843",
        "BTN_HOVER":      "#E01035",
        "BTN_FG":         "#FFFFFF",     # white on red — fix critique
        "SV_TTK_THEME":   "light",
    },
    "cyber": {                             # Combo 03 — Charcoal Violet + Cyber Lime
        "SURFACE":        "#3C1A47",
        "SURFACE_SUBTLE": "#4E2460",
        "BORDER":         "#6A3882",
        "TEXT_PRIMARY":   "#B6FF00",
        "TEXT_SECONDARY": "#90D000",
        "TEXT_MUTED":     "#68A000",
        "TEXT_DISABLED":  "#486800",
        "BTN_SURFACE":    "#6A3890",
        "BTN_HOVER":      "#7A48A8",
        "BTN_FG":         "#B6FF00",
        "SV_TTK_THEME":   "dark",
    },
    "chypre": {                            # Combo 04 — Cyprus teal + Sand beige
        "SURFACE":        "#004741",
        "SURFACE_SUBTLE": "#005850",
        "BORDER":         "#007868",
        "TEXT_PRIMARY":   "#F0EDE4",
        "TEXT_SECONDARY": "#C8C5BC",
        "TEXT_MUTED":     "#909085",
        "TEXT_DISABLED":  "#606055",
        "BTN_SURFACE":    "#00A888",
        "BTN_HOVER":      "#00C0A0",
        "BTN_FG":         "#003830",
        "SV_TTK_THEME":   "dark",
    },
    "limon": {                             # Combo 05 — Lime Sprout + Fresh Canopy
        "SURFACE":        "#E4FD97",
        "SURFACE_SUBTLE": "#D0EC80",
        "BORDER":         "#A8C860",
        "TEXT_PRIMARY":   "#2D3E2C",
        "TEXT_SECONDARY": "#3E5438",
        "TEXT_MUTED":     "#607850",
        "TEXT_DISABLED":  "#80A070",
        "BTN_SURFACE":    "#6A9828",
        "BTN_HOVER":      "#588020",
        "BTN_FG":         "#FFFFFF",
        "SV_TTK_THEME":   "light",
    },
    "menthe": {                            # Combo 06 — Milky white + Mantis green
        "SURFACE":        "#FFFDF1",
        "SURFACE_SUBTLE": "#F0FAE0",
        "BORDER":         "#C0E8A0",
        "TEXT_PRIMARY":   "#2A5A20",
        "TEXT_SECONDARY": "#3A7828",
        "TEXT_MUTED":     "#7AB868",
        "TEXT_DISABLED":  "#A0D090",
        "BTN_SURFACE":    "#48B038",
        "BTN_HOVER":      "#389828",
        "BTN_FG":         "#FFFDF1",
        "SV_TTK_THEME":   "light",
    },
    "curcuma": {                           # Combo 07 — Malt dark + Turmeric gold
        "SURFACE":        "#2A2312",
        "SURFACE_SUBTLE": "#3C3218",
        "BORDER":         "#584820",
        "TEXT_PRIMARY":   "#FFBE0B",
        "TEXT_SECONDARY": "#E0A000",
        "TEXT_MUTED":     "#A87800",
        "TEXT_DISABLED":  "#705000",
        "BTN_SURFACE":    "#FFBE0B",
        "BTN_HOVER":      "#E0A800",
        "BTN_FG":         "#2A2312",
        "SV_TTK_THEME":   "dark",
    },
    "silver": {                            # Combo 08 — Silver black + Luminous Moss
        "SURFACE":        "#141414",
        "SURFACE_SUBTLE": "#222222",
        "BORDER":         "#2A3A2A",
        "TEXT_PRIMARY":   "#2BEE34",
        "TEXT_SECONDARY": "#20C828",
        "TEXT_MUTED":     "#18A020",
        "TEXT_DISABLED":  "#0E6814",
        "BTN_SURFACE":    "#1A5A20",
        "BTN_HOVER":      "#207028",
        "BTN_FG":         "#2BEE34",
        "SV_TTK_THEME":   "dark",
    },
    "volcan": {                            # Combo 09 — Noturno navy + Vulcanico red
        "SURFACE":        "#001621",
        "SURFACE_SUBTLE": "#002538",
        "BORDER":         "#003858",
        "TEXT_PRIMARY":   "#FF4103",
        "TEXT_SECONDARY": "#E03800",
        "TEXT_MUTED":     "#A02800",
        "TEXT_DISABLED":  "#681800",
        "BTN_SURFACE":    "#FF4103",
        "BTN_HOVER":      "#E03800",
        "BTN_FG":         "#001621",
        "SV_TTK_THEME":   "dark",
    },
    "nacre": {                             # Combo 10 — Skin Tone peach + Bridal wine
        "SURFACE":        "#FFF0E8",
        "SURFACE_SUBTLE": "#FFE0D0",
        "BORDER":         "#E8B090",
        "TEXT_PRIMARY":   "#741A2F",
        "TEXT_SECONDARY": "#9A2040",
        "TEXT_MUTED":     "#B85060",
        "TEXT_DISABLED":  "#D08090",
        "BTN_SURFACE":    "#A02840",
        "BTN_HOVER":      "#881E34",
        "BTN_FG":         "#FFF0E8",
        "SV_TTK_THEME":   "light",
    },
}

_THEME_COURANT = "clair"


def _palette() -> dict:
    return _PALETTES[_THEME_COURANT]


# ---------------------------------------------------------------------------
# Module-level color constants (updated by appliquer_theme)
# ---------------------------------------------------------------------------

# Brand primaries — static, not theme-dependent
PRIMARY         = "#1976D2"
PRIMARY_DARK    = "#1565C0"
PRIMARY_DARKER  = "#1A237E"
PRIMARY_LIGHT   = "#E3F2FD"

# Semantic — static
SUCCESS         = "#2E7D32"
SUCCESS_LIGHT   = "#E8F5E9"
SUCCESS_MED     = "#c8e6c9"
WARNING         = "#E65100"
WARNING_MED     = "#F57C00"
WARNING_LIGHT   = "#FFF8E1"
WARNING_PALE    = "#FFE0B2"
DANGER          = "#C62828"
DANGER_DARK     = "#B71C1C"
DANGER_BRIGHT   = "#D32F2F"
DANGER_LIGHT    = "#FFEBEE"
DANGER_MED      = "#ffcdd2"
PURPLE          = "#6A1B9A"
PURPLE_MED      = "#7B1FA2"
PURPLE_LIGHT    = "#F3E5F5"
ORANGE_DARK     = "#E65100"

# Confidence / row tints — static
CONF_HIGH       = SUCCESS_MED
CONF_MED        = "#fff9c4"
CONF_LOW        = DANGER_MED
ROW_AEM         = "#E3F2FD"
ROW_BP          = SUCCESS_LIGHT
ROW_CS          = WARNING_LIGHT
ROW_CT          = WARNING_LIGHT
ROW_STC         = "#FCE4EC"
ROW_TOTAL       = "#C5CAE9"
ROW_SEP         = "#E8EAF6"
ROW_PREV        = PURPLE_LIGHT
ROW_OK          = SUCCESS_MED
ROW_ERR         = DANGER_MED
ROW_FALLBACK    = WARNING_PALE
ROW_IGNORE      = "#E0E0E0"

# Button presets — (bg, fg)
BTN_PRIMARY     = (PRIMARY,       "white")
BTN_SUCCESS     = ("#388E3C",     "white")
BTN_SUCCESS_DK  = ("#1B5E20",     "white")
BTN_DANGER      = (DANGER_BRIGHT, "white")
BTN_WARNING     = (WARNING_MED,   "white")
BTN_PURPLE      = (PURPLE,        "white")

# Theme-dependent — updated by appliquer_theme()
SURFACE         = "#FFFFFF"
SURFACE_SUBTLE  = "#F5F5F5"
BORDER          = "#E0E0E0"
TEXT_PRIMARY    = "#212121"
TEXT_SECONDARY  = "#555555"
TEXT_MUTED      = "#888888"
TEXT_DISABLED   = "#9E9E9E"
BTN_SURFACE     = "#EEEEEE"
BTN_HOVER       = "#E0E0E0"
BTN_FG          = "#212121"
BTN_NEUTRAL     = (SURFACE, TEXT_PRIMARY)

# ---------------------------------------------------------------------------
# Typography / spacing — static
# ---------------------------------------------------------------------------

FONT_BASE       = ("Segoe UI", 9)
FONT_SMALL      = ("Segoe UI", 8)
FONT_BODY       = ("Segoe UI", 10)
FONT_LABEL      = ("Segoe UI", 9, "bold")
FONT_HEADING    = ("Segoe UI", 11, "bold")
FONT_KPI_VALUE  = ("Segoe UI", 16, "bold")
FONT_KPI_LABEL  = ("Segoe UI", 8)
FONT_MONO       = ("Consolas", 9)
FONT_MONO_MED   = ("Consolas", 10)

PAD_XS  = 2
PAD_SM  = 4
PAD_MD  = 8
PAD_LG  = 12
PAD_XL  = 16
PAD_2XL = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_globals(p: dict) -> None:
    """Refresh theme-dependent module-level constants from palette p."""
    g = globals()
    for key in ("SURFACE", "SURFACE_SUBTLE", "BORDER",
                "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED", "TEXT_DISABLED",
                "BTN_SURFACE", "BTN_HOVER", "BTN_FG"):
        g[key] = p[key]
    g["BTN_NEUTRAL"] = (p["SURFACE"], p["TEXT_PRIMARY"])


def _appliquer_options_tk(root: tk.Misc, p: dict) -> None:
    """Set option_add defaults — specific widget classes only (no '*' wildcard)."""
    surf = p["SURFACE"]
    text = p["TEXT_PRIMARY"]
    btn  = p["BTN_SURFACE"]
    bhov = p["BTN_HOVER"]
    bfg  = p["BTN_FG"]
    bord = p["BORDER"]

    for cls in ("Frame", "Label", "Canvas", "Toplevel", "LabelFrame"):
        root.option_add(f"*{cls}.background",  surf,  "interactive")
        root.option_add(f"*{cls}.foreground",  text,  "interactive")

    root.option_add("*Entry.background",          surf,  "interactive")
    root.option_add("*Entry.foreground",          text,  "interactive")
    root.option_add("*Entry.relief",              "solid", "interactive")
    root.option_add("*Entry.borderWidth",         "1",   "interactive")
    root.option_add("*Entry.highlightThickness",  "1",   "interactive")
    root.option_add("*Entry.highlightColor",      PRIMARY, "interactive")
    root.option_add("*Entry.highlightBackground", bord,  "interactive")

    root.option_add("*Button.relief",           "flat", "interactive")
    root.option_add("*Button.background",       btn,   "interactive")
    root.option_add("*Button.foreground",       bfg,   "interactive")
    root.option_add("*Button.activeBackground", bhov,  "interactive")
    root.option_add("*Button.activeForeground", bfg,   "interactive")
    root.option_add("*Button.padX",             "10",  "interactive")
    root.option_add("*Button.padY",             "5",   "interactive")
    root.option_add("*Button.cursor",           "hand2", "interactive")
    root.option_add("*Button.borderWidth",      "0",   "interactive")

    root.option_add("*selectBackground", PRIMARY, "interactive")
    root.option_add("*selectForeground", "white", "interactive")


def _patch_ttk_style(p: dict) -> None:
    """Update ttk Style tokens to match the current palette."""
    surf  = p["SURFACE"]
    sub   = p["SURFACE_SUBTLE"]
    text  = p["TEXT_PRIMARY"]
    bsrf  = p["BTN_SURFACE"]
    bfg   = p["BTN_FG"]

    style = ttk.Style()

    style.configure("TFrame",       background=surf)
    style.configure("TLabel",       background=surf, foreground=text)
    style.configure("TLabelframe",  background=surf, foreground=text)
    style.configure("TLabelframe.Label", background=surf, foreground=text)
    style.configure("TButton",      background=bsrf, foreground=bfg, relief="flat", padding=(8, 4))
    style.map("TButton",
              background=[("active", p["BTN_HOVER"])],
              foreground=[("disabled", p["TEXT_DISABLED"])])

    style.configure("Treeview",
                    rowheight=26,
                    font=("Segoe UI", 9),
                    background=surf,
                    fieldbackground=surf,
                    foreground=text)
    style.configure("Treeview.Heading",
                    font=("Segoe UI", 9, "bold"),
                    padding=(4, 4),
                    background=sub,
                    foreground=text,
                    relief="flat")
    style.map("Treeview.Heading", relief=[("active", "flat")])
    style.map("Treeview",
              background=[("selected", PRIMARY)],
              foreground=[("selected", "white")])

    style.configure("TNotebook",     background=sub)
    style.configure("TNotebook.Tab", font=("Segoe UI", 9), padding=(12, 6),
                    background=sub, foreground=text)
    style.map("TNotebook.Tab",
              background=[("selected", surf)],
              foreground=[("selected", text)])

    style.configure("TCombobox",  background=surf, foreground=text,
                    fieldbackground=surf, selectbackground=PRIMARY,
                    selectforeground="white")
    style.configure("TScrollbar", background=sub, troughcolor=surf, arrowcolor=text)


def _recolorer_widgets(widget: tk.Misc, p: dict) -> None:
    """Recursively recolor tk (non-ttk) widgets to match palette p."""
    surf = p["SURFACE"]
    text = p["TEXT_PRIMARY"]
    btn  = p["BTN_SURFACE"]
    bfg  = p["BTN_FG"]

    cls = widget.winfo_class()

    # Only touch "plain" tk widgets — avoid ttk and custom-colored ones
    if cls in ("Frame", "Toplevel"):
        try:
            widget.configure(bg=surf)
        except tk.TclError:
            pass
    elif cls == "Label":
        try:
            # Preserve explicitly set foreground colors (e.g. colored status labels)
            current_fg = widget.cget("fg")
            _text_tokens = {p["TEXT_PRIMARY"] for p in _PALETTES.values()}
            if current_fg in _text_tokens:
                widget.configure(fg=text)
            widget.configure(bg=surf)
        except tk.TclError:
            pass
    elif cls == "Canvas":
        try:
            widget.configure(bg=surf)
        except tk.TclError:
            pass
    elif cls == "Button":
        try:
            current_bg = widget.cget("bg")
            _btn_tokens = {p["BTN_SURFACE"] for p in _PALETTES.values()}
            _surf_tokens = {p["SURFACE"] for p in _PALETTES.values()}
            if current_bg in _btn_tokens | _surf_tokens:
                widget.configure(bg=btn, fg=bfg, activebackground=p["BTN_HOVER"],
                                 activeforeground=bfg)
        except tk.TclError:
            pass
    elif cls == "Entry":
        try:
            widget.configure(bg=surf, fg=text)
        except tk.TclError:
            pass
    elif cls == "Text":
        try:
            widget.configure(bg=surf, fg=text)
        except tk.TclError:
            pass

    for child in widget.winfo_children():
        _recolorer_widgets(child, p)


def _set_fonts(root: tk.Misc) -> None:
    """Set Segoe UI as the default font globally (once)."""
    import tkinter.font as tkfont
    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                  "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(fname).configure(family="Segoe UI", size=9)
        except Exception:
            pass
    try:
        tkfont.nametofont("TkFixedFont").configure(family="Consolas", size=9)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_theme(root: tk.Tk) -> None:
    """
    Initialize the theme system (call once, BEFORE any widgets are created).
    Uses sv_ttk if available, then sets tk defaults.
    """
    global _THEME_COURANT
    _THEME_COURANT = "clair"
    p = _palette()
    _update_globals(p)

    try:
        import sv_ttk
        sv_ttk.set_theme(p["SV_TTK_THEME"])
    except Exception:
        style = ttk.Style(root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")

    root.configure(bg=p["SURFACE"])
    _appliquer_options_tk(root, p)
    _set_fonts(root)
    _patch_ttk_style(p)


def appliquer_theme(root: tk.Tk, nom: str) -> None:
    """
    Switch to a different theme at runtime.
    nom: "clair" | "medium" | "sombre"
    """
    global _THEME_COURANT
    if nom not in _PALETTES:
        return
    _THEME_COURANT = nom
    p = _palette()
    _update_globals(p)

    try:
        import sv_ttk
        sv_ttk.set_theme(p["SV_TTK_THEME"])
    except Exception:
        pass

    root.configure(bg=p["SURFACE"])
    _appliquer_options_tk(root, p)
    _patch_ttk_style(p)
    _recolorer_widgets(root, p)


def theme_courant() -> str:
    return _THEME_COURANT


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def btn(parent, text: str, command=None, preset=None, **kwargs) -> tk.Button:
    """tk.Button with consistent styling. preset = (bg, fg)."""
    if preset is None:
        preset = BTN_NEUTRAL
    bg, fg = preset
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        relief=tk.FLAT,
        padx=kwargs.pop("padx", PAD_MD),
        pady=kwargs.pop("pady", PAD_SM - 1),
        cursor="hand2",
        activebackground=_darken(bg),
        activeforeground=fg,
        font=kwargs.pop("font", FONT_BASE),
        **kwargs,
    )


def _darken(hex_color: str, amount: int = 20) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "#" + h
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{max(0,r-amount):02x}{max(0,g-amount):02x}{max(0,b-amount):02x}"


def section_title(parent, text: str, color: str = PRIMARY_DARKER) -> tk.Label:
    return tk.Label(parent, text=text, font=FONT_HEADING, fg=color, anchor="w")


def kpi_card(parent, label: str, value: str = "—",
             value_color: str = PRIMARY_DARK) -> tuple:
    frame = tk.Frame(parent, padx=PAD_MD, pady=PAD_SM)
    lbl_val  = tk.Label(frame, text=value, font=FONT_KPI_VALUE,
                        fg=value_color, anchor="center")
    lbl_val.pack()
    lbl_name = tk.Label(frame, text=label, font=FONT_KPI_LABEL,
                        fg=TEXT_MUTED, anchor="center")
    lbl_name.pack()
    return frame, lbl_val
