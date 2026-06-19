# PDF Classifier — Intermittent du Spectacle

Programme de classification automatique de documents PDF pour les intermittents du spectacle.
Détecte le type de document (AEM, BP, CS, CT, STC), extrait les informations clés et copie les pages vers la bonne arborescence.

## Prérequis

- Python 3.10 ou supérieur
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (pour les PDFs scannés) — chemin par défaut : `C:\Program Files\Tesseract-OCR\tesseract.exe`
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

## Utilisation

1. Cliquer sur **Parcourir…** pour choisir un fichier PDF
2. Cliquer sur **▶ Analyser** : le programme extrait et analyse chaque page
3. Vérifier / corriger les champs dans le tableau (double-clic pour éditer)
4. Cliquer sur **📁 Classifier tout** pour copier les fichiers vers leur dossier

## Structure des dossiers de destination

```
01 Janvier/
    AEM/
    BP/
    CS/
    CT/
    STC/
02 Fevrier/
    ...
12 Decembre/
    STC/
```

Utilisez **Outils → Créer la structure de dossiers** pour générer l'arborescence complète.

## Convention de nommage

```
[TYPE]-YYYY-MM-DDauDD-NOM_EMPLOYEUR.pdf
```

Exemples :
- `[BP]-2024-03-01au31-SARL_PRODUCTIONS_XYZ.pdf`
- `[CT]-2024-06-15au17-ASSOCIATION_LES_ARTS.pdf`
- `[AEM]-2024-01-01au31-FRANCE_TRAVAIL.pdf`

## Paramètres (Outils → Paramètres)

| Paramètre | Description |
|-----------|-------------|
| Clé API Anthropic | Requise pour l'analyse Claude |
| Chemin Tesseract | Chemin vers tesseract.exe |
| Dossier de base | Dossier racine de l'arborescence (défaut : dossier du script) |
| Langue OCR | ex : `fra+eng` (français + anglais) |

## Types de documents reconnus

| Code | Nom complet |
|------|-------------|
| AEM | Attestation Employeur Mensuelle |
| BP | Bulletin de Paie |
| CS | Contrat de travail (spectacle / CDDU) |
| CT | Contrat de travail général |
| STC | Solde de Tout Compte |
| INCONNU | Type non identifié |
