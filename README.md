# IntermitDoc — Assistant administratif de l'intermittent du spectacle

IntermitDoc classe automatiquement vos documents PDF (AEM, bulletins de paie, contrats…),
suit vos heures pour le renouvellement de vos droits ARE et estime votre allocation
journalière selon les formules officielles France Travail.

**Aucune compétence technique requise** : téléchargez, dézippez, lancez.

---

## 📥 Installation (utilisateur)

1. Téléchargez le zip `IntermitDoc-vX.Y.Z-win64.zip` depuis la page
   [Releases](https://github.com/ethilbalde/IntermitDoc/releases/latest)
2. Dézippez le dossier où vous voulez (ex : `C:\IntermitDoc`)
3. Lancez `IntermitDoc.exe`

Aucune installation de Python n'est nécessaire. Windows 10/11 uniquement.

### Premier lancement

Au premier démarrage, le programme vous demande :

- **Votre clé API IA** (optionnelle mais recommandée) — l'analyse automatique des PDF
  utilise une IA. Créez une clé sur [console.anthropic.com](https://console.anthropic.com)
  (Claude), ou configurez OpenAI / Gemini / Mistral dans **Outils → Boost IA**.
- **Votre annexe** : **8** (technicien), **10** (artiste) ou **8+10** — elle pilote
  les formules de calcul de votre allocation.
- **Votre dossier de classement** : là où les PDF classés seront rangés.
- **Votre date anniversaire** ARE (JJ/MM) pour le calcul automatique de votre période.

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
