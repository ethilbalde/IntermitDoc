# IntermitDoc — Assistant administratif de l'intermittent du spectacle

IntermitDoc classe automatiquement vos documents PDF (AEM, bulletins de paie, contrats…),
suit vos heures pour le renouvellement de vos droits ARE et estime votre allocation
journalière selon les formules officielles France Travail.

**Aucune compétence technique requise** : téléchargez, installez, lancez.

---

## À quoi ça sert

En tant qu'intermittent, vous accumulez des dizaines de PDF chaque année : attestations
employeur, bulletins de paie, contrats, soldes de tout compte… IntermitDoc s'occupe de
tout :

- **Range** chaque document au bon endroit, avec un nom clair et cohérent
- **Lit** automatiquement l'employeur, la période, les heures et le salaire
- **Suit** votre progression vers le seuil des 507 h qui ouvre vos droits
- **Estime** votre allocation journalière (ARE) avec les vraies formules France Travail
- **Anticipe** grâce aux contrats prévisionnels : voyez où vous en serez après vos
  prochains cachets, importables automatiquement depuis votre agenda Google
- **Alerte** quand votre revenu dépasse le seuil où déclarer en intermittent n'est plus
  rentable

Tout se passe sur votre ordinateur. Vos données ne sont jamais partagées.

---

## Comment ça marche — les 8 onglets

### 1. Analyser & Classer
Le cœur du programme. Déposez un ou plusieurs PDF (ou un dossier entier) : le programme
lit le texte, identifie le type de document, l'employeur, la période, les heures et le
salaire brut. Pour les AEM, une seconde analyse cible précisément les libellés officiels
Unedic (« Nombre d'HEURES effectuées », « salaire brut soumis à la contribution
d'assurance chômage »). Chaque document déjà traité est reconnu — pas de doublon possible.
Vous vérifiez, corrigez si besoin, puis classez d'un clic.

### 2. Suivi Intermittent
Votre tableau de bord ARE :
- **Période automatique** calculée depuis votre date anniversaire
- **Jauge 507 h** : vos heures réelles + prévisionnelles vers le seuil de renouvellement
- **Indicateurs** : heures travaillées, heures manquantes, salaire brut, SJR, allocation
  journalière estimée, nombre de documents — chaque tuile affiche la valeur réelle **et**
  la projection avec vos contrats prévisionnels (⏳)
- **Alerte seuil de rentabilité** : au-delà de 14 400 € brut (réel + prévisionnel) sur la
  période, le programme signale qu'il n'est plus rentable de déclarer en intermittent
- **Calculer ARE & Congés Spectacle** : détail complet de l'estimation

### 3. Historique & Contrats futurs
Navigation mois par mois dans vos contrats. Double-clic : aperçu du PDF. Clic droit :
ouvrir, dupliquer vers d'autres dates (calendrier), modifier, supprimer (sélection
multiple possible). Bouton **+ Contrat Futur** pour saisir un engagement à venir, et
**📅 Agenda...** pour importer automatiquement vos prévisionnels depuis un agenda Google
(lien ICS, sans OAuth) via une table de correspondance mot-clé du titre → employeur/type
entièrement personnalisable.

### 4. Bilan par période
Vue d'ensemble par période anniversaire ARE : toutes vos périodes côte à côte (heures,
salaire, contrats, employeurs, droits ouverts ou non) + tableau détaillé de tous les
contrats, filtrable par type de document, avec alerte sur les bulletins de paie sans AEM
correspondante.

### 5. Revenus
Vue transversale toutes périodes ARE confondues : graphique d'évolution du salaire brut
(réel + prévisionnel, avec % d'évolution d'une période sur l'autre), tableau par période,
répartition par employeur et par type de document, revenu mensuel moyen, estimation nette
(taux d'abattement personnalisable), historique du seuil de rentabilité, export CSV.

### 6. Scan & Déplacement
Scanne un dossier plein de PDF en vrac et propose un classement en masse, avec
prévisualisation et confirmation avant tout déplacement.

### 7. Calculatrice AEM/ARE
Calculatrice heures / cachets / salaire pour préparer une attestation, et estimation de
l'allocation ARE.

### 8. Employeurs
Votre carnet d'employeurs. Les noms enregistrés ici sont reconnus **directement dans le
texte des documents** — détection instantanée et fiable pour vos employeurs habituels.
Fusion des doublons intégrée (« LR GROUP » / « Lr Group »).

---

## Utilisation au quotidien

1. Onglet **Analyse** : glissez vos PDF
2. Cliquez **Analyser le PDF** — les informations sont détectées automatiquement
3. Vérifiez / corrigez si besoin (double-clic sur une ligne)
4. Cliquez **Classifier** : le fichier est renommé et rangé au bon endroit

Vos fichiers sont classés selon ce modèle :

```
<dossier de classement>\
  2026\
    07 Juillet\
      AEM\   [AEM] 2026-07-18 LA VOUIVRE 6h 140EUR.pdf
      BP\    CS\    CT\    STC\
```

### Documents reconnus

| Code | Nom complet |
|------|-------------|
| AEM  | Attestation Employeur Mensuelle |
| BP   | Bulletin de Paie |
| CS   | Contrat CDDU spectacle / Congés Spectacles |
| CT   | Contrat ou certificat de travail |
| STC  | Solde de Tout Compte |

---

## Contrats prévisionnels

Vous pouvez saisir vos engagements futurs (depuis Suivi ou Historique). Ils apparaissent
en violet italique partout et alimentent les projections (jauge 507 h, indicateurs ⏳).

Quand l'AEM réelle arrive et est classée, le programme **détecte et supprime
automatiquement** le prévisionnel correspondant (même employeur, même mois, même date de
début). En cas de chevauchement ambigu, il vous avertit au lieu de supprimer. Un rapport
s'affiche à chaque actualisation si des prévisionnels ont été nettoyés.

---

## Calcul de l'allocation (formules officielles France Travail)

L'allocation journalière est estimée avec la formule intermittents **AJ = A + B + C** :

| Partie | Annexe 8 (technicien) | Annexe 10 (artiste) |
|---|---|---|
| A (salaires) | AJ min × (42 % × SR ≤ 14 400 € + 5 % au-delà) / 5000 | AJ min × (36 % × SR ≤ 13 700 € + 5 % au-delà) / 5000 |
| B (heures) | AJ min × (26 % × NHT ≤ 720 h + 8 % au-delà) / 507 | AJ min × (26 % × NHT ≤ 690 h + 8 % au-delà) / 507 |
| C (fixe) | AJ min × 40 % | AJ min × 70 % |
| Plancher | 38,00 € | 44,00 € |

AJ minimale : 31,96 € (juillet 2023). Déductions appliquées : retraite complémentaire
3 %, puis CSG 6,2 % + CRDS 0,5 % (assiette 98,25 %) au-delà de 60 €/j. Si votre annexe est
« 8+10 », l'estimation retient la plus favorable.

> ⚠ Ces calculs sont des **estimations** — seul France Travail calcule vos droits exacts.
> Vous pouvez recouper avec [tauxintermittent.net](http://tauxintermittent.net/allocation-journaliere/).

---

## Installation

### Installeur (recommandé)

1. Téléchargez `IntermitDoc-Setup-X.Y.Z.exe` depuis la page
   [Releases](https://github.com/ethilbalde/IntermitDoc/releases/latest)
2. Double-cliquez, suivez l'assistant (aucun droit administrateur requis)
3. Le programme se lance à la fin de l'installation

Un raccourci est créé dans le menu Démarrer (et sur le Bureau si vous cochez l'option).
L'assistant propose aussi d'installer **Tesseract OCR** (coché par défaut, ignoré
automatiquement s'il est déjà présent) — nécessaire uniquement si vous analysez des PDF
scannés/photographiés sans texte numérique ; vous pouvez décocher si vous n'en avez pas
l'usage.

La désinstallation se fait via **Paramètres → Applications**, et conserve vos données
(clés API, employeurs, contrats) en cas de réinstallation ultérieure.

### Alternative — zip portable

Si vous préférez ne rien installer (ex : usage depuis une clé USB) : téléchargez
`IntermitDoc-vX.Y.Z-win64.zip`, dézippez, lancez `IntermitDoc.exe` directement.

Aucune installation de Python n'est nécessaire dans les deux cas. Windows 10/11.

### Premier lancement

Au premier démarrage, le programme vous demande :

- **Votre clé API IA** — pour l'analyse automatique des PDF (voir section technique
  ci-dessous pour les fournisseurs). Sans clé, le programme classe par heuristiques
  locales, plus lent mais fonctionnel.
- **Votre annexe** : **8** (technicien), **10** (artiste) ou **8+10** — elle pilote les
  formules de calcul de votre allocation.
- **Votre dossier de classement** : là où les PDF classés seront rangés.
- **Votre date anniversaire** ARE (JJ/MM) pour le calcul automatique de votre période.

Vos réglages et données sont stockés dans `%APPDATA%\IntermitDoc\` sur **votre** machine.

---

## Confidentialité

- Clés API, employeurs, contrats, prévisionnels : stockés uniquement dans
  `%APPDATA%\IntermitDoc\` sur votre machine
- L'exe distribué ne contient **aucune donnée personnelle** — vous pouvez le transmettre
  sans risque
- Seul le texte extrait des PDF est envoyé au fournisseur IA que vous avez configuré, au
  moment de l'analyse

## Mises à jour

Le programme vérifie les nouvelles versions au démarrage (menu **Outils → Mises à jour**)
et peut se mettre à jour tout seul depuis les releases GitHub.

---
---

# Partie technique

## Fournisseurs IA supportés

L'analyse automatique des PDF s'appuie sur un modèle d'IA. Quatre fournisseurs sont
supportés — configurables dans **Outils → Boost IA** :

| Fournisseur | Modèle | Qualité | Latence | Configuration |
|---|---|---|---|---|
| **Claude** (Anthropic) | claude-sonnet-4-6 | ⭐⭐⭐⭐⭐ Excellent français | Moyen | Défaut, recommandé |
| OpenAI | gpt-4o | ⭐⭐⭐⭐⭐ Très bon | Rapide | Menu Outils → Boost IA |
| Google Gemini | gemini-1.5-flash | ⭐⭐⭐⭐ Bon multilangue | Rapide | Menu Outils → Boost IA |
| Mistral | mistral-small-latest | ⭐⭐⭐⭐ Bon, léger | ⭐ Très rapide | Menu Outils → Boost IA |

Créez une clé sur le site du fournisseur choisi
([console.anthropic.com](https://console.anthropic.com) pour Claude). Sans clé API, le
programme classe par heuristiques locales (détection de mots-clés) — plus lent, moins
précis, mais fonctionnel.

## Tesseract OCR (optionnel)

L'OCR n'est utile que pour les PDF **scannés sans texte intégré** (rare — la plupart des
AEM et bulletins de paie contiennent déjà du texte numérique, extrait directement sans
OCR). Le programme cherche Tesseract au chemin par défaut
`C:\Program Files\Tesseract-OCR\tesseract.exe`.

- **L'installeur `.exe` le propose automatiquement** (case cochée par défaut, ignorée si
  déjà présent) — installation silencieuse au chemin standard.
- Installé ailleurs ? Reconfigurez le chemin dans **Outils → Paramètres → Chemin
  Tesseract**, ou éditez `config.json` : `"tesseract_path": "C:\\votre\\chemin\\tesseract.exe"`
- Absent ? Aucun problème si vos PDF contiennent du texte (cas courant) — seuls les
  documents image tomberont en type INCONNU et devront être complétés manuellement.

Téléchargement manuel : [Tesseract OCR (UB Mannheim)](https://github.com/UB-Mannheim/tesseract/wiki).

## Lancement depuis les sources

Installez Python 3.10+ :
- **Windows** : [python.org](https://www.python.org/downloads/) (cochez « Add Python to
  PATH ») ou via [Microsoft Store](https://apps.microsoft.com/detail/9NRWMJP3717K)
- Vérification : `python --version` doit afficher 3.10 ou +

```bash
pip install -r requirements.txt
python main.py
```

## Tests

```bash
python -m pytest tests/ -v
```

## Installeur Windows

Pas besoin de Python ni de compiler quoi que ce soit : téléchargez directement le
dernier installeur depuis la page des [releases GitHub](https://github.com/ethilbalde/IntermitDoc/releases/latest)
(`IntermitDoc-Setup-X.Y.Z.exe`), lancez-le et suivez l'assistant.

## Architecture

| Fichier | Rôle |
|---|---|
| `main.py` | point d'entrée |
| `ui.py` | interface Tkinter (8 onglets) |
| `extractor.py` | extraction texte PDF (PyMuPDF) |
| `analyzer.py` | analyse IA (Claude par défaut ; OpenAI / Gemini / Mistral en option) |
| `classifier.py` | renommage + copie vers l'arborescence |
| `config.py` | configuration, logs, registre des fichiers traités |
| `previsionnel.py` | contrats prévisionnels + dédoublonnage |
| `agenda.py` | import de prévisionnels depuis un agenda Google (lien ICS) |
| `updater.py` | mise à jour automatique via GitHub Releases |
