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
import io
from PIL import Image, ImageTk

from ui import (
    FenetrePrincipale,
    OngletEmployeurs, OngletCalcul, OngletSuivi,
    OngletRecap, OngletScan, OngletHistorique,
    TableauPages,
    DialogueFusionEmployeurs,
    DialogueEdition, FenetreApercu,
    TYPES_DOCUMENTS, charger_employeurs,
    _installer_tri,
    DND_DISPONIBLE,
)


# ===========================================================================
# Dialogues refondus
# ===========================================================================

class DialogueFusionEmployeursV2(DialogueFusionEmployeurs):
    """Dialogue de fusion refondu (Soft UI). Logique héritée."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)
        self.geometry("840x620")
        self.minsize(720, 520)

        ctk.CTkLabel(
            self,
            text="Gauche : noms à fusionner (Ctrl+clic = multi)   ·   "
                 "Droite : nom à conserver   ·   Double-clic = voir les documents",
            font=TH2.FONT_LABEL, text_color=TH2.C.TEXT_3, justify="left",
        ).pack(padx=20, pady=(16, 8), anchor="w")

        # Bas (boutons + statut) packé EN PREMIER pour rester toujours visible
        self._lbl_statut = tk.Label(self, text="", bg=TH2.C.BG,
                                    fg=TH2.C.TEXT_3, font=TH2.FONT_SMALL)
        self._lbl_statut.pack(side="bottom", pady=(0, 12))

        btns = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        btns.pack(side="bottom", pady=12)
        W.bouton_primaire(btns, "Fusionner", command=self._appliquer,
                          width=200, height=46,
                          font=TH2.FONT_HEADING).pack(side="left", padx=10)
        W.bouton_secondaire(btns, "Annuler", command=self.destroy,
                            width=150, height=46,
                            font=TH2.FONT_HEADING).pack(side="left", padx=10)

        listes = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        listes.pack(fill="both", expand=True, padx=20, pady=4)
        listes.columnconfigure(0, weight=1)
        listes.columnconfigure(2, weight=1)
        listes.rowconfigure(1, weight=1)

        def _colonne(col, titre, couleur, mode):
            ctk.CTkLabel(listes, text=titre, font=TH2.FONT_LABEL,
                         text_color=couleur, anchor="w").grid(
                row=0, column=col, sticky="w", pady=(0, 4))
            carte = W.Card(listes)
            carte.grid(row=1, column=col, sticky="nsew")
            carte.rowconfigure(0, weight=1)
            carte.columnconfigure(0, weight=1)
            sb = ctk.CTkScrollbar(carte)
            sb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 6))
            lb = tk.Listbox(
                carte, selectmode=mode, yscrollcommand=sb.set,
                exportselection=False, font=("Segoe UI", 11),
                activestyle="none", height=18,
                bg=TH2.C.SURFACE, fg=TH2.C.TEXT,
                selectbackground=TH2.C.PRIMARY, selectforeground=TH2.C.ON_PRIMARY,
                relief="flat", highlightthickness=0, bd=0,
            )
            lb.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
            sb.configure(command=lb.yview)
            return lb

        self._lb_sources = _colonne(0, "Noms à fusionner (sources)",
                                    TH2.C.DANGER, tk.MULTIPLE)
        ctk.CTkLabel(listes, text="→", font=(TH2.FONT_FAMILY, 18, "bold"),
                     text_color=TH2.C.PRIMARY).grid(row=1, column=1, padx=10)
        self._lb_cible = _colonne(2, "Nom à conserver (cible)",
                                  TH2.C.SUCCESS, tk.SINGLE)

        for emp in self._employeurs:
            self._lb_sources.insert(tk.END, f"  {emp}")
            self._lb_cible.insert(tk.END, f"  {emp}")
        self._lb_sources.bind("<Double-1>", lambda e: self._voir_docs(self._lb_sources))
        self._lb_cible.bind("<Double-1>", lambda e: self._voir_docs(self._lb_cible))

        self._lb_sources.bind("<<ListboxSelect>>", self._maj_statut)
        self._lb_cible.bind("<<ListboxSelect>>",   self._maj_statut)


class DialogueEditionV2(DialogueEdition):
    """Dialogue d'édition refondu (Soft UI). Champs tk/ttk conservés (manipulés
    par la logique héritée), structure et lisibilité modernisées."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)
        self.geometry("760x640")

        cont = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        cont.pack(fill="both", expand=True, padx=16, pady=16)

        # ── Aperçu (gauche) ──────────────────────────────────────────────
        carte_ap = W.Card(cont)
        carte_ap.pack(side="left", fill="y", padx=(0, 14))
        ctk.CTkLabel(carte_ap, text="Aperçu", font=TH2.FONT_HEADING,
                     text_color=TH2.C.TEXT).pack(padx=16, pady=(12, 6))
        if self.ligne.miniature_bytes:
            try:
                img = Image.open(io.BytesIO(self.ligne.miniature_bytes))
                img.thumbnail((220, 300))
                self._photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(carte_ap, image=self._photo, cursor="hand2",
                               bg=TH2.C.SURFACE, bd=0)
                lbl.pack(padx=16)
                lbl.bind("<Button-1>", lambda e: FenetreApercu(
                    self, self.ligne.info_page["chemin_source"],
                    self.ligne.info_page["numero"], f"Page {self.ligne.numero}"))
                ctk.CTkLabel(carte_ap, text="Cliquer pour agrandir",
                             font=TH2.FONT_SMALL, text_color=TH2.C.TEXT_3).pack(
                    padx=16, pady=(6, 14))
            except Exception:
                ctk.CTkLabel(carte_ap, text="(pas d'aperçu)",
                             text_color=TH2.C.TEXT_3).pack(padx=20, pady=20)

        # ── Formulaire (droite) ──────────────────────────────────────────
        carte_form = W.Card(cont)
        carte_form.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(carte_form, text="Informations du document",
                     font=TH2.FONT_HEADING, text_color=TH2.C.TEXT,
                     anchor="w").pack(fill="x", padx=18, pady=(14, 8))

        form = tk.Frame(carte_form, bg=TH2.C.SURFACE)
        form.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        a = self.ligne.analyse

        def _lbl(parent, txt, r, col=0, **kw):
            return tk.Label(parent, text=txt, anchor="w", bg=TH2.C.SURFACE,
                            fg=TH2.C.TEXT_2, font=TH2.FONT_LABEL, **kw)

        def _entry(parent, var, width):
            return tk.Entry(parent, textvariable=var, width=width,
                            font=TH2.FONT_BODY, relief="solid", bd=1,
                            bg=TH2.C.SURFACE_2, fg=TH2.C.TEXT,
                            insertbackground=TH2.C.TEXT,
                            highlightthickness=1, highlightbackground=TH2.C.BORDER,
                            highlightcolor=TH2.C.PRIMARY)

        row = 0
        _lbl(form, "Type", row).grid(row=row, column=0, sticky="w", pady=5)
        self.var_type = tk.StringVar(value=a.get("type", "INCONNU"))
        ttk.Combobox(form, textvariable=self.var_type, values=TYPES_DOCUMENTS,
                     state="readonly", width=14).grid(row=row, column=1, sticky="w",
                                                      padx=8, pady=5)
        conf = a.get("confiance", 0)
        if conf >= 0.8:
            conf_txt, conf_fg = f"{conf:.0%}  ✓ élevée", TH2.C.SUCCESS
        elif conf >= 0.5:
            conf_txt, conf_fg = f"{conf:.0%}  ~ moyenne", TH2.C.WARNING
        else:
            conf_txt, conf_fg = (f"{conf:.0%}  ✗ basse", TH2.C.DANGER) if conf else ("", TH2.C.TEXT_3)
        if conf_txt:
            tk.Label(form, text=conf_txt, font=TH2.FONT_SMALL, bg=TH2.C.SURFACE,
                     fg=conf_fg).grid(row=row, column=2, sticky="w", padx=4)
        row += 1

        _lbl(form, "Année (YYYY)", row).grid(row=row, column=0, sticky="w", pady=5)
        self.var_annee = tk.StringVar(value=a.get("annee", ""))
        _entry(form, self.var_annee, 8).grid(row=row, column=1, sticky="w", padx=8, pady=5)
        row += 1

        _lbl(form, "Mois", row).grid(row=row, column=0, sticky="w", pady=5)
        mois_val = a.get("mois", "")
        mois_label = next((m for m in self.LISTE_MOIS if m.startswith(mois_val)),
                          self.LISTE_MOIS[0])
        self.var_mois = tk.StringVar(value=mois_label)
        ttk.Combobox(form, textvariable=self.var_mois, values=self.LISTE_MOIS,
                     state="readonly", width=18).grid(row=row, column=1, sticky="w",
                                                      padx=8, pady=5)
        row += 1

        _lbl(form, "Date début (JJ)", row).grid(row=row, column=0, sticky="w", pady=5)
        self.var_debut = tk.StringVar(value=a.get("date_debut", ""))
        _entry(form, self.var_debut, 5).grid(row=row, column=1, sticky="w", padx=8, pady=5)
        row += 1

        _lbl(form, "Date fin (JJ)", row).grid(row=row, column=0, sticky="w", pady=5)
        self.var_fin = tk.StringVar(value=a.get("date_fin", ""))
        _entry(form, self.var_fin, 5).grid(row=row, column=1, sticky="w", padx=8, pady=5)
        row += 1

        _lbl(form, "Employeur", row).grid(row=row, column=0, sticky="w", pady=5)
        self.var_employeur = tk.StringVar(value=a.get("employeur", ""))
        frame_emp = tk.Frame(form, bg=TH2.C.SURFACE)
        frame_emp.grid(row=row, column=1, columnspan=2, sticky="w", padx=8, pady=5)
        self._employeurs_liste = charger_employeurs()
        self._cb_employeur = ttk.Combobox(frame_emp, textvariable=self.var_employeur,
                                          values=self._employeurs_liste, width=28)
        self._cb_employeur.pack(side="left")
        W.bouton_secondaire(frame_emp, "+ Ajouter", command=self._ajouter_employeur,
                            width=90, height=28, font=TH2.FONT_SMALL).pack(
            side="left", padx=(6, 0))
        row += 1

        self._sep_aem = ttk.Separator(form, orient="horizontal")
        self._sep_aem.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        row += 1
        self._lbl_aem_section = tk.Label(form, text="Champs spécifiques AEM",
                                         font=TH2.FONT_SMALL, bg=TH2.C.SURFACE,
                                         fg=TH2.C.TEXT_3, anchor="w")
        self._lbl_aem_section.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        row += 1

        self._lbl_heures = _lbl(form, "Heures", row)
        self._lbl_heures.grid(row=row, column=0, sticky="w", pady=5)
        self.var_heures = tk.StringVar(value=a.get("heures", ""))
        self.entry_heures = _entry(form, self.var_heures, 10)
        self.entry_heures.grid(row=row, column=1, sticky="w", padx=8, pady=5)
        tk.Label(form, text="h", bg=TH2.C.SURFACE, fg=TH2.C.TEXT_2,
                 font=TH2.FONT_BODY).grid(row=row, column=2, sticky="w")
        self.var_heures.trace_add("write",
                                  lambda *_: self.entry_heures.config(bg=TH2.C.SURFACE_2))
        row += 1

        self._lbl_salaire = _lbl(form, "Salaire brut", row)
        self._lbl_salaire.grid(row=row, column=0, sticky="w", pady=5)
        self.var_salaire = tk.StringVar(value=a.get("salaire_brut", ""))
        self.entry_salaire = _entry(form, self.var_salaire, 12)
        self.entry_salaire.grid(row=row, column=1, sticky="w", padx=8, pady=5)
        tk.Label(form, text="EUR", bg=TH2.C.SURFACE, fg=TH2.C.TEXT_2,
                 font=TH2.FONT_BODY).grid(row=row, column=2, sticky="w")
        self.var_salaire.trace_add("write",
                                   lambda *_: self.entry_salaire.config(bg=TH2.C.SURFACE_2))
        row += 1

        ttk.Separator(form, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        row += 1
        tk.Label(form, text="Nom prévu", bg=TH2.C.SURFACE, fg=TH2.C.TEXT_2,
                 font=TH2.FONT_LABEL).grid(row=row, column=0, sticky="w", pady=4)
        self.lbl_nom = tk.Label(form, text=self.ligne.nom_fichier_prevu(),
                                font=TH2.FONT_SMALL, bg=TH2.C.SURFACE,
                                fg=TH2.C.PRIMARY, wraplength=360, justify="left")
        self.lbl_nom.grid(row=row, column=1, columnspan=2, sticky="w", padx=8)

        for var in (self.var_type, self.var_annee, self.var_mois, self.var_debut,
                    self.var_fin, self.var_employeur, self.var_heures, self.var_salaire):
            var.trace_add("write", self._maj_nom_prevu)
        self.var_type.trace_add("write", self._on_type_change)
        self._on_type_change()

        # ── Boutons (ancrés en bas) ──────────────────────────────────────
        barre = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        barre.pack(side="bottom", fill="x", padx=16, pady=(0, 14))
        W.bouton_primaire(barre, "Enregistrer et classifier",
                          command=self._enregistrer_et_classifier,
                          width=210, height=42).pack(side="left", padx=(0, 8))
        W.bouton_secondaire(barre, "Enregistrer",
                            command=self._enregistrer, width=130, height=42).pack(
            side="left", padx=(0, 8))
        W.bouton_secondaire(barre, "Annuler", command=self.destroy,
                            width=110, height=42).pack(side="left")


class TableauPagesV2(TableauPages):
    """TableauPages utilisant le dialogue d'édition refondu."""

    def _ouvrir_edition(self, idx: int):
        ligne = self.lignes[idx]

        def callback_maj(classifier=False):
            self.mettre_a_jour_ligne(idx)
            if classifier:
                self.app._classifier_ligne(idx)

        DialogueEditionV2(self, ligne, callback_maj)


# ===========================================================================
# Pages refondues (héritent la logique des onglets, réécrivent le layout)
# ===========================================================================

class PageRecap(OngletRecap):
    """Onglet Récapitulatif refondu (chrome CTk, logique héritée)."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)

        # En-tête
        entete = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        entete.pack(fill="x", padx=24, pady=(20, 6))
        ctk.CTkLabel(entete, text="Récapitulatif annuel", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(side="left")
        W.bouton_primaire(entete, "↻  Actualiser", command=self.actualiser,
                          width=140).pack(side="right")

        # Filtre année
        filtre = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        filtre.pack(fill="x", padx=24, pady=(0, 6))
        ctk.CTkLabel(filtre, text="Filtrer par année", font=TH2.FONT_LABEL,
                     text_color=TH2.C.TEXT_2).pack(side="left", padx=(0, 8))
        self.var_annee = tk.StringVar(value="Toutes")
        self._combo_annee = ttk.Combobox(filtre, textvariable=self.var_annee,
                                          width=10, state="readonly")
        self._combo_annee.pack(side="left")
        self._combo_annee.bind("<<ComboboxSelected>>", lambda e: self._filtrer())

        # Cartes de synthèse (dessinées par _maj_cartes — héritent crème)
        self._frame_cartes = tk.Frame(self, bg=TH2.C.BG)
        self._frame_cartes.pack(fill="x", padx=24, pady=4)

        # Tableau détail dans une Card
        carte = W.Card(self)
        carte.pack(fill="both", expand=True, padx=24, pady=8)
        carte.grid_rowconfigure(0, weight=1)
        carte.grid_columnconfigure(0, weight=1)
        zone = tk.Frame(carte, bg=TH2.C.SURFACE)
        zone.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        sv = ctk.CTkScrollbar(zone)
        sh = ctk.CTkScrollbar(zone, orientation="horizontal")
        self.tree = ttk.Treeview(
            zone, columns=[c[0] for c in self.COL], show="headings",
            yscrollcommand=sv.set, xscrollcommand=sh.set, height=14)
        sv.configure(command=self.tree.yview)
        sh.configure(command=self.tree.xview)
        for col_id, col_titre, col_larg in self.COL:
            self.tree.column(col_id, width=col_larg, minwidth=40,
                             stretch=(col_id == "employeur"))
            self.tree.heading(col_id, text=col_titre)
        self.tree.tag_configure("aem",       background="#E3F2FD")
        self.tree.tag_configure("bp",        background="#E8F5E9")
        self.tree.tag_configure("cs",        background="#FFF8E1")
        self.tree.tag_configure("ct",        background="#FFF8E1")
        self.tree.tag_configure("stc",       background="#FCE4EC")
        self.tree.tag_configure("total",     background="#C5CAE9", font=("", 9, "bold"))
        self.tree.tag_configure("separateur", background="#E8EAF6",
                                font=("", 9, "bold"), foreground="#1A237E")
        self.tree.tag_configure("previsionnel", background="#F3E5F5",
                                foreground="#6A1B9A", font=("", 9, "italic"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sv.grid(row=0, column=1, sticky="ns")
        sh.grid(row=1, column=0, sticky="ew")
        zone.grid_rowconfigure(0, weight=1)
        zone.grid_columnconfigure(0, weight=1)
        self._tri = _installer_tri(self.tree, [c[0] for c in self.COL])

        # Pied
        self._lbl_pied = tk.Label(self, text="", font=TH2.FONT_SMALL,
                                  bg=TH2.C.BG, fg=TH2.C.TEXT_3)
        self._lbl_pied.pack(pady=4)


class PageHistorique(OngletHistorique):
    """Onglet Historique refondu. Logique 100% héritée."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)

        # ── En-tête ─────────────────────────────────────────────────────────
        entete = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        entete.pack(fill="x", padx=24, pady=(20, 6))
        ctk.CTkLabel(entete, text="Historique", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(side="left")
        W.bouton_primaire(entete, "+ Contrat Futur",
                          command=self._creer_previsionnel,
                          width=160).pack(side="right")

        # ── Barre navigation ────────────────────────────────────────────────
        nav = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        nav.pack(fill="x", padx=24, pady=(0, 6))

        def _btn_nav(parent, txt, cmd):
            return ctk.CTkButton(parent, text=txt, command=cmd, width=36,
                                 height=32, corner_radius=TH2.RADIUS_MD,
                                 font=TH2.FONT_BODY, fg_color=TH2.C.PRIMARY,
                                 hover_color=TH2.C.PRIMARY_HOV,
                                 text_color=TH2.C.ON_PRIMARY)

        _btn_nav(nav, "◀", lambda: self._naviguer(-1)).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(nav, text="Année", font=TH2.FONT_LABEL,
                     text_color=TH2.C.TEXT_2).pack(side="left", padx=(0, 4))
        self._cb_annee = ttk.Combobox(nav, textvariable=self._annee_var,
                                      width=7, state="readonly")
        self._cb_annee.pack(side="left", padx=(0, 12))
        self._cb_annee.bind("<<ComboboxSelected>>", lambda e: self._on_annee_change())

        ctk.CTkLabel(nav, text="Mois", font=TH2.FONT_LABEL,
                     text_color=TH2.C.TEXT_2).pack(side="left", padx=(0, 4))
        self._cb_mois = ttk.Combobox(nav, textvariable=self._mois_var,
                                     width=14, state="readonly")
        self._cb_mois.pack(side="left", padx=(0, 6))
        self._cb_mois.bind("<<ComboboxSelected>>", lambda e: self._actualiser_liste())

        _btn_nav(nav, "▶", lambda: self._naviguer(+1)).pack(side="left", padx=(0, 16))
        W.bouton_secondaire(nav, "🔄 Actualiser",
                            command=self._actualiser_liste,
                            width=130).pack(side="left")

        # ── Corps : liste (gauche) + détails (droite) ────────────────────────
        corps = tk.Frame(self, bg=TH2.C.BG)
        corps.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        corps.columnconfigure(0, weight=1)
        corps.columnconfigure(1, weight=0)
        corps.rowconfigure(0, weight=1)

        # ── Carte liste ──────────────────────────────────────────────────────
        carte_liste = W.Card(corps)
        carte_liste.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        carte_liste.grid_rowconfigure(0, weight=1)
        carte_liste.grid_columnconfigure(0, weight=1)

        zone_tree = tk.Frame(carte_liste, bg=TH2.C.SURFACE)
        zone_tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        zone_tree.columnconfigure(0, weight=1)
        zone_tree.rowconfigure(0, weight=1)

        cols = [c[0] for c in self.COL]
        self.tree = ttk.Treeview(zone_tree, columns=cols, show="headings",
                                 selectmode="browse")
        for cid, label, w in self.COL:
            self.tree.heading(cid, text=label)
            self.tree.column(cid, width=w, minwidth=40, anchor="w")

        self.tree.tag_configure("previsionnel", foreground="#6A1B9A",
                                font=("Segoe UI", 9, "italic"))
        self.tree.tag_configure("classifie", foreground=TH2.C.PRIMARY)

        sv = ctk.CTkScrollbar(zone_tree, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sv.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sv.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>",  self._on_double_clic)
        self.tree.bind("<Button-3>",         self._on_clic_droit)
        self._tri = _installer_tri(self.tree, [c[0] for c in self.COL
                                               if c[0] != "statut"])

        # Menu contextuel clic droit
        self._menu_ctx = tk.Menu(self, tearoff=0)
        self._menu_ctx.add_command(label="📄  Ouvrir le document",
                                   command=self._ouvrir_pdf_fenetre)
        self._menu_ctx.add_command(label="📁  Ouvrir le dossier dans l'Explorateur",
                                   command=self._ouvrir_dossier_explorateur)
        self._menu_ctx.add_separator()
        self._menu_ctx.add_command(label="📋  Dupliquer vers d'autres dates...",
                                   command=self._dupliquer_contrat)
        self._menu_ctx.add_separator()
        self._menu_ctx.add_command(label="💾  Enregistrer les modifications",
                                   command=self._sauvegarder)
        self._menu_ctx.add_command(label="🗑  Supprimer le prévisionnel",
                                   command=self._supprimer_previsionnel)

        # ── Carte détails ────────────────────────────────────────────────────
        carte_detail = W.Card(corps)
        carte_detail.grid(row=0, column=1, sticky="nsew")
        carte_detail.configure(width=350)

        corps_detail = ctk.CTkFrame(carte_detail, fg_color=TH2.C.SURFACE)
        corps_detail.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(corps_detail, text="Détails du contrat",
                     font=TH2.FONT_HEADING, text_color=TH2.C.TEXT,
                     anchor="w").pack(fill="x", pady=(0, 8))

        champs = [
            ("type",       "Type",         ["AEM", "BP", "CS", "CT", "STC"]),
            ("annee",      "Année",        None),
            ("mois",       "Mois",         list(self.MOIS_NUM)),
            ("employeur",  "Employeur",    None),
            ("date_debut", "Date début",   None),
            ("date_fin",   "Date fin",     None),
            ("heures",     "Heures",       None),
            ("salaire",    "Salaire brut", None),
        ]
        self._vars_form: dict = {}
        self._widgets_form: dict = {}

        for key, label, options in champs:
            ligne = ctk.CTkFrame(corps_detail, fg_color=TH2.C.SURFACE)
            ligne.pack(fill="x", pady=2)
            ctk.CTkLabel(ligne, text=label + " :", font=TH2.FONT_LABEL,
                         text_color=TH2.C.TEXT_2, width=100,
                         anchor="e").pack(side="left", padx=(0, 6))
            var = tk.StringVar()
            self._vars_form[key] = var
            if options:
                w = ctk.CTkComboBox(ligne, variable=var, values=options,
                                    width=170, font=TH2.FONT_BODY,
                                    fg_color=TH2.C.SURFACE_2,
                                    border_color=TH2.C.BORDER,
                                    text_color=TH2.C.TEXT,
                                    corner_radius=TH2.RADIUS_MD)
            else:
                w = ctk.CTkEntry(ligne, textvariable=var, width=170,
                                 font=TH2.FONT_BODY,
                                 fg_color=TH2.C.SURFACE_2,
                                 border_color=TH2.C.BORDER,
                                 text_color=TH2.C.TEXT,
                                 corner_radius=TH2.RADIUS_MD)
            w.config = w.configure
            w.pack(side="left")
            self._widgets_form[key] = w

        # Champ note
        ligne_note = ctk.CTkFrame(corps_detail, fg_color=TH2.C.SURFACE)
        ligne_note.pack(fill="x", pady=2)
        ctk.CTkLabel(ligne_note, text="Note :", font=TH2.FONT_LABEL,
                     text_color=TH2.C.TEXT_2, width=100,
                     anchor="e").pack(side="left", padx=(0, 6))
        self._var_note = tk.StringVar()
        self._txt_note = ctk.CTkEntry(ligne_note, textvariable=self._var_note,
                                      width=170, font=TH2.FONT_BODY,
                                      fg_color=TH2.C.SURFACE_2,
                                      border_color=TH2.C.BORDER,
                                      text_color=TH2.C.TEXT,
                                      corner_radius=TH2.RADIUS_MD)
        self._txt_note.config = self._txt_note.configure
        self._txt_note.pack(side="left")

        # Boutons
        btns = ctk.CTkFrame(corps_detail, fg_color=TH2.C.SURFACE)
        btns.pack(fill="x", pady=(12, 0))
        self._btn_save = W.bouton_primaire(btns, "💾 Enregistrer",
                                           command=self._sauvegarder,
                                           state="disabled", width=140)
        self._btn_save.config = self._btn_save.configure
        self._btn_save.pack(side="left", padx=(0, 8))

        self._btn_delete = ctk.CTkButton(
            btns, text="🗑 Supprimer", command=self._supprimer_previsionnel,
            state="disabled", width=130, corner_radius=TH2.RADIUS_MD, height=38,
            fg_color="transparent", hover_color=TH2.C.SURFACE_2,
            text_color=TH2.C.DANGER, border_color=TH2.C.DANGER,
            border_width=1, font=TH2.FONT_BODY)
        self._btn_delete.config = self._btn_delete.configure
        self._btn_delete.pack(side="left")

        # Label status (tk.Label car la logique utilise fg="green"/"red")
        self._lbl_status = tk.Label(corps_detail, text="", font=TH2.FONT_SMALL,
                                    bg=TH2.C.SURFACE, fg=TH2.C.TEXT_3)
        self._lbl_status.pack(pady=(6, 0))

        self.after(200, self._init_navigation)


class PageEmployeurs(OngletEmployeurs):
    """Onglet Employeurs refondu (Soft UI). Logique 100% héritée."""

    def _construire(self):
        self.configure(bg=TH2.C.BG)

        # En-tête
        entete = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        entete.pack(fill="x", padx=24, pady=(20, 6))
        ctk.CTkLabel(entete, text="Employeurs", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            entete,
            text="Noms recherchés directement dans chaque document — "
                 "prioritaires sur la détection IA. Double-clic pour modifier.",
            font=TH2.FONT_LABEL, text_color=TH2.C.TEXT_3,
            anchor="w", justify="left").pack(anchor="w")

        # Carte d'ajout rapide
        carte_ajout = W.Card(self)
        carte_ajout.pack(fill="x", padx=24, pady=8)
        ligne = ctk.CTkFrame(carte_ajout, fg_color=TH2.C.SURFACE)
        ligne.pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(ligne, text="Ajouter un employeur",
                     font=TH2.FONT_LABEL, text_color=TH2.C.TEXT_2).pack(
            side="left", padx=(0, 10))
        self.var_nom = tk.StringVar()
        entry = ctk.CTkEntry(ligne, textvariable=self.var_nom,
                             font=TH2.FONT_BODY, height=36,
                             corner_radius=TH2.RADIUS_MD,
                             fg_color=TH2.C.SURFACE_2, border_color=TH2.C.BORDER,
                             text_color=TH2.C.TEXT,
                             placeholder_text="Nom de l'employeur…")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        entry.bind("<Return>", lambda e: self._ajouter())
        W.bouton_primaire(ligne, "Ajouter", command=self._ajouter,
                          width=110).pack(side="left")

        # Carte liste
        carte_liste = W.Card(self)
        carte_liste.pack(fill="both", expand=True, padx=24, pady=8)
        corps = ctk.CTkFrame(carte_liste, fg_color=TH2.C.SURFACE)
        corps.pack(fill="both", expand=True, padx=12, pady=12)

        scroll = ctk.CTkScrollbar(corps)
        scroll.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            corps, yscrollcommand=scroll.set,
            selectmode=tk.SINGLE, font=("Segoe UI", 12),
            activestyle="none", height=16,
            bg=TH2.C.SURFACE, fg=TH2.C.TEXT,
            selectbackground=TH2.C.PRIMARY, selectforeground=TH2.C.ON_PRIMARY,
            relief="flat", highlightthickness=0, bd=0,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.configure(command=self.listbox.yview)
        self.listbox.bind("<Double-1>", lambda e: self._editer())

        # Barre d'actions
        actions = ctk.CTkFrame(self, fg_color=TH2.C.BG)
        actions.pack(fill="x", padx=24, pady=(0, 16))
        W.bouton_secondaire(actions, "Modifier", command=self._editer,
                            width=110).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions, text="Supprimer", command=self._supprimer, width=110,
            corner_radius=TH2.RADIUS_MD, height=38, fg_color="transparent",
            hover_color=TH2.C.SURFACE_2, text_color=TH2.C.DANGER,
            border_color=TH2.C.DANGER, border_width=1, font=TH2.FONT_BODY,
        ).pack(side="left", padx=(0, 8))
        W.bouton_secondaire(actions, "Scanner les documents",
                            command=self._scanner_depuis_docs,
                            width=190).pack(side="left", padx=(0, 8))
        W.bouton_secondaire(actions, "Fusionner doublons…",
                            command=self._fusionner_doublons,
                            width=180).pack(side="left", padx=(0, 8))

        self.lbl_count = ctk.CTkLabel(actions, text="", font=TH2.FONT_LABEL,
                                      text_color=TH2.C.TEXT_3)
        self.lbl_count.config = self.lbl_count.configure
        self.lbl_count.pack(side="right", padx=8)

        self._rafraichir_liste()

    def _fusionner_doublons(self):
        """Override : utilise le dialogue de fusion refondu."""
        if not self._employeurs:
            from tkinter import messagebox
            messagebox.showinfo("Liste vide", "Aucun employeur enregistré.", parent=self)
            return
        from config import charger_config
        dossier_base = charger_config().get("dossier_base", "")
        DialogueFusionEmployeursV2(self, self._employeurs, dossier_base,
                                   self._appliquer_fusions)

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

    def _construire_menu(self):
        """Override : pas de barre de menus tk (remplacée par la sidebar)."""
        pass

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
        self.tab_employeurs = self._page_refonte("employeurs", PageEmployeurs)
        self.tab_calcul     = self._page_hote("calcul",     OngletCalcul)
        self.tab_suivi      = self._page_hote("suivi",      OngletSuivi,  cfg=True)
        self.tab_recap      = self._page_refonte("recap",   PageRecap,    cfg=True)
        self.tab_scan       = self._page_hote("scan",       OngletScan,   cfg=True)
        self.tab_historique = self._page_refonte("historique", PageHistorique, cfg=True)

        self._harmoniser_onglets()
        self._afficher_page("analyse")

    def _harmoniser_onglets(self):
        """Recolore les onglets tk existants en palette 'figma' (crème/teal),
        sans toucher au shell customtkinter."""
        import theme as TH
        try:
            TH._THEME_COURANT = "figma"
            p = TH._palette()
            TH._update_globals(p)
            TH._patch_ttk_style(p)
            # Défauts option_add → tous les dialogues tk créés ensuite (Édition,
            # Aperçu, Paramètres…) héritent automatiquement de la palette figma.
            TH._appliquer_options_tk(self, p)
            # Onglets pas encore refondus uniquement (les pages CTk gèrent leurs couleurs)
            for onglet in (self.tab_calcul, self.tab_suivi,
                           self.tab_scan):
                TH._recolorer_widgets(onglet, p)
        except Exception:
            pass

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

    def _page_refonte(self, cle: str, Classe, cfg: bool = False):
        """Crée une page refondue (CTk) — gère ses propres couleurs."""
        hote = ctk.CTkFrame(self._zone, fg_color=TH2.C.BG, corner_radius=0)
        hote.grid(row=0, column=0, sticky="nsew")
        if cfg:
            onglet = Classe(hote, cfg_getter=lambda: self.cfg)
        else:
            onglet = Classe(hote)
        onglet.pack(fill="both", expand=True)
        self._pages[cle] = hote
        return onglet

    def _construire_sidebar(self, parent):
        bar = ctk.CTkFrame(parent, width=190, corner_radius=0,
                           fg_color=TH2.C.SIDEBAR)
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)

        # Logo / titre
        entete = ctk.CTkFrame(bar, fg_color=TH2.C.SIDEBAR)
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

        # Bas de sidebar : outils + thème
        bas = ctk.CTkFrame(bar, fg_color=TH2.C.SIDEBAR)
        bas.pack(side="bottom", fill="x", padx=10, pady=12)

        outils = [
            ("⊞  Boost IA",        self._ouvrir_boost_ia),
            ("⊕  Créer dossiers",  self._creer_dossiers),
            ("↻  Mises à jour",    self._ouvrir_mises_a_jour),
            ("⚙  Paramètres",      self._ouvrir_parametres),
        ]
        for libelle, cmd in outils:
            ctk.CTkButton(
                bas, text=f"  {libelle}", anchor="w",
                corner_radius=TH2.RADIUS_MD, height=32,
                fg_color="transparent", hover_color=TH2.C.SURFACE_2,
                text_color=TH2.C.TEXT_2, font=TH2.FONT_LABEL,
                command=cmd,
            ).pack(fill="x", pady=1)

        ctk.CTkLabel(bas, text=f"v{__import__('version').__version__}",
                     font=TH2.FONT_SMALL, text_color=TH2.C.TEXT_3).pack(pady=(10, 0))

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
        entete = ctk.CTkFrame(parent, fg_color=TH2.C.BG)
        entete.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        ctk.CTkLabel(entete, text="Analyse de documents", font=TH2.FONT_TITLE,
                     text_color=TH2.C.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(entete, text="Déposez vos PDF pour classification automatique",
                     font=TH2.FONT_LABEL, text_color=TH2.C.TEXT_3,
                     anchor="w").pack(anchor="w")

        # Bloc haut : drop zone + KPI
        haut = ctk.CTkFrame(parent, fg_color=TH2.C.BG)
        haut.grid(row=1, column=0, sticky="ew", padx=24, pady=6)
        haut.grid_columnconfigure(0, weight=3)
        haut.grid_columnconfigure(1, weight=2)

        # Zone de dépôt
        self._drop = ctk.CTkFrame(haut, corner_radius=TH2.RADIUS_LG,
                                  fg_color=TH2.C.SURFACE,
                                  border_color=TH2.C.ACCENT, border_width=2)
        self._drop.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        inner = ctk.CTkFrame(self._drop, fg_color=TH2.C.SURFACE)
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
        kpis = ctk.CTkFrame(haut, fg_color=TH2.C.BG)
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
        actions = ctk.CTkFrame(parent, fg_color=TH2.C.BG)
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
        self.tableau = TableauPagesV2(hote_tab, app=self)
        self.tableau.pack(fill="both", expand=True)

        # Actions de classification
        cl = ctk.CTkFrame(parent, fg_color=TH2.C.BG)
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
        footer = ctk.CTkFrame(parent, fg_color=TH2.C.BG)
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
