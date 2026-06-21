# -*- coding: utf-8 -*-
"""
IntermitDoc — Shell UI v2 (refonte Soft UI crème/teal).

FenetreV2 sous-classe FenetrePrincipale : toute la logique métier
(analyse IA, threading, classification, dédoublonnage) est héritée et
réutilisée telle quelle. Seule la PRÉSENTATION est refondue :
  - barre latérale (sidebar) à la place du Notebook
  - page Analyse reconstruite avec composants customtkinter + loader animé
Les 6 autres onglets existants sont embarqués inchangés (restylage progressif).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext
from pathlib import Path

import customtkinter as ctk

import theme_v2 as TH2
import widgets_v2 as W
from ui import (
    FenetrePrincipale,
    OngletEmployeurs, OngletCalcul, OngletSuivi,
    OngletRecap, OngletScan, OngletHistorique,
    TableauPages,
    DND_DISPONIBLE,
)

try:
    from tkinterdnd2 import DND_FILES
except Exception:
    DND_FILES = None


# Items de navigation : (clé, libellé, icône texte)
_NAV = [
    ("analyse",    "Analyse",      "⌕"),
    ("employeurs", "Employeurs",   "☰"),
    ("calcul",     "Calcul AEM",   "∑"),
    ("suivi",      "Suivi",        "◷"),
    ("recap",      "Récapitulatif","▦"),
    ("scan",       "Scan",         "⊞"),
    ("historique", "Historique",   "⟲"),
]


class FenetreV2(FenetrePrincipale):

    def __init__(self):
        TH2.appliquer("figma")
        super().__init__()

    # ------------------------------------------------------------------
    # Construction de l'interface (override complet)
    # ------------------------------------------------------------------
    def _construire_interface(self):
        self.configure(bg=TH2.C.BG)
        self._pages: dict[str, tk.Widget] = {}
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._page_active = None

        conteneur = ctk.CTkFrame(self, fg_color=TH2.C.BG, corner_radius=0)
        conteneur.pack(fill="both", expand=True)
        conteneur.grid_columnconfigure(1, weight=1)
        conteneur.grid_rowconfigure(0, weight=1)

        self._construire_sidebar(conteneur)

        self._zone = ctk.CTkFrame(conteneur, fg_color=TH2.C.BG, corner_radius=0)
        self._zone.grid(row=0, column=1, sticky="nsew")
        self._zone.grid_rowconfigure(0, weight=1)
        self._zone.grid_columnconfigure(0, weight=1)

        # Page Analyse (reconstruite)
        page_analyse = ctk.CTkFrame(self._zone, fg_color=TH2.C.BG, corner_radius=0)
        page_analyse.grid(row=0, column=0, sticky="nsew")
        self._construire_page_analyse(page_analyse)
        self._pages["analyse"] = page_analyse

        # Pages existantes (onglets inchangés) embarquées dans un conteneur CTk
        self.tab_employeurs = self._page_hote("employeurs", OngletEmployeurs)
        self.tab_calcul     = self._page_hote("calcul",     OngletCalcul)
        self.tab_suivi      = self._page_hote("suivi",      OngletSuivi,  cfg=True)
        self.tab_recap      = self._page_hote("recap",      OngletRecap,  cfg=True)
        self.tab_scan       = self._page_hote("scan",       OngletScan,   cfg=True)
        self.tab_historique = self._page_hote("historique", OngletHistorique, cfg=True)

        self._afficher_page("analyse")

    def _page_hote(self, cle: str, Classe, cfg: bool = False):
        """Crée une page-hôte CTk contenant un onglet tk existant."""
        hote = ctk.CTkFrame(self._zone, fg_color=TH2.C.BG, corner_radius=0)
        hote.grid(row=0, column=0, sticky="nsew")
        if cfg:
            onglet = Classe(hote, cfg_getter=lambda: self.cfg)
        else:
            onglet = Classe(hote)
        onglet.pack(fill="both", expand=True, padx=4, pady=4)
        self._pages[cle] = hote
        return onglet

    def _construire_sidebar(self, parent):
        bar = ctk.CTkFrame(parent, width=190, corner_radius=0,
                           fg_color=TH2.C.SIDEBAR)
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)

        # Logo / titre
        entete = ctk.CTkFrame(bar, fg_color="transparent")
        entete.pack(fill="x", padx=14, pady=(18, 18))
        logo = ctk.CTkLabel(entete, text="  IntermitDoc", font=TH2.FONT_HEADING,
                            text_color=TH2.C.TEXT, anchor="w")
        logo.pack(fill="x")

        for cle, libelle, icone in _NAV:
            b = ctk.CTkButton(
                bar, text=f"  {icone}   {libelle}", anchor="w",
                corner_radius=TH2.RADIUS_MD, height=38,
                fg_color="transparent", hover_color=TH2.C.SURFACE_2,
                text_color=TH2.C.TEXT_2, font=TH2.FONT_BODY,
                command=lambda c=cle: self._afficher_page(c),
            )
            b.pack(fill="x", padx=10, pady=2)
            self._nav_btns[cle] = b

        # Bas de sidebar : thème + paramètres
        bas = ctk.CTkFrame(bar, fg_color="transparent")
        bas.pack(side="bottom", fill="x", padx=10, pady=12)
        ctk.CTkButton(
            bas, text="  ⚙   Paramètres", anchor="w",
            corner_radius=TH2.RADIUS_MD, height=34,
            fg_color="transparent", hover_color=TH2.C.SURFACE_2,
            text_color=TH2.C.TEXT_2, font=TH2.FONT_LABEL,
            command=self._ouvrir_parametres,
        ).pack(fill="x", pady=2)

    def _afficher_page(self, cle: str):
        page = self._pages.get(cle)
        if page is None:
            return
        page.tkraise()
        self._page_active = cle
        for c, b in self._nav_btns.items():
            if c == cle:
                b.configure(fg_color=TH2.C.PRIMARY, text_color=TH2.C.ON_PRIMARY)
            else:
                b.configure(fg_color="transparent", text_color=TH2.C.TEXT_2)

    # ------------------------------------------------------------------
    # Page Analyse — chrome refondu, logique héritée
    # ------------------------------------------------------------------
    def _construire_page_analyse(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # En-tête
        entete = ctk.CTkFrame(parent, fg_color="transparent")
        entete.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        ctk.CTkLabel(entete, text="Analyse de documents", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(entete, text="Déposez vos PDF pour classification automatique",
                     font=TH2.FONT_LABEL, text_color=TH2.C.TEXT_3,
                     anchor="w").pack(anchor="w")

        # Bloc haut : drop zone + KPI
        haut = ctk.CTkFrame(parent, fg_color="transparent")
        haut.grid(row=1, column=0, sticky="ew", padx=24, pady=6)
        haut.grid_columnconfigure(0, weight=3)
        haut.grid_columnconfigure(1, weight=2)

        # Zone de dépôt
        self._drop = ctk.CTkFrame(haut, corner_radius=TH2.RADIUS_LG,
                                  fg_color=TH2.C.SURFACE,
                                  border_color=TH2.C.ACCENT, border_width=2)
        self._drop.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        inner = ctk.CTkFrame(self._drop, fg_color="transparent")
        inner.pack(expand=True, pady=18)
        self._drop_icon = ctk.CTkLabel(inner, text="⬆", font=(TH2.FONT_FAMILY, 30),
                                       text_color=TH2.C.PRIMARY)
        self._drop_icon.pack()
        self._drop_lbl = ctk.CTkLabel(
            inner, text="Glissez vos PDF ici", font=TH2.FONT_BODY,
            text_color=TH2.C.TEXT)
        self._drop_lbl.pack(pady=(4, 0))
        self._drop_sub = ctk.CTkLabel(
            inner, text="ou cliquez pour parcourir", font=TH2.FONT_SMALL,
            text_color=TH2.C.TEXT_3)
        self._drop_sub.pack()
        for wdg in (self._drop, inner, self._drop_icon, self._drop_lbl, self._drop_sub):
            wdg.bind("<Button-1>", lambda e: self._choisir_fichier())
        if DND_DISPONIBLE and DND_FILES:
            try:
                self._drop.drop_target_register(DND_FILES)
                self._drop.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        # KPI
        kpis = ctk.CTkFrame(haut, fg_color="transparent")
        kpis.grid(row=0, column=1, sticky="nsew")
        kpis.grid_columnconfigure((0, 1), weight=1)
        self._kpi_docs   = W.KPICard(kpis, "Documents", "0")
        self._kpi_clas   = W.KPICard(kpis, "Classés", "0")
        self._kpi_att    = W.KPICard(kpis, "En attente", "0",
                                     value_color=TH2.C.WARNING)
        self._kpi_docs.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self._kpi_clas.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self._kpi_att.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

        # Barre d'actions
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 4))
        W.bouton_secondaire(actions, "Parcourir…", command=self._choisir_fichier,
                            width=130).pack(side="left", padx=(0, 8))
        W.bouton_secondaire(actions, "Scanner un dossier…",
                            command=self._scanner_dossier_recursif,
                            width=180).pack(side="left", padx=(0, 8))

        self.btn_analyser = W.bouton_primaire(actions, "Analyser",
                                              command=self._lancer_analyse, width=140)
        self.btn_analyser.pack(side="right")
        self._aliaser_config(self.btn_analyser)

        # Variables réutilisées par la logique héritée
        self.var_chemin = tk.StringVar()
        self.var_dossier_sortie = tk.StringVar(value=self.cfg.get("dossier_base", ""))

        # Résultats (TableauPages — widget existant) dans une Card
        carte_res = W.Card(parent)
        carte_res.grid(row=3, column=0, sticky="nsew", padx=24, pady=8)
        carte_res.grid_rowconfigure(0, weight=1)
        carte_res.grid_columnconfigure(0, weight=1)
        hote_tab = tk.Frame(carte_res, bg=TH2.C.SURFACE)
        hote_tab.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.tableau = TableauPages(hote_tab, app=self)
        self.tableau.pack(fill="both", expand=True)

        # Actions de classification
        cl = ctk.CTkFrame(parent, fg_color="transparent")
        cl.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 4))
        self.btn_classifier = W.bouton_primaire(cl, "Classifier tout",
                                                command=self._classifier_tout, width=150)
        self.btn_classifier.pack(side="left", padx=(0, 8))
        self.btn_classifier_sel = W.bouton_secondaire(cl, "Classifier sélection",
                                                      command=self._classifier_selection,
                                                      width=170)
        self.btn_classifier_sel.pack(side="left", padx=(0, 8))
        W.bouton_secondaire(cl, "Vider", command=self._vider_tableau,
                            width=90).pack(side="left")
        for b in (self.btn_classifier, self.btn_classifier_sel):
            self._aliaser_config(b)
            b.configure(state="disabled")

        # Footer : loader + progression + log
        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 14))
        footer.grid_columnconfigure(1, weight=1)

        self._loader = W.LoaderFondu(footer, size=30)
        self._loader.set_bg(TH2.C.BG)
        self._loader.grid(row=0, column=0, padx=(0, 10))

        self.lbl_progress = tk.Label(footer, text="Prêt.", anchor="w",
                                     bg=TH2.C.BG, fg=TH2.C.TEXT_2,
                                     font=TH2.FONT_LABEL)
        self.lbl_progress.grid(row=0, column=1, sticky="ew")

        self.progress = ttk.Progressbar(footer, mode="determinate", length=240)
        self.progress.grid(row=0, column=2, padx=6)

        self.log = scrolledtext.ScrolledText(
            footer, height=4, state=tk.DISABLED, font=("Consolas", 9),
            bg=TH2.C.SURFACE, fg=TH2.C.TEXT_2, relief="flat", bd=0)
        self.log.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    # ------------------------------------------------------------------
    # Compat + overrides légers (logique inchangée)
    # ------------------------------------------------------------------
    @staticmethod
    def _aliaser_config(widget) -> None:
        """Permet aux méthodes héritées d'appeler .config(state=…) sur un CTkButton."""
        widget.config = widget.configure

    def _charger_fichiers(self, chemins: list[str], dossier_sortie: str = None):
        """Override : met à jour la zone de dépôt stylée au lieu d'un tk.Label."""
        if len(chemins) == 1:
            affichage = chemins[0]
        else:
            affichage = (f"{len(chemins)} fichiers : "
                         + ", ".join(Path(p).name for p in chemins))
        self.var_chemin.set(affichage)
        self._fichiers_en_attente = chemins

        noms = ", ".join(Path(p).name for p in chemins)
        self._drop_icon.configure(text="✓", text_color=TH2.C.SUCCESS)
        self._drop_lbl.configure(text=f"{len(chemins)} fichier(s) prêt(s)")
        self._drop_sub.configure(text=noms[:70])
        self._drop.configure(border_color=TH2.C.SUCCESS)
        self._kpi_docs.set_value(str(len(chemins)))

    def _lancer_analyse(self):
        super()._lancer_analyse()
        if getattr(self, "_en_traitement", False):
            self._loader.start()
            self._surveiller_traitement()

    def _surveiller_traitement(self):
        """Arrête le loader et rafraîchit les KPI à la fin du traitement."""
        if getattr(self, "_en_traitement", False):
            self.after(200, self._surveiller_traitement)
            return
        self._loader.stop()
        self._maj_kpi()

    def _maj_kpi(self):
        lignes = getattr(self.tableau, "lignes", [])
        total = len(lignes)
        classes = sum(1 for l in lignes if getattr(l, "statut", "") in ("Copie",))
        attente = total - classes
        self._kpi_docs.set_value(str(total))
        self._kpi_clas.set_value(str(classes))
        self._kpi_att.set_value(str(attente))

    def _vider_tableau(self):
        super()._vider_tableau()
        self._drop_icon.configure(text="⬆", text_color=TH2.C.PRIMARY)
        self._drop_lbl.configure(text="Glissez vos PDF ici")
        self._drop_sub.configure(text="ou cliquez pour parcourir")
        self._drop.configure(border_color=TH2.C.ACCENT)
        for k in (self._kpi_docs, self._kpi_clas, self._kpi_att):
            k.set_value("0")


def lancer():
    app = FenetreV2()
    app.mainloop()


if __name__ == "__main__":
    lancer()
