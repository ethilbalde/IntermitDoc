# -*- coding: utf-8 -*-
"""
Gestion locale des contrats prévisionnels (sans dépendance cloud).
Stockage JSON dans le dossier de config (%APPDATA%/IntermitDoc en mode exe).
"""
import json
import os
import uuid
from datetime import date as _date
from pathlib import Path


def _dossier_config() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        d = Path(appdata) / "IntermitDoc"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


def _chemin_prev() -> Path:
    return _dossier_config() / "previsionnels.json"


def charger_previsionnels() -> list:
    p = _chemin_prev()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def sauvegarder_previsionnels(prevs: list):
    _chemin_prev().write_text(
        json.dumps(prevs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ajouter_previsionnel(contrat: dict) -> list:
    """Ajoute un contrat prévisionnel et retourne la liste mise à jour."""
    prevs = charger_previsionnels()
    contrat.setdefault("id", f"prev_{_date.today().isoformat()}_{uuid.uuid4().hex[:6]}")
    contrat.setdefault("date_saisie", str(_date.today()))
    prevs.append(contrat)
    sauvegarder_previsionnels(prevs)
    return prevs


def supprimer_previsionnel(prev_id: str) -> list:
    prevs = [p for p in charger_previsionnels() if p.get("id") != prev_id]
    sauvegarder_previsionnels(prevs)
    return prevs


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _periodes_se_chevauchent(a: dict, b: dict) -> bool:
    """Vérifie si deux contrats ont des périodes qui se chevauchent."""
    try:
        a_debut = _date.fromisoformat(a.get("date_debut", ""))
        a_fin   = _date.fromisoformat(a.get("date_fin", a.get("date_debut", "")))
        b_debut = _date.fromisoformat(b.get("date_debut", ""))
        b_fin   = _date.fromisoformat(b.get("date_fin", b.get("date_debut", "")))
        return a_debut <= b_fin and b_debut <= a_fin
    except (ValueError, TypeError):
        return False
