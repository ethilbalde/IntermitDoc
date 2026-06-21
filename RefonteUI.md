# Refonte UI — Guide complet

> Branche : `refonte-ui`  
> Lanceur de dev : `python _run_v2.py`  
> **Ne pas pousser sur GitHub avant validation locale complète.**

---

## 1. Pourquoi cette architecture

L'application d'origine (`ui.py`) est un Notebook Tkinter classique avec barre de menus. Le but est d'obtenir une interface Soft UI crème/teal (inspirée des maquettes Figma @design.deb) **sans réécrire la logique métier**.

La stratégie choisie est la **sous-classe** : au lieu de repartir de zéro, `FenetreV2` hérite de `FenetrePrincipale` et en réécrit uniquement la présentation. Toute la logique (analyse IA, threading, classification, dédoublonnage, prévisionnels…) est héritée et réutilisée telle quelle.

---

## 2. Fichiers de la refonte

| Fichier | Rôle |
|---|---|
| `theme_v2.py` | Design tokens : palettes dict, `C = _Colors()`, `appliquer(nom)` |
| `widgets_v2.py` | Composants CTk réutilisables : `Card`, `KPICard`, `bouton_primaire/secondaire`, loaders |
| `ui_v2.py` | Shell principal + pages refondues |
| `_run_v2.py` | Lanceur de dev (`from ui_v2 import lancer; lancer()`) |
| `_demo_loaders.py` | Démo isolée des composants (ignoré par git) |

Ces fichiers coexistent avec `ui.py`, `theme.py`, etc. qui restent intacts (branche `master` non affectée).

---

## 3. Le design system (theme_v2.py)

### Palette figma (défaut)

```
BG          #F4F0E6   fond fenêtre (crème)
SIDEBAR     #EFEADC   barre latérale (crème plus sombre)
SURFACE     #FBF8F0   cartes / panneaux
SURFACE_2   #F2ECDD   fond entrées, survol léger
BORDER      #DED6C2   bordures fines
PRIMARY     #16504A   boutons, actif (teal sapin)
PRIMARY_HOV #0F3F39   survol PRIMARY
ON_PRIMARY  #F2EEDF   texte sur bouton teal
TEXT        #23221E   texte principal
TEXT_2      #5C584C   texte secondaire / labels
TEXT_3      #8A8675   hints / pieds de page
SUCCESS     #2E7D52
WARNING     #B07A2E
DANGER      #B0402E
```

### Accès aux couleurs

```python
import theme_v2 as TH2
TH2.appliquer("figma")   # à appeler une seule fois au démarrage
TH2.C.PRIMARY            # accès attribut dynamique à la palette courante
```

### Typographie

```python
TH2.FONT_TITLE   = ("Segoe UI", 18, "bold")   # titres de page
TH2.FONT_HEADING = ("Segoe UI", 15, "bold")   # sous-titres / titres de dialogue
TH2.FONT_BODY    = ("Segoe UI", 13)            # corps de texte, boutons
TH2.FONT_LABEL   = ("Segoe UI", 12)            # labels de formulaire
TH2.FONT_SMALL   = ("Segoe UI", 11)            # hints, pieds
TH2.FONT_KPI     = ("Segoe UI", 22, "bold")   # grandes valeurs KPI
```

### Rayons

```python
TH2.RADIUS_SM = 8    # badges, petits éléments
TH2.RADIUS_MD = 11   # boutons, entrées
TH2.RADIUS_LG = 14   # cartes
TH2.RADIUS_XL = 18   # dialogues, modals
```

---

## 4. Les composants (widgets_v2.py)

### Card
Cadre à surface ivoire, bordure fine, coins arrondis. Sert d'enveloppe pour grouper du contenu.
```python
carte = W.Card(parent)
carte.pack(fill="both", expand=True, padx=24, pady=8)
```

### KPICard
Compteur visuel : libellé en majuscules + grande valeur numérique.
```python
kpi = W.KPICard(parent, "Documents", "0", value_color=TH2.C.WARNING)
kpi.set_value("12")
```

### Boutons

```python
# Bouton principal (fond teal)
W.bouton_primaire(parent, "Analyser", command=fn, width=140)

# Bouton secondaire (contour teal, fond transparent)
W.bouton_secondaire(parent, "Annuler", command=fn, width=110)

# Pour surcharger la taille ou la police :
W.bouton_primaire(parent, "Fusionner", height=46, font=TH2.FONT_HEADING)
```

### Loaders animés (Canvas)
Démarrés avec `.start()`, arrêtés avec `.stop()`. Méthode interne `_render()` (jamais `_draw()` — conflit avec CTkFrame).

```python
self._loader = W.LoaderFondu(parent, size=30)   # pulse — loader principal
self._loader.set_bg(TH2.C.BG)
self._loader.start()
# ... fin de traitement ...
self._loader.stop()
```

---

## 5. Architecture de FenetreV2

```
FenetreV2(FenetrePrincipale)
  │
  ├── sidebar CTk (190px, fond SIDEBAR)
  │     ├── logo "IntermitDoc"
  │     ├── boutons nav (⌕ Analyse / ☰ Employeurs / …)
  │     └── outils bas (Paramètres, version…)
  │
  └── zone principale (CTkFrame, grille de pages superposées)
        ├── page "analyse"      → _construire_page_analyse()  [CTk natif]
        ├── page "employeurs"   → PageEmployeurs              [_page_refonte]
        ├── page "recap"        → PageRecap                   [_page_refonte]
        ├── page "calcul"       → OngletCalcul                [_page_hote]
        ├── page "suivi"        → OngletSuivi                 [_page_hote]
        ├── page "scan"         → OngletScan                  [_page_hote]
        └── page "historique"   → OngletHistorique            [_page_hote]
```

### _page_refonte vs _page_hote

**`_page_refonte("cle", PageXxx)`** : pour les onglets **refondus**.  
La classe `PageXxx` hérite d'un `OngletXxx` et réécrit `_construire()`. Elle gère ses propres couleurs avec les tokens CTk.

**`_page_hote("cle", OngletXxx)`** : pour les onglets **encore legacy**.  
L'onglet tk original est embarqué dans un conteneur CTk, puis recoloré par `_harmoniser_onglets()`.

### _harmoniser_onglets()

Appelée une seule fois à la construction. Elle applique la palette figma via `theme.py` (l'ancien système) à tous les onglets tk legacy. Effet important : `TH._appliquer_options_tk(self, p)` configure les `option_add` globaux, ce qui fait que **tous les dialogues tk créés ensuite** (Édition, Aperçu, Paramètres, Fusion…) héritent automatiquement de la palette crème/teal, sans code supplémentaire.

---

## 6. Pattern pour refondre un onglet

### Étape 1 — Créer la classe

Dans `ui_v2.py`, sous la dernière `Page` existante :

```python
class PageNom(OngletNom):
    """Onglet Xxx refondu. Logique 100% héritée."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)

        # 1. En-tête
        entete = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        entete.pack(fill="x", padx=24, pady=(20, 6))
        ctk.CTkLabel(entete, text="Titre de la page", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(side="left")
        # bouton d'action principal à droite si besoin
        W.bouton_primaire(entete, "↻ Actualiser", command=self.actualiser,
                          width=140).pack(side="right")

        # 2. Zone de contenu dans une Card
        carte = W.Card(self)
        carte.pack(fill="both", expand=True, padx=24, pady=8)
        # ... widgets internes ...
```

### Étape 2 — Basculer de _page_hote vers _page_refonte

Dans `_construire_interface()`, remplacer :
```python
self.tab_nom = self._page_hote("nom", OngletNom, cfg=True)
```
par :
```python
self.tab_nom = self._page_refonte("nom", PageNom, cfg=True)
```

### Étape 3 — Retirer l'onglet de _harmoniser_onglets()

Dans `_harmoniser_onglets()`, supprimer `self.tab_nom` de la liste des onglets recolorés (il gère ses propres couleurs maintenant).

### Étape 4 — Identifier les attributs attendus par la logique héritée

Lire l'onglet original dans `ui.py`. La méthode `_construire()` crée des attributs (`self.tree`, `self.var_annee`, `self.listbox`…) que le reste de la classe utilise. La refonte **doit créer exactement les mêmes attributs avec les mêmes noms** pour que la logique héritée fonctionne sans modification.

### Étape 5 — Gérer les widgets CTk sans `.config`

Si la logique héritée appelle `.config(state=…)` sur un widget CTk, aliaser :
```python
self.mon_bouton.config = self.mon_bouton.configure
```
Même chose pour `CTkLabel` si utilisé à la place d'un `tk.Label`.

---

## 7. Pièges connus

| Piège | Solution |
|---|---|
| `_draw()` conflit CTkFrame | Toujours nommer `_render()` dans les loaders |
| Boutons cachés dans un dialogue | Packer `side="bottom"` EN PREMIER, avant le widget `expand=True` |
| `CTkLabel` n'a pas `.config` | Aliaser `.config = .configure` |
| `CTkCombobox` n'existe pas | Utiliser `CTkComboBox` (B majuscule) |
| Label status avec `fg="red"/"green"` | Garder `tk.Label` — CTkLabel ne supporte pas `fg=` |
| Boutons trop petits | `bouton_primaire/secondaire` : passer `height=` et `font=` directement |
| Treeview scrollbar CTk | `ctk.CTkScrollbar(zone)` puis `sv.configure(command=self.tree.yview)` |
| Fond blanc résiduel dans une Card | `zone = tk.Frame(carte, bg=TH2.C.SURFACE)` et non `bg="white"` |
| `_frame_cartes` fond blanc | `tk.Frame(self, bg=TH2.C.BG)` |
| `_lbl_pied` fond blanc | `tk.Label(..., bg=TH2.C.BG, fg=TH2.C.TEXT_3)` |

---

## 8. État d'avancement

| Page | Classe | Statut |
|---|---|---|
| Analyse | _(dans FenetreV2)_ | ✅ validé |
| Employeurs | `PageEmployeurs` | ✅ validé |
| Récapitulatif | `PageRecap`      | ✅ validé |
| Historique    | `PageHistorique` | ✅ validé |
| Calcul AEM    | `OngletCalcul` legacy | ⏳ à refondre |
| Suivi         | `OngletSuivi` legacy  | ⏳ à refondre |
| Scan          | `OngletScan` legacy   | ⏳ à refondre |

**Ordre prévu** : Scan → Suivi → Calcul

---

## 9. Dialogues refondus

Les dialogues héritent des originaux de `ui.py` et réécrivent `_construire()`.

| Classe | Parent | Particularités |
|---|---|---|
| `DialogueFusionEmployeursV2` | `DialogueFusionEmployeurs` | `geometry("840x620")`, boutons en bas EN PREMIER |
| `DialogueEditionV2` | `DialogueEdition` | deux cartes : Aperçu gauche + Formulaire droite |
| `TableauPagesV2` | `TableauPages` | override `_ouvrir_edition()` → `DialogueEditionV2` |

---

## 10. Checklist avant de marquer une page comme validée

- [ ] La page s'affiche sans erreur au démarrage
- [ ] La navigation sidebar active/désactive correctement le bouton
- [ ] Les actions principales fonctionnent (actualiser, ajouter, supprimer…)
- [ ] Les tri colonnes fonctionnent si Treeview
- [ ] Les dialogues qui s'ouvrent depuis cette page ont la palette crème/teal
- [ ] Aucun fond blanc résiduel visible
- [ ] Commit git avec message clair : `feat(ui): refonte PageNom`

---

## 11. Commandes utiles

```bash
# Lancer la version refonte
python _run_v2.py

# Lancer les tests (logique métier — pas de dépendance tkinter)
python -m pytest tests/ -v

# Vérifier une import isolée
python -c "import ui_v2"
```
