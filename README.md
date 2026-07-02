# IntermitDoc — Assistant administratif de l'intermittent du spectacle

IntermitDoc classe automatiquement vos documents PDF (AEM, bulletins de paie, contrats…),
suit vos heures pour le renouvellement de vos droits ARE et estime votre allocation
journalière selon les formules officielles France Travail.

**Aucune compétence technique requise** : téléchargez, dézippez, lancez.

## Fournisseurs IA supportés

| Fournisseur | Modèle | Qualité | Latence | Configuration |
|---|---|---|---|---|
| **Claude** (Anthropic) | claude-sonnet-4-6 | ⭐⭐⭐⭐⭐ Excellent français | Moyen | Défaut, recommandé |
| OpenAI | gpt-4o | ⭐⭐⭐⭐⭐ Très bon | Rapide | Menu Outils → Boost IA |
| Google Gemini | gemini-1.5-flash | ⭐⭐⭐⭐ Bon multilangue | Rapide | Menu Outils → Boost IA |
| Mistral | mistral-small-latest | ⭐⭐⭐⭐ Bon, léger | ⭐ Très rapide | Menu Outils → Boost IA |

Tous gratuits (forfait gratuit ou pay-as-you-go). Sans clé API, le programme classe
par heuristiques locales (plus lent, moins précis).

---

## 📥 Installation (utilisateur)

### Utilisateur final — installeur (recommandé)

1. Téléchargez `IntermitDoc-Setup-X.Y.Z.exe` depuis la page
   [Releases](https://github.com/ethilbalde/IntermitDoc/releases/latest)
2. Double-cliquez, suivez l'assistant (aucun droit administrateur requis)
3. Le programme se lance à la fin de l'installation

Un raccourci est créé dans le menu Démarrer (et sur le Bureau si vous cochez
l'option). La désinstallation se fait normalement via
**Paramètres → Applications**, et conserve vos données (clés API, employeurs,
contrats) en cas de réinstallation ultérieure.

### Alternative — zip portable

Si vous préférez ne rien installer (ex : usage depuis une clé USB) :

1. Téléchargez `IntermitDoc-vX.Y.Z-win64.zip`
2. Dézippez le dossier où vous voulez
3. Lancez `IntermitDoc.exe` directement

**Aucune installation de Python n'est nécessaire** dans les deux cas. Windows 10/11.

### Développeur — depuis les sources

Installez d'abord Python 3.10+ :
- **Windows** : [python.org](https://www.python.org/downloads/) → téléchargez le .exe
  (cochez « Add Python to PATH ») ou via [Microsoft Store](https://apps.microsoft.com/detail/9NRWMJP3717K)
- **Vérification** : `python --version` dans une console doit afficher 3.10 ou +

Puis :
```bash
pip install -r requirements.txt
python main.py
```

### Premier lancement — configuration

Au premier démarrage, le programme vous demande :

- **Votre clé API IA** — obligatoire pour l'analyse automatique des PDF.
  - **Claude (Anthropic)** est le fournisseur par défaut, **recommandé** pour les
    documents français. Créez une clé gratuite sur
    [console.anthropic.com](https://console.anthropic.com).
  - **Alternative** : OpenAI (GPT-4o), Google Gemini, ou Mistral. Configurables dans
    **Outils → Boost IA** — chacun a ses forces (Gemini pour le multilangue, Mistral
    pour la latence faible, OpenAI pour une qualité max).
  - **Aucune clé ?** Le programme tourne quand même : les documents seront classifiés
    par heuristiques locales (détection de mots-clés). Analyse manuelle plus lente,
    mais possible.
- **Votre annexe** : **8** (technicien), **10** (artiste) ou **8+10** — elle pilote
  les formules de calcul de votre allocation.
- **Votre dossier de classement** : là où les PDF classés seront rangés.
- **Votre date anniversaire** ARE (JJ/MM) pour le calcul automatique de votre période.

> **Et Tesseract OCR ?** Le programme cherche Tesseract au chemin par défaut
> (`C:\Program Files\Tesseract-OCR\tesseract.exe`). Si vous l'avez installé ailleurs,
> deux options :
> - (Utilisateur) Réinstallez Tesseract au chemin par défaut, ou utilisez Windows
>   "Add/Remove Programs" pour noter le chemin, puis reconfigurer dans
>   **Outils → Paramètres → Chemin Tesseract**.
> - (Développeur) Éditer `config.json` : `"tesseract_path": "C:\\your\\path\\tesseract.exe"`
>
> **Tesseract absent ?** Aucun problème si vos PDF ont du texte (cas courant). L'OCR
> est utile uniquement pour les images scannées sans texte intégré. Vous pouvez
> classer des AEM, bulletins de paie, etc. sans lui.

Vos réglages et données sont stockés dans `%APPDATA%\IntermitDoc\` sur **votre**
machine — rien ne quitte votre PC (hormis le texte des PDF envoyé à l'IA pour analyse).

---

## 🚀 Utilisation rapide

1. Onglet **Analyse** : glissez vos PDF (ou un dossier complet)
2. Cliquez **Analyser le PDF** — le type, l'employeur, les dates, heures et salaire
   sont détectés automatiquement
3. Vérifiez / corrigez si besoin (double-clic sur une ligne)
4. Cliquez **Classifier** : le fichier est renommé et copié au bon endroit

Les fichiers classés suivent ce modèle :

```
<dossier de classement>\
  2026\
    07 Juillet\
      AEM\   [AEM] 2026-07-18 LA VOUIVRE 6h 140EUR.pdf
      BP\    CS\    CT\    STC\
```

---

## 🗂 Les 7 onglets en détail

### 1. Analyse
Le cœur du programme. Déposez un ou plusieurs PDF : le texte est extrait
(PyMuPDF), l'IA identifie le type de document, l'employeur, la période, les heures
et le salaire brut. Pour les AEM, une seconde analyse cible précisément les libellés
officiels Unedic (« Nombre d'HEURES effectuées », « salaire brut soumis à la
contribution d'assurance chômage »). Chaque document déjà traité est reconnu par
son empreinte SHA-256 — pas de doublon possible.

### 2. Employeurs
Votre carnet d'employeurs. Les noms enregistrés ici sont recherchés **directement
dans le texte des documents, avant l'IA** — détection instantanée et fiable pour
vos employeurs habituels. Fusion des doublons intégrée (« LR GROUP » / « Lr Group »).

### 3. Calcul AEM
Calculatrice heures / cachets / salaire pour préparer une AEM.

### 4. Suivi Intermittent
Votre tableau de bord ARE :
- **Période automatique** calculée depuis votre date anniversaire
- **Jauge 507 h** : heures réelles + prévisionnelles vers le seuil de renouvellement
- **Indicateurs** : heures travaillées, heures manquantes, salaire brut, SJR,
  allocation journalière estimée, nombre de documents — chaque tuile affiche la
  valeur réelle **et** la projection avec vos contrats prévisionnels (⏳)
- **Calculer ARE & Congés Spectacle** : détail complet de l'estimation (voir
  formules plus bas)

### 5. Récapitulatif
Vue d'ensemble par période anniversaire : toutes vos années côte à côte
(heures, salaire, contrats, employeurs, droits ouverts ou non) + tableau détaillé
de tous les contrats, réels et prévisionnels.

### 6. Scan & Déplacement
Scanne un dossier existant plein de PDF en vrac et propose un classement en masse,
avec prévisualisation et confirmation avant tout déplacement.

### 7. Historique
Navigation mois par mois dans vos contrats. Double-clic : aperçu du PDF.
Clic droit : ouvrir, dupliquer vers d'autres dates (calendrier), modifier, supprimer.
Bouton **+ Contrat Futur** pour saisir un engagement à venir.

---

## ⏳ Contrats prévisionnels — comment ça marche

Vous pouvez saisir vos engagements futurs (depuis Suivi ou Historique). Ils
apparaissent en violet italique partout et alimentent les projections (jauge 507 h,
indicateurs ⏳).

Quand l'AEM réelle arrive et est classée, le programme **détecte et supprime
automatiquement** le prévisionnel correspondant (même employeur, même mois, même
date de début). En cas de chevauchement ambigu, il vous avertit au lieu de supprimer.
Un rapport s'affiche à chaque actualisation si des prévisionnels ont été nettoyés.

---

## 💶 Formules de calcul (officielles France Travail)

L'allocation journalière est estimée avec la formule intermittents **AJ = A + B + C** :

| Partie | Annexe 8 (technicien) | Annexe 10 (artiste) |
|---|---|---|
| A (salaires) | AJ min × (42 % × SR ≤ 14 400 € + 5 % au-delà) / 5000 | AJ min × (36 % × SR ≤ 13 700 € + 5 % au-delà) / 5000 |
| B (heures) | AJ min × (26 % × NHT ≤ 720 h + 8 % au-delà) / 507 | AJ min × (26 % × NHT ≤ 690 h + 8 % au-delà) / 507 |
| C (fixe) | AJ min × 40 % | AJ min × 70 % |
| Plancher | 38,00 € | 44,00 € |

AJ minimale : 31,96 € (juillet 2023). Déductions appliquées : retraite
complémentaire 3 %, puis CSG 6,2 % + CRDS 0,5 % (assiette 98,25 %) au-delà de 60 €/j.
Si votre annexe est « 8+10 », l'estimation retient la plus favorable.

> ⚠ Ces calculs sont des **estimations** — seul France Travail calcule vos droits
> exacts. Vous pouvez recouper avec [tauxintermittent.net](http://tauxintermittent.net/allocation-journaliere/).

---

## 🔒 Confidentialité

- Clés API, employeurs, contrats, prévisionnels : stockés uniquement dans
  `%APPDATA%\IntermitDoc\` sur votre machine
- L'exe distribué ne contient **aucune donnée personnelle** — vous pouvez le
  transmettre sans risque
- Seul le texte extrait des PDF est envoyé au fournisseur IA que vous avez
  configuré, au moment de l'analyse

---

## 🔄 Mises à jour

Le programme vérifie les nouvelles versions au démarrage (menu **Outils → Mises à
jour**) et peut se mettre à jour tout seul depuis les releases GitHub.

---

## 🛠 Pour les développeurs

### Prérequis
- Python 3.10+
- `pip install -r requirements.txt`

### Lancement depuis les sources
```bash
python main.py        # interface classique
python _run_v2.py     # interface v2 en cours de refonte (branche refonte-ui)
```

### Tests
```bash
python -m pytest tests/ -v
```

### Compilation de l'exe
```bash
python -m PyInstaller intermitdoc.spec --noconfirm
# résultat : dist\IntermitDoc\
```

### Architecture
| Fichier | Rôle |
|---|---|
| `main.py` | point d'entrée |
| `ui.py` | interface Tkinter (7 onglets) |
| `extractor.py` | extraction texte PDF (PyMuPDF) |
| `analyzer.py` | analyse IA (Claude par défaut ; OpenAI / Gemini / Mistral en option) |
| `classifier.py` | renommage + copie vers l'arborescence |
| `config.py` | configuration, logs, registre des fichiers traités |
| `previsionnel.py` | contrats prévisionnels + dédoublonnage |
| `updater.py` | mise à jour automatique via GitHub Releases |

## Types de documents reconnus

| Code | Nom complet |
|------|-------------|
| AEM  | Attestation Employeur Mensuelle |
| BP   | Bulletin de Paie |
| CS   | Contrat CDDU spectacle / Congés Spectacles |
| CT   | Contrat ou certificat de travail |
| STC  | Solde de Tout Compte |
