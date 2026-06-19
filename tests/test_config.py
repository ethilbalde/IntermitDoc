# -*- coding: utf-8 -*-
"""Tests for config.py — hash calculation and config loading."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
import config as cfg_module
from config import calculer_empreinte, charger_config


class TestCalculerEmpreinte:

    def test_hash_coherent(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"contenu test")
        h1 = calculer_empreinte(str(f))
        h2 = calculer_empreinte(str(f))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_contenu_different_hash_different(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_bytes(b"contenu A")
        f2.write_bytes(b"contenu B")
        assert calculer_empreinte(str(f1)) != calculer_empreinte(str(f2))

    def test_fichier_absent_leve_exception(self, tmp_path):
        # calculer_empreinte raises on missing file — callers must handle this
        with pytest.raises((FileNotFoundError, OSError)):
            calculer_empreinte(str(tmp_path / "inexistant.pdf"))


class TestChargerConfig:

    def test_charge_config_depuis_fichier(self, tmp_path, monkeypatch):
        chemin = tmp_path / "config.json"
        chemin.write_text(
            json.dumps({"dossier_base": "D:/documents", "annexe": "8"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", chemin)
        result = charger_config()
        assert result["dossier_base"] == "D:/documents"
        assert result["annexe"] == "8"

    def test_config_absente_retourne_defauts(self, tmp_path, monkeypatch):
        chemin = tmp_path / "config.json"
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", chemin)
        result = charger_config()
        assert isinstance(result, dict)
        assert "dossier_base" in result

    def test_config_invalide_retourne_defauts(self, tmp_path, monkeypatch):
        chemin = tmp_path / "config.json"
        chemin.write_text("not valid json", encoding="utf-8")
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", chemin)
        result = charger_config()
        assert isinstance(result, dict)
        # Should still have default keys
        assert "dossier_base" in result
