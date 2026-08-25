# -*- coding: utf-8 -*-
"""
Import de contrats prévisionnels depuis un agenda Google (lien ICS public).
Aucune dépendance OAuth : simple lecture d'un flux .ics en HTTP.
Stockage JSON dans le dossier de config (%APPDATA%/IntermitDoc en mode exe).
"""
import json
import os
import re
import urllib.request
from datetime import date as _date, datetime as _datetime
from pathlib import Path

from previsionnel import charger_previsionnels, ajouter_previsionnel

_DEFAUT_TAGS = ["[taff]", "[Flo]"]


def _dossier_config() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        d = Path(appdata) / "IntermitDoc"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


def _chemin_agenda() -> Path:
    return _dossier_config() / "agenda_liaisons.json"


def charger_config_agenda() -> dict:
    p = _chemin_agenda()
    defaut = {"url_ics": "", "tags_travail": list(_DEFAUT_TAGS), "liaisons": []}
    if not p.exists():
        return defaut
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return defaut
    defaut.update(cfg)
    return defaut


def sauvegarder_config_agenda(cfg: dict):
    _chemin_agenda().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Parsing ICS minimal (RFC 5545, sans dépendance externe) ─────────────────

def _deplier_lignes(texte: str) -> list:
    """Recolle les lignes de continuation (commençant par espace/tab)."""
    brutes = texte.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lignes = []
    for ligne in brutes:
        if ligne.startswith((" ", "\t")) and lignes:
            lignes[-1] += ligne[1:]
        elif ligne.strip():
            lignes.append(ligne)
    return lignes


def _desechapper(v: str) -> str:
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",") \
             .replace("\\;", ";").replace("\\\\", "\\")


def _parser_date_ics(valeur: str):
    """Retourne (date_ou_datetime, tout_le_jour: bool)."""
    valeur = valeur.strip().rstrip("Z")
    if "T" in valeur:
        d, t = valeur.split("T", 1)
        t = (t + "000000")[:6]
        return _datetime(int(d[0:4]), int(d[4:6]), int(d[6:8]),
                          int(t[0:2]), int(t[2:4]), int(t[4:6])), False
    return _date(int(valeur[0:4]), int(valeur[4:6]), int(valeur[6:8])), True


def parser_ics(texte: str) -> list:
    """Extrait les VEVENT d'un flux ICS -> liste de dicts summary/dtstart/dtend/all_day."""
    evenements = []
    en_event = False
    courant = {}
    for ligne in _deplier_lignes(texte):
        if ligne.startswith("BEGIN:VEVENT"):
            en_event = True
            courant = {}
            continue
        if ligne.startswith("END:VEVENT"):
            if en_event and "summary" in courant and "dtstart" in courant:
                evenements.append(courant)
            en_event = False
            continue
        if not en_event or ":" not in ligne:
            continue
        cle_params, valeur = ligne.split(":", 1)
        cle = cle_params.split(";")[0].upper()
        if cle == "SUMMARY":
            courant["summary"] = _desechapper(valeur.strip())
        elif cle == "DTSTART":
            courant["dtstart"], courant["all_day"] = _parser_date_ics(valeur)
        elif cle == "DTEND":
            courant["dtend"], _ = _parser_date_ics(valeur)
        elif cle == "UID":
            courant["uid"] = valeur.strip()
    return evenements


def telecharger_ics(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as rep:
        return rep.read().decode("utf-8", errors="replace")


# ── Rapprochement mots-clés / liaisons ───────────────────────────────────────

def _a_tag_travail(titre: str, tags_travail: list) -> bool:
    if not tags_travail:
        return True
    return any(tag in titre for tag in tags_travail)


def _trouver_liaison(titre: str, liaisons: list):
    titre_bas = titre.lower()
    for liaison in liaisons:
        mot = liaison.get("mot_cle", "").strip().lower()
        if mot and mot in titre_bas:
            return liaison
    return None


def _previsionnel_existe(prevs: list, annee, mois, employeur, date_debut) -> bool:
    for p in prevs:
        if (str(p.get("annee")) == str(annee) and str(p.get("mois")) == str(mois)
                and p.get("employeur", "").strip().lower() == employeur.strip().lower()
                and p.get("date_debut") == date_debut):
            return True
    return False


def importer_evenements(cfg: dict = None) -> dict:
    """Télécharge l'ICS, filtre les évènements de travail futurs, crée les
    prévisionnels correspondant aux liaisons configurées.
    Retourne un rapport {"importes": [...], "deja_existants": [...], "ignores_sans_lien": [...]}.
    """
    cfg = cfg or charger_config_agenda()
    url = cfg.get("url_ics", "").strip()
    tags_travail = cfg.get("tags_travail") or []
    liaisons = cfg.get("liaisons") or []

    rapport = {"importes": [], "deja_existants": [], "ignores_sans_lien": []}
    if not url:
        return rapport

    texte = telecharger_ics(url)
    evenements = parser_ics(texte)
    aujourdhui = _date.today()
    prevs = charger_previsionnels()

    for ev in evenements:
        debut = ev["dtstart"]
        date_debut = debut.date() if isinstance(debut, _datetime) else debut
        if date_debut < aujourdhui:
            continue

        titre = ev.get("summary", "")
        if not _a_tag_travail(titre, tags_travail):
            continue

        liaison = _trouver_liaison(titre, liaisons)
        if not liaison:
            rapport["ignores_sans_lien"].append((titre, date_debut.isoformat()))
            continue

        fin = ev.get("dtend")
        heures = liaison.get("heures", "").strip() if liaison.get("heures") else ""
        if not heures and isinstance(debut, _datetime) and isinstance(fin, _datetime):
            heures = str(round((fin - debut).total_seconds() / 3600, 2))
        salaire = liaison.get("salaire", "").strip() if liaison.get("salaire") else ""

        date_fin_iso = (fin.date() if isinstance(fin, _datetime) else fin or date_debut).isoformat()

        employeur = liaison.get("employeur", "").strip()
        annee = str(date_debut.year)
        mois = f"{date_debut.month:02d}"
        date_debut_iso = date_debut.isoformat()

        if _previsionnel_existe(prevs, annee, mois, employeur, date_debut_iso):
            rapport["deja_existants"].append((titre, date_debut_iso))
            continue

        contrat = {
            "type":       liaison.get("type", "AEM"),
            "annee":      annee,
            "mois":       mois,
            "employeur":  employeur,
            "date_debut": date_debut_iso,
            "date_fin":   date_fin_iso,
            "heures":     heures,
            "salaire":    salaire,
            "note":       f"Importé depuis l'agenda : {titre}",
        }
        prevs = ajouter_previsionnel(contrat)
        rapport["importes"].append((titre, date_debut_iso, employeur))

    return rapport
