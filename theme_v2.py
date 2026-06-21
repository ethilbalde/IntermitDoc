# -*- coding: utf-8 -*-
"""
IntermitDoc — Design system v2 (Soft UI, crème/teal).

Tokens centralisés pour la refonte UI basée sur customtkinter.
Inspiré des références @design.deb : fond crème, accent teal sapin,
coins arrondis généreux, élévation douce (bordures fines, pas d'ombre).

Usage:
    import theme_v2 as TH2
    TH2.appliquer(nom="figma")          # applique une palette
    c = TH2.C                            # accès aux couleurs courantes
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Palettes — chaque palette définit le jeu complet de tokens couleur
# ---------------------------------------------------------------------------
# Clés:
#   BG          fond fenêtre / app
#   SIDEBAR     fond barre latérale
#   SURFACE     fond carte / panneau
#   SURFACE_2   fond carte secondaire / hover léger
#   BORDER      bordure fine (élévation)
#   PRIMARY     accent principal (boutons, actif)
#   PRIMARY_HOV survol accent principal
#   ON_PRIMARY  texte/icône sur accent
#   ACCENT      accent secondaire (sable / décoratif)
#   TEXT        texte principal
#   TEXT_2      texte secondaire / labels
#   TEXT_3      texte discret / hints
#   SUCCESS / WARNING / DANGER  états sémantiques
#   APPEARANCE  "light" | "dark" (mode CTk sous-jacent)

_PALETTES: dict[str, dict] = {
    "figma": {                       # crème + teal sapin (défaut)
        "BG":          "#F4F0E6",
        "SIDEBAR":     "#EFEADC",
        "SURFACE":     "#FBF8F0",
        "SURFACE_2":   "#F2ECDD",
        "BORDER":      "#DED6C2",
        "PRIMARY":     "#16504A",
        "PRIMARY_HOV": "#0F3F39",
        "ON_PRIMARY":  "#F2EEDF",
        "ACCENT":      "#C9A876",
        "TEXT":        "#23221E",
        "TEXT_2":      "#5C584C",
        "TEXT_3":      "#8A8675",
        "SUCCESS":     "#2E7D52",
        "WARNING":     "#B07A2E",
        "DANGER":      "#B0402E",
        "APPEARANCE":  "light",
    },
    "clair": {
        "BG":          "#FFFFFF",
        "SIDEBAR":     "#F5F5F5",
        "SURFACE":     "#FFFFFF",
        "SURFACE_2":   "#F0F0F0",
        "BORDER":      "#E0E0E0",
        "PRIMARY":     "#1976D2",
        "PRIMARY_HOV": "#1565C0",
        "ON_PRIMARY":  "#FFFFFF",
        "ACCENT":      "#90CAF9",
        "TEXT":        "#212121",
        "TEXT_2":      "#555555",
        "TEXT_3":      "#888888",
        "SUCCESS":     "#2E7D32",
        "WARNING":     "#E65100",
        "DANGER":      "#C62828",
        "APPEARANCE":  "light",
    },
    "sombre": {
        "BG":          "#1F1F1F",
        "SIDEBAR":     "#262626",
        "SURFACE":     "#2B2B2B",
        "SURFACE_2":   "#3C3C3C",
        "BORDER":      "#454545",
        "PRIMARY":     "#3B9C82",
        "PRIMARY_HOV": "#46B095",
        "ON_PRIMARY":  "#0F1A17",
        "ACCENT":      "#C9A876",
        "TEXT":        "#E8E8E8",
        "TEXT_2":      "#AAAAAA",
        "TEXT_3":      "#777777",
        "SUCCESS":     "#4CAF7D",
        "WARNING":     "#E0A000",
        "DANGER":      "#E06A56",
        "APPEARANCE":  "dark",
    },
    "bourgogne": {
        "BG":          "#3D0A0E",
        "SIDEBAR":     "#4A0C11",
        "SURFACE":     "#5B0E14",
        "SURFACE_2":   "#6A1218",
        "BORDER":      "#7A2020",
        "PRIMARY":     "#C9A23E",
        "PRIMARY_HOV": "#E0B850",
        "ON_PRIMARY":  "#3D0A0E",
        "ACCENT":      "#F1E194",
        "TEXT":        "#F1E194",
        "TEXT_2":      "#D4C060",
        "TEXT_3":      "#988840",
        "SUCCESS":     "#9FC24E",
        "WARNING":     "#E0A000",
        "DANGER":      "#E06A56",
        "APPEARANCE":  "dark",
    },
    "ocean": {
        "BG":          "#CBDDE9",
        "SIDEBAR":     "#B8CDD8",
        "SURFACE":     "#E6F0F6",
        "SURFACE_2":   "#D2E2EC",
        "BORDER":      "#A0BCD0",
        "PRIMARY":     "#1E6A98",
        "PRIMARY_HOV": "#155680",
        "ON_PRIMARY":  "#FFFFFF",
        "ACCENT":      "#5898B8",
        "TEXT":        "#143048",
        "TEXT_2":      "#2872A1",
        "TEXT_3":      "#5E8AAB",
        "SUCCESS":     "#2E7D52",
        "WARNING":     "#B07A2E",
        "DANGER":      "#B0402E",
        "APPEARANCE":  "light",
    },
    "tiffany": {
        "BG":          "#171717",
        "SIDEBAR":     "#1F1F1F",
        "SURFACE":     "#242424",
        "SURFACE_2":   "#2E2E2E",
        "BORDER":      "#34433C",
        "PRIMARY":     "#21F1A8",
        "PRIMARY_HOV": "#3BF5B8",
        "ON_PRIMARY":  "#0A1A14",
        "ACCENT":      "#18C888",
        "TEXT":        "#E8FFF6",
        "TEXT_2":      "#7FD9BC",
        "TEXT_3":      "#4E9E84",
        "SUCCESS":     "#21F1A8",
        "WARNING":     "#E0C000",
        "DANGER":      "#FF6B5B",
        "APPEARANCE":  "dark",
    },
    "curcuma": {
        "BG":          "#2A2312",
        "SIDEBAR":     "#332B16",
        "SURFACE":     "#3A3218",
        "SURFACE_2":   "#473C1E",
        "BORDER":      "#584820",
        "PRIMARY":     "#FFBE0B",
        "PRIMARY_HOV": "#FFD040",
        "ON_PRIMARY":  "#2A2312",
        "ACCENT":      "#E0A000",
        "TEXT":        "#FFEFC8",
        "TEXT_2":      "#E0A000",
        "TEXT_3":      "#A87800",
        "SUCCESS":     "#9FC24E",
        "WARNING":     "#FFBE0B",
        "DANGER":      "#E06A56",
        "APPEARANCE":  "dark",
    },
}

DEFAUT = "figma"
_courant = DEFAUT


class _Colors:
    """Accès attribut aux tokens de la palette courante : TH2.C.PRIMARY etc."""
    def __getattr__(self, name: str) -> str:
        try:
            return _PALETTES[_courant][name]
        except KeyError as e:
            raise AttributeError(name) from e


C = _Colors()


# ---------------------------------------------------------------------------
# Échelles — radius, spacing, typo
# ---------------------------------------------------------------------------

RADIUS_SM = 8
RADIUS_MD = 11
RADIUS_LG = 14
RADIUS_XL = 18

PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 22
PAD_2XL = 30

FONT_FAMILY = "Segoe UI"
FONT_TITLE   = (FONT_FAMILY, 18, "bold")
FONT_HEADING = (FONT_FAMILY, 15, "bold")
FONT_BODY    = (FONT_FAMILY, 13)
FONT_LABEL   = (FONT_FAMILY, 12)
FONT_SMALL   = (FONT_FAMILY, 11)
FONT_KPI     = (FONT_FAMILY, 22, "bold")
FONT_CAPS    = (FONT_FAMILY, 11)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def noms_palettes() -> list[str]:
    return list(_PALETTES.keys())


def palette_courante() -> str:
    return _courant


def appliquer(nom: str = DEFAUT) -> None:
    """Définit la palette active + le mode d'apparence CTk sous-jacent."""
    global _courant
    if nom not in _PALETTES:
        nom = DEFAUT
    _courant = nom
    try:
        import customtkinter as ctk
        ctk.set_appearance_mode(_PALETTES[nom]["APPEARANCE"])
    except Exception:
        pass


def couleurs(nom: str | None = None) -> dict:
    return dict(_PALETTES[nom or _courant])
