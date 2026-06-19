# -*- coding: utf-8 -*-
"""Tests for classifier.py — filename construction and metadata parsing."""
import pytest
from classifier import construire_nom_fichier


class TestConstruireNomFichier:

    def test_aem_complet(self):
        info = {
            "type": "AEM", "annee": "2026", "mois": "07",
            "date_debut": "06", "date_fin": "06",
            "employeur": "La Vouivre", "heures": "6", "salaire_brut": "140",
        }
        assert construire_nom_fichier(info) == "[AEM] 2026-07-06 La Vouivre 6h 140EUR.pdf"

    def test_aem_periode(self):
        info = {
            "type": "AEM", "annee": "2026", "mois": "07",
            "date_debut": "12", "date_fin": "19",
            "employeur": "La Vouivre", "heures": "48", "salaire_brut": "1120",
        }
        assert construire_nom_fichier(info) == "[AEM] 2026-07-12_19 La Vouivre 48h 1120EUR.pdf"

    def test_bp_sans_heures(self):
        info = {
            "type": "BP", "annee": "2025", "mois": "03",
            "date_debut": "01", "date_fin": "31",
            "employeur": "Productions XYZ", "heures": "", "salaire_brut": "",
        }
        assert construire_nom_fichier(info) == "[BP] 2025-03-01_31 Productions XYZ.pdf"

    def test_aem_heures_float(self):
        info = {
            "type": "AEM", "annee": "2026", "mois": "07",
            "date_debut": "05", "date_fin": "05",
            "employeur": "La Vouivre", "heures": "3.0", "salaire_brut": "70.0",
        }
        result = construire_nom_fichier(info)
        assert "3h" in result
        assert "70EUR" in result

    def test_sans_date_debut(self):
        info = {
            "type": "CS", "annee": "2025", "mois": "06",
            "date_debut": "", "date_fin": "",
            "employeur": "URSSAF", "heures": "", "salaire_brut": "",
        }
        assert construire_nom_fichier(info) == "[CS] 2025-06 URSSAF.pdf"

    def test_date_debut_egale_fin(self):
        info = {
            "type": "CT", "annee": "2026", "mois": "01",
            "date_debut": "15", "date_fin": "15",
            "employeur": "Theatre du Nord", "heures": "", "salaire_brut": "",
        }
        # date_debut == date_fin → single date format
        result = construire_nom_fichier(info)
        assert "2026-01-15 " in result
        assert "2026-01-15_15" not in result

    def test_salaire_float_arrondi(self):
        info = {
            "type": "AEM", "annee": "2026", "mois": "06",
            "date_debut": "22", "date_fin": "22",
            "employeur": "La Vouivre", "heures": "6.0", "salaire_brut": "140.00",
        }
        result = construire_nom_fichier(info)
        assert "140EUR" in result
        assert "140.0EUR" not in result
