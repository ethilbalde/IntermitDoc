# IntermitDoc — Règles de Développement

Application Python/Tkinter de classification de PDF pour intermittents du spectacle.

## Commandes fréquentes

- Lancer en dev : `python main.py`
- Lancer les tests : `python -m pytest tests/ -v`
- Compiler l'exe : `python -m PyInstaller intermitdoc.spec --noconfirm`
- Exe généré : `dist\IntermitDoc\IntermitDoc.exe`
- Logs runtime : `%APPDATA%\IntermitDoc\intermitdoc.log`
- Config/données : `%APPDATA%\IntermitDoc\` (config.json, employeurs.json, traites.json, previsionnels.json)

## Architecture

- `main.py` — point d'entrée
- `ui.py` — interface Tkinter (8 onglets — voir section Onglets)
- `classifier.py` — construction des noms de fichiers et copie vers la destination
- `extractor.py` — extraction texte PDF via PyMuPDF (fitz)
- `analyzer.py` — analyse IA via Claude API (claude-sonnet-4-6) + providers alternatifs (OpenAI, Gemini, Mistral)
- `config.py` — configuration, logging rotatif, traites.json, employeurs.json
- `previsionnel.py` — CRUD des contrats prévisionnels (previsionnels.json)
- `theme.py` — tokens couleur, 3 palettes, `apply_theme()` + `appliquer_theme()`
- `tests/` — suite pytest (33 tests, 0 dépendance tkinter/API)

## Onglets UI (ui.py)

1. **Analyse** — glisser-déposer PDF, analyse IA, classification
2. **Employeurs** — `OngletEmployeurs` — CRUD liste employeurs
3. **Calcul AEM** — `OngletCalcul` — calcul heures/salaire
4. **Suivi Intermittent** — `OngletSuivi` — suivi ARE, heures glissantes
5. **Récapitulatif** — `OngletRecap` — tableau tous documents + prévisionnels
6. **Scan & Déplacement** — `OngletScan` — scan dossier et déplacement en masse
7. **Historique** — `OngletHistorique` — navigation année/mois, liste AEM, fiche éditable, contrats futurs

## Système de thèmes (theme.py)

- 3 palettes : `"clair"` (blanc), `"medium"` (gris Tkinter classique), `"sombre"` (fond #2B2B2B)
- `apply_theme(root)` — init au démarrage, avant toute création de widget
- `appliquer_theme(root, nom)` — bascule à chaud (met à jour constantes globales + ttk Style + widgets existants)
- `theme_courant()` — retourne le nom de la palette active
- Menu **🎨 Thème** dans la barre de menus (☀ Clair / ◑ Medium / ● Sombre)
- **Performance** : option_add utilise des sélecteurs de classe précis (`*Frame`, `*Label`, etc.) — jamais le wildcard `*`
- Les constantes couleur (`TH.SURFACE`, `TH.TEXT_PRIMARY`, etc.) sont des variables globales mises à jour à chaque changement de thème

## Contrats prévisionnels (previsionnel.py)

- Stockage : `%APPDATA%\IntermitDoc\previsionnels.json`
- Champs : `id`, `annee`, `mois`, `employeur`, `date_debut`, `date_fin`, `heures`, `salaire_brut`, `date_saisie`
- `id` auto-généré : `prev_YYYY-MM-DD_N`
- **Dédoublonnage** (déclenché à l'Actualiser de Suivi et Récap) :
  - Niveau 1 (auto-suppression) : même `annee + mois + employeur + date_debut` exact
  - Niveau 2 (avertissement) : même employeur/mois, dates chevauchantes mais `date_debut` différent
- `_DialogueRapportDedup` affiche ce qui a été supprimé + ce qui reste pour mois courant/précédent
- Affichage dans Récap : tag `"previsionnel"` (violet italique), colonne Type affiche ⏳

## Onglet Historique — points clés

- Navigation année (combobox) + mois (combobox + flèches ◀ ▶)
- Liste contrats AEM + prévisionnels, colonnes triables
- **Double-clic** → `FenetreApercu` (visionneuse plein écran)
- **Clic droit** → menu contextuel : 📄 Ouvrir / 📁 Explorateur / 📋 Dupliquer / 💾 Sauvegarder / 🗑 Supprimer
- `_iid_index` : dict `{iid_tree: index_liste}` — rebuild à chaque rechargement (évite le bug "détails sur dernier élément seulement")
- **Dupliquer vers d'autres dates** : `_DialogueDupliquerContrat` avec `tkcalendar` (`selectmode="day"` + `<<CalendarSelected>>`)
- Bouton **+ Contrat Futur** : `_DialogueContratFutur` avec combobox employeurs

## Structure des fichiers classifiés

```
D:\document pro\intermitent\
  ANNEE\
    MM Mois\          (ex: 07 Juillet)
      AEM\            [AEM] AAAA-MM-JJ Employeur Xh YYYEUR.pdf
      BP\
      CS\
      CT\
      STC\
```

## Données utilisateur

- dossier_base : `D:/document pro/intermitent`
- Date anniversaire ARE : 28/03 (annexe 8)
- Seuil renouvellement : 507h sur 12 mois glissants
- Période ARE courante : 22/03/2026 → 21/03/2027

## Préférences de Code

- Langue : toujours répondre en **français**, code et commentaires en **anglais**
- Style : Python 3.10+, fonctions courtes, early returns, try/except explicites
- Tkinter : frames imbriquées, grid ou pack (pas les deux dans le même widget)
- Pas de commentaires évidents — seulement si le WHY n'est pas clair
- Ne pas créer de nouveaux fichiers inutiles — préférer éditer l'existant

## Règle d'or Avant de Coder

- Si la modification touche plus de 2 fichiers : valider le plan d'abord
- Après toute modification de `classifier.py`, `ui.py` ou `theme.py` : recompiler l'exe
- Ne jamais utiliser `shutil.move()` en masse sans prévisualisation et confirmation explicite
- Le dossier de destination est TOUJOURS `dossier_base/annee/mois/TYPE/` — jamais le dossier parent du fichier source
- Après toute modification de logique métier : lancer `python -m pytest tests/ -v`

## Dépendances

- Toujours ajouter un nouveau package à `requirements.txt` immédiatement après `pip install`
- Le `.spec` PyInstaller référence les packages via `collect_all()` — vérifier qu'il est à jour aussi
- Si un widget Tkinter tombe en fallback silencieux, vérifier d'abord si son package est installé (`python -c "import X"`)

## Dépendances

- `Path.rename()` sur Windows lève `FileExistsError` si la destination existe (contrairement à Linux)
- `rglob("[AEM]*.pdf")` traite `[AEM]` comme une classe de caractères — utiliser `os.walk()` avec comparaison exacte
- `traites.json` stocke le SHA-256 du fichier SOURCE (avant injection metadata) — les fichiers classifiés ont un hash différent, c'est normal
- `date_debut` dans traites.json contient le jour seul (ex: "01"), pas une date complète — ne jamais parser `[:4]` pour l'année
- `tkcalendar` : utiliser `selectmode="day"` + événement `<<CalendarSelected>>` + `self._cal.selection_get()` — l'événement `<<CalendarDay>>` n'existe pas
- `sv_ttk` : ne jamais appeler `sv_ttk.set_theme()` dans `option_add("*", ...)` — utiliser des sélecteurs de classe précis pour éviter les ralentissements
- `option_add("*", ...)` avec wildcard est très lent — toujours cibler une classe spécifique
- `_iid_index` dans OngletHistorique doit être rebuild via `enumerate` (pas `len()-1`) après chaque insert dans le Treeview

---

## CHANTIER EN COURS — Refonte UI (branche `refonte-ui`)

### Objectif
Remplacer le Notebook tk classique par une UI moderne Soft UI crème/teal,
inspirée des références Figma (@design.deb). L'application se lance avec `python _run_v2.py`.
**Ne pas pousser sur GitHub avant validation locale complète.**

### Fichiers ajoutés (refonte uniquement)
- `theme_v2.py` — design tokens v2 (palettes dict, `C = _Colors()`, `appliquer(nom)`)
- `widgets_v2.py` — composants CTk : `Card`, `KPICard`, `bouton_primaire/secondaire`, `LoaderFondu/Anneau/Points`
- `ui_v2.py` — `FenetreV2(FenetrePrincipale)` : sidebar + pages refondues (logique 100% héritée)
- `_run_v2.py` — lanceur de dev (`from ui_v2 import lancer; lancer()`)
- `_demo_loaders.py` — démo isolée des loaders animés (ignoré par git)

### Architecture de la refonte (pattern clé)
```
FenetreV2(FenetrePrincipale)
  ├── _page_refonte("cle", PageXxx)   → CTk natif, gère ses couleurs
  └── _page_hote("cle", OngletXxx)   → onglet tk existant, recoloré par _harmoniser_onglets()
```
- `_harmoniser_onglets()` : applique la palette figma (via `theme.py`) à tous les onglets tk legacy
  et tous les dialogues tk créés ensuite (Édition, Aperçu, Paramètres…) héritent crème/teal automatiquement
- Boutons CTk : `.config = .configure` pour compat avec logique héritée qui appelle `.config(state=…)`

### État d'avancement des pages

| Page            | Classe dans ui_v2.py          | Statut          |
|-----------------|-------------------------------|-----------------|
| Analyse         | (dans FenetreV2 directement)  | ✅ refondu + validé |
| Employeurs      | `PageEmployeurs`              | ✅ refondu + validé |
| Récapitulatif   | `PageRecap`                   | ✅ refondu + validé |
| Historique      | `PageHistorique`              | ✅ refondu + validé |
| Calcul AEM      | `OngletCalcul` (legacy)       | ⏳ à refondre   |
| Suivi           | `OngletSuivi` (legacy)        | ⏳ à refondre   |
| Scan            | `OngletScan` (legacy)         | ⏳ à refondre   |

**Ordre prévu** : Scan → Suivi → Calcul

### Dialogues refondus
- `DialogueFusionEmployeursV2` — boutons packés `side="bottom"` EN PREMIER (sinon cachés)
- `DialogueEditionV2` — deux cartes (Aperçu gauche + Infos droite), boutons en bas
- `TableauPagesV2` — override `_ouvrir_edition()` → `DialogueEditionV2`

### Pièges connus (refonte)
- `_BaseLoader._render()` (PAS `_draw()` — conflit avec CTkFrame interne)
- `CTkLabel` : pas de `.config` → aliaser `.config = .configure`
- `CTkComboBox` (B majuscule) — pas `CTkCombobox`
- `_lbl_status` dans Historique : garder `tk.Label` car la logique appelle `fg="green"/"red"` (incompatible CTkLabel)
- Dialogues Fusion : toujours packer boutons + statut `side="bottom"` AVANT la liste expansible
- `bouton_primaire/secondaire` : utiliser `kwargs.setdefault()` pour height/font (surchargeables)
- Palette figma theme_v2 : BG="#F4F0E6", SIDEBAR="#EFEADC", PRIMARY="#16504A", ON_PRIMARY="#F2EEDF"
