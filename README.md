# IntermitDoc — Intermittent du Spectacle

Application de classification automatique de documents PDF pour les intermittents du spectacle.
Détecte le type de document (AEM, BP, CS, CT, STC), extrait les informations clés et copie les fichiers vers la bonne arborescence.

## Prérequis

- Python 3.10 ou supérieur
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — chemin par défaut : `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Une clé API Anthropic (https://console.anthropic.com)

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

Au premier lancement, le programme demande votre clé API Anthropic.

## Compilation exe

```bash
python -m PyInstaller intermitdoc.spec --noconfirm
# ou double-cliquer build.bat
```

Exe généré : `dist\IntermitDoc\IntermitDoc.exe`

## Utilisation

1. Glisser-déposer un PDF sur l'onglet **Analyse**
2. Cliquer sur **▶ Analyser** : l'IA extrait les informations
3. Vérifier / corriger les champs
4. Cliquer sur **📁 Classifier** pour copier le fichier vers son dossier

## Structure des dossiers de destination

```
D:\document pro\intermitent\
  ANNEE\
    MM Mois\
      AEM\
      BP\
      CS\
      CT\
      STC\
```

## Types de documents reconnus

| Code | Nom complet |
|------|-------------|
| AEM  | Attestation Employeur Mensuelle |
| BP   | Bulletin de Paie |
| CS   | Contrat de travail Spectacle (CDDU) |
| CT   | Contrat de travail général |
| STC  | Solde de Tout Compte |
