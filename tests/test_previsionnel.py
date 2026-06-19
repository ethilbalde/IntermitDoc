# -*- coding: utf-8 -*-
"""Tests for previsionnel.py — overlap detection and CRUD logic."""
import json
import pytest
from unittest.mock import patch, MagicMock
from previsionnel import (
    _periodes_se_chevauchent,
    charger_previsionnels,
    ajouter_previsionnel,
    supprimer_previsionnel,
)


class TestPeriodesSeChevauchent:

    def _c(self, debut, fin=None):
        return {"date_debut": debut, "date_fin": fin or debut}

    def test_meme_jour(self):
        assert _periodes_se_chevauchent(self._c("2026-07-06"), self._c("2026-07-06"))

    def test_sans_chevauchement(self):
        assert not _periodes_se_chevauchent(
            self._c("2026-07-01", "2026-07-03"),
            self._c("2026-07-05", "2026-07-07"),
        )

    def test_chevauchement_partiel(self):
        assert _periodes_se_chevauchent(
            self._c("2026-07-01", "2026-07-05"),
            self._c("2026-07-04", "2026-07-08"),
        )

    def test_inclusion_totale(self):
        assert _periodes_se_chevauchent(
            self._c("2026-07-01", "2026-07-31"),
            self._c("2026-07-10", "2026-07-15"),
        )

    def test_contigus_sans_chevauchement(self):
        # Ends on the 5th, starts on the 6th → no overlap
        assert not _periodes_se_chevauchent(
            self._c("2026-07-01", "2026-07-05"),
            self._c("2026-07-06", "2026-07-10"),
        )

    def test_date_invalide(self):
        # Invalid dates should not raise, just return False
        assert not _periodes_se_chevauchent(
            {"date_debut": "", "date_fin": ""},
            {"date_debut": "2026-07-01", "date_fin": "2026-07-01"},
        )

    def test_date_fin_absente(self):
        # date_fin falls back to date_debut
        a = {"date_debut": "2026-07-06"}
        b = {"date_debut": "2026-07-06"}
        assert _periodes_se_chevauchent(a, b)


class TestChargerSauvegarder:

    def test_fichier_absent_retourne_liste_vide(self, tmp_path):
        chemin = tmp_path / "previsionnels.json"
        with patch("previsionnel._chemin_prev", return_value=chemin):
            assert charger_previsionnels() == []

    def test_fichier_invalide_retourne_liste_vide(self, tmp_path):
        chemin = tmp_path / "previsionnels.json"
        chemin.write_text("not json", encoding="utf-8")
        with patch("previsionnel._chemin_prev", return_value=chemin):
            assert charger_previsionnels() == []

    def test_ajouter_puis_supprimer(self, tmp_path):
        chemin = tmp_path / "previsionnels.json"
        with patch("previsionnel._chemin_prev", return_value=chemin):
            ajouter_previsionnel({"employeur": "La Vouivre", "annee": "2026", "mois": "07"})
            prevs = charger_previsionnels()
            assert len(prevs) == 1
            prev_id = prevs[0]["id"]

            supprimer_previsionnel(prev_id)
            assert charger_previsionnels() == []

    def test_ajouter_genere_id_unique(self, tmp_path):
        chemin = tmp_path / "previsionnels.json"
        with patch("previsionnel._chemin_prev", return_value=chemin):
            ajouter_previsionnel({"employeur": "A"})
            ajouter_previsionnel({"employeur": "B"})
            prevs = charger_previsionnels()
            ids = [p["id"] for p in prevs]
            assert len(set(ids)) == 2
