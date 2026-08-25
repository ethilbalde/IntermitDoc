"""
Configuration d'IntermitDoc.
Gestion de la persistance des paramètres via config.json.
"""
import json
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path

import sys as _sys

_LOCK_TRAITES = threading.Lock()

def _dossier_config() -> Path:
    # Quand lance depuis le .exe PyInstaller : sauvegarder dans %APPDATA%
    # Ce dossier n est jamais efface par les rebuilds
    if getattr(_sys, "frozen", False):
        appdata = Path(_sys.executable).parent  # fallback
        try:
            import os
            appdata_env = os.environ.get("APPDATA")
            if appdata_env:
                dossier = Path(appdata_env) / "IntermitDoc"
                dossier.mkdir(parents=True, exist_ok=True)
                return dossier
        except Exception:
            pass
        return appdata
    # Quand lance en mode script Python : meme dossier que config.py
    return Path(__file__).parent

CONFIG_FILE     = _dossier_config() / "config.json"
EMPLOYEURS_FILE = _dossier_config() / "employeurs.json"
TRAITES_FILE    = _dossier_config() / "traites.json"
LOG_FILE        = _dossier_config() / "intermitdoc.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import logging as _logging
from logging.handlers import RotatingFileHandler as _RotatingFileHandler

def _init_logger() -> _logging.Logger:
    logger = _logging.getLogger("IntermitDoc")
    if logger.handlers:
        return logger  # déjà initialisé
    logger.setLevel(_logging.DEBUG)
    # Fichier rotatif : 1 Mo max, 30 fichiers gardés
    fh = _RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=30, encoding="utf-8"
    )
    fh.setLevel(_logging.DEBUG)
    fmt = _logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

logger = _init_logger()

IA_PROVIDERS = {
    "claude":  {"nom": "Claude (Anthropic)", "modele": "claude-sonnet-4-6"},
    "openai":  {"nom": "GPT-4o (OpenAI)",    "modele": "gpt-4o-mini"},
    "gemini":  {"nom": "Gemini (Google)",     "modele": "gemini-1.5-flash"},
    "mistral": {"nom": "Mistral AI",          "modele": "mistral-small-latest"},
}

DEFAULT_CONFIG = {
    "api_key": "",
    "tesseract_path": "C:/Program Files/Tesseract-OCR/tesseract.exe",
    "dossier_base": "",
    "langue_ocr": "fra+eng",
    "seuil_confiance": 0.7,
    "modele_claude": "claude-sonnet-4-6",
    "date_anniversaire": "",   # JJ/MM de la date anniversaire intermittent
    "annexe": "",              # "8", "10", ou "8+10"
    "taux_abattement_net": 10.0,  # % estimatif brut -> net (onglet Revenus)
    "ia_providers": {
        "claude":  {"enabled": True,  "api_key": ""},
        "openai":  {"enabled": False, "api_key": ""},
        "gemini":  {"enabled": False, "api_key": ""},
        "mistral": {"enabled": False, "api_key": ""},
    }
}

MOIS_DOSSIERS = {
    "01": "01 Janvier",
    "02": "02 Fevrier",
    "03": "03 Mars",
    "04": "04 Avril",
    "05": "05 Mai",
    "06": "06 Juin",
    "07": "07 Juillet",
    "08": "08 Aout",
    "09": "09 Septembre",
    "10": "10 Octobre",
    "11": "11 Novembre",
    "12": "12 Decembre",
}

TYPES_DOCUMENTS = ["AEM", "BP", "CS", "CT", "STC", "INCONNU"]


def charger_config() -> dict:
    """Charge la config depuis config.json. Crée le fichier si inexistant."""
    if not CONFIG_FILE.exists():
        sauvegarder_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        config = {}

    for key, val in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = val

    # Fusionner ia_providers sans ecraser les cles existantes
    if "ia_providers" not in config:
        config["ia_providers"] = {}
    for provider_id, defaults in DEFAULT_CONFIG["ia_providers"].items():
        if provider_id not in config["ia_providers"]:
            config["ia_providers"][provider_id] = dict(defaults)
        else:
            for k, v in defaults.items():
                if k not in config["ia_providers"][provider_id]:
                    config["ia_providers"][provider_id][k] = v

    # Synchroniser la cle Claude principale avec ia_providers
    if config.get("api_key"):
        config["ia_providers"]["claude"]["api_key"] = config["api_key"]

    return config


def sauvegarder_config(config: dict) -> None:
    """Sauvegarde la config dans config.json. Synchronise la cle Claude principale."""
    # Garder api_key principale en sync avec ia_providers.claude.api_key
    cle_claude = config.get("ia_providers", {}).get("claude", {}).get("api_key", "")
    if cle_claude:
        config["api_key"] = cle_claude
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def demander_api_key(parent=None) -> str | None:
    """Ouvre une boîte de dialogue pour saisir la clé API."""
    root = parent
    created = False
    if root is None:
        root = tk.Tk()
        root.withdraw()
        created = True

    api_key = simpledialog.askstring(
        "Clé API Anthropic",
        "Entrez votre clé API Anthropic :\n(Disponible sur console.anthropic.com)",
        parent=root,
        show="*"
    )

    if created:
        root.destroy()

    return api_key


def valider_config(config: dict, parent=None) -> bool:
    """
    Vérifie que la config est valide.
    Demande la clé API si absente.
    Retourne True si la config est utilisable.
    """
    if not config.get("api_key"):
        api_key = demander_api_key(parent)
        if not api_key:
            messagebox.showerror(
                "Clé API manquante",
                "Une clé API Anthropic est requise pour analyser les documents."
            )
            return False
        config["api_key"] = api_key
        sauvegarder_config(config)

    return True


def charger_employeurs() -> list:
    """Charge la liste des employeurs connus depuis employeurs.json."""
    if not EMPLOYEURS_FILE.exists():
        return []
    try:
        with open(EMPLOYEURS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return sorted(data) if isinstance(data, list) else []
    except Exception:
        return []


def sauvegarder_employeurs(employeurs: list) -> None:
    """Sauvegarde la liste des employeurs connus."""
    with open(EMPLOYEURS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(set(e.strip() for e in employeurs if e.strip())),
                  f, indent=2, ensure_ascii=False)


def calculer_empreinte(chemin: str) -> str:
    """SHA-256 des premiers 64 Ko du PDF — rapide et suffisant pour identifier un fichier."""
    import hashlib
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()


def charger_traites() -> dict:
    """Charge le registre des fichiers deja traites par IntermitDoc."""
    if not TRAITES_FILE.exists():
        return {}
    try:
        with open(TRAITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def enregistrer_traite(chemin_source: str, info: dict) -> str:
    """
    Enregistre un fichier comme traite dans traites.json.
    Retourne l'empreinte calculee.
    """
    from datetime import date as _date
    empreinte = calculer_empreinte(chemin_source)
    with _LOCK_TRAITES:
        traites = charger_traites()
        traites[empreinte] = {
            "chemin_source":      chemin_source,
            "chemin_destination": info.get("chemin_destination", ""),
            "nom_fichier":        info.get("nom_fichier", ""),
            "date_traitement":    str(_date.today()),
            "type":               info.get("type", ""),
            "annee":              info.get("annee", ""),
            "mois":               info.get("mois", ""),
            "date_debut":         info.get("date_debut", ""),
            "date_fin":           info.get("date_fin", ""),
            "employeur":          info.get("employeur", ""),
            "heures":             info.get("heures", ""),
            "salaire_brut":       info.get("salaire_brut", ""),
        }
        with open(TRAITES_FILE, "w", encoding="utf-8") as f:
            json.dump(traites, f, indent=2, ensure_ascii=False)
    return empreinte


def verifier_traite(chemin: str) -> dict | None:
    """
    Verifie si un fichier a deja ete traite.
    Retourne le dict d'info ou None.
    """
    try:
        empreinte = calculer_empreinte(chemin)
        with _LOCK_TRAITES:
            return charger_traites().get(empreinte)
    except Exception:
        return None


def scanner_aem_classes(dossier_base: str) -> list:
    """
    Scanne récursivement dossier_base à la recherche de fichiers AEM classés.
    Retourne une liste de dicts {annee, mois, employeur, heures, salaire_brut, chemin}.
    Format attendu : [AEM] AAAA-MM-DD_DD Employeur Xh YYYYeurEUR.pdf
    """
    import re as _re
    base = Path(dossier_base)
    if not base.exists():
        return []

    resultats = []
    # Pattern : [AEM] 2025-03-01_31 Employeur 120h 2639EUR.pdf (ou variantes)
    pat = _re.compile(
        r"\[AEM\]\s*"
        r"(\d{4})-(\d{2})-\d{2}(?:_\d+)?\s+"   # année-mois
        r"(.+?)\s+"                               # employeur
        r"(\d+(?:[.,]\d+)?)h\s*"                 # heures
        r"(\d+(?:[.,]\d+)?)(?:EUR|eur)?",         # salaire
        _re.IGNORECASE,
    )

    for pdf in base.rglob("*.pdf"):
        nom = pdf.stem
        m = pat.search(nom)
        if not m:
            # Tentative sur le nom complet avec crochets
            continue
        annee, mois, employeur, heures_str, salaire_str = m.groups()
        try:
            heures      = float(heures_str.replace(",", "."))
            salaire_brut = float(salaire_str.replace(",", "."))
        except ValueError:
            continue
        resultats.append({
            "annee":       annee,
            "mois":        mois,
            "employeur":   employeur.strip(),
            "heures":      heures,
            "salaire_brut": salaire_brut,
            "chemin":      str(pdf),
            "nom":         pdf.name,
        })

    resultats.sort(key=lambda r: (r["annee"], r["mois"]))
    return resultats


def resoudre_dossier_base(config: dict) -> Path:
    """
    Résout le dossier de base pour les fichiers classifiés.
    Si non configuré, utilise le dossier Documents de l'utilisateur.
    """
    if config.get("dossier_base"):
        return Path(config["dossier_base"])
    return Path.home() / "Documents"
