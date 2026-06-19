# -*- coding: utf-8 -*-
"""Tests for analyzer.py — filename parsing and info merging (no API calls)."""
import sys
from unittest.mock import MagicMock
import pytest

# Stub out heavy optional dependencies before importing analyzer
for _mod in ("anthropic", "fitz", "pymupdf"):
    sys.modules.setdefault(_mod, MagicMock())

from analyzer import extraire_info_nom_fichier, fusionner_info_nom_analyse


class TestExtraireInfoNomFichier:

    def test_format_intermitdoc_aem(self):
        info = extraire_info_nom_fichier("[AEM] 2026-07-06 La Vouivre 6h 140EUR.pdf")
        assert info["type"]        == "AEM"
        assert info["annee"]       == "2026"
        assert info["mois"]        == "07"
        assert info["date_debut"]  == "06"
        assert info["date_fin"]    == "06"
        assert info["employeur"]   == "La Vouivre"
        assert info["heures"]      == "6"
        assert info["salaire_brut"]== "140"

    def test_format_intermitdoc_periode(self):
        info = extraire_info_nom_fichier("[AEM] 2026-07-12_19 La Vouivre 48h 1120EUR.pdf")
        assert info["date_debut"] == "12"
        assert info["date_fin"]   == "19"

    def test_format_intermitdoc_bp(self):
        info = extraire_info_nom_fichier("[BP] 2025-03-01_31 Productions XYZ.pdf")
        assert info["type"]      == "BP"
        assert info["annee"]     == "2025"
        assert info["mois"]      == "03"
        assert info["heures"]    == ""
        assert info["salaire_brut"] == ""

    def test_nom_inconnu_extrait_annee(self):
        info = extraire_info_nom_fichier("bulletin_paie_2024.pdf")
        assert info["annee"] == "2024"
        assert info["type"]  == ""

    def test_nom_inconnu_extrait_type(self):
        # Word boundary before _ doesn't fire (AEM_ has no \b between M and _)
        # so use a space-separated filename for the generic detection path
        info = extraire_info_nom_fichier("contrat AEM mars 2025.pdf")
        assert info["type"] == "AEM"

    def test_nom_vide(self):
        info = extraire_info_nom_fichier("")
        assert info["type"] == ""
        assert info["annee"] == ""


class TestFusionnerInfoNomAnalyse:

    def test_analyse_complete_gagne(self):
        info_nom = {"type": "AEM", "annee": "2026", "mois": "07",
                    "employeur": "Du nom", "heures": "6", "salaire_brut": "140",
                    "date_debut": "06", "date_fin": "06"}
        analyse  = {"type": "AEM", "annee": "2026", "mois": "07",
                    "employeur": "De l'analyse", "heures": "8", "salaire_brut": "200",
                    "date_debut": "07", "date_fin": "07"}
        result = fusionner_info_nom_analyse(info_nom, analyse)
        assert result["employeur"]    == "De l'analyse"
        assert result["heures"]       == "8"
        assert result["date_debut"]   == "07"  # content always wins

    def test_analyse_vide_utilise_nom(self):
        info_nom = {"type": "BP", "annee": "2025", "mois": "03",
                    "employeur": "XYZ", "heures": "", "salaire_brut": "",
                    "date_debut": "01", "date_fin": "31"}
        analyse  = {"type": "", "annee": "", "mois": "", "employeur": "",
                    "heures": "", "salaire_brut": "",
                    "date_debut": "01", "date_fin": "31"}
        result = fusionner_info_nom_analyse(info_nom, analyse)
        assert result["type"]      == "BP"
        assert result["annee"]     == "2025"
        assert result["employeur"] == "XYZ"

    def test_ne_modifie_pas_analyse_original(self):
        info_nom = {"type": "AEM", "annee": "2026", "mois": "07",
                    "employeur": "XYZ", "heures": "6", "salaire_brut": "140",
                    "date_debut": "01", "date_fin": "01"}
        analyse  = {"type": "", "annee": "", "mois": "",
                    "employeur": "", "heures": "", "salaire_brut": "",
                    "date_debut": "01", "date_fin": "01"}
        original_analyse = dict(analyse)
        fusionner_info_nom_analyse(info_nom, analyse)
        assert analyse == original_analyse  # analyse dict untouched
