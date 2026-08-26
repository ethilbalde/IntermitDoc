# -*- coding: utf-8 -*-
"""
Interface graphique principale d'IntermitDoc.
"""
import io
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from datetime import date as _date_today, timedelta
from pathlib import Path

from PIL import Image, ImageTk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_DISPONIBLE = True
except ImportError:
    DND_DISPONIBLE = False

from version import __version__
import updater

from config import (
    TYPES_DOCUMENTS, MOIS_DOSSIERS, IA_PROVIDERS,
    charger_config, sauvegarder_config, valider_config,
    charger_employeurs, sauvegarder_employeurs,
    verifier_traite, enregistrer_traite,
    charger_traites, calculer_empreinte,
    logger,
)
from extractor import ExtracteurPDF, extraire_valeurs_aem_page, extraire_valeurs_aem_natif
from analyzer import (
    analyser_document, analyser_document_multi,
    analyser_details_aem, chercher_employeur_connu,
    tester_connexion_ia,
    extraire_info_nom_fichier, fusionner_info_nom_analyse,
)
from classifier import (
    construire_nom_fichier,
    copier_page_classifiee,
    creer_structure_dossiers,
    lire_metadata_intermitdoc,
    _injecter_metadata,
    _synchroniser_dossier_mois,
    synchroniser_aem_vers_bp,
)

import theme as TH

COULEURS_CONFIANCE = {
    "haute":   TH.CONF_HIGH,
    "moyenne": TH.CONF_MED,
    "basse":   TH.CONF_LOW,
}
COULEUR_OK  = TH.ROW_OK
COULEUR_ERR = TH.ROW_ERR


# ---------------------------------------------------------------------------
# Utilitaire tri Treeview générique
# ---------------------------------------------------------------------------
def _trier_colonne(tree: ttk.Treeview, col: str, etat: dict):
    """
    Trie un Treeview par la colonne col en basculant asc/desc.
    etat = dict mutable partagé par tous les en-têtes du même tableau :
           {"col": str|None, "asc": bool, "originals": dict}
    Les lignes de séparateur (valeur vide sur toutes les colonnes) sont
    ignorées du tri et laissées en place.
    """
    if etat.get("col") == col:
        etat["asc"] = not etat["asc"]
    else:
        etat["col"] = col
        etat["asc"] = True

    def _num(v: str) -> tuple:
        v = v.strip().rstrip("hH").rstrip("€").replace("EUR", "").replace(",", ".").strip()
        try:
            return (0, float(v))
        except (ValueError, TypeError):
            return (1, v.lower())

    items = [(tree.set(k, col), k) for k in tree.get_children("")]
    items.sort(key=lambda x: _num(x[0]), reverse=not etat["asc"])
    for i, (_, k) in enumerate(items):
        tree.move(k, "", i)

    # Flèche visuelle sur l'en-tête actif, texte original sur les autres
    originals = etat.setdefault("originals", {})
    for c in tree["columns"]:
        orig = originals.get(c)
        if orig is None:
            orig = tree.heading(c)["text"].rstrip(" ▲▼")
            originals[c] = orig
        arrow = (" ▲" if etat["asc"] else " ▼") if c == col else ""
        tree.heading(c, text=orig + arrow)


def _installer_tri(tree: ttk.Treeview, colonnes: list[str]) -> dict:
    """
    Branche le tri sur les en-têtes listés.
    Retourne le dict d'état (à conserver dans l'instance).
    """
    etat: dict = {"col": None, "asc": True, "originals": {}}
    for c in colonnes:
        orig = tree.heading(c)["text"]
        etat["originals"][c] = orig
        tree.heading(c, command=lambda col=c: _trier_colonne(tree, col, etat))
    return etat


# ---------------------------------------------------------------------------
# Apercu pleine page — rendu haute resolution via PyMuPDF
# ---------------------------------------------------------------------------
class FenetreApercu(tk.Toplevel):
    DPI_BASE  = 150
    DPI_MAX   = 300
    ZOOM_STEP = 0.20

    def __init__(self, parent, chemin_source: str, numero_page: int, titre: str = "Apercu"):
        super().__init__(parent)
        self.title(titre)
        self.geometry("760x960")
        self.minsize(400, 500)
        self.resizable(True, True)

        self._chemin   = chemin_source
        self._page_num = numero_page
        self._zoom     = 1.0
        self._photo    = None
        self._img_base = None

        self._construire()
        self._rendre_page()
        self.focus_set()

    def _construire(self):
        bar = tk.Frame(self, pady=3, relief=tk.RAISED, bd=1)
        bar.pack(fill=tk.X)

        tk.Button(bar, text="  +  ", command=self._zoom_in,
                  font=("", 12, "bold"), width=3).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(bar, text="  -  ", command=self._zoom_out,
                  font=("", 12, "bold"), width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="Ajuster", command=self._zoom_fit).pack(side=tk.LEFT, padx=6)
        tk.Button(bar, text="100%",    command=self._zoom_reset).pack(side=tk.LEFT, padx=2)

        self.lbl_zoom = tk.Label(bar, text="100%", width=6, font=("", 9))
        self.lbl_zoom.pack(side=tk.LEFT, padx=8)

        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(frame, bg="#555555", cursor="crosshair")
        sv = tk.Scrollbar(frame, orient=tk.VERTICAL,   command=self.canvas.yview)
        sh = tk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sv.set, xscrollcommand=sh.set)

        sv.pack(side=tk.RIGHT,  fill=tk.Y)
        sh.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>",   self._on_mousewheel)
        self.canvas.bind("<Button-5>",   self._on_mousewheel)
        self.canvas.bind("<Configure>",  lambda e: self._afficher())

    def _rendre_page(self):
        try:
            import fitz
            doc  = fitz.open(self._chemin)
            page = doc[self._page_num]
            mat  = fitz.Matrix(self.DPI_BASE / 72, self.DPI_BASE / 72)
            pix  = page.get_pixmap(matrix=mat, alpha=False)
            data = pix.tobytes("png")
            doc.close()
            self._img_base = Image.open(io.BytesIO(data))
            self._zoom_fit()
        except Exception as e:
            self.canvas.create_text(10, 10, anchor="nw",
                                    text=f"Erreur rendu : {e}", fill="red")

    def _afficher(self):
        if self._img_base is None:
            return
        w = int(self._img_base.width  * self._zoom)
        h = int(self._img_base.height * self._zoom)
        img = self._img_base.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, w, h))
        self.lbl_zoom.config(text=f"{int(self._zoom * 100)}%")

    def _zoom_fit(self):
        if self._img_base is None:
            return
        self.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            cw, ch = 700, 880
        zx = cw / self._img_base.width
        zy = ch / self._img_base.height
        self._zoom = min(zx, zy) * 0.97
        self._afficher()

    def _zoom_in(self):
        self._zoom = min(self._zoom + self.ZOOM_STEP, 6.0)
        self._afficher()

    def _zoom_out(self):
        self._zoom = max(self._zoom - self.ZOOM_STEP, 0.15)
        self._afficher()

    def _zoom_reset(self):
        self._zoom = 1.0
        self._afficher()

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()


# ---------------------------------------------------------------------------
# Dialogue doublon
# ---------------------------------------------------------------------------
class DialogueDoublon(tk.Toplevel):
    """Affiche deux pages ayant le meme nom prevu et demande laquelle conserver."""

    def __init__(self, parent, ligne1, ligne2, nom_fichier: str):
        super().__init__(parent)
        self.title("Doublon detecte")
        self.resizable(False, False)
        self.ligne1 = ligne1
        self.ligne2 = ligne2
        self.choix  = "les_deux"
        self._photos = []
        self._construire(nom_fichier)
        self.grab_set()
        self.focus_set()

    def _construire(self, nom_fichier):
        tk.Label(self, text="Doublon detecte — meme nom de fichier prevu :",
                 font=("", 11, "bold"), fg="#D32F2F").pack(pady=(12, 4))
        tk.Label(self, text=nom_fichier, font=("Consolas", 9), fg="#1565C0",
                 wraplength=500).pack(pady=(0, 10))

        frame = tk.Frame(self)
        frame.pack(padx=16, pady=4)

        for col, ligne in enumerate([self.ligne1, self.ligne2]):
            f = tk.LabelFrame(frame, text=f"Page {ligne.numero}", padx=8, pady=8)
            f.grid(row=0, column=col, padx=12)
            if ligne.miniature_bytes:
                try:
                    img = Image.open(io.BytesIO(ligne.miniature_bytes))
                    img.thumbnail((180, 250))
                    photo = ImageTk.PhotoImage(img)
                    self._photos.append(photo)
                    lbl = tk.Label(f, image=photo, cursor="hand2")
                    lbl.pack()
                    lbl.bind("<Button-1>", lambda e, l=ligne: FenetreApercu(
                        self, l.info_page["chemin_source"],
                        l.info_page["numero"], f"Page {l.numero}"
                    ))
                    tk.Label(f, text="Cliquer pour agrandir",
                             font=("", 8), fg="#666").pack()
                except Exception:
                    tk.Label(f, text="(pas d'apercu)").pack()
            nom_src = Path(ligne.info_page.get("chemin_source", "")).name
            tk.Label(f, text=nom_src, font=("", 8), fg="#444",
                     wraplength=180).pack(pady=(4, 0))

        frame_btn = tk.Frame(self, pady=12)
        frame_btn.pack()
        tk.Button(frame_btn, text=f"Garder page {self.ligne1.numero}",
                  command=lambda: self._choisir("page1"),
                  bg="#1976D2", fg="white", padx=10, pady=6).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btn, text=f"Garder page {self.ligne2.numero}",
                  command=lambda: self._choisir("page2"),
                  bg="#1976D2", fg="white", padx=10, pady=6).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btn, text="Garder les deux",
                  command=lambda: self._choisir("les_deux"),
                  bg="#388E3C", fg="white", padx=10, pady=6).pack(side=tk.LEFT, padx=6)

    def _choisir(self, choix):
        self.choix = choix
        self.destroy()


# ---------------------------------------------------------------------------
# Dialogue document deja traite
# ---------------------------------------------------------------------------
class DialogueDejaTraite(tk.Toplevel):
    """Propose 4 actions quand IntermitDoc reconnait un document deja classe."""

    CHOIX_LABELS = [
        ("ignorer",  "Ignorer",           "#757575", "Ne pas retraiter ce document."),
        ("retraiter","Retraiter (analyse)","#1976D2", "Relancer l'analyse IA complète."),
        ("voir",     "Voir où classé",    "#388E3C", "Ouvrir le dossier de destination."),
        ("reclasser","Classer à nouveau", "#F57C00", "Copier sans relancer l'analyse."),
    ]

    def __init__(self, parent, chemin_source: str, info_traite: dict):
        super().__init__(parent)
        self.title("Document déjà traité")
        self.resizable(False, False)
        self.choix = "ignorer"
        self._construire(chemin_source, info_traite)
        self.grab_set()
        self.focus_set()

    def _construire(self, chemin_source: str, info_traite: dict):
        tk.Label(self, text="Ce document a déjà été traité par IntermitDoc :",
                 font=("", 11, "bold"), fg="#E65100").pack(pady=(14, 4))

        nom = Path(chemin_source).name
        tk.Label(self, text=nom, font=("Consolas", 9), fg="#1565C0",
                 wraplength=480).pack(pady=(0, 6))

        # Infos du traitement précédent
        frame_info = tk.Frame(self, relief=tk.GROOVE, bd=1)
        frame_info.pack(padx=16, pady=4, fill=tk.X)
        infos = [
            ("Traité le",    info_traite.get("date_traitement", "?")),
            ("Type",         info_traite.get("type", "?")),
            ("Employeur",    info_traite.get("employeur", "?")),
            ("Classé dans",  info_traite.get("chemin_destination", "?")),
        ]
        for label, valeur in infos:
            row = tk.Frame(frame_info)
            row.pack(fill=tk.X, padx=8, pady=2)
            tk.Label(row, text=f"{label} :", width=12, anchor="e",
                     font=("", 9, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text=str(valeur), anchor="w", font=("", 9),
                     fg="#333", wraplength=380).pack(side=tk.LEFT, fill=tk.X)

        frame_btn = tk.Frame(self, pady=14)
        frame_btn.pack()
        for val, texte, couleur, _ in self.CHOIX_LABELS:
            tk.Button(frame_btn, text=texte,
                      command=lambda v=val: self._choisir(v),
                      bg=couleur, fg="white", padx=8, pady=6,
                      relief=tk.FLAT).pack(side=tk.LEFT, padx=6)

    def _choisir(self, choix):
        self.choix = choix
        self.destroy()


# ---------------------------------------------------------------------------
# Dialogue d'edition
# ---------------------------------------------------------------------------
class DialogueEdition(tk.Toplevel):

    NOMS_MOIS = {v: k for k, v in MOIS_DOSSIERS.items()}
    LISTE_MOIS = [
        "01 - Janvier", "02 - Fevrier", "03 - Mars",    "04 - Avril",
        "05 - Mai",     "06 - Juin",    "07 - Juillet",  "08 - Aout",
        "09 - Septembre","10 - Octobre","11 - Novembre", "12 - Decembre",
    ]

    def __init__(self, parent, ligne, callback_maj):
        super().__init__(parent)
        self.title(f"Edition -- Page {ligne.numero}")
        self.resizable(False, False)
        self.ligne        = ligne
        self.callback_maj = callback_maj
        self._valide      = False
        self._construire()
        self.grab_set()
        self.focus_set()

    def _construire(self):
        # ── Left panel: PDF preview ──────────────────────────────────────────
        frame_gauche = tk.LabelFrame(self, text="  Aperçu  ", padx=4, pady=4)
        frame_gauche.grid(row=0, column=0, padx=10, pady=10, sticky="n")

        if self.ligne.miniature_bytes:
            try:
                img = Image.open(io.BytesIO(self.ligne.miniature_bytes))
                img.thumbnail((200, 280))
                self._photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(frame_gauche, image=self._photo, cursor="hand2")
                lbl.pack()
                lbl.bind("<Button-1>", lambda e: FenetreApercu(
                    self,
                    self.ligne.info_page["chemin_source"],
                    self.ligne.info_page["numero"],
                    f"Page {self.ligne.numero}"
                ))
                tk.Label(frame_gauche, text="Cliquer pour agrandir",
                         font=TH.FONT_SMALL, fg=TH.TEXT_MUTED).pack()
            except Exception:
                tk.Label(frame_gauche, text="(pas d'aperçu)").pack()

        # ── Right panel: form ────────────────────────────────────────────────
        frame_form = tk.LabelFrame(self, text="  Informations du document  ",
                                   padx=12, pady=8)
        frame_form.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        a   = self.ligne.analyse
        row = 0

        # Type
        tk.Label(frame_form, text="Type :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        self.var_type = tk.StringVar(value=a.get("type", "INCONNU"))
        cb_type = ttk.Combobox(frame_form, textvariable=self.var_type,
                               values=TYPES_DOCUMENTS, state="readonly", width=12)
        cb_type.grid(row=row, column=1, sticky="w", padx=6, pady=3)

        # Confidence badge next to type
        conf   = a.get("confiance", 0)
        if conf >= 0.8:
            conf_txt, conf_fg = f"Confiance : {conf:.0%}  ✓ élevée", TH.SUCCESS
        elif conf >= 0.5:
            conf_txt, conf_fg = f"Confiance : {conf:.0%}  ~ moyenne", TH.WARNING_MED
        else:
            conf_txt, conf_fg = (f"Confiance : {conf:.0%}  ✗ basse", TH.DANGER) if conf else ("", TH.TEXT_MUTED)
        if conf_txt:
            tk.Label(frame_form, text=conf_txt, font=TH.FONT_SMALL,
                     fg=conf_fg).grid(row=row, column=2, sticky="w", padx=4)
        row += 1

        # Annee
        tk.Label(frame_form, text="Année (YYYY) :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        self.var_annee = tk.StringVar(value=a.get("annee", ""))
        tk.Entry(frame_form, textvariable=self.var_annee, width=8).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        row += 1

        # Mois
        tk.Label(frame_form, text="Mois :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        mois_val   = a.get("mois", "")
        mois_label = next((m for m in self.LISTE_MOIS if m.startswith(mois_val)), self.LISTE_MOIS[0])
        self.var_mois = tk.StringVar(value=mois_label)
        ttk.Combobox(frame_form, textvariable=self.var_mois,
                     values=self.LISTE_MOIS, state="readonly", width=18).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        row += 1

        # Date debut
        tk.Label(frame_form, text="Date début (JJ) :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        self.var_debut = tk.StringVar(value=a.get("date_debut", ""))
        tk.Entry(frame_form, textvariable=self.var_debut, width=5).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        row += 1

        # Date fin
        tk.Label(frame_form, text="Date fin (JJ) :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        self.var_fin = tk.StringVar(value=a.get("date_fin", ""))
        tk.Entry(frame_form, textvariable=self.var_fin, width=5).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        row += 1

        # Employeur
        tk.Label(frame_form, text="Employeur :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=3)
        self.var_employeur = tk.StringVar(value=a.get("employeur", ""))
        frame_emp = tk.Frame(frame_form)
        frame_emp.grid(row=row, column=1, columnspan=2, sticky="w", padx=6, pady=3)
        self._employeurs_liste = charger_employeurs()
        self._cb_employeur = ttk.Combobox(
            frame_emp, textvariable=self.var_employeur,
            values=self._employeurs_liste, width=30)
        self._cb_employeur.pack(side=tk.LEFT)
        tk.Button(frame_emp, text="+ Ajouter", width=9, padx=0,
                  command=self._ajouter_employeur,
                  font=TH.FONT_SMALL).pack(side=tk.LEFT, padx=(4, 0))
        row += 1

        # ── AEM-only section (progressive disclosure) ────────────────────────
        # Separator + label visible only when type == AEM
        self._sep_aem = ttk.Separator(frame_form, orient=tk.HORIZONTAL)
        self._sep_aem.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        row += 1

        self._lbl_aem_section = tk.Label(
            frame_form,
            text="Champs spécifiques AEM",
            font=TH.FONT_SMALL,
            fg=TH.TEXT_MUTED,
            anchor="w",
        )
        self._lbl_aem_section.grid(row=row, column=0, columnspan=3,
                                   sticky="w", padx=2, pady=(0, 4))
        row += 1

        # Heures
        self._lbl_heures = tk.Label(frame_form, text="Heures :", anchor="w",
                                    font=TH.FONT_BASE)
        self._lbl_heures.grid(row=row, column=0, sticky="w", pady=3)
        self.var_heures = tk.StringVar(value=a.get("heures", ""))
        self.entry_heures = tk.Entry(frame_form, textvariable=self.var_heures, width=10)
        self.entry_heures.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(frame_form, text="h", font=TH.FONT_BASE,
                 fg=TH.TEXT_SECONDARY).grid(row=row, column=2, sticky="w")
        self.var_heures.trace_add("write", lambda *_: self.entry_heures.config(bg="white"))
        self._row_heures = row
        row += 1

        # Salaire brut
        self._lbl_salaire = tk.Label(frame_form, text="Salaire brut :", anchor="w",
                                     font=TH.FONT_BASE)
        self._lbl_salaire.grid(row=row, column=0, sticky="w", pady=3)
        self.var_salaire = tk.StringVar(value=a.get("salaire_brut", ""))
        self.entry_salaire = tk.Entry(frame_form, textvariable=self.var_salaire, width=12)
        self.entry_salaire.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(frame_form, text="EUR", font=TH.FONT_BASE,
                 fg=TH.TEXT_SECONDARY).grid(row=row, column=2, sticky="w")
        self.var_salaire.trace_add("write", lambda *_: self.entry_salaire.config(bg="white"))
        self._row_salaire = row
        row += 1

        # ── File name preview ────────────────────────────────────────────────
        ttk.Separator(frame_form, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1

        tk.Label(frame_form, text="Nom prévu :", anchor="w",
                 font=TH.FONT_BASE).grid(row=row, column=0, sticky="w", pady=4)
        self.lbl_nom = tk.Label(
            frame_form,
            text=self.ligne.nom_fichier_prevu(),
            font=TH.FONT_MONO,
            fg=TH.PRIMARY_DARK,
            wraplength=380,
            justify="left",
        )
        self.lbl_nom.grid(row=row, column=1, columnspan=2, sticky="w", padx=6)
        row += 1

        # Wire all vars to live-update the filename preview
        for var in (self.var_type, self.var_annee, self.var_mois,
                    self.var_debut, self.var_fin, self.var_employeur,
                    self.var_heures, self.var_salaire):
            var.trace_add("write", self._maj_nom_prevu)

        # Wire type change to show/hide AEM section
        self.var_type.trace_add("write", self._on_type_change)
        self._on_type_change()   # apply initial state

        # ── Action buttons ───────────────────────────────────────────────────
        ttk.Separator(frame_form, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1

        frame_btn = tk.Frame(frame_form)
        frame_btn.grid(row=row, column=0, columnspan=3, pady=4)

        tk.Button(
            frame_btn,
            text="Enregistrer et classifier",
            command=self._enregistrer_et_classifier,
            bg=TH.BTN_SUCCESS[0], fg=TH.BTN_SUCCESS[1],
            padx=10, pady=4,
            font=TH.FONT_LABEL,
            relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            frame_btn,
            text="Enregistrer seulement",
            command=self._enregistrer,
            bg=TH.BTN_PRIMARY[0], fg=TH.BTN_PRIMARY[1],
            padx=10, pady=4,
            relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            frame_btn,
            text="Annuler",
            command=self.destroy,
            padx=10, pady=4,
            relief=tk.FLAT, cursor="hand2",
        ).pack(side=tk.LEFT, padx=4)

    def _on_type_change(self, *_):
        """Show AEM-specific fields only when type == AEM (progressive disclosure)."""
        is_aem = self.var_type.get() == "AEM"
        state  = tk.NORMAL if is_aem else tk.DISABLED

        for widget in (self._lbl_aem_section, self._sep_aem,
                       self._lbl_heures, self.entry_heures,
                       self._lbl_salaire, self.entry_salaire):
            try:
                widget.config(state=state)
            except tk.TclError:
                # ttk.Separator does not accept state= kwarg
                pass

        # Visual hint: dim the label when inactive
        dim_color = TH.TEXT_MUTED if not is_aem else TH.TEXT_PRIMARY
        self._lbl_aem_section.config(
            fg=TH.PRIMARY_DARK if is_aem else TH.TEXT_MUTED,
            text="Champs spécifiques AEM" if is_aem else "Champs AEM (non applicable pour ce type)",
        )
        self._lbl_heures.config(fg=dim_color)
        self._lbl_salaire.config(fg=dim_color)

    def _ajouter_employeur(self):
        """Ajoute un nouvel employeur à la liste après confirmation."""
        nom = self.var_employeur.get().strip()
        if not nom:
            messagebox.showinfo("Saisir un nom",
                "Tapez d'abord le nom de l'employeur dans le champ,\n"
                "puis cliquez ➕ pour l'enregistrer.", parent=self)
            return
        if nom in self._employeurs_liste:
            messagebox.showinfo("Déjà enregistré",
                f'"{nom}" est déjà dans la liste des employeurs.', parent=self)
            return
        if messagebox.askyesno("Ajouter un employeur",
                f'Ajouter "{nom}" à la liste des employeurs ?', parent=self):
            self._employeurs_liste.append(nom)
            self._employeurs_liste.sort()
            sauvegarder_employeurs(self._employeurs_liste)
            self._cb_employeur["values"] = self._employeurs_liste
            messagebox.showinfo("Enregistré",
                f'"{nom}" ajouté à la liste des employeurs.', parent=self)

    def _lire_mois(self) -> str:
        return self.var_mois.get()[:2]

    def _maj_nom_prevu(self, *_):
        a_temp = {
            "type":        self.var_type.get(),
            "annee":       self.var_annee.get().strip(),
            "mois":        self._lire_mois(),
            "date_debut":  self.var_debut.get().strip().zfill(2) if self.var_debut.get().strip() else "",
            "date_fin":    self.var_fin.get().strip().zfill(2)   if self.var_fin.get().strip()   else "",
            "employeur":   self.var_employeur.get().strip(),
            "heures":      self.var_heures.get().strip(),
            "salaire_brut":self.var_salaire.get().strip(),
        }
        self.lbl_nom.config(text=construire_nom_fichier(a_temp))

    def _appliquer(self):
        a = self.ligne.analyse
        a["type"]        = self.var_type.get()
        a["annee"]       = self.var_annee.get().strip()
        a["mois"]        = self._lire_mois()
        a["date_debut"]  = self.var_debut.get().strip().zfill(2) if self.var_debut.get().strip() else ""
        a["date_fin"]    = self.var_fin.get().strip().zfill(2)   if self.var_fin.get().strip()   else ""
        a["employeur"]   = self.var_employeur.get().strip()
        a["heures"]      = self.var_heures.get().strip()
        a["salaire_brut"]= self.var_salaire.get().strip()

    def _enregistrer(self):
        self._appliquer()
        self.callback_maj()
        self.destroy()

    def _enregistrer_et_classifier(self):
        self._appliquer()
        a = self.ligne.analyse

        if a.get("type") == "AEM":
            heures  = a.get("heures",      "").strip()
            salaire = a.get("salaire_brut", "").strip()
            manquant = False
            self.entry_heures.config( bg="#FFCDD2" if not heures  else "white")
            self.entry_salaire.config(bg="#FFCDD2" if not salaire else "white")
            if not heures or not salaire:
                messagebox.showwarning(
                    "Information manquante",
                    "Les champs surlignés en rouge sont obligatoires pour une AEM.",
                    parent=self,
                )
                return
            try:
                if 1 <= float(heures) <= 4:
                    if not messagebox.askyesno(
                        "Heures suspectes",
                        f"{heures}h semble anormalement bas pour une AEM.\n"
                        "Classifier quand même ?",
                        parent=self,
                    ):
                        return
            except ValueError:
                pass

        self.callback_maj(classifier=True)
        self.destroy()


# ---------------------------------------------------------------------------
class LigneTableau:
    def __init__(self, info_page: dict, analyse: dict):
        self.info_page       = info_page
        self.analyse         = dict(analyse)
        self.miniature_bytes = info_page.get("miniature_bytes", b"")
        self.page_pdf_bytes  = info_page.get("page_pdf_bytes", b"")
        self.statut          = "En attente"
        self.chemin_copie    = ""

    @property
    def numero(self) -> int:
        return self.info_page.get("numero", 0) + 1

    def nom_fichier_prevu(self) -> str:
        return construire_nom_fichier(self.analyse)


# ---------------------------------------------------------------------------
class DialogueBoostIA(tk.Toplevel):
    """
    Fenetre de gestion des fournisseurs IA.
    Chaque IA a une case a cocher + panneau de saisie de cle API inline.
    """

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.title("Boost IA — Fournisseurs d'intelligence artificielle")
        self.resizable(False, False)
        self.cfg = cfg
        self._vars_enabled  = {}
        self._vars_key      = {}
        self._vars_modele   = {}
        self._frames_detail = {}
        self._construire()
        self.grab_set()

    def _construire(self):
        tk.Label(
            self,
            text="Activez les IA que vous souhaitez utiliser pour l'analyse.\n"
                 "Quand plusieurs IA sont actives, un vote majoritaire determine le type.",
            fg="#555", font=("", 9), justify="left",
        ).pack(padx=16, pady=(12, 6), anchor="w")

        self._frame_providers = tk.Frame(self)
        self._frame_providers.pack(fill=tk.X, padx=16, pady=4)

        providers = self.cfg.setdefault("ia_providers", {})

        for provider_id, meta in IA_PROVIDERS.items():
            pcfg = providers.setdefault(provider_id, {"enabled": False, "api_key": ""})

            var_en  = tk.BooleanVar(value=pcfg.get("enabled", False))
            var_key = tk.StringVar(value=pcfg.get("api_key", ""))
            var_mod = tk.StringVar(value=pcfg.get("modele", meta["modele"]))
            self._vars_enabled[provider_id] = var_en
            self._vars_key[provider_id]     = var_key
            self._vars_modele[provider_id]  = var_mod

            # Carte par fournisseur
            card = tk.LabelFrame(self._frame_providers, padx=10, pady=6)
            card.pack(fill=tk.X, pady=4)

            # Ligne titre avec checkbox
            row_titre = tk.Frame(card)
            row_titre.pack(fill=tk.X)

            cb = tk.Checkbutton(
                row_titre, text=meta["nom"],
                variable=var_en, font=("", 10, "bold"),
                command=lambda pid=provider_id: self._toggle_detail(pid),
            )
            cb.pack(side=tk.LEFT)

            # Indicateur de statut
            lbl_statut = tk.Label(row_titre, text="", font=("", 9), width=18, anchor="e")
            lbl_statut.pack(side=tk.RIGHT, padx=4)

            # Panneau detail (cle + modele + boutons)
            frame_detail = tk.Frame(card, bg="#F5F5F5", bd=1, relief=tk.GROOVE)
            self._frames_detail[provider_id] = (frame_detail, lbl_statut)

            pad = {"padx": 6, "pady": 3}
            tk.Label(frame_detail, text="Cle API :", bg="#F5F5F5", anchor="w", width=10).grid(
                row=0, column=0, sticky="w", **pad)
            entry_key = tk.Entry(frame_detail, textvariable=var_key, width=52, show="*")
            entry_key.grid(row=0, column=1, sticky="w", **pad)

            tk.Button(
                frame_detail, text="Voir",
                command=lambda e=entry_key: e.config(show="" if e.cget("show") == "*" else "*"),
                width=5,
            ).grid(row=0, column=2, padx=4)

            tk.Label(frame_detail, text="Modele :", bg="#F5F5F5", anchor="w", width=10).grid(
                row=1, column=0, sticky="w", **pad)
            tk.Entry(frame_detail, textvariable=var_mod, width=35).grid(
                row=1, column=1, sticky="w", **pad)

            tk.Button(
                frame_detail, text="Tester la connexion",
                command=lambda pid=provider_id, ls=lbl_statut: self._tester(pid, ls),
                bg="#1976D2", fg="white", padx=8,
            ).grid(row=2, column=1, sticky="w", padx=6, pady=4)

            # Afficher le panneau si deja active ou cle presente
            if var_en.get() or var_key.get():
                frame_detail.pack(fill=tk.X, pady=(4, 0))

        # Boutons du bas
        frame_btn = tk.Frame(self)
        frame_btn.pack(pady=10)
        tk.Button(frame_btn, text="Enregistrer",
                  command=self._sauvegarder,
                  bg="#388E3C", fg="white", padx=12, pady=4,
                  font=("", 9, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btn, text="Annuler",
                  command=self.destroy, padx=12, pady=4).pack(side=tk.LEFT, padx=6)

    def _toggle_detail(self, provider_id: str):
        frame_detail, _ = self._frames_detail[provider_id]
        if self._vars_enabled[provider_id].get():
            frame_detail.pack(fill=tk.X, pady=(4, 0))
        else:
            frame_detail.pack_forget()

    def _tester(self, provider_id: str, lbl_statut: tk.Label):
        cle = self._vars_key[provider_id].get().strip()
        if not cle:
            lbl_statut.config(text="Cle manquante", fg="#D32F2F")
            return
        lbl_statut.config(text="Test en cours...", fg="#1565C0")
        self.update_idletasks()

        def _run():
            ok, msg = tester_connexion_ia(provider_id, cle, charger_config())
            def _maj():
                if ok:
                    lbl_statut.config(text="✓ Connexion OK", fg="#2E7D32")
                else:
                    lbl_statut.config(text="✗ Erreur", fg="#D32F2F")
                    DialogueRapport.afficher(self, "Erreur de connexion",
                                             f"{IA_PROVIDERS[provider_id]['nom']} :\n{msg}")
            self.after(0, _maj)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _sauvegarder(self):
        providers = self.cfg.setdefault("ia_providers", {})
        for pid in IA_PROVIDERS:
            providers.setdefault(pid, {})
            providers[pid]["enabled"] = self._vars_enabled[pid].get()
            providers[pid]["api_key"] = self._vars_key[pid].get().strip()
            providers[pid]["modele"]  = self._vars_modele[pid].get().strip()

        # Sync cle Claude principale
        cle_claude = providers.get("claude", {}).get("api_key", "")
        if cle_claude:
            self.cfg["api_key"] = cle_claude

        sauvegarder_config(self.cfg)
        self.destroy()


class DialogueParametres(tk.Toplevel):

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.title("Parametres")
        self.resizable(False, False)
        self.cfg = dict(cfg)
        self._construire()
        self.grab_set()

    def _construire(self):
        pad = {"padx": 8, "pady": 4}

        tk.Label(self, text="Chemin Tesseract :").grid(row=0, column=0, sticky="w", **pad)
        self.var_tess = tk.StringVar(value=self.cfg.get("tesseract_path", ""))
        tk.Entry(self, textvariable=self.var_tess, width=50).grid(row=0, column=1, **pad)

        tk.Label(self, text="Dossier de base :").grid(row=1, column=0, sticky="w", **pad)
        self.var_base = tk.StringVar(value=self.cfg.get("dossier_base", ""))
        frame_base = tk.Frame(self)
        frame_base.grid(row=1, column=1, **pad)
        tk.Entry(frame_base, textvariable=self.var_base, width=40).pack(side=tk.LEFT)
        tk.Button(frame_base, text="...", command=self._choisir_dossier).pack(side=tk.LEFT, padx=4)

        # Détection dossiers cloud (OneDrive / Google Drive / Dropbox)
        dossiers_cloud = self._detecter_dossiers_cloud()
        if dossiers_cloud:
            frame_cloud = tk.Frame(self)
            frame_cloud.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
            tk.Label(frame_cloud, text="☁ Synchro cloud détectée :",
                     font=("", 8, "bold"), fg="#1565C0").pack(side=tk.LEFT)
            for nom, chemin in dossiers_cloud:
                tk.Button(frame_cloud, text=f"Utiliser {nom}",
                          font=("", 8),
                          command=lambda c=chemin: self._utiliser_dossier_cloud(c)
                          ).pack(side=tk.LEFT, padx=4)

        tk.Label(self, text="Langue OCR :").grid(row=3, column=0, sticky="w", **pad)
        self.var_lang = tk.StringVar(value=self.cfg.get("langue_ocr", "fra+eng"))
        tk.Entry(self, textvariable=self.var_lang, width=20).grid(row=3, column=1, sticky="w", **pad)

        # Annexe intermittent
        tk.Label(self, text="Annexe intermittent :").grid(row=4, column=0, sticky="w", **pad)
        self.var_annexe = tk.StringVar(value=self.cfg.get("annexe", ""))
        frame_annexe = tk.Frame(self)
        frame_annexe.grid(row=4, column=1, sticky="w", **pad)
        for val, label in [("8", "Annexe 8 (Technicien)"),
                            ("10", "Annexe 10 (Artiste)"),
                            ("8+10", "Les deux")]:
            tk.Radiobutton(frame_annexe, text=label,
                           variable=self.var_annexe, value=val).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_annexe, text="Changer...",
                  command=self._changer_annexe,
                  font=("", 8)).pack(side=tk.LEFT, padx=8)

        tk.Label(self, text="Date anniversaire :").grid(row=5, column=0, sticky="w", **pad)
        self.var_date_ann = tk.StringVar(value=self.cfg.get("date_anniversaire", ""))
        frame_ann = tk.Frame(self)
        frame_ann.grid(row=5, column=1, sticky="w", **pad)
        tk.Entry(frame_ann, textvariable=self.var_date_ann, width=8).pack(side=tk.LEFT)
        tk.Label(frame_ann, text="format JJ/MM  (ex: 15/09)", font=("", 8),
                 fg="#666").pack(side=tk.LEFT, padx=6)

        tk.Label(self, text="Abattement net (onglet Revenus) :").grid(
            row=6, column=0, sticky="w", **pad)
        self.var_taux_net = tk.StringVar(
            value=str(self.cfg.get("taux_abattement_net", 10.0)))
        frame_taux = tk.Frame(self)
        frame_taux.grid(row=6, column=1, sticky="w", **pad)
        tk.Entry(frame_taux, textvariable=self.var_taux_net, width=6).pack(side=tk.LEFT)
        tk.Label(frame_taux, text="%", font=("", 8), fg="#666").pack(side=tk.LEFT, padx=4)

        frame_btn = tk.Frame(self)
        frame_btn.grid(row=7, column=0, columnspan=2, pady=8)
        tk.Button(frame_btn, text="🤖 Boost IA...", bg="#5E35B1", fg="white",
                  command=self._ouvrir_boost_ia).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="📅 Agenda...", bg="#00838F", fg="white",
                  command=self._ouvrir_dialogue_agenda).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="Enregistrer", command=self._sauvegarder).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="Annuler",     command=self.destroy).pack(side=tk.LEFT, padx=4)

    def _ouvrir_dialogue_agenda(self):
        dlg = _DialogueAgenda(self)
        self.wait_window(dlg)

    def _ouvrir_boost_ia(self):
        dlg = DialogueBoostIA(self, self.cfg)
        self.wait_window(dlg)
        self.cfg = charger_config()

    def _choisir_dossier(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            self.var_base.set(d)

    @staticmethod
    def _detecter_dossiers_cloud() -> list:
        """Détecte les dossiers de synchro cloud courants présents sur la machine."""
        home = Path.home()
        candidats = [
            ("OneDrive",     home / "OneDrive"),
            ("Google Drive", home / "Google Drive"),
            ("Google Drive", home / "GoogleDrive"),
            ("Dropbox",      home / "Dropbox"),
        ]
        trouves = []
        noms_vus = set()
        for nom, chemin in candidats:
            if chemin.is_dir() and nom not in noms_vus:
                trouves.append((nom, str(chemin / "IntermitDoc")))
                noms_vus.add(nom)
        return trouves

    def _utiliser_dossier_cloud(self, chemin: str):
        Path(chemin).mkdir(parents=True, exist_ok=True)
        self.var_base.set(chemin)

    def _changer_annexe(self):
        dlg = DialogueBienvenue(self)
        self.wait_window(dlg)
        if dlg.annexe_choisie:
            self.var_annexe.set(dlg.annexe_choisie)

    def _sauvegarder(self):
        self.cfg["tesseract_path"]   = self.var_tess.get().strip()
        self.cfg["dossier_base"]     = self.var_base.get().strip()
        self.cfg["langue_ocr"]       = self.var_lang.get().strip()
        self.cfg["annexe"]           = self.var_annexe.get().strip()
        self.cfg["date_anniversaire"] = self.var_date_ann.get().strip()
        try:
            self.cfg["taux_abattement_net"] = float(self.var_taux_net.get().strip().replace(",", "."))
        except ValueError:
            pass
        sauvegarder_config(self.cfg)
        try:
            self.master._maj_titre()
        except Exception:
            pass
        self.destroy()


# ---------------------------------------------------------------------------
class DialogueSauvegarde(tk.Toplevel):
    """Conseils pratiques pour sauvegarder ses documents et données IntermitDoc."""

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.title("Conseils de sauvegarde")
        self.geometry("620x560")
        self.minsize(560, 480)
        self.cfg = cfg
        self._construire()
        self.grab_set()

    def _construire(self):
        hdr = tk.Frame(self, bg="#1565C0")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="💾  Conseils de sauvegarde", bg="#1565C0", fg="white",
                 font=("", 13, "bold"), pady=10).pack(padx=14, anchor="w")

        # Zone scrollable
        frame_scroll = tk.Frame(self)
        frame_scroll.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        canvas = tk.Canvas(frame_scroll, highlightthickness=0)
        scroll = tk.Scrollbar(frame_scroll, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def section(titre: str, couleur: str = "#1565C0"):
            tk.Label(inner, text=titre, font=("", 10, "bold"), fg=couleur,
                     anchor="w").pack(fill=tk.X, padx=14, pady=(14, 2))

        def texte(txt: str):
            tk.Label(inner, text=txt, font=("", 9), fg="#333", justify="left",
                     anchor="w", wraplength=560).pack(fill=tk.X, padx=14, pady=1)

        section("Pourquoi sauvegarder ?", "#C62828")
        texte(
            "Vos PDF classés (AEM, bulletins de paie, contrats) sont vos seules preuves "
            "en cas de litige ou de contrôle sur vos droits ARE. Une panne de disque dur "
            "sans sauvegarde peut vous faire perdre des années de justificatifs."
        )

        section("Méthode recommandée : synchro cloud automatique")
        texte(
            "Installez l'application de bureau de votre service cloud (Google Drive, "
            "OneDrive ou Dropbox) et configurez-la pour synchroniser votre dossier de "
            "classement en continu. Une fois configuré, chaque document classé par "
            "IntermitDoc se sauvegarde automatiquement, sans action de votre part."
        )
        texte(
            "1. Installez l'app de synchro (ex. drive.google.com/drive/download)\n"
            "2. Choisissez ou déplacez votre dossier de classement à l'intérieur du "
            "dossier synchronisé (ex. Google Drive/document pro/intermitent)\n"
            "3. Dans Outils → Paramètres, mettez à jour le Dossier de base vers ce "
            "nouvel emplacement"
        )

        dossiers_cloud = DialogueParametres._detecter_dossiers_cloud()
        if dossiers_cloud:
            section("☁ Synchro détectée sur cette machine", "#2E7D32")
            for nom, chemin in dossiers_cloud:
                texte(f"• {nom} : {chemin}")

        section("Vos PDF classés sont doublement protégés", "#2E7D32")
        texte(
            "Dès qu'un document a été traité une fois, IntermitDoc peut retrouver "
            "toutes ses infos (type, dates, employeur, heures, salaire) rien qu'en "
            "regardant vos dossiers — de deux façons indépendantes :"
        )
        texte(
            "1. Le nom du fichier lui-même (ex. [AEM] 2026-07-18 LA VOUIVRE 6h "
            "140EUR.pdf)\n"
            "2. Des métadonnées écrites à l'intérieur du PDF (invisibles à l'oeil, "
            "lues automatiquement par l'onglet Scan & Déplacement)"
        )
        texte(
            "Résultat concret : si vous restaurez juste vos PDF classés dans la bonne "
            "arborescence après un changement de PC (même sans %APPDATA%), Suivi, "
            "Récapitulatif et Historique retrouvent tout tout seuls au prochain "
            "Actualiser — même si un fichier a été renommé, l'onglet Scan le "
            "retrouve grâce à sa métadonnée interne."
        )

        section("Ce qui N'EST PAS récupérable automatiquement", "#C62828")
        texte(
            "Vos contrats prévisionnels (⏳ engagements futurs saisis à l'avance) "
            "n'ont PAS de PDF associé — ils n'existent que dans un fichier "
            "previsionnels.json. S'il est perdu, ils sont perdus pour de bon et "
            "devront être ressaisis à la main. C'est le seul élément vraiment "
            "irremplaçable de l'application."
        )

        section("Le reste de vos données (confort, pas critique)")
        texte(
            "Votre liste d'employeurs, votre clé API et l'historique anti-doublons "
            "sont stockés dans :\n%APPDATA%\\IntermitDoc\\\n(config.json, "
            "employeurs.json, traites.json, previsionnels.json)\n\n"
            "Ces fichiers ne sont PAS synchronisés automatiquement avec vos PDF. "
            "Sauvegardez au minimum previsionnels.json (voir ci-dessus) ; les "
            "autres accélèrent juste le travail au quotidien mais ne font pas "
            "perdre vos justificatifs s'ils manquent."
        )
        texte(
            "⚠ config.json contient votre clé API en clair — ne la mettez jamais sur "
            "un espace partagé ou public, uniquement sur votre propre cloud privé."
        )

        section("Bonnes pratiques")
        texte(
            "• Gardez toujours au moins 2 copies sur 2 supports différents "
            "(ex. disque local + cloud)\n"
            "• Vérifiez de temps en temps que la synchro fonctionne bien (pas d'icône "
            "d'erreur sur le dossier)\n"
            "• Avant de changer de PC, faites une copie manuelle complète en plus de "
            "la synchro automatique"
        )

        frame_btn = tk.Frame(self)
        frame_btn.pack(fill=tk.X, padx=10, pady=8)
        tk.Button(frame_btn, text="📁 Ouvrir mon dossier de classement",
                  command=self._ouvrir_dossier_base).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="Fermer", command=self.destroy).pack(side=tk.RIGHT, padx=4)

    def _ouvrir_dossier_base(self):
        dossier = self.cfg.get("dossier_base", "").strip()
        if dossier and Path(dossier).is_dir():
            import subprocess
            subprocess.Popen(["explorer", dossier])
        else:
            messagebox.showwarning(
                "Dossier introuvable",
                "Configurez d'abord votre dossier de classement dans Outils → Paramètres.",
                parent=self)


# ---------------------------------------------------------------------------
class TableauPages(tk.Frame):

    COLONNES = [
        ("num",         "#",             35),
        ("type",        "Type",          70),
        ("annee",       "Annee",         55),
        ("mois",        "Mois",          45),
        ("dates",       "Dates",         90),
        ("employeur",   "Employeur",    180),
        ("confiance",   "Conf.",         50),
        ("nom_fichier", "Nom de fichier",310),
        ("statut",      "Statut",        90),
        ("actions",     "Actions",       80),
    ]

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app    = app
        self.lignes: list[LigneTableau] = []
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._items:  dict[str, int] = {}
        self._widget_edition = None
        self._construire()

    def _construire(self):
        scroll_v = tk.Scrollbar(self, orient=tk.VERTICAL)
        scroll_h = tk.Scrollbar(self, orient=tk.HORIZONTAL)

        # Style dédié : la ligne doit être assez haute pour la miniature
        # (voir _creer_photo) — sinon l'image déborde sur les lignes
        # suivantes et donne une impression d'empilement illisible.
        style = ttk.Style()
        style.configure("Apercu.Treeview", rowheight=100)

        self.tree = ttk.Treeview(
            self,
            columns=[c[0] for c in self.COLONNES],
            show="tree headings",
            yscrollcommand=scroll_v.set,
            xscrollcommand=scroll_h.set,
            height=14,
            selectmode="browse",
            style="Apercu.Treeview",
        )
        scroll_v.config(command=self.tree.yview)
        scroll_h.config(command=self.tree.xview)

        self.tree.column("#0", width=90, minwidth=80, stretch=False)
        self.tree.heading("#0", text="Apercu  (clic)")

        for col_id, col_titre, col_larg in self.COLONNES:
            self.tree.column(col_id, width=col_larg, minwidth=30,
                             stretch=(col_id == "nom_fichier"))
            self.tree.heading(col_id, text=col_titre)

        self.tree.tag_configure("conf_haute",      background=COULEURS_CONFIANCE["haute"])
        self.tree.tag_configure("conf_moyenne",    background=COULEURS_CONFIANCE["moyenne"])
        self.tree.tag_configure("conf_basse",      background=COULEURS_CONFIANCE["basse"])
        self.tree.tag_configure("statut_ok",       background=COULEUR_OK)
        self.tree.tag_configure("statut_err",      background=COULEUR_ERR)
        self.tree.tag_configure("statut_fallback", background="#FFE0B2")
        self.tree.tag_configure("statut_ignore",   background="#E0E0E0", foreground="#9E9E9E")
        self.tree.tag_configure("aem_incomplet",   background="#FFCDD2")

        self.tree.bind("<Button-1>", self._on_clic)
        self.tree.bind("<Double-1>", self._on_double_clic)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")
        scroll_h.grid(row=1, column=0, sticky="ew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Tri par clic sur les en-têtes (sauf Apercu, num et actions)
        cols_triables = [c[0] for c in self.COLONNES
                         if c[0] not in ("num", "actions")]
        self._tri = _installer_tri(self.tree, cols_triables)

    def vider(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lignes.clear()
        self._photos.clear()
        self._items.clear()

    def ajouter_ligne(self, ligne: LigneTableau):
        idx   = len(self.lignes)
        self.lignes.append(ligne)
        photo = self._creer_photo(ligne.miniature_bytes)
        if photo:
            self._photos[idx] = photo
        tag     = self._tag_confiance(ligne.analyse.get("confiance", 0))
        item_id = self.tree.insert(
            "", tk.END,
            image=photo if photo else "",
            values=self._valeurs_ligne(ligne),
            tags=(tag,)
        )
        self._items[item_id] = idx

    def mettre_a_jour_ligne(self, idx: int):
        if idx >= len(self.lignes):
            return
        ligne = self.lignes[idx]
        items = self.tree.get_children()
        if idx < len(items):
            item_id = items[idx]
            tag = self._tag_confiance(ligne.analyse.get("confiance", 0))
            if ligne.statut == "Copie":
                tag = "statut_ok"
            elif ligne.statut == "Non classe":
                tag = "statut_fallback"
            elif ligne.statut in ("Ignore (doublon)", "Info manquante"):
                tag = "statut_ignore"
            elif ligne.statut.startswith("Erreur"):
                tag = "statut_err"
            self.tree.item(item_id, values=self._valeurs_ligne(ligne), tags=(tag,))

    def _valeurs_ligne(self, ligne: LigneTableau) -> tuple:
        a  = ligne.analyse
        d1 = a.get("date_debut", "")
        d2 = a.get("date_fin", "")
        if d1 and d2 and d1 != d2:
            dates = f"{d1} au {d2}"
        elif d1:
            dates = d1
        else:
            dates = ""
        conf     = a.get("confiance", 0)
        conf_str = f"{conf:.0%}" if conf else "-"
        return (
            ligne.numero,
            a.get("type",      "-"),
            a.get("annee",     "-"),
            a.get("mois",      "-"),
            dates,
            a.get("employeur", "-"),
            conf_str,
            ligne.nom_fichier_prevu(),
            ligne.statut,
            "[ Editer ]",
        )

    def _creer_photo(self, data: bytes):
        if not data:
            return None
        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((80, 92))  # tient dans rowheight=100 (style Apercu.Treeview)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _tag_confiance(self, confiance: float) -> str:
        if confiance >= 0.8:
            return "conf_haute"
        elif confiance >= 0.5:
            return "conf_moyenne"
        return "conf_basse"

    def _idx_depuis_event(self, event) -> int | None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None
        return self._items.get(item_id)

    def _on_clic(self, event):
        if self._widget_edition:
            self._widget_edition.destroy()
            self._widget_edition = None

        region  = self.tree.identify("region", event.x, event.y)
        col_id  = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        idx     = self._items.get(item_id) if item_id else None
        if idx is None:
            return

        ligne = self.lignes[idx]

        if col_id == "#0" and region in ("tree", "cell"):
            FenetreApercu(
                self,
                ligne.info_page["chemin_source"],
                ligne.info_page["numero"],
                f"Page {ligne.numero}"
            )
            return

        if col_id == "#10":
            self._ouvrir_edition(idx)

    def _on_double_clic(self, event):
        region  = self.tree.identify("region", event.x, event.y)
        item_id = self.tree.identify_row(event.y)
        if region not in ("cell", "tree") or not item_id:
            return
        idx = self._items.get(item_id)
        if idx is not None:
            self._ouvrir_edition(idx)

    def _ouvrir_edition(self, idx: int):
        ligne = self.lignes[idx]

        def callback_maj(classifier=False):
            self.mettre_a_jour_ligne(idx)
            if classifier:
                self.app._classifier_ligne(idx)

        DialogueEdition(self, ligne, callback_maj)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Suivi intermittent — parseurs et calculs
# ---------------------------------------------------------------------------
_RE_TOUT_DOC = re.compile(
    r'^\[([A-Z]+)\]\s+'
    r'(\d{4}-\d{2}-\d{2})(?:_(\d{2}|\d{4}-\d{2}-\d{2}))?'   # date_debut + optional _fin (jour, ou date complete si chevauche 2 mois)
    r'\s+(.*?)'                              # employeur
    r'(?:\s+(\d+(?:\.\d+)?)h)?'             # heures (optionnel)
    r'(?:\s+(\d+(?:\.\d+)?)EUR)?'           # salaire (optionnel)
    r'\.pdf$',
    re.IGNORECASE
)


def _parser_nom_doc(nom: str) -> dict | None:
    """Parse un nom de fichier IntermitDoc de n'importe quel type."""
    m = _RE_TOUT_DOC.match(nom)
    if not m:
        return None
    type_doc   = m.group(1).upper()
    date_debut = m.group(2)
    fin_brut   = m.group(3)
    employeur  = m.group(4).strip()
    heures     = m.group(5) or ""
    salaire    = m.group(6) or ""
    if fin_brut and len(fin_brut) == 10:
        # Contrat chevauchant deux mois (ex: AEM) : date complete deja fournie
        date_fin = fin_brut
    else:
        date_fin = f"{date_debut[:7]}-{fin_brut.zfill(2)}" if fin_brut else date_debut
    # annee/mois = mois de classement = celui de date_fin (coincide toujours
    # avec le dossier physique, meme si date_debut est dans le mois d'avant)
    return {
        "nom":        nom,
        "type":       type_doc,
        "annee":      date_fin[:4],
        "mois":       date_fin[5:7],
        "date_debut": date_debut,
        "date_fin":   date_fin,
        "employeur":  employeur,
        "heures":     heures,
        "salaire":    salaire,
    }


def _scanner_tous_docs(dossier_base: str) -> list:
    """Scanne récursivement le dossier et retourne tous les docs classifiés."""
    base = Path(dossier_base)
    if not base.is_dir():
        return []
    vus = {}
    for f in sorted(base.rglob("*.pdf")):
        if f.name in vus:
            continue
        info = _parser_nom_doc(f.name)
        if info:
            info["chemin"] = str(f)
            vus[f.name] = info
    return sorted(vus.values(), key=lambda x: x["date_debut"])


# Au-delà de ce montant brut (réel + prévisionnel) sur la période, l'utilisateur
# considère que déclarer en intermittent n'est plus rentable pour lui.
SEUIL_SALAIRE_RENTABLE = 14400


def _calculer_stats(docs: list, date_debut_str: str, date_fin_str: str,
                    annexe: str = "8") -> dict:
    """
    Filtre les docs sur la période et calcule heures, salaires, SJR, employeurs.
    Seuls les AEM comptent pour les heures ; AEM + BP pour les salaires.
    `annexe` : "8", "10" ou "8+10" — pilote la formule d'allocation journalière.
    """
    try:
        d_debut = _date_today.fromisoformat(date_debut_str)
        d_fin   = _date_today.fromisoformat(date_fin_str)
    except ValueError:
        return {}

    docs_periode = [
        d for d in docs
        if d.get("date_debut", "") >= date_debut_str
        and d.get("date_fin",   "") <= date_fin_str
    ]

    total_heures  = 0.0
    total_salaire = 0.0
    employeurs    = set()
    docs_aem = []
    docs_bp  = []

    for d in docs_periode:
        emp = d.get("employeur", "")
        if emp:
            employeurs.add(emp)
        if d["type"] == "AEM":
            docs_aem.append(d)
            try:
                total_heures  += float(d["heures"])
            except (ValueError, TypeError):
                pass
            try:
                total_salaire += float(d["salaire"])
            except (ValueError, TypeError):
                pass
        elif d["type"] == "BP":
            docs_bp.append(d)
            try:
                total_salaire += float(d["salaire"])
            except (ValueError, TypeError):
                pass

    # SJR = salaire brut total / jours calendaires de la période
    nb_jours = max(1, (d_fin - d_debut).days + 1)
    sjr = total_salaire / nb_jours if total_salaire else 0.0

    # Estimation allocation journalière : formule officielle intermittents
    # A+B+C — alignée sur DialogueCalculARE et tauxintermittent.net.
    # Pour "8+10" on calcule les deux annexes et on retient la plus favorable
    # (le détail par annexe reste visible dans le dialogue Calculer ARE).
    if total_heures or total_salaire:
        annexes = ["8", "10"] if annexe == "8+10" else \
                  [annexe if annexe in ("8", "10") else "8"]
        aj_estime = max(
            DialogueCalculARE._calc_aj_brute(
                total_heures, total_salaire, ann,
                DialogueCalculARE.ANNEXE_PARAMS[ann],
                DialogueCalculARE.AJ_MIN, DialogueCalculARE.PLAFOND_AJ)[0]
            for ann in annexes
        )
    else:
        aj_estime = 0.0

    return {
        "docs_periode":    docs_periode,
        "nb_docs":         len(docs_periode),
        "total_heures":    total_heures,
        "total_salaire":   total_salaire,
        "manquantes":      max(0.0, 507 - total_heures),
        "pct_507":         min(1.0, total_heures / 507),
        "pct_720":         min(1.0, total_heures / 720),
        "pct_salaire":     min(1.0, total_salaire / SEUIL_SALAIRE_RENTABLE),
        "employeurs":      sorted(employeurs),
        "nb_employeurs":   len(employeurs),
        "sjr":             sjr,
        "aj_estime":       aj_estime,
        "nb_jours":        nb_jours,
        "droits_ouverts":  total_heures >= 507,
    }


def _generer_pdf_bilan(chemin_dest: str, stats: dict,
                        date_debut_str: str, date_fin_str: str) -> None:
    """Génère un PDF bilan avec PyMuPDF (déjà disponible dans l'exe)."""
    import fitz

    BLEU  = (0.098, 0.376, 0.753)
    BLANC = (1, 1, 1)
    NOIR  = (0, 0, 0)
    GRIS  = (0.95, 0.95, 0.95)
    VERT  = (0.082, 0.537, 0.231)
    ROUGE = (0.8, 0.1, 0.1)

    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # — En-tête —
    page.draw_rect(fitz.Rect(0, 0, 595, 70), color=BLEU, fill=BLEU)
    page.insert_text((30, 44), "BILAN INTERMITTENT DU SPECTACLE", fontsize=17,
                     color=BLANC, fontname="helv")
    page.insert_text((30, 62), f"IntermitDoc — généré le {_date_today.today().strftime('%d/%m/%Y')}",
                     fontsize=9, color=(0.8, 0.9, 1.0), fontname="helv")

    y = 90

    def ligne(texte, taille=10, couleur=NOIR, gras=False, indent=30):
        nonlocal y
        fn = "helvB" if gras else "helv"
        page.insert_text((indent, y), texte, fontsize=taille, color=couleur, fontname=fn)
        y += taille + 5

    def separateur(couleur=BLEU):
        nonlocal y
        page.draw_line((30, y), (565, y), color=couleur, width=0.5)
        y += 8

    # — Période —
    ligne(f"Période de référence : {date_debut_str}  →  {date_fin_str}",
          taille=10, couleur=BLEU, gras=True)
    y += 4
    separateur()

    # — Progression heures (507h seuil / 720h max) —
    ligne("PROGRESSION HEURES  (seuil : 507h — cible : 720h)", taille=11, gras=True)
    y += 2

    barre_x, barre_w, barre_h = 30, 535, 20
    # Fond
    page.draw_rect(fitz.Rect(barre_x, y, barre_x+barre_w, y+barre_h),
                   color=(0.85, 0.85, 0.85), fill=(0.85, 0.85, 0.85))
    # Remplissage (échelle = 720h)
    pct_720 = stats.get("pct_720", 0)
    fill_w_h = int(barre_w * pct_720)
    fill_col_h = VERT if stats.get("droits_ouverts") else BLEU
    if fill_w_h > 0:
        page.draw_rect(fitz.Rect(barre_x, y, barre_x+fill_w_h, y+barre_h),
                       color=fill_col_h, fill=fill_col_h)
    # Marqueur 507h (rouge pointillé)
    x_507 = barre_x + int(barre_w * 507/720)
    page.draw_line((x_507, y-3), (x_507, y+barre_h+3), color=ROUGE, width=1.5)
    page.insert_text((x_507-8, y+barre_h+9), "507h", fontsize=7, color=ROUGE, fontname="helv")
    # Marqueur 720h (orange)
    page.insert_text((barre_x+barre_w-14, y+barre_h+9), "720h", fontsize=7,
                     color=(0.9, 0.4, 0), fontname="helv")
    # Valeur
    h_txt = f"{stats.get('total_heures', 0):.0f}h  ({pct_720*100:.0f}% des 720h)"
    page.insert_text((barre_x+barre_w//2-50, y+14), h_txt,
                     fontsize=9, color=BLANC, fontname="helvB")
    y += barre_h + 18

    # — Progression salaire (cible 14 400 €) —
    ligne("PROGRESSION SALAIRE BRUT  (cible : 14 400 €)", taille=11, gras=True)
    y += 2

    VIOLET = (0.48, 0.10, 0.55)
    page.draw_rect(fitz.Rect(barre_x, y, barre_x+barre_w, y+barre_h),
                   color=(0.85, 0.85, 0.85), fill=(0.85, 0.85, 0.85))
    pct_sal = stats.get("pct_salaire", 0)
    fill_w_s = int(barre_w * pct_sal)
    if fill_w_s > 0:
        page.draw_rect(fitz.Rect(barre_x, y, barre_x+fill_w_s, y+barre_h),
                       color=VIOLET, fill=VIOLET)
    page.insert_text((barre_x+barre_w-22, y+barre_h+9), "14 400€", fontsize=7,
                     color=(0.9, 0.4, 0), fontname="helv")
    s_txt = f"{stats.get('total_salaire', 0):.0f} €  ({pct_sal*100:.0f}% des 14 400 €)"
    page.insert_text((barre_x+barre_w//2-55, y+14), s_txt,
                     fontsize=9, color=BLANC, fontname="helvB")
    y += barre_h + 18

    statut = "DROITS OUVERTS" if stats.get("droits_ouverts") else \
             f"{stats.get('manquantes', 0):.0f}h manquantes pour ouvrir les droits"
    statut_col = VERT if stats.get("droits_ouverts") else ROUGE
    ligne(statut, taille=11, couleur=statut_col, gras=True)
    y += 4
    separateur()

    # — Chiffres clés —
    ligne("CHIFFRES CLÉS", taille=11, gras=True)
    y += 2
    chiffres = [
        ("Heures travaillées",     f"{stats.get('total_heures', 0):.1f} h"),
        ("Salaire brut total",     f"{stats.get('total_salaire', 0):.2f} EUR"),
        ("Nombre de contrats AEM", str(len([d for d in stats.get('docs_periode', []) if d['type']=='AEM']))),
        ("Employeurs différents",  str(stats.get('nb_employeurs', 0))),
        ("Jours calendaires",      str(stats.get('nb_jours', 0))),
        ("SJR estimé",             f"{stats.get('sjr', 0):.2f} EUR/jour"),
        ("Allocation estimée",     f"~{stats.get('aj_estime', 0):.2f} EUR/jour"),
    ]
    for label, val in chiffres:
        page.draw_rect(fitz.Rect(30, y-10, 565, y+4), color=GRIS, fill=GRIS)
        page.insert_text((34, y),  label, fontsize=9.5, color=NOIR, fontname="helv")
        page.insert_text((380, y), val,   fontsize=9.5, color=BLEU, fontname="helvB")
        y += 18

    y += 4
    separateur()

    # — Employeurs —
    ligne("EMPLOYEURS SUR LA PÉRIODE", taille=11, gras=True)
    y += 2
    for emp in stats.get("employeurs", []):
        ligne(f"• {emp}", taille=9.5, indent=40)

    y += 4
    separateur()

    # — Tableau des contrats —
    ligne("DÉTAIL DES CONTRATS", taille=11, gras=True)
    y += 4

    col_x = [30, 100, 170, 290, 400, 470]
    entetes = ["Type", "Début", "Fin", "Employeur", "Heures", "Salaire"]
    page.draw_rect(fitz.Rect(30, y-10, 565, y+4), color=BLEU, fill=BLEU)
    for cx, ent in zip(col_x, entetes):
        page.insert_text((cx, y), ent, fontsize=8.5, color=BLANC, fontname="helvB")
    y += 14

    for i, d in enumerate(stats.get("docs_periode", [])):
        if y > 800:  # sécurité : nouvelle page si débordement
            page = doc.new_page(width=595, height=842)
            y = 40
        bg = GRIS if i % 2 == 0 else BLANC
        page.draw_rect(fitz.Rect(30, y-9, 565, y+5), color=bg, fill=bg)
        vals = [d["type"], d["date_debut"], d["date_fin"],
                d["employeur"][:20], f"{d['heures']}h" if d['heures'] else "-",
                f"{d['salaire']} EUR" if d['salaire'] else "-"]
        for cx, v in zip(col_x, vals):
            page.insert_text((cx, y), str(v), fontsize=8, color=NOIR, fontname="helv")
        y += 14

    # — Note légale —
    y += 10
    separateur((0.7, 0.7, 0.7))
    ligne("Note : les calculs SJR et allocation sont des estimations. "
          "Seul France Travail peut déterminer vos droits exacts.",
          taille=7.5, couleur=(0.5, 0.5, 0.5))

    doc.save(chemin_dest)
    doc.close()


# Onglet Calcul — lecture des AEM depuis un dossier, totaux, total.txt
# ---------------------------------------------------------------------------
_RE_AEM = re.compile(
    r'^\[AEM\]\s+'
    r'(\d{4}-\d{2}-\d{2}(?:_\d{2})?)'          # date
    r'\s+(.*?)'                                   # employeur
    r'(?:\s+(\d+(?:\.\d+)?)h)?'                  # heures (optionnel)
    r'(?:\s+(\d+(?:\.\d+)?)EUR)?'                # salaire (optionnel)
    r'\.pdf$',
    re.IGNORECASE
)


def _scanner_aem_dossier(dossier: str) -> list:
    """
    Scanne un dossier (et son sous-dossier AEM/) pour les fichiers [AEM]*.pdf.
    Retourne une liste de dicts tries par date, sans doublons.
    """
    trouves = {}
    for rep in [Path(dossier), Path(dossier) / "AEM"]:
        if not rep.is_dir():
            continue
        for f in sorted(rep.iterdir()):
            if f.is_file() and f.name not in trouves:
                info = _parser_nom_aem(f.name)
                if info:
                    trouves[f.name] = info
    return sorted(trouves.values(), key=lambda x: x["date"])


def _scanner_aem_annee(dossier_annee: str) -> list:
    """
    Scanne récursivement tous les [AEM]*.pdf sous le dossier année.
    Retourne une liste de dicts tries par date, sans doublons.
    """
    trouves = {}
    for f in sorted(Path(dossier_annee).rglob("*.pdf")):
        if f.name not in trouves:
            info = _parser_nom_aem(f.name)
            if info:
                trouves[f.name] = info
    return sorted(trouves.values(), key=lambda x: x["date"])


def _ecrire_total_txt(dossier: str, contrats: list, annee: str = "") -> str:
    """
    Cree ou ecrase total.txt dans le dossier donne.
    Groupe les contrats par mois avec sous-totaux.
    Retourne le chemin du fichier cree.
    """
    from datetime import date as _d
    titre = f"RECAPITULATIF ANNUEL AEM — {annee}" if annee else "RECAPITULATIF DES CONTRATS AEM"
    lignes = [
        "=" * 65,
        titre,
        f"Genere le {_d.today().strftime('%d/%m/%Y')}  —  {dossier}",
        "=" * 65,
        "",
    ]

    total_h = total_eur = 0.0
    mois_courant = None
    mois_h = mois_eur = 0.0
    NOMS_MOIS = {
        "01": "Janvier", "02": "Fevrier",  "03": "Mars",     "04": "Avril",
        "05": "Mai",     "06": "Juin",     "07": "Juillet",  "08": "Aout",
        "09": "Septembre","10": "Octobre", "11": "Novembre", "12": "Decembre",
    }

    for c in contrats:
        mois_doc = c.get("annee_mois", c["date"][:7])   # "2026-05"
        mois_num = mois_doc[5:7] if len(mois_doc) >= 7 else "??"

        if mois_doc != mois_courant:
            # Sous-total du mois précédent
            if mois_courant is not None:
                lignes += [
                    f"  {'— Sous-total':<50}  {mois_h:>7g}h  {mois_eur:>10g} EUR",
                    "",
                ]
            mois_courant = mois_doc
            mois_h = mois_eur = 0.0
            nom_mois = NOMS_MOIS.get(mois_num, mois_num)
            lignes.append(f"── {mois_doc[:4]}/{mois_num}  {nom_mois} {'─' * 40}")

        h   = c["heures"]  or "?"
        sal = c["salaire"] or "?"
        lignes.append(f"  {c['date']:<18}  {c['employeur']:<28}  {h:>6}h  {sal:>10} EUR")
        try:
            mois_h   += float(c["heures"])
            total_h  += float(c["heures"])
        except (ValueError, TypeError):
            pass
        try:
            mois_eur  += float(c["salaire"])
            total_eur += float(c["salaire"])
        except (ValueError, TypeError):
            pass

    # Sous-total dernier mois
    if mois_courant is not None:
        lignes += [
            f"  {'— Sous-total':<50}  {mois_h:>7g}h  {mois_eur:>10g} EUR",
            "",
        ]

    lignes += [
        "=" * 65,
        f"TOTAL HEURES    : {total_h:g} h",
        f"TOTAL SALAIRE   : {total_eur:g} EUR",
        f"NOMBRE CONTRATS : {len(contrats)}",
        "=" * 65,
    ]
    chemin = Path(dossier) / "total.txt"
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    return str(chemin)


def _parser_nom_aem(nom: str) -> dict | None:
    """
    Parse un nom de fichier AEM.
    Ex : [AEM] 2026-05-01_31 LaVouivre 151h 2500EUR.pdf
    Retourne None si le nom ne correspond pas.
    """
    m = _RE_AEM.match(nom)
    if not m:
        return None
    date_str  = m.group(1)  # "2026-05-01_31"
    employeur = m.group(2).strip()
    heures    = m.group(3) or ""
    salaire   = m.group(4) or ""
    # Annee-mois pour le tri : "2026-05"
    annee_mois = date_str[:7]
    return {
        "nom":       nom,
        "date":      date_str,
        "annee_mois":annee_mois,
        "employeur": employeur,
        "heures":    heures,
        "salaire":   salaire,
    }


class OngletCalcul(tk.Frame):

    COL_AEM = [
        ("fichier",  "Fichier",     340),
        ("date",     "Date",        130),
        ("employeur","Employeur",   180),
        ("heures",   "Heures",       70),
        ("salaire",  "Salaire brut", 100),
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._dossier   = ""
        self._contrats  = []   # list[dict]
        self._construire()

    def _construire(self):
        # Zone de drop dossier
        if DND_DISPONIBLE:
            self.lbl_drop = tk.Label(
                self,
                text="  Glissez un dossier ici  --  ou  --  cliquez Parcourir",
                relief=tk.RIDGE, bd=2, pady=10,
                bg="#E3F2FD", fg="#1565C0",
                font=("", 10, "bold"), cursor="hand2",
            )
            self.lbl_drop.pack(fill=tk.X, padx=10, pady=(8, 2))
            self.lbl_drop.bind("<Button-1>", lambda e: self._choisir_dossier())
            self.lbl_drop.drop_target_register(DND_FILES)
            self.lbl_drop.dnd_bind("<<Drop>>", self._on_drop_dossier)
        else:
            self.lbl_drop = None

        # Barre de sélection de dossier
        frame_top = tk.Frame(self, pady=4)
        frame_top.pack(fill=tk.X, padx=10)

        tk.Label(frame_top, text="Dossier :", width=10, anchor="w").pack(side=tk.LEFT)
        self.var_dossier = tk.StringVar()
        tk.Entry(frame_top, textvariable=self.var_dossier, width=60).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        tk.Button(frame_top, text="Parcourir...", command=self._choisir_dossier).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_top, text="Actualiser",  command=self._scanner_dossier,
                  bg="#1976D2", fg="white").pack(side=tk.LEFT, padx=4)

        # Tableau
        frame_table = tk.Frame(self)
        frame_table.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        scroll_v = tk.Scrollbar(frame_table, orient=tk.VERTICAL)
        scroll_h = tk.Scrollbar(frame_table, orient=tk.HORIZONTAL)

        self.tree = ttk.Treeview(
            frame_table,
            columns=[c[0] for c in self.COL_AEM],
            show="headings",
            yscrollcommand=scroll_v.set,
            xscrollcommand=scroll_h.set,
            height=16,
        )
        scroll_v.config(command=self.tree.yview)
        scroll_h.config(command=self.tree.xview)

        for col_id, col_titre, col_larg in self.COL_AEM:
            self.tree.column(col_id, width=col_larg, minwidth=40,
                             stretch=(col_id in ("fichier", "employeur")))
            self.tree.heading(col_id, text=col_titre)

        self.tree.tag_configure("total", background="#BBDEFB", font=("", 9, "bold"))
        self.tree.tag_configure("manquant", background="#FFF9C4")

        self._tri = _installer_tri(self.tree, [c[0] for c in self.COL_AEM])

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")
        scroll_h.grid(row=1, column=0, sticky="ew")
        frame_table.grid_rowconfigure(0, weight=1)
        frame_table.grid_columnconfigure(0, weight=1)

        # Barre du bas : totaux + bouton
        frame_bas = tk.Frame(self, pady=6)
        frame_bas.pack(fill=tk.X, padx=10)

        self.lbl_totaux = tk.Label(frame_bas,
                                   text="Total : -- h  |  -- EUR  |  0 contrat(s)",
                                   font=("", 10, "bold"), fg="#1565C0")
        self.lbl_totaux.pack(side=tk.LEFT, padx=4)

        tk.Button(frame_bas, text="Generer total.txt",
                  command=self._generer_total_txt,
                  bg="#388E3C", fg="white", padx=10, pady=4,
                  font=("", 9, "bold")).pack(side=tk.RIGHT, padx=6)

    # ---- logique ----

    def _on_drop_dossier(self, event):
        """Gere le glisser-deposer d un dossier."""
        data = event.data.strip()
        # Extraire le premier chemin (avec ou sans accolades)
        if data.startswith("{"):
            fin = data.find("}")
            chemin = data[1:fin] if fin != -1 else data[1:]
        else:
            chemin = data.split()[0]

        p = Path(chemin)
        # Accepter le dossier lui-meme ou un fichier a l interieur
        if p.is_file():
            p = p.parent
        if not p.is_dir():
            messagebox.showwarning("Dossier invalide", f"Impossible de lire : {chemin}")
            return

        if self.lbl_drop:
            self.lbl_drop.config(text=f"  {p.name}", bg="#E8F5E9", fg="#2E7D32")
        self.rafraichir_depuis_dossier(str(p))

    def _choisir_dossier(self):
        d = filedialog.askdirectory(title="Choisir le dossier contenant les AEM")
        if d:
            if self.lbl_drop:
                self.lbl_drop.config(text=f"  {Path(d).name}", bg="#E8F5E9", fg="#2E7D32")
            self.rafraichir_depuis_dossier(d)

    def _scanner_dossier(self):
        dossier = self.var_dossier.get().strip()
        if not dossier or not Path(dossier).is_dir():
            messagebox.showwarning("Dossier invalide", "Veuillez selectionner un dossier valide.")
            return
        self.rafraichir_depuis_dossier(dossier)

    def rafraichir_depuis_dossier(self, dossier: str):
        """Charge les AEM d un dossier et met a jour le tableau (appelable en externe)."""
        self._dossier = dossier
        self.var_dossier.set(dossier)
        self._contrats = _scanner_aem_dossier(dossier)
        self._afficher_tableau()

    def _afficher_tableau(self):
        """Remplit le Treeview et calcule les totaux."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        total_h   = 0.0
        total_eur = 0.0
        has_manquant = False

        for c in self._contrats:
            h   = c["heures"]
            sal = c["salaire"]
            tag = ()
            if not h or not sal:
                tag     = ("manquant",)
                has_manquant = True
            else:
                try:
                    total_h   += float(h)
                    total_eur += float(sal)
                except ValueError:
                    pass

            self.tree.insert("", tk.END, values=(
                c["nom"],
                c["date"],
                c["employeur"],
                f"{h}h" if h else "?",
                f"{sal} EUR" if sal else "?",
            ), tags=tag)

        # Ligne de total
        if self._contrats:
            h_str   = f"{total_h:g}h"
            eur_str = f"{total_eur:g} EUR"
            self.tree.insert("", tk.END, values=(
                f"--- TOTAL ({len(self._contrats)} contrat(s)) ---",
                "", "", h_str, eur_str,
            ), tags=("total",))

        # Label totaux
        nb = len(self._contrats)
        self.lbl_totaux.config(
            text=f"Total : {total_h:g} h  |  {total_eur:g} EUR  |  {nb} contrat(s)"
        )

    @staticmethod
    def _trouver_racine_annee(dossier: str) -> tuple[str, str] | None:
        """
        Remonte dans l'arborescence jusqu'à trouver un dossier nommé YYYY.
        Retourne (chemin_annee, annee) ou None si non trouvé.
        """
        p = Path(dossier).resolve()
        for _ in range(6):
            if re.fullmatch(r'\d{4}', p.name):
                return str(p), p.name
            if p.parent == p:
                break
            p = p.parent
        return None

    def _generer_total_txt(self):
        """
        Remonte jusqu'à la racine de l'année, scanne tous les AEM de l'année
        et écrit total.txt à la racine de l'année.
        """
        if not self._dossier:
            messagebox.showwarning("Aucun dossier", "Selectionnez un dossier d'abord.")
            return

        resultat = self._trouver_racine_annee(self._dossier)
        if resultat:
            dossier_annee, annee = resultat
            contrats = _scanner_aem_annee(dossier_annee)
            label = f"année {annee}"
        else:
            # Fallback : utiliser le dossier courant
            dossier_annee = self._dossier
            annee = ""
            contrats = self._contrats
            label = "dossier courant"

        if not contrats:
            messagebox.showwarning("Aucun contrat",
                f"Aucun fichier AEM trouvé dans le {label}.")
            return

        try:
            chemin = _ecrire_total_txt(dossier_annee, contrats, annee)
            messagebox.showinfo("Fichier créé",
                f"total.txt généré ({len(contrats)} contrat(s)) :\n{chemin}")
        except OSError as e:
            messagebox.showerror("Erreur", f"Impossible d'écrire total.txt :\n{e}")


# ---------------------------------------------------------------------------
# Onglet Suivi Intermittent
# ---------------------------------------------------------------------------
class OngletSuivi(tk.Frame):
    """Tableau de bord du suivi des droits intermittent."""

    def __init__(self, parent, cfg_getter, **kwargs):
        super().__init__(parent, **kwargs)
        self._cfg_getter  = cfg_getter
        self._docs_tous   = []
        self._prevs       = []
        self._stats       = {}
        self._stats_prev  = {}   # stats incluant le prévisionnel
        self._construire()

    # ---- Construction -------------------------------------------------------

    def _construire(self):
        # ── Barre du haut : dossier + période ──────────────────────────────
        frame_top = tk.LabelFrame(self, text="Source & Période", padx=8, pady=6)
        frame_top.pack(fill=tk.X, padx=10, pady=(8, 4))

        # Dossier
        row1 = tk.Frame(frame_top)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Dossier :", width=10, anchor="w").pack(side=tk.LEFT)
        self.var_dossier = tk.StringVar()
        tk.Entry(row1, textvariable=self.var_dossier, width=55).pack(
            side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        tk.Button(row1, text="Parcourir...",
                  command=self._choisir_dossier).pack(side=tk.LEFT, padx=2)
        tk.Button(row1, text="Actualiser",
                  command=self._actualiser,
                  bg="#1976D2", fg="white").pack(side=tk.LEFT, padx=2)

        # Date anniversaire (ligne 2)
        row2 = tk.Frame(frame_top)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Date anniv. :", width=10, anchor="w").pack(side=tk.LEFT)
        cfg_init = self._cfg_getter()
        self.var_date_ann_suivi = tk.StringVar(value=cfg_init.get("date_anniversaire", ""))
        entry_ann = tk.Entry(row2, textvariable=self.var_date_ann_suivi, width=8)
        entry_ann.pack(side=tk.LEFT, padx=4)
        tk.Label(row2, text="(JJ/MM)", fg="#888", font=("", 8)).pack(side=tk.LEFT)
        tk.Button(row2, text="Appliquer date",
                  command=self._appliquer_date_ann,
                  bg="#4CAF50", fg="white", padx=6).pack(side=tk.LEFT, padx=8)
        tk.Label(row2, text="→ la période commence le lendemain de cette date",
                 fg="#888", font=("", 8)).pack(side=tk.LEFT)

        # Période manuelle (ligne 3)
        row3 = tk.Frame(frame_top)
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="Période :", width=10, anchor="w").pack(side=tk.LEFT)
        today     = _date_today.today()
        an_pass   = today.replace(year=today.year - 1)
        self.var_date_debut = tk.StringVar(value=str(an_pass))
        self.var_date_fin   = tk.StringVar(value=str(today))
        tk.Label(row3, text="du").pack(side=tk.LEFT)
        tk.Entry(row3, textvariable=self.var_date_debut, width=12).pack(side=tk.LEFT, padx=4)
        tk.Label(row3, text="au").pack(side=tk.LEFT)
        tk.Entry(row3, textvariable=self.var_date_fin, width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(row3, text="Appliquer",
                  command=self._recalculer,
                  bg="#F57C00", fg="white").pack(side=tk.LEFT, padx=6)
        tk.Label(row3, text="(format YYYY-MM-DD)", fg="#888", font=("", 8)).pack(side=tk.LEFT)

        # ── Bandeau annexe ────────────────────────────────────────────────
        self._lbl_annexe = tk.Label(self, text="", font=("", 9, "bold"),
                                     fg="white", pady=3, anchor="center")
        self._lbl_annexe.pack(fill=tk.X, padx=10, pady=(0, 2))
        self._maj_lbl_annexe()

        # ── Bandeau date anniversaire ──────────────────────────────────────
        self._lbl_anniversaire = tk.Label(self, text="", font=("", 9),
                                           fg="white", pady=3, anchor="center",
                                           cursor="hand2")
        self._lbl_anniversaire.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._maj_lbl_anniversaire()

        # ── Zone tableau de bord (2 cartes côte à côte) ───────────────────
        frame_dash = tk.Frame(self)
        frame_dash.pack(fill=tk.X, padx=10, pady=4)

        # Carte gauche : progression + prévisionnel
        self._carte_507 = tk.LabelFrame(frame_dash, text="Progression & Prévisionnel",
                                         padx=10, pady=8, width=310)
        self._carte_507.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self._carte_507.pack_propagate(False)

        self._canvas_barre = tk.Canvas(self._carte_507, height=118,
                                        bg="white", highlightthickness=0)
        self._canvas_barre.pack(fill=tk.X, pady=(4, 2))

        self.lbl_statut = tk.Label(self._carte_507, text="—",
                                    font=("", 10, "bold"), wraplength=280)
        self.lbl_statut.pack(pady=1)

        self.lbl_progression = tk.Label(self._carte_507, text="",
                                         font=("", 9), fg="#555", wraplength=280)
        self.lbl_progression.pack(pady=0)

        self.lbl_employeurs = tk.Label(self._carte_507, text="",
                                        font=("", 9), fg="#555", wraplength=280)
        self.lbl_employeurs.pack(pady=1)

        self.lbl_alerte_salaire = tk.Label(self._carte_507, text="",
                                            font=("", 9, "bold"), fg="#C62828",
                                            wraplength=280, justify="left")
        self.lbl_alerte_salaire.pack(pady=(2, 0))

        # Bouton + Prévisionnel
        tk.Button(self._carte_507, text="+ Ajouter un contrat prévisionnel",
                  command=self._ajouter_previsionnel,
                  bg="#7B1FA2", fg="white", pady=3).pack(pady=(4, 2))

        # Carte droite : KPI tiles (2-column grid)
        self._carte_chiffres = tk.LabelFrame(frame_dash, text="  Indicateurs  ",
                                              padx=8, pady=6, width=300)
        self._carte_chiffres.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self._carte_chiffres.pack_propagate(False)

        self._labels_chiffres = {}

        # KPI definition: key, label, color, col, row
        kpi_defs = [
            ("heures",    "Heures travaillées", TH.PRIMARY_DARK,  0, 0),
            ("manquantes","Heures manquantes",  TH.DANGER,         1, 0),
            ("salaire",   "Salaire brut",       TH.SUCCESS,        0, 1),
            ("sjr",       "SJR estimé",         TH.PURPLE,         1, 1),
            ("aj",        "Allocation /jour",   TH.WARNING,        0, 2),
            ("nb_docs",   "Documents",          TH.TEXT_SECONDARY, 1, 2),
        ]

        for key, titre, color, col, tile_row in kpi_defs:
            tile = tk.Frame(self._carte_chiffres,
                            relief=tk.GROOVE, bd=1,
                            padx=8, pady=6)
            tile.grid(row=tile_row, column=col,
                      padx=4, pady=4, sticky="nsew")
            self._carte_chiffres.grid_columnconfigure(col, weight=1)

            lbl_val = tk.Label(tile, text="—",
                               font=TH.FONT_KPI_VALUE, fg=color, anchor="center")
            lbl_val.pack(fill=tk.X)

            tk.Label(tile, text=titre,
                     font=TH.FONT_KPI_LABEL,
                     fg=TH.TEXT_MUTED, anchor="center").pack(fill=tk.X)

            self._labels_chiffres[key] = lbl_val

        # ── Barre du bas : bouton export ───────────────────────────────────
        frame_bas = tk.Frame(self, pady=6)
        frame_bas.pack(fill=tk.X, padx=10)

        tk.Button(frame_bas, text="Exporter PDF bilan",
                  command=self._exporter_pdf,
                  bg="#1976D2", fg="white",
                  font=("", 9, "bold"), padx=12, pady=5).pack(side=tk.LEFT, padx=4)

        tk.Button(frame_bas, text="Calculer ARE & Congés Spectacle",
                  command=self._ouvrir_calcul_are,
                  bg="#E65100", fg="white",
                  font=("", 9, "bold"), padx=12, pady=5).pack(side=tk.LEFT, padx=4)

        self.lbl_bas = tk.Label(frame_bas, text="",
                                 font=("", 9), fg="#555")
        self.lbl_bas.pack(side=tk.LEFT, padx=10)

        tk.Label(frame_bas,
                 text="⚠  SJR et allocation sont des estimations — seul France Travail calcule vos droits exacts.",
                 font=("", 8), fg="#B71C1C", wraplength=460, justify=tk.LEFT).pack(
            side=tk.RIGHT, padx=4)

    # ---- Logique ------------------------------------------------------------

    def _maj_lbl_annexe(self):
        """Met à jour le bandeau d'annexe selon la config."""
        cfg = self._cfg_getter()
        annexe = cfg.get("annexe", "")
        infos = {
            "8":    ("Annexe 8 — Technicien du spectacle", "#1565C0"),
            "10":   ("Annexe 10 — Artiste du spectacle",   "#6A1B9A"),
            "8+10": ("Annexes 8 & 10 — Technicien + Artiste", "#2E7D32"),
        }
        if annexe in infos:
            texte, couleur = infos[annexe]
            self._lbl_annexe.config(text=texte, bg=couleur)
        else:
            self._lbl_annexe.config(
                text="Annexe non définie — allez dans Outils → Paramètres",
                bg="#B71C1C")

    def _maj_lbl_anniversaire(self, heures: float = -1):
        """Calcule et affiche le compte à rebours avant la date anniversaire.
        La couleur reflète l'état des heures : rouge <507h, bleu ≥507h, vert ≥720h.
        heures=-1 signifie 'inconnu' (init avant le premier calcul).
        """
        from datetime import date as _d
        cfg = self._cfg_getter()
        date_ann_str = cfg.get("date_anniversaire", "").strip()  # format JJ/MM
        if not date_ann_str:
            self._lbl_anniversaire.config(
                text="Date anniversaire non définie — configurez-la dans Paramètres",
                bg="#757575")
            return

        # Couleur selon état des heures
        if heures < 0:
            heures = getattr(self, "_stats", {}).get("total_heures", -1)
        if heures >= 720:
            couleur_h = "#2E7D32"   # vert
        elif heures >= 507:
            couleur_h = "#1565C0"   # bleu
        else:
            couleur_h = "#B71C1C"   # rouge

        try:
            jour, mois = int(date_ann_str[:2]), int(date_ann_str[3:5])
            today = _d.today()
            ann = _d(today.year, mois, jour)
            if ann <= today:   # <= car le lendemain de la date anniv démarre la période
                ann = _d(today.year + 1, mois, jour)
            jours_restants = (ann - today).days

            if jours_restants == 0:
                txt = "⚠  Date anniversaire AUJOURD'HUI — Contactez France Travail maintenant !"
            elif jours_restants <= 7:
                txt = f"⚠  Date anniversaire dans {jours_restants} jour(s) — {ann.strftime('%d/%m/%Y')} — Urgence !"
            elif jours_restants <= 30:
                txt = f"⚠  Date anniversaire dans {jours_restants} jours — {ann.strftime('%d/%m/%Y')} — Vérifiez vos droits"
            elif jours_restants <= 60:
                txt = f"Date anniversaire dans {jours_restants} jours — {ann.strftime('%d/%m/%Y')}"
            else:
                txt = f"Date anniversaire : {ann.strftime('%d/%m/%Y')}  ({jours_restants} jours)"

            self._lbl_anniversaire.config(text=txt, bg=couleur_h)
        except Exception:
            self._lbl_anniversaire.config(
                text="Date anniversaire invalide (format attendu : JJ/MM)",
                bg="#757575")

    def _appliquer_date_ann(self):
        """Sauvegarde la date anniversaire depuis le champ Suivi et recalcule."""
        from config import charger_config, sauvegarder_config
        val = self.var_date_ann_suivi.get().strip()
        # Valider format JJ/MM
        import re as _re
        if val and not _re.match(r"^\d{2}/\d{2}$", val):
            messagebox.showwarning("Format invalide",
                "La date anniversaire doit être au format JJ/MM (ex: 15/06).",
                parent=self)
            return
        cfg = self._cfg_getter()
        cfg["date_anniversaire"] = val
        sauvegarder_config(cfg)
        self._maj_lbl_anniversaire()
        # Recalculer la période depuis la date anniversaire
        if val:
            self._appliquer_periode_anniversaire(val)

    def _appliquer_periode_anniversaire(self, date_ann_str: str):
        """Calcule et applique la période actuelle basée sur la date anniversaire."""
        from datetime import date, timedelta
        try:
            jour, mois = int(date_ann_str[:2]), int(date_ann_str[3:5])
            today = date.today()
            # Date anniversaire précédente = début de période (lendemain)
            anniv_prec = date(today.year, mois, jour)
            if anniv_prec >= today:
                anniv_prec = date(today.year - 1, mois, jour)
            debut = anniv_prec + timedelta(days=1)
            # Date anniversaire courante = fin de période
            fin = date(anniv_prec.year + 1, mois, jour)
            self.var_date_debut.set(str(debut))
            self.var_date_fin.set(str(fin))
            self._recalculer()
        except (ValueError, IndexError):
            pass

    def _choisir_dossier(self):
        d = filedialog.askdirectory(title="Choisir le dossier de documents classifiés")
        if d:
            self.var_dossier.set(d)
            self._actualiser()

    def _actualiser(self):
        """Recharge tous les docs du dossier, déduplique les prévisionnels et recalcule."""
        from previsionnel import charger_previsionnels
        dossier = self.var_dossier.get().strip()
        cfg = self._cfg_getter()
        if not dossier:
            dossier = cfg.get("dossier_base", "")
            if dossier:
                self.var_dossier.set(dossier)
        if not dossier or not Path(dossier).is_dir():
            messagebox.showwarning("Dossier invalide",
                                   "Sélectionnez un dossier contenant vos documents classifiés.")
            return
        self._docs_tous = _scanner_tous_docs(dossier)

        # Déduplication prévisionnels vs AEM réels
        global _dedup_en_cours
        if not _dedup_en_cours:
            _dedup_en_cours = True
            self.after(60000, self._reset_dedup)
            rapport = _deduplication_previsionnels(self._docs_tous)
            en_attente_visibles = _prevs_mois_courant_et_precedent(rapport["en_attente"])
            if rapport["supprimes"] or rapport["conflits"] or en_attente_visibles:
                _DialogueRapportDedup(self, rapport["supprimes"],
                                      rapport["conflits"], en_attente_visibles)

        # Recharger après suppressions éventuelles
        self._prevs = charger_previsionnels()

        # Si date anniversaire configurée, calculer automatiquement la période
        date_ann = cfg.get("date_anniversaire", "").strip()
        if date_ann:
            self._appliquer_periode_anniversaire(date_ann)
        else:
            self._recalculer()

    def _reset_dedup(self):
        global _dedup_en_cours
        _dedup_en_cours = False

    def _recalculer(self):
        """Recalcule les stats réel + prévisionnel et met à jour l'UI."""
        d1 = self.var_date_debut.get().strip()
        d2 = self.var_date_fin.get().strip()
        annexe = self._cfg_getter().get("annexe", "8")
        self._stats = _calculer_stats(self._docs_tous, d1, d2, annexe=annexe)
        # Stats combinées réel + prévisionnel (pour les jauges)
        # Reconstruct full ISO dates from annee+mois+day before filtering
        docs_prev_comme_docs = []
        for p in self._prevs:
            d = {**p, "type": p.get("type", "AEM")}
            a, mo, dd_raw = d.get("annee", ""), d.get("mois", ""), d.get("date_debut", "")
            df_raw = d.get("date_fin", dd_raw)
            if a and mo and dd_raw and len(dd_raw) == 2:
                d["date_debut"] = f"{a}-{mo}-{dd_raw}"
                d["date_fin"] = f"{a}-{mo}-{df_raw}" if df_raw and len(df_raw) == 2 else d["date_debut"]
            docs_prev_comme_docs.append(d)
        self._stats_prev = _calculer_stats(
            self._docs_tous + docs_prev_comme_docs, d1, d2, annexe=annexe
        )
        self._afficher_barre()
        self._afficher_chiffres()
        self._maj_resume_periode()

    def _ajouter_previsionnel(self):
        """Ouvre le dialogue de saisie d'un contrat prévisionnel."""
        from previsionnel import ajouter_previsionnel, charger_previsionnels
        dlg = DialoguePrevisionnel(self)
        self.wait_window(dlg)
        if dlg.contrat:
            ajouter_previsionnel(dlg.contrat)
            self._prevs = charger_previsionnels()
            self._recalculer()
            self._log_externe(
                f"[Prévi] Ajouté : {dlg.contrat.get('employeur','')} "
                f"{dlg.contrat.get('date_debut','')} "
                f"{dlg.contrat.get('heures','')}h"
            )

    def _log_externe(self, msg: str):
        """Log vers la console principale si disponible."""
        try:
            master = self.winfo_toplevel()
            if hasattr(master, "_log"):
                master._log(msg)
        except Exception:
            pass

    def _afficher_barre(self):
        """
        Dessine 3 barres superposées réel+prévisionnel :
        - Heures (échelle 720h, seuil 507h)
        - Salaire (échelle 14 400€)
        Prévisionnel en fond semi-opaque, réel en plein par-dessus.
        """
        c = self._canvas_barre
        c.update_idletasks()
        W = c.winfo_width() or 280
        c.delete("all")

        s      = self._stats
        sp     = self._stats_prev   # stats réel + prévisionnel cumulé

        heures  = s.get("total_heures",  0)
        salaire = s.get("total_salaire", 0)
        droits  = s.get("droits_ouverts", False)
        h_prev  = sp.get("total_heures",  heures)
        s_prev  = sp.get("total_salaire", salaire)

        BW = W - 8   # largeur utile de la barre

        def _barre_duo(y0, y1, pct_reel, pct_prev,
                       couleur_reel, couleur_prev,
                       pct_seuil, label, label_seuil, label_max, val_txt):
            """Barre avec fond prévisionnel + remplissage réel par-dessus."""
            # Fond gris
            c.create_rectangle(4, y0, W-4, y1, fill="#E0E0E0", outline="")
            # Barre prévisionnel (couleur claire)
            fw_p = max(0, int(BW * min(1.0, pct_prev)))
            if fw_p:
                c.create_rectangle(4, y0, 4+fw_p, y1, fill=couleur_prev, outline="")
            # Barre réel (couleur pleine)
            fw_r = max(0, int(BW * min(1.0, pct_reel)))
            if fw_r:
                c.create_rectangle(4, y0, 4+fw_r, y1, fill=couleur_reel, outline="")
            # Marqueur seuil (rouge pointillé)
            if pct_seuil > 0:
                x_s = 4 + int(BW * pct_seuil)
                c.create_line(x_s, y0-2, x_s, y1+2, fill="#D32F2F", width=1, dash=(3, 2))
                c.create_text(x_s, y1+3, text=label_seuil, anchor="n",
                              font=("", 6), fill="#D32F2F")
            # Marqueur max (orange)
            c.create_line(W-4, y0-2, W-4, y1+2, fill="#E65100", width=2)
            c.create_text(W-4, y1+3, text=label_max, anchor="n",
                          font=("", 6), fill="#E65100")
            # Label gauche
            c.create_text(6, y0-5, text=label, anchor="sw",
                          font=("", 7, "bold"), fill="#444")
            # Valeur au centre
            txt_col = "white" if fw_r > BW//2 else ("#333" if fw_p < BW//2 else "#333")
            c.create_text(W//2, (y0+y1)//2, text=val_txt,
                          font=("", 8, "bold"), fill=txt_col)

        # ── Barre 1 : Heures (échelle 720h) ───────────────────────────────
        _barre_duo(
            y0=10, y1=32,
            pct_reel=s.get("pct_720", 0),
            pct_prev=min(1.0, h_prev / 720),
            couleur_reel="#1565C0" if not droits else "#2E7D32",
            couleur_prev="#90CAF9" if not droits else "#A5D6A7",
            pct_seuil=507/720,
            label="Heures  (réel / prévi)",
            label_seuil="507h",
            label_max="720h",
            val_txt=f"Réel {heures:.0f}h  |  Prévi {h_prev:.0f}h",
        )

        # ── Barre 2 : Salaire (échelle 14 400€) ───────────────────────────
        _barre_duo(
            y0=50, y1=72,
            pct_reel=s.get("pct_salaire", 0),
            pct_prev=min(1.0, s_prev / SEUIL_SALAIRE_RENTABLE),
            couleur_reel="#4A148C",
            couleur_prev="#CE93D8",
            pct_seuil=0,
            label="Salaire brut  (réel / prévi)",
            label_seuil="",
            label_max="14 400€",
            val_txt=f"Réel {salaire:.0f}€  |  Prévi {s_prev:.0f}€",
        )

        # ── Légende ───────────────────────────────────────────────────────
        c.create_rectangle(4, 88, 16, 98, fill="#1565C0", outline="")
        c.create_text(20, 93, text="Réel", anchor="w", font=("", 7), fill="#333")
        c.create_rectangle(60, 88, 72, 98, fill="#90CAF9", outline="")
        c.create_text(76, 93, text="Prévisionnel", anchor="w", font=("", 7), fill="#333")
        c.create_line(120, 93, 130, 93, fill="#D32F2F", width=1, dash=(3, 2))
        c.create_text(133, 93, text="Seuil 507h", anchor="w", font=("", 7), fill="#D32F2F")
        c.create_line(195, 88, 195, 98, fill="#E65100", width=2)
        c.create_text(199, 93, text="Cible max", anchor="w", font=("", 7), fill="#E65100")

        # Statut + indicateur de progression détaillé
        if droits:
            surplus = heures - 507
            self.lbl_statut.config(text="✓ Droits ouverts (≥ 507h)", fg="#2E7D32")
            if heures >= 720:
                prog_txt = f"+{heures-507:.0f}h au-delà du seuil · Cible 720h atteinte ✓"
                prog_col = "#2E7D32"
            else:
                manq_720 = 720 - heures
                prog_txt = f"+{surplus:.0f}h au-delà de 507h · Il manque {manq_720:.0f}h pour 720h"
                prog_col = "#1565C0"
        else:
            manq = s.get("manquantes", 0)
            self.lbl_statut.config(
                text=f"✗ Il manque {manq:.0f}h pour ouvrir les droits (min 507h)",
                fg="#C62828")
            if 338 <= heures < 507:
                prog_txt = "Clause de rattrapage possible si ≥ 5 ans d'ancienneté"
                prog_col = "#E65100"
            else:
                prog_txt = f"{heures:.0f}h / 507h — {507-heures:.0f}h restantes"
                prog_col = "#C62828"
        self.lbl_progression.config(text=prog_txt, fg=prog_col)
        self._maj_lbl_anniversaire(heures=heures)

        emps = s.get("employeurs", [])
        self.lbl_employeurs.config(
            text=(f"{len(emps)} employeur(s) : {', '.join(emps)}" if emps
                  else "Aucun employeur trouvé sur la période")
        )

        # Alerte seuil de rentabilité (14 400 € brut réel + prévisionnel)
        if s_prev > SEUIL_SALAIRE_RENTABLE:
            depassement = s_prev - SEUIL_SALAIRE_RENTABLE
            self.lbl_alerte_salaire.config(
                text=f"⚠ Vous dépassez 14 400 € brut sur la période "
                     f"(+{depassement:.0f} €, réel + prévisionnel) : au-delà de ce "
                     "montant, il est conseillé de ne plus déclarer en intermittent.")
        else:
            self.lbl_alerte_salaire.config(text="")

    def _afficher_chiffres(self):
        s  = self._stats
        sp = self._stats_prev or s
        h_reel = s.get("total_heures", 0)
        h_prev = sp.get("total_heures", h_reel)
        sal_reel = s.get("total_salaire", 0)
        sal_prev = sp.get("total_salaire", sal_reel)
        manquantes = s.get("manquantes", 0)
        manq_prev  = sp.get("manquantes", manquantes)

        def _avec_prev(reel_txt: str, reel_val, prev_val, prev_txt: str) -> str:
            """Append forecast value (⏳) when it differs from actual."""
            if abs(float(prev_val) - float(reel_val)) < 0.01:
                return reel_txt
            return f"{reel_txt}  ⏳ {prev_txt}"

        mises_a_jour = {
            "heures":     _avec_prev(f"{h_reel:.1f} h", h_reel, h_prev,
                                     f"{h_prev:.1f} h"),
            "manquantes": _avec_prev(
                f"{manquantes:.0f} h" if manquantes > 0 else "0 h  ✓",
                manquantes, manq_prev,
                f"{manq_prev:.0f} h" if manq_prev > 0 else "0 h ✓"),
            "salaire":    _avec_prev(f"{sal_reel:.0f} €", sal_reel, sal_prev,
                                     f"{sal_prev:.0f} €"),
            "sjr":        _avec_prev(f"{s.get('sjr', 0):.2f} €/j",
                                     s.get("sjr", 0), sp.get("sjr", s.get("sjr", 0)),
                                     f"{sp.get('sjr', 0):.2f}"),
            "aj":         _avec_prev(f"~{s.get('aj_estime', 0):.2f} €/j",
                                     s.get("aj_estime", 0),
                                     sp.get("aj_estime", s.get("aj_estime", 0)),
                                     f"~{sp.get('aj_estime', 0):.2f}"),
            "nb_docs":    _avec_prev(str(s.get("nb_docs", 0)),
                                     s.get("nb_docs", 0),
                                     sp.get("nb_docs", s.get("nb_docs", 0)),
                                     str(sp.get("nb_docs", 0))),
        }
        for key, val in mises_a_jour.items():
            lbl = self._labels_chiffres.get(key)
            if lbl:
                lbl.config(text=val)
                if key == "manquantes":
                    lbl.config(fg=TH.DANGER if manquantes > 0 else TH.SUCCESS)

    def _maj_resume_periode(self):
        """Résumé texte (nb documents réels/prévisionnels) sur la période —
        remplace l'ancien tableau détaillé, retiré pour alléger l'affichage."""
        docs = self._stats.get("docs_periode", [])

        d1 = self.var_date_debut.get().strip()
        d2 = self.var_date_fin.get().strip()
        prevs_periode = []
        for p in self._prevs:
            a, mo = p.get("annee", ""), p.get("mois", "")
            dd_raw = p.get("date_debut", "")
            df_raw = p.get("date_fin", dd_raw)
            dd = f"{a}-{mo}-{dd_raw}" if (a and mo and dd_raw and len(dd_raw) == 2) else dd_raw
            df = f"{a}-{mo}-{df_raw}" if (a and mo and df_raw and len(df_raw) == 2) else dd
            if dd >= d1 and df <= d2:
                prevs_periode.append(p)

        self.lbl_bas.config(
            text=f"{len(docs)} doc(s) réel(s) + {len(prevs_periode)} prévisionnel(s) "
                 f"sur la période  |  {len(self._docs_tous)} au total"
        )

    def _ouvrir_calcul_are(self):
        if not self._stats or not self._stats.get("nb_docs"):
            messagebox.showwarning("Aucune donnée",
                                   "Actualisez d'abord le suivi avant de calculer.")
            return
        cfg = self._cfg_getter()
        dlg = DialogueCalculARE(self, self._stats, cfg)
        dlg.focus_set()

    def _exporter_pdf(self):
        if not self._stats:
            messagebox.showwarning("Aucune donnée",
                                   "Actualisez d'abord le suivi avant d'exporter.")
            return
        chemin = filedialog.asksaveasfilename(
            title="Enregistrer le bilan PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"bilan_intermittent_{_date_today.today().strftime('%Y%m%d')}.pdf",
        )
        if not chemin:
            return
        try:
            _generer_pdf_bilan(
                chemin, self._stats,
                self.var_date_debut.get().strip(),
                self.var_date_fin.get().strip(),
            )
            messagebox.showinfo("Export réussi", f"PDF généré :\n{chemin}")
            import os
            os.startfile(chemin)
        except Exception as e:
            DialogueRapport.afficher(self, "Erreur export PDF", str(e))

    def rafraichir_depuis_dossier(self, dossier: str):
        """Appelable depuis l'extérieur après une classification."""
        self.var_dossier.set(dossier)
        self._docs_tous = _scanner_tous_docs(dossier)
        self._recalculer()


# ---------------------------------------------------------------------------
# Dialogue saisie contrat prévisionnel
# ---------------------------------------------------------------------------
class DialoguePrevisionnel(tk.Toplevel):
    """Formulaire de saisie d'un contrat prévisionnel."""

    TYPES = ["AEM", "BP", "CS", "CT", "STC"]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Ajouter un contrat prévisionnel")
        self.resizable(False, False)
        self.contrat = None
        self._construire()
        self.grab_set()
        self.focus_set()

    def _construire(self):
        pad = {"padx": 10, "pady": 4}

        tk.Label(self, text="Nouveau contrat prévisionnel",
                 font=("", 11, "bold"), fg="#7B1FA2").pack(pady=(14, 6))

        frame = tk.Frame(self, padx=16)
        frame.pack(fill=tk.X)

        champs = [
            ("Type de doc",    "var_type",       None),
            ("Employeur",      "var_employeur",  None),
            ("Date début",     "var_debut",      "YYYY-MM-DD"),
            ("Date fin",       "var_fin",        "YYYY-MM-DD"),
            ("Heures prévues", "var_heures",     "ex: 120"),
            ("Salaire prévu",  "var_salaire",    "ex: 2500"),
            ("Notes",          "var_notes",      "optionnel"),
        ]

        for i, (label, attr, placeholder) in enumerate(champs):
            tk.Label(frame, text=f"{label} :", width=16,
                     anchor="e").grid(row=i, column=0, pady=3, sticky="e")
            if label == "Type de doc":
                var = tk.StringVar(value="AEM")
                setattr(self, attr, var)
                ttk.Combobox(frame, textvariable=var, values=self.TYPES,
                             width=18, state="readonly").grid(row=i, column=1, pady=3, sticky="w", padx=6)
            else:
                var = tk.StringVar()
                setattr(self, attr, var)
                e = tk.Entry(frame, textvariable=var, width=22)
                e.grid(row=i, column=1, pady=3, sticky="w", padx=6)
                if placeholder:
                    e.insert(0, placeholder)
                    e.config(fg="#AAA")
                    e.bind("<FocusIn>",
                           lambda ev, en=e, ph=placeholder: self._clear_placeholder(ev, en, ph))
                    e.bind("<FocusOut>",
                           lambda ev, en=e, ph=placeholder, v=var: self._restore_placeholder(ev, en, ph, v))

        frame_btn = tk.Frame(self, pady=14)
        frame_btn.pack()
        tk.Button(frame_btn, text="Annuler",
                  command=self.destroy,
                  padx=10, pady=5).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btn, text="Enregistrer",
                  command=self._valider,
                  bg="#7B1FA2", fg="white",
                  padx=10, pady=5).pack(side=tk.LEFT, padx=6)

    def _clear_placeholder(self, event, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg="black")

    def _restore_placeholder(self, event, entry, placeholder, var):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg="#AAA")

    def _valider(self):
        def _val(attr, placeholder=""):
            v = getattr(self, attr).get().strip()
            return "" if v == placeholder else v

        employeur = _val("var_employeur")
        date_debut = _val("var_debut", "YYYY-MM-DD")
        if not employeur or not date_debut:
            messagebox.showwarning("Champ manquant",
                                   "Employeur et date de début sont obligatoires.",
                                   parent=self)
            return

        date_fin = _val("var_fin", "YYYY-MM-DD") or date_debut
        self.contrat = {
            "type":       self.var_type.get(),
            "employeur":  employeur,
            "date_debut": date_debut,
            "date_fin":   date_fin,
            "heures":     _val("var_heures", "ex: 120"),
            "salaire":    _val("var_salaire", "ex: 2500"),
            "notes":      _val("var_notes", "optionnel"),
        }
        self.destroy()


# ---------------------------------------------------------------------------
# Utilitaire distance Levenshtein (détection doublons employeurs)
# ---------------------------------------------------------------------------
def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                            prev[j] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


class DialogueFusionEmployeurs(tk.Toplevel):
    """
    2 colonnes :
      - Gauche  : sélection multiple des noms à fusionner (sources)
      - Droite  : sélection du nom cible à conserver
    Double-clic sur un nom → affiche les PDFs liés.
    """

    def __init__(self, parent, employeurs: list, dossier_base: str, callback):
        super().__init__(parent)
        self.title("Fusionner des employeurs")
        self.resizable(True, True)
        self.geometry("780x520")
        self.grab_set()
        self._employeurs   = list(employeurs)
        self._dossier_base = dossier_base
        self._callback     = callback
        self._construire()

    def _construire(self):
        tk.Label(self,
                 text="Colonne gauche : sélectionnez les noms à supprimer (Ctrl+clic = multi)\n"
                      "Colonne droite : sélectionnez le nom à conserver\n"
                      "Double-clic sur un nom pour voir ses documents",
                 fg="#555", font=("", 9), justify="left").pack(padx=14, pady=(10, 4), anchor="w")

        # ── Deux listes côte à côte ────────────────────────────────────────
        frame_listes = tk.Frame(self)
        frame_listes.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        frame_listes.columnconfigure(0, weight=1)
        frame_listes.columnconfigure(2, weight=1)

        # Colonne gauche — sources (multi-sélection)
        tk.Label(frame_listes, text="Noms à fusionner (sources) :",
                 font=("", 9, "bold"), fg="#B71C1C").grid(row=0, column=0, sticky="w", pady=(0, 2))
        sb_g = tk.Scrollbar(frame_listes)
        self._lb_sources = tk.Listbox(frame_listes, selectmode=tk.MULTIPLE,
                                       yscrollcommand=sb_g.set, exportselection=False,
                                       font=("Consolas", 10), activestyle="dotbox", height=18)
        sb_g.config(command=self._lb_sources.yview)
        self._lb_sources.grid(row=1, column=0, sticky="nsew")
        sb_g.grid(row=1, column=1, sticky="ns")
        self._lb_sources.bind("<Double-1>", lambda e: self._voir_docs(self._lb_sources))

        # Séparateur
        tk.Label(frame_listes, text=" → ", font=("", 14, "bold"),
                 fg="#1A237E").grid(row=1, column=2, padx=8)

        # Colonne droite — cible (sélection unique)
        tk.Label(frame_listes, text="Nom à conserver (cible) :",
                 font=("", 9, "bold"), fg="#1B5E20").grid(row=0, column=3, sticky="w", pady=(0, 2))
        sb_d = tk.Scrollbar(frame_listes)
        self._lb_cible = tk.Listbox(frame_listes, selectmode=tk.SINGLE,
                                     yscrollcommand=sb_d.set, exportselection=False,
                                     font=("Consolas", 10), activestyle="dotbox", height=18)
        sb_d.config(command=self._lb_cible.yview)
        self._lb_cible.grid(row=1, column=3, sticky="nsew")
        sb_d.grid(row=1, column=4, sticky="ns")
        self._lb_cible.bind("<Double-1>", lambda e: self._voir_docs(self._lb_cible))
        frame_listes.rowconfigure(1, weight=1)
        frame_listes.columnconfigure(3, weight=1)

        # Remplir les deux listes
        for emp in self._employeurs:
            self._lb_sources.insert(tk.END, f"  {emp}")
            self._lb_cible.insert(tk.END, f"  {emp}")

        # ── Boutons ───────────────────────────────────────────────────────
        frame_btn = tk.Frame(self, pady=10)
        frame_btn.pack()
        tk.Button(frame_btn, text="✔ Fusionner",
                  bg="#1976D2", fg="white", width=16, pady=5,
                  command=self._appliquer).pack(side=tk.LEFT, padx=8)
        tk.Button(frame_btn, text="Annuler",
                  command=self.destroy, width=12, pady=5).pack(side=tk.LEFT, padx=8)

        self._lbl_statut = tk.Label(self, text="", fg="#555", font=("", 8))
        self._lbl_statut.pack(pady=(0, 6))

        self._lb_sources.bind("<<ListboxSelect>>", self._maj_statut)
        self._lb_cible.bind("<<ListboxSelect>>",   self._maj_statut)

    def _maj_statut(self, *_):
        sources = [self._employeurs[i] for i in self._lb_sources.curselection()]
        cibles  = [self._employeurs[i] for i in self._lb_cible.curselection()]
        if sources and cibles:
            cible = cibles[0]
            srcs  = [s for s in sources if s != cible]
            if srcs:
                self._lbl_statut.config(
                    text=f"{len(srcs)} source(s) → \"{cible}\"", fg="#1565C0")
                return
        self._lbl_statut.config(text="Sélectionnez des sources (gauche) et une cible (droite)", fg="#888")

    def _voir_docs(self, listbox: tk.Listbox):
        """Ouvre une fenêtre listant les PDFs liés à l'employeur double-cliqué."""
        sel = listbox.curselection()
        if not sel:
            return
        emp = self._employeurs[sel[-1]]
        if not self._dossier_base:
            messagebox.showinfo("Dossier non configuré",
                "Configurez le dossier de base dans Paramètres.", parent=self)
            return
        base = Path(self._dossier_base)
        pdfs = [str(p) for p in base.rglob("*.pdf") if emp in p.stem]
        if not pdfs:
            messagebox.showinfo(f"Documents — {emp}",
                f"Aucun PDF trouvé avec \"{emp}\" dans le nom.", parent=self)
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Documents — {emp} ({len(pdfs)} fichier(s))")
        dlg.geometry("700x340")
        sb = tk.Scrollbar(dlg)
        lb = tk.Listbox(dlg, yscrollcommand=sb.set, font=("Consolas", 9), height=18)
        sb.config(command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for p in sorted(pdfs):
            lb.insert(tk.END, p)
        def _ouvrir(event):
            idx = lb.curselection()
            if idx:
                import os
                os.startfile(pdfs[lb.curselection()[0]])
        lb.bind("<Double-1>", _ouvrir)
        tk.Label(dlg, text="Double-clic pour ouvrir un fichier",
                 fg="#888", font=("", 8)).pack(pady=(0, 6))

    def _appliquer(self):
        sources_idx = self._lb_sources.curselection()
        cible_idx   = self._lb_cible.curselection()
        if not sources_idx or not cible_idx:
            messagebox.showwarning("Sélection incomplète",
                "Sélectionnez au moins un nom source (gauche) ET le nom cible (droite).",
                parent=self)
            return
        cible   = self._employeurs[cible_idx[0]]
        sources = [self._employeurs[i] for i in sources_idx if self._employeurs[i] != cible]
        if not sources:
            messagebox.showwarning("Rien à fusionner",
                "Les noms source et cible sont identiques.", parent=self)
            return
        resume = "\n".join(f'  "{s}"  →  "{cible}"' for s in sources)
        if messagebox.askyesno("Confirmer la fusion",
                f"Fusionner :\n{resume}\n\nContinuer ?", parent=self):
            fusions = {s: cible for s in sources}
            self._callback(fusions)
            self.destroy()


# ---------------------------------------------------------------------------
# Onglet Employeurs connus
# ---------------------------------------------------------------------------
class OngletEmployeurs(tk.Frame):
    """
    Onglet de gestion de la liste des employeurs connus.
    Ces noms sont cherches directement dans les documents et ont priorite
    sur la detection automatique par Claude.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._employeurs = charger_employeurs()
        self._construire()

    def _construire(self):
        # En-tete explicatif
        tk.Label(self,
                 text="Les noms de cette liste sont recherches directement dans chaque document.\n"
                      "Ils ont priorite sur la detection automatique. "
                      "Double-clic pour modifier.",
                 fg="#555", font=("", 9), justify="left").pack(padx=14, pady=(10, 4), anchor="w")

        # Saisie rapide en haut
        frame_saisie = tk.Frame(self, pady=4)
        frame_saisie.pack(fill=tk.X, padx=14)
        tk.Label(frame_saisie, text="Ajouter un employeur :", width=20, anchor="w").pack(side=tk.LEFT)
        self.var_nom = tk.StringVar()
        entry = tk.Entry(frame_saisie, textvariable=self.var_nom, width=40, font=("", 10))
        entry.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda e: self._ajouter())
        tk.Button(frame_saisie, text="  Ajouter  ",
                  command=self._ajouter,
                  bg="#1976D2", fg="white", font=("", 9, "bold")).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=14, pady=4)

        # Liste principale
        frame_liste = tk.Frame(self)
        frame_liste.pack(fill=tk.BOTH, expand=True, padx=14, pady=2)

        scrollbar = tk.Scrollbar(frame_liste)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            frame_liste, yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE, font=("Consolas", 11),
            activestyle="dotbox", height=18,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<Double-1>", lambda e: self._editer())

        # Boutons d action
        frame_btn = tk.Frame(self, pady=6)
        frame_btn.pack(fill=tk.X, padx=14)
        tk.Button(frame_btn, text="Modifier",
                  command=self._editer, width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="Supprimer",
                  command=self._supprimer, width=12,
                  bg="#D32F2F", fg="white").pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="🔍 Scanner les documents",
                  command=self._scanner_depuis_docs,
                  bg="#1565C0", fg="white", padx=8).pack(side=tk.LEFT, padx=4)
        tk.Button(frame_btn, text="🔀 Fusionner doublons...",
                  command=self._fusionner_doublons,
                  bg="#6A1B9A", fg="white", padx=8).pack(side=tk.LEFT, padx=4)

        self.lbl_count = tk.Label(frame_btn, text="", fg="#555", font=("", 9))
        self.lbl_count.pack(side=tk.RIGHT, padx=8)

        self._rafraichir_liste()

    def _rafraichir_liste(self):
        self.listbox.delete(0, tk.END)
        for emp in self._employeurs:
            self.listbox.insert(tk.END, f"  {emp}")
        n = len(self._employeurs)
        self.lbl_count.config(text=f"{n} employeur(s) enregistre(s)")

    def _ajouter(self):
        nom = self.var_nom.get().strip()
        if not nom:
            return
        if nom not in self._employeurs:
            self._employeurs.append(nom)
            self._employeurs.sort()
            sauvegarder_employeurs(self._employeurs)
            self._rafraichir_liste()
            logger.info(f"[Employeur] Ajouté manuellement : {nom}")
        self.var_nom.set("")
        # Selectionner le nouvel employeur
        try:
            idx = self._employeurs.index(nom)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
        except ValueError:
            pass

    def _editer(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx    = sel[0]
        ancien = self._employeurs[idx]
        nouveau = simpledialog.askstring(
            "Modifier",
            "Nouveau nom :",
            initialvalue=ancien,
            parent=self,
        )
        if not nouveau or not nouveau.strip() or nouveau.strip() == ancien:
            return
        nouveau = nouveau.strip()
        self._employeurs[idx] = nouveau
        self._employeurs.sort()
        sauvegarder_employeurs(self._employeurs)
        self._rafraichir_liste()
        logger.info(f"[Employeur] Renommé : '{ancien}' -> '{nouveau}'")
        # Renommer les PDFs et mettre à jour traites.json
        self._appliquer_fusions({ancien: nouveau})

    def _supprimer(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        emp = self._employeurs[sel[0]]
        if messagebox.askyesno("Supprimer", f'Supprimer "{emp}" de la liste ?', parent=self):
            logger.info(f"[Employeur] Supprimé : '{emp}'")
            self._employeurs.pop(sel[0])
            sauvegarder_employeurs(self._employeurs)
            self._rafraichir_liste()

    def _scanner_depuis_docs(self):
        """Scanne les noms de fichiers PDF du dossier de base et extrait les employeurs."""
        cfg = charger_config()
        dossier = cfg.get("dossier_base", "").strip()
        if not dossier:
            dossier = filedialog.askdirectory(
                title="Choisir le dossier de documents classifiés", parent=self)
            if not dossier:
                return

        base = Path(dossier)
        if not base.exists():
            messagebox.showerror("Dossier introuvable", f"Le dossier n'existe pas :\n{dossier}", parent=self)
            return

        # Parser tous les noms de fichiers PDF
        nouveaux = []
        existants_lower = {e.lower() for e in self._employeurs}
        for pdf in base.rglob("*.pdf"):
            info = _parser_nom_doc(pdf.name)
            if not info:
                continue
            emp = info.get("employeur", "").strip()
            if (emp and emp != "INCONNU"
                    and emp.lower() not in existants_lower
                    and emp.lower() not in {n.lower() for n in nouveaux}):
                nouveaux.append(emp)

        if not nouveaux:
            messagebox.showinfo("Scan terminé",
                "Aucun nouvel employeur trouvé dans les noms de fichiers.", parent=self)
            return

        # Afficher la liste et demander confirmation
        resume = "\n".join(f"  • {e}" for e in sorted(nouveaux)[:20])
        if len(nouveaux) > 20:
            resume += f"\n  … et {len(nouveaux) - 20} autre(s)"
        if messagebox.askyesno("Nouveaux employeurs trouvés",
                f"{len(nouveaux)} nouvel(aux) employeur(s) trouvé(s) :\n\n{resume}\n\n"
                "Ajouter tous à la liste ?", parent=self):
            self._employeurs.extend(nouveaux)
            self._employeurs.sort()
            sauvegarder_employeurs(self._employeurs)
            self._rafraichir_liste()
            messagebox.showinfo("Ajout terminé",
                f"{len(nouveaux)} employeur(s) ajouté(s).", parent=self)

    def _fusionner_doublons(self):
        """Ouvre la fenêtre de fusion manuelle à 2 colonnes."""
        if not self._employeurs:
            messagebox.showinfo("Liste vide", "Aucun employeur enregistré.", parent=self)
            return
        cfg = charger_config()
        dossier_base = cfg.get("dossier_base", "")
        DialogueFusionEmployeurs(self, self._employeurs, dossier_base, self._appliquer_fusions)

    def _appliquer_fusions(self, fusions: dict):
        """fusions = {ancien_nom: nom_cible, ...} — met à jour la liste ET renomme les PDFs."""
        for ancien, cible in fusions.items():
            if ancien in self._employeurs and ancien != cible:
                self._employeurs.remove(ancien)
                if cible not in self._employeurs:
                    self._employeurs.append(cible)
        self._employeurs.sort()
        sauvegarder_employeurs(self._employeurs)
        self._rafraichir_liste()

        # Renommer les PDFs classifiés qui contiennent l'ancien nom
        cfg = charger_config()
        dossier_base = cfg.get("dossier_base", "")
        if not dossier_base:
            return
        base = Path(dossier_base)
        if not base.exists():
            return

        # Charger traites.json pour mettre à jour les références après renommage
        traites = charger_traites()

        nb_renommes = 0
        erreurs = []
        for ancien, cible in fusions.items():
            if ancien == cible:
                continue
            for pdf in list(base.rglob("*.pdf")):
                nom = pdf.stem
                if ancien not in nom:
                    continue
                nouveau_nom = nom.replace(ancien, cible) + ".pdf"
                nouveau_chemin = pdf.parent / nouveau_nom
                if nouveau_chemin.resolve() == pdf.resolve():
                    continue
                # Destination existe déjà = doublon, la source est obsolète → supprimer
                if nouveau_chemin.exists():
                    try:
                        pdf.unlink()
                        nb_renommes += 1
                        logger.info(f"[Fusion] Doublon supprimé : {pdf.name}")
                        # Supprimer aussi l'entrée traites.json de l'ancien fichier
                        for empreinte, info in list(traites.items()):
                            if info.get("nom_fichier") == pdf.name:
                                del traites[empreinte]
                                break
                    except Exception as e:
                        erreurs.append(f"{pdf.name} (suppression doublon): {e}")
                        logger.error(f"[Fusion] Erreur suppression doublon : {pdf.name} — {e}")
                    continue
                try:
                    pdf.rename(nouveau_chemin)
                    nb_renommes += 1
                    logger.info(f"[Fusion] Renommé : {pdf.name} -> {nouveau_nom}")
                    # Mettre à jour traites.json : chercher l'entrée par nom_fichier
                    for empreinte, info in traites.items():
                        if info.get("nom_fichier") == pdf.name:
                            info["nom_fichier"] = nouveau_nom
                            info["chemin_destination"] = str(nouveau_chemin)
                            break
                except Exception as e:
                    erreurs.append(f"{pdf.name}: {e}")
                    logger.error(f"[Fusion] Erreur renommage : {pdf.name} — {e}")

        # Sauvegarder traites.json mis à jour
        if nb_renommes:
            from config import TRAITES_FILE
            import json as _json
            with open(TRAITES_FILE, "w", encoding="utf-8") as f:
                _json.dump(traites, f, indent=2, ensure_ascii=False)

        if nb_renommes or erreurs:
            msg = f"{nb_renommes} fichier(s) traité(s) (renommés ou doublons supprimés)."
            if erreurs:
                msg += f"\n\n{len(erreurs)} erreur(s) :\n" + "\n".join(erreurs)
                DialogueRapport.afficher(self, "Fusion — erreurs", msg)
            else:
                messagebox.showinfo("Fusion terminée", msg, parent=self)

    def recharger(self):
        """Recharge depuis le fichier (appele apres import ou modif externe)."""
        self._employeurs = charger_employeurs()
        self._rafraichir_liste()


# ---------------------------------------------------------------------------
# Onglet Scan & Déplacement
# ---------------------------------------------------------------------------
class OngletScan(tk.Frame):
    """
    Scanne un dossier source à la recherche de fichiers déjà classifiés
    (nommés selon la convention IntermitDoc) et les déplace vers le dossier
    de base en respectant la structure ANNEE/MM Mois/TYPE/.
    """

    COL = [
        ("type",       "Type",        50),
        ("date_debut", "Date début",  95),
        ("employeur",  "Employeur",  200),
        ("heures",     "Heures",      60),
        ("salaire",    "Salaire",     80),
        ("source",     "Fichier source", 300),
        ("statut",     "Statut",      100),
    ]

    def __init__(self, parent, cfg_getter, **kwargs):
        super().__init__(parent, **kwargs)
        self._cfg_getter = cfg_getter
        self._docs: list = []   # [{"info": dict, "chemin": str, "statut": str}, ...]
        self._construire()

    def _construire(self):
        # ── Barre du haut ──────────────────────────────────────────────────
        frame_top = tk.LabelFrame(self, text="Dossiers", padx=8, pady=6)
        frame_top.pack(fill=tk.X, padx=10, pady=(8, 4))

        # Dossier source
        row1 = tk.Frame(frame_top)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Dossier à scanner :", width=18, anchor="w").pack(side=tk.LEFT)
        self.var_source = tk.StringVar()
        tk.Entry(row1, textvariable=self.var_source, width=55).pack(
            side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        tk.Button(row1, text="Parcourir...",
                  command=self._choisir_source).pack(side=tk.LEFT, padx=2)
        tk.Button(row1, text="🔍 Scanner",
                  command=self._scanner,
                  bg="#1976D2", fg="white", padx=8).pack(side=tk.LEFT, padx=4)

        # Dossier de sortie
        row2 = tk.Frame(frame_top)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Dossier de sortie :", width=18, anchor="w").pack(side=tk.LEFT)
        cfg = self._cfg_getter()
        self.var_sortie = tk.StringVar(value=cfg.get("dossier_base", ""))
        tk.Entry(row2, textvariable=self.var_sortie, width=55).pack(
            side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        tk.Button(row2, text="Parcourir...",
                  command=self._choisir_sortie).pack(side=tk.LEFT, padx=2)
        tk.Label(row2, text="(dossier de base par défaut)",
                 fg="#888", font=("", 8)).pack(side=tk.LEFT, padx=6)

        # ── Rattrapage heures/salaire AEM → BP ───────────────────────────────
        row3 = tk.Frame(frame_top)
        row3.pack(fill=tk.X, pady=(6, 2))
        tk.Button(row3, text="🔗 Synchroniser AEM ↔ BP (heures/salaire)",
                  command=self._synchroniser_aem_bp,
                  bg="#5E35B1", fg="white", padx=8).pack(side=tk.LEFT)
        tk.Label(row3,
                 text="Complète les BP dont les heures/salaire manquent, "
                      "à partir de l'AEM du même mois/employeur.",
                 fg="#888", font=("", 8)).pack(side=tk.LEFT, padx=6)

        # ── Tableau ────────────────────────────────────────────────────────
        frame_tree = tk.LabelFrame(self, text="Fichiers classifiés trouvés", padx=4, pady=4)
        frame_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        sv = tk.Scrollbar(frame_tree, orient=tk.VERTICAL)
        sh = tk.Scrollbar(frame_tree, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            frame_tree,
            columns=[c[0] for c in self.COL],
            show="headings",
            yscrollcommand=sv.set,
            xscrollcommand=sh.set,
            selectmode="extended",
        )
        sv.config(command=self.tree.yview)
        sh.config(command=self.tree.xview)
        for col_id, col_titre, col_larg in self.COL:
            self.tree.column(col_id, width=col_larg, minwidth=40,
                             stretch=(col_id in ("employeur", "source")))
            self.tree.heading(col_id, text=col_titre)
        self.tree.tag_configure("ok",      background="#E8F5E9")
        self.tree.tag_configure("erreur",  background="#FFEBEE")
        self.tree.tag_configure("deplace", background="#E3F2FD", foreground="#555")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sv.grid(row=0, column=1, sticky="ns")
        sh.grid(row=1, column=0, sticky="ew")
        frame_tree.grid_rowconfigure(0, weight=1)
        frame_tree.grid_columnconfigure(0, weight=1)

        self._tri = _installer_tri(self.tree,
                                   [c[0] for c in self.COL if c[0] != "statut"])

        # ── Pied ───────────────────────────────────────────────────────────
        frame_pied = tk.Frame(self, pady=6)
        frame_pied.pack(fill=tk.X, padx=10)

        self._lbl_pied = tk.Label(frame_pied, text="Aucun fichier scanné.", fg="#555", font=("", 9))
        self._lbl_pied.pack(side=tk.LEFT)

        tk.Button(frame_pied, text="Tout sélectionner",
                  command=self._tout_selectionner).pack(side=tk.RIGHT, padx=4)
        tk.Button(frame_pied, text="📦 Déplacer la sélection",
                  command=self._deplacer_selection,
                  bg="#2E7D32", fg="white", padx=10, pady=4,
                  font=("", 9, "bold")).pack(side=tk.RIGHT, padx=4)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _choisir_source(self):
        d = filedialog.askdirectory(title="Dossier à scanner")
        if d:
            self.var_source.set(d)

    def _choisir_sortie(self):
        d = filedialog.askdirectory(title="Dossier de sortie (dossier de base)")
        if d:
            self.var_sortie.set(d)

    def _synchroniser_aem_bp(self):
        cfg = self._cfg_getter()
        dossier = self.var_sortie.get().strip() or cfg.get("dossier_base", "")
        if not dossier or not Path(dossier).is_dir():
            messagebox.showwarning(
                "Dossier invalide",
                "Sélectionnez un dossier de sortie valide.", parent=self)
            return
        if not messagebox.askyesno(
            "Synchroniser AEM ↔ BP",
            f"Parcourir {dossier} et compléter les BP dont les heures/salaire "
            "manquent avec les valeurs de l'AEM correspondant (même mois, "
            "même employeur) ?\n\nLes fichiers déjà complets ne sont pas "
            "modifiés.", parent=self):
            return
        rapport = synchroniser_aem_vers_bp(dossier)
        n_sync = len(rapport["synchronises"])
        n_sans = len(rapport["sans_correspondance"])
        detail = ""
        if rapport["synchronises"]:
            detail += "Synchronisés :\n" + "\n".join(
                f"  • {n}" for n in rapport["synchronises"][:30])
            if n_sync > 30:
                detail += f"\n  … et {n_sync - 30} de plus"
        if rapport["sans_correspondance"]:
            if detail:
                detail += "\n\n"
            detail += "Sans AEM correspondant :\n" + "\n".join(
                f"  • {n}" for n in rapport["sans_correspondance"][:15])
            if n_sans > 15:
                detail += f"\n  … et {n_sans - 15} de plus"
        messagebox.showinfo(
            "Synchronisation terminée",
            f"{n_sync} BP complété(s).\n{n_sans} sans AEM correspondant.\n\n"
            + (detail or "Tous les BP étaient déjà complets."),
            parent=self)

    def _scanner(self):
        source = self.var_source.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showwarning("Dossier invalide",
                "Sélectionnez un dossier source valide.", parent=self)
            return

        # Mettre à jour le dossier de sortie depuis la config si vide
        if not self.var_sortie.get().strip():
            cfg = self._cfg_getter()
            self.var_sortie.set(cfg.get("dossier_base", ""))

        # Vider le tableau
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._docs.clear()

        from classifier import lire_metadata_intermitdoc

        base = Path(source)
        trouves = 0
        for pdf in sorted(base.rglob("*.pdf")):
            # Détection uniquement par métadonnée PDF IntermitDoc
            meta = lire_metadata_intermitdoc(str(pdf))
            if not meta:
                continue

            annee = meta.get("annee", "")
            mois  = meta.get("mois",  "")
            # Contrat chevauchant deux mois (AEM) : la date de début a son
            # propre mois/année si différent du mois de classement.
            annee_d = meta.get("annee_debut", "") or annee
            mois_d  = meta.get("mois_debut", "") or mois
            jour_debut = meta.get("date_debut", "")
            jour_fin   = meta.get("date_fin", "") or jour_debut
            info = {
                "type":       meta.get("type", ""),
                "date_debut": (f"{annee_d}-{mois_d}-{jour_debut}" if jour_debut
                               else f"{annee}-{mois}-01" if annee and mois else ""),
                "date_fin":   f"{annee}-{mois}-{jour_fin}" if jour_fin else "",
                "employeur":  meta.get("employeur", ""),
                "heures":     meta.get("heures", ""),
                "salaire":    meta.get("salaire", ""),
                "annee":      annee,
                "mois":       mois,
            }

            if not info.get("type") or info.get("type") == "INCONNU":
                continue

            doc = {"info": info, "chemin": str(pdf), "statut": "En attente"}
            self._docs.append(doc)
            h = info.get("heures", "")
            s = info.get("salaire", "")
            statut_lbl = "✓ métadonnée"
            self.tree.insert("", tk.END, iid=str(len(self._docs) - 1), values=(
                info.get("type", ""),
                info.get("date_debut", ""),
                info.get("employeur", ""),
                f"{h}h" if h else "—",
                f"{s}€" if s else "—",
                str(pdf),
                statut_lbl,
            ), tags=("ok",))
            trouves += 1

        self._lbl_pied.config(
            text=f"{trouves} fichier(s) IntermitDoc trouvé(s) — "
                 "sélectionnez puis cliquez Déplacer.")
        if trouves:
            self._tout_selectionner()

    def _tout_selectionner(self):
        for item in self.tree.get_children():
            self.tree.selection_add(item)

    def _deplacer_selection(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Rien sélectionné",
                "Sélectionnez d'abord les fichiers à déplacer.", parent=self)
            return

        sortie = self.var_sortie.get().strip()
        if not sortie:
            messagebox.showwarning("Dossier de sortie manquant",
                "Configurez le dossier de sortie (dossier de base).", parent=self)
            return

        if not messagebox.askyesno(
            "Confirmer le déplacement",
            f"Déplacer {len(sel)} fichier(s) vers la structure IntermitDoc ?\n\nCette action est irréversible.",
            icon="warning",
            parent=self,
        ):
            return

        base_sortie = Path(sortie)
        nb_ok = nb_err = 0

        for iid in sel:
            idx = int(iid)
            doc = self._docs[idx]
            if doc["statut"] == "Déplacé":
                continue

            info    = doc["info"]
            chemin  = Path(doc["chemin"])
            type_doc = info.get("type", "INCONNU")
            # Utiliser annee/mois directement (date_debut peut être juste le jour "01")
            annee = info.get("annee", "") or info.get("date_debut", "")[:4] or "0000"
            mois  = info.get("mois",  "") or info.get("date_debut", "")[5:7] or "00"
            nom_mois = MOIS_DOSSIERS.get(mois, mois)

            # Structure : dossier_base / ANNEE / MM Mois / TYPE /
            dest_dossier = base_sortie / annee / nom_mois / type_doc
            dest_dossier.mkdir(parents=True, exist_ok=True)
            dest_fichier = dest_dossier / chemin.name

            # Éviter d'écraser si identique
            if dest_fichier == chemin:
                doc["statut"] = "Déjà en place"
                self._maj_ligne(iid, "Déjà en place", "deplace")
                nb_ok += 1
                continue

            try:
                import shutil
                shutil.move(str(chemin), str(dest_fichier))
                doc["statut"] = "Déplacé"
                doc["chemin"] = str(dest_fichier)
                self._maj_ligne(iid, f"→ {annee}/{nom_mois}/{type_doc}", "deplace")
                logger.info(f"[Scan] Déplacé : {Path(chemin).name} -> {annee}/{nom_mois}/{type_doc}/")
                nb_ok += 1
            except Exception as e:
                doc["statut"] = f"Erreur"
                self._maj_ligne(iid, f"Erreur: {str(e)[:30]}", "erreur")
                logger.error(f"[Scan] Erreur déplacement : {Path(chemin).name} — {e}")
                nb_err += 1

        msg = f"{nb_ok} fichier(s) déplacé(s)."
        if nb_err:
            msg += f"\n{nb_err} erreur(s)."
        self._lbl_pied.config(text=msg)
        if nb_err:
            rapport = msg + "\n\nDétail des erreurs :\n" + "\n".join(
                f"  {self.tree.item(iid, 'values')[0]}" for iid in sel
                if self.tree.item(iid, 'tags') and 'erreur' in self.tree.item(iid, 'tags')
            )
            DialogueRapport.afficher(self, "Déplacement — erreurs", rapport)
        else:
            messagebox.showinfo("Déplacement terminé", msg, parent=self)

    def _maj_ligne(self, iid: str, statut: str, tag: str):
        vals = list(self.tree.item(iid, "values"))
        vals[6] = statut
        self.tree.item(iid, values=vals, tags=(tag,))


# ---------------------------------------------------------------------------
# Déduplication prévisionnels vs AEM classifiés
# ---------------------------------------------------------------------------
# Guard to prevent _deduplication_previsionnels from running twice per cycle
# (OngletSuivi and OngletRecap can both trigger it on the same refresh).
_dedup_en_cours = False

def _employeurs_correspondent(a: str, b: str) -> bool:
    """
    Compare deux noms d'employeur (déjà normalisés en minuscules) en
    tolérant la troncature héritée d'un ancien bug de métadonnées PDF
    (ex: "muzik" au lieu de "muzik event") — préfixe dans un sens ou
    l'autre, en plus de l'égalité stricte.
    """
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _deduplication_previsionnels(docs_reels: list) -> dict:
    """
    Compare les prévisionnels avec les AEM réels.

    Niveau 1 (match fort) : annee + mois + employeur + date_debut identiques
      → supprimé automatiquement de previsionnels.json
    Niveau 2 (chevauchement) : meme annee + mois + employeur, dates qui se
      chevauchent mais date_debut différente (ex: un AEM multi-jours couvrant
      plusieurs prévisionnels saisis un par un) → supprimé automatiquement
      aussi, mais listé séparément dans le rapport pour rester traçable

    Retourne un dict :
      {
        "supprimes":      [prev, ...],   # supprimés — match exact
        "conflits":       [(prev, reel), ...],  # supprimés — chevauchement
        "en_attente":     [prev, ...],   # prévisionnels non touchés
      }
    """
    from previsionnel import (charger_previsionnels, supprimer_previsionnel,
                              _periodes_se_chevauchent)

    prevs = charger_previsionnels()
    aems  = [d for d in docs_reels if d.get("type") == "AEM"]

    supprimes = []
    conflits  = []
    restes    = []

    for prev in prevs:
        pa = prev.get("annee", "")
        pm = prev.get("mois",  "")
        pe = (prev.get("employeur") or "").strip().lower()
        pd = prev.get("date_debut", "")
        # Le prévisionnel ne stocke que le jour ("22") ; les docs réels ont la
        # date ISO complète ("2026-06-22") — reconstruire pour comparer juste.
        pd_full = f"{pa}-{pm}-{pd}" if pd and len(pd) == 2 else pd

        match_fort = False
        for reel in aems:
            ra = reel.get("annee", "")
            rm = reel.get("mois",  "")
            re_emp = (reel.get("employeur") or "").strip().lower()
            rd = reel.get("date_debut", "")

            if pa == ra and pm == rm and _employeurs_correspondent(pe, re_emp) and pd_full == rd:
                match_fort = True
                break

        if match_fort:
            supprimer_previsionnel(prev.get("id", ""))
            supprimes.append(prev)
            continue

        # Niveau 2 : chercher chevauchement
        conflit_trouve = None
        for reel in aems:
            ra = reel.get("annee", "")
            rm = reel.get("mois",  "")
            re_emp = (reel.get("employeur") or "").strip().lower()

            if pa != ra or pm != rm or not _employeurs_correspondent(pe, re_emp):
                continue

            # Construire des dicts avec des dates complètes pour la comparaison
            prev_c = {
                "date_debut": f"{pa}-{pm}-{pd}" if pd and len(pd) == 2 else prev.get("date_debut", ""),
                "date_fin":   f"{pa}-{pm}-{prev.get('date_fin', pd)}" if prev.get("date_fin") else f"{pa}-{pm}-{pd}",
            }
            reel_c = {
                "date_debut": reel.get("date_debut", ""),
                "date_fin":   reel.get("date_fin", reel.get("date_debut", "")),
            }
            if _periodes_se_chevauchent(prev_c, reel_c):
                conflit_trouve = reel
                break

        if conflit_trouve:
            supprimer_previsionnel(prev.get("id", ""))
            conflits.append((prev, conflit_trouve))
        else:
            restes.append(prev)

    return {"supprimes": supprimes, "conflits": conflits, "en_attente": restes}


def _prevs_mois_courant_et_precedent(en_attente: list) -> list:
    """Filtre les prévisionnels du mois courant et du mois précédent."""
    from datetime import date
    today = date.today()
    # Mois courant
    ac, mc = str(today.year), f"{today.month:02d}"
    # Mois précédent
    if today.month == 1:
        ap, mp = str(today.year - 1), "12"
    else:
        ap, mp = str(today.year), f"{today.month - 1:02d}"

    return [
        p for p in en_attente
        if (p.get("annee") == ac and p.get("mois") == mc)
        or (p.get("annee") == ap and p.get("mois") == mp)
    ]


class _DialogueRapportDedup(tk.Toplevel):
    """Rapport après déduplication prévisionnels vs AEM classifiés."""

    def __init__(self, parent, supprimes: list, conflits: list,
                 en_attente_visibles: list):
        super().__init__(parent)
        self.title("Rapport — Prévisionnels & Contrats classifiés")
        self.resizable(True, True)
        self.geometry("560x480")
        self.grab_set()
        self._construire(supprimes, conflits, en_attente_visibles)
        self.transient(parent)

    def _construire(self, supprimes, conflits, en_attente):
        txt = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Consolas", 9),
                                        padx=8, pady=8)
        txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        MOIS_NOMS = {
            "01":"Janvier","02":"Février","03":"Mars","04":"Avril",
            "05":"Mai","06":"Juin","07":"Juillet","08":"Août",
            "09":"Septembre","10":"Octobre","11":"Novembre","12":"Décembre",
        }

        def _fmt(p):
            a = p.get("annee","?")
            m = MOIS_NOMS.get(p.get("mois",""),"?")
            e = p.get("employeur","?")
            d = p.get("date_debut","")
            h = p.get("heures","")
            return f"  • {a}/{m} — {e}{' le '+d if d else ''}{' — '+h+'h' if h else ''}"

        if supprimes:
            txt.insert(tk.END, f"✓ {len(supprimes)} prévisionnel(s) supprimé(s) automatiquement\n")
            txt.insert(tk.END, "  (contrat réel trouvé avec même employeur, même date)\n\n")
            for p in supprimes:
                txt.insert(tk.END, _fmt(p) + "\n")
            txt.insert(tk.END, "\n")
        else:
            txt.insert(tk.END, "✓ Aucun doublon exact détecté.\n\n")

        if conflits:
            txt.insert(tk.END, f"✓ {len(conflits)} prévisionnel(s) supprimé(s) par chevauchement\n")
            txt.insert(tk.END, "  (couverts par un contrat réel du même mois/employeur, "
                                "sans correspondance exacte — ex: AEM multi-jours)\n\n")
            for prev, reel in conflits:
                txt.insert(tk.END, f"  Prévisionnel :\n{_fmt(prev)}\n")
                txt.insert(tk.END, f"  Contrat réel  :\n{_fmt(reel)}\n\n")

        if en_attente:
            txt.insert(tk.END,
                       f"⏳ {len(en_attente)} prévisionnel(s) en attente "
                       f"(mois courant / mois précédent)\n\n")
            for p in en_attente:
                txt.insert(tk.END, _fmt(p) + "\n")
        elif not conflits and not supprimes:
            txt.insert(tk.END,
                       "Aucun prévisionnel en attente pour le mois courant "
                       "et le mois précédent.\n")

        txt.config(state=tk.DISABLED)

        tk.Button(self, text="Fermer", command=self.destroy,
                  width=12, pady=4).pack(pady=(0, 8))


# ---------------------------------------------------------------------------
# Onglet Historique — navigation année/mois + édition contrats AEM
# ---------------------------------------------------------------------------
from previsionnel import (
    charger_previsionnels  as _charger_previsions,
    sauvegarder_previsionnels as _sauvegarder_previsions,
    ajouter_previsionnel   as _ajouter_previsionnel_hist,
    supprimer_previsionnel as _supprimer_previsionnel_hist,
    _periodes_se_chevauchent,
)
from agenda import (
    charger_config_agenda, sauvegarder_config_agenda, importer_evenements,
    telecharger_ics, parser_ics,
)


class OngletHistorique(tk.Frame):
    """
    Navigation par année/mois dans les contrats AEM classifiés.
    Affiche la liste, l'aperçu PDF et permet l'édition des métadonnées.
    Les contrats prévisionnels sont stockés dans previsions.json.
    """

    MOIS_LABELS = [
        ("01", "Janvier"), ("02", "Février"), ("03", "Mars"),
        ("04", "Avril"),   ("05", "Mai"),      ("06", "Juin"),
        ("07", "Juillet"), ("08", "Août"),     ("09", "Septembre"),
        ("10", "Octobre"), ("11", "Novembre"), ("12", "Décembre"),
    ]
    MOIS_NUM   = [m for m, _ in MOIS_LABELS]
    MOIS_NOMS  = {m: n for m, n in MOIS_LABELS}

    COL = [
        ("date_debut","Date début",   80),
        ("date_fin",  "Date fin",     80),
        ("employeur", "Employeur",   150),
        ("heures",    "Heures",       60),
        ("salaire",   "Salaire",      80),
        ("statut",    "Statut",       90),
    ]

    def __init__(self, parent, cfg_getter):
        super().__init__(parent)
        self._cfg_getter  = cfg_getter
        self._annee_var   = tk.StringVar()
        self._mois_var    = tk.StringVar()
        self._contrats    : list = []   # [{"chemin":..., "info":..., "previsionnel": bool}]
        self._chemin_ouvert: str = ""
        self._construire()

    # ── Construction UI ─────────────────────────────────────────────────────

    def _construire(self):
        # ── Barre navigation ────────────────────────────────────────────────
        nav = tk.Frame(self, pady=6, padx=10, relief=tk.RAISED, bd=1)
        nav.pack(fill=tk.X)

        tk.Button(nav, text="◀", width=3, command=lambda: self._naviguer(-1),
                  font=("", 11, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        tk.Label(nav, text="Année :").pack(side=tk.LEFT)
        self._cb_annee = ttk.Combobox(nav, textvariable=self._annee_var,
                                      width=7, state="readonly")
        self._cb_annee.pack(side=tk.LEFT, padx=(2, 10))
        self._cb_annee.bind("<<ComboboxSelected>>", lambda e: self._on_annee_change())

        tk.Label(nav, text="Mois :").pack(side=tk.LEFT)
        self._cb_mois = ttk.Combobox(nav, textvariable=self._mois_var,
                                     width=14, state="readonly")
        self._cb_mois.pack(side=tk.LEFT, padx=(2, 4))
        self._cb_mois.bind("<<ComboboxSelected>>", lambda e: self._actualiser_liste())

        tk.Button(nav, text="▶", width=3, command=lambda: self._naviguer(+1),
                  font=("", 11, "bold")).pack(side=tk.LEFT, padx=(4, 20))

        tk.Button(nav, text="🔄 Actualiser", command=self._actualiser_liste,
                  pady=2).pack(side=tk.LEFT, padx=4)

        tk.Button(nav, text="🔍 Scanner doublons du mois",
                  command=self._scanner_doublons_mois,
                  bg="#7B1FA2", fg="white",
                  pady=2, padx=6).pack(side=tk.LEFT, padx=4)

        tk.Button(nav, text="+ Contrat Futur",
                  bg="#1565C0", fg="white", font=("", 9, "bold"),
                  command=self._creer_previsionnel,
                  pady=2, padx=8).pack(side=tk.RIGHT, padx=6)

        tk.Button(nav, text="📅 Agenda...",
                  bg="#00838F", fg="white", font=("", 9, "bold"),
                  command=self._ouvrir_dialogue_agenda,
                  pady=2, padx=8).pack(side=tk.RIGHT, padx=6)

        # ── Corps principal : liste à gauche, formulaire à droite ──────────
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Panneau gauche : liste ───────────────────────────────────────────
        frame_liste = tk.Frame(paned)
        paned.add(frame_liste, minsize=320)

        cols = [c[0] for c in self.COL]
        self.tree = ttk.Treeview(frame_liste, columns=cols, show="headings",
                                 selectmode="extended")
        for cid, label, w in self.COL:
            self.tree.heading(cid, text=label)
            self.tree.column(cid, width=w, minwidth=40, anchor="w")

        self.tree.tag_configure("previsionnel", foreground="#888888",
                                font=("", 9, "italic"))
        self.tree.tag_configure("classifie",   foreground="#1a5276")

        sb_l = tk.Scrollbar(frame_liste, orient=tk.VERTICAL,
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_l.set)
        sb_l.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>",  self._on_double_clic)
        self.tree.bind("<Button-3>",         self._on_clic_droit)

        self._tri = _installer_tri(self.tree, [c[0] for c in self.COL
                                               if c[0] != "statut"])

        # Menu contextuel clic droit
        self._menu_ctx = tk.Menu(self, tearoff=0)
        self._menu_ctx.add_command(
            label="📄  Ouvrir le document",
            command=self._ouvrir_pdf_fenetre)
        self._menu_ctx.add_command(
            label="📁  Ouvrir le dossier dans l'Explorateur",
            command=self._ouvrir_dossier_explorateur)
        self._menu_ctx.add_separator()
        self._menu_ctx.add_command(
            label="📋  Dupliquer vers d'autres dates...",
            command=self._dupliquer_contrat)
        self._menu_ctx.add_separator()
        self._menu_ctx.add_command(
            label="💾  Enregistrer les modifications",
            command=self._sauvegarder)
        self._menu_ctx.add_command(
            label="🗑  Supprimer le(s) prévisionnel(s) sélectionné(s)",
            command=self._supprimer_previsionnel)

        # ── Panneau droit : formulaire seul ──────────────────────────────────
        frame_detail = tk.Frame(paned)
        paned.add(frame_detail, minsize=320)

        # Formulaire d'édition
        frame_form = tk.LabelFrame(frame_detail, text="  Détails du contrat  ",
                                   padx=8, pady=6)
        frame_form.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        champs = [
            ("type",      "Type",         ["AEM", "BP", "CS", "CT", "STC"]),
            ("annee",     "Année",        None),
            ("mois",      "Mois",         list(self.MOIS_NUM)),
            ("employeur", "Employeur",    sorted(charger_employeurs())),
            ("date_debut","Date début",   None),
            ("date_fin",  "Date fin",     None),
            ("heures",    "Heures",       None),
            ("salaire",   "Salaire brut", None),
        ]
        self._vars_form: dict[str, tk.StringVar] = {}
        self._widgets_form: dict[str, tk.Widget] = {}

        for row_idx, (key, label, options) in enumerate(champs):
            tk.Label(frame_form, text=label + " :", anchor="e",
                     width=13).grid(row=row_idx, column=0, sticky="e",
                                    pady=2, padx=(0, 4))
            var = tk.StringVar()
            self._vars_form[key] = var
            if options:
                w = ttk.Combobox(frame_form, textvariable=var,
                                 values=options, width=18, state="normal")
            else:
                w = tk.Entry(frame_form, textvariable=var, width=20)
            w.grid(row=row_idx, column=1, sticky="w", pady=2)
            self._widgets_form[key] = w

        # Champ note (uniquement prévisionnels)
        tk.Label(frame_form, text="Note :", anchor="e",
                 width=13).grid(row=len(champs), column=0, sticky="ne",
                                pady=2, padx=(0, 4))
        self._var_note = tk.StringVar()
        self._txt_note = tk.Entry(frame_form, textvariable=self._var_note,
                                  width=30)
        self._txt_note.grid(row=len(champs), column=1, sticky="w", pady=2)

        # Boutons bas de formulaire
        frame_btns = tk.Frame(frame_form)
        frame_btns.grid(row=len(champs) + 1, column=0, columnspan=2,
                        pady=(8, 2))

        self._btn_save = tk.Button(frame_btns, text="💾 Enregistrer",
                                   bg="#1B5E20", fg="white", font=("", 9, "bold"),
                                   command=self._sauvegarder, state=tk.DISABLED,
                                   padx=8, pady=4)
        self._btn_save.pack(side=tk.LEFT, padx=4)

        self._btn_delete = tk.Button(frame_btns, text="🗑 Supprimer prévision",
                                     bg="#B71C1C", fg="white", font=("", 9),
                                     command=self._supprimer_previsionnel,
                                     state=tk.DISABLED, padx=6, pady=4)
        self._btn_delete.pack(side=tk.LEFT, padx=4)

        self._lbl_status = tk.Label(frame_form, text="", fg="#555555",
                                    font=("", 8))
        self._lbl_status.grid(row=len(champs) + 2, column=0, columnspan=2)

        # Initialisation
        self.after(200, self._init_navigation)

    # ── Navigation ──────────────────────────────────────────────────────────

    def _init_navigation(self):
        annees = self._lister_annees()
        if not annees:
            self._cb_annee["values"] = []
            self._cb_mois["values"]  = []
            return
        self._cb_annee["values"] = annees
        annee_courante = str(_date_today.today().year)
        self._annee_var.set(annee_courante if annee_courante in annees
                            else annees[-1])
        self._on_annee_change()

    def _lister_annees(self) -> list[str]:
        cfg  = self._cfg_getter()
        base = Path(cfg.get("dossier_base", ""))
        annees = set()
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and re.fullmatch(r"\d{4}", d.name):
                    annees.add(d.name)
        # Ajouter les années des prévisionnels
        for p in _charger_previsions():
            a = p.get("annee", "")
            if a:
                annees.add(a)
        return sorted(annees)

    def _on_annee_change(self):
        annee = self._annee_var.get()
        mois_labels = [f"{m} {self.MOIS_NOMS[m]}" for m in self.MOIS_NUM]
        self._cb_mois["values"] = mois_labels
        # Aller au mois courant si l'année correspond
        mois_courant = f"{_date_today.today().month:02d}"
        label_courant = f"{mois_courant} {self.MOIS_NOMS[mois_courant]}"
        if str(_date_today.today().year) == annee:
            self._mois_var.set(label_courant)
        elif not self._mois_var.get():
            self._mois_var.set(mois_labels[0])
        else:
            # Conserver le mois sélectionné si valide
            if self._mois_var.get() not in mois_labels:
                self._mois_var.set(mois_labels[0])
        self._actualiser_liste()

    def _mois_num_courant(self) -> str:
        val = self._mois_var.get()
        if val and " " in val:
            return val.split(" ")[0]
        return val[:2] if val else "01"

    def _naviguer(self, delta: int):
        annee = self._annee_var.get()
        mois  = self._mois_num_courant()
        if not annee or not mois:
            return
        try:
            idx = self.MOIS_NUM.index(mois)
        except ValueError:
            return
        idx += delta
        if idx < 0:
            nouvelle_annee = str(int(annee) - 1)
            idx = 11
        elif idx > 11:
            nouvelle_annee = str(int(annee) + 1)
            idx = 0
        else:
            nouvelle_annee = annee

        annees = list(self._cb_annee["values"])
        if nouvelle_annee not in annees:
            annees.append(nouvelle_annee)
            annees.sort()
            self._cb_annee["values"] = annees
        self._annee_var.set(nouvelle_annee)

        nouveau_mois = self.MOIS_NUM[idx]
        self._mois_var.set(f"{nouveau_mois} {self.MOIS_NOMS[nouveau_mois]}")
        self._actualiser_liste()

    # ── Chargement liste ────────────────────────────────────────────────────

    def _actualiser_liste(self):
        self.tree.delete(*self.tree.get_children())
        self._contrats = []
        self._vider_detail()

        annee = self._annee_var.get()
        mois  = self._mois_num_courant()
        if not annee or not mois:
            return

        cfg  = self._cfg_getter()
        base = Path(cfg.get("dossier_base", ""))

        # Fichiers classifiés AEM du dossier
        nom_mois_dossier = MOIS_DOSSIERS.get(mois, "")
        if nom_mois_dossier and base.exists():
            dossier_aem = base / annee / nom_mois_dossier / "AEM"
            if dossier_aem.exists():
                for pdf in sorted(dossier_aem.glob("*.pdf")):
                    meta = lire_metadata_intermitdoc(str(pdf))
                    if meta:
                        info = {
                            "type":       meta.get("type", "AEM"),
                            "annee":      meta.get("annee", annee),
                            "mois":       meta.get("mois", mois),
                            "employeur":  meta.get("employeur", ""),
                            "heures":     meta.get("heures", ""),
                            "salaire":    meta.get("salaire", ""),
                            "date_debut": meta.get("date_debut", ""),
                            "date_fin":   meta.get("date_fin", ""),
                            "annee_debut": meta.get("annee_debut", ""),
                            "mois_debut":  meta.get("mois_debut", ""),
                        }
                    else:
                        # PDF sans métadonnées IntermitDoc — extraire du nom
                        info = self._info_depuis_nom(pdf.name, annee, mois)
                    self._contrats.append({"chemin": str(pdf), "info": info,
                                           "previsionnel": False})

        # Contrats prévisionnels
        for prev in _charger_previsions():
            if prev.get("annee") == annee and prev.get("mois") == mois:
                self._contrats.append({"chemin": "", "info": prev,
                                       "previsionnel": True,
                                       "id": prev.get("id", "")})

        for i, c in enumerate(self._contrats):
            info = c["info"]
            annee_mois = f"{info.get('annee','')}-{info.get('mois','')}"
            # Contrat chevauchant deux mois (AEM) : la date de début garde
            # son propre mois/année si différent du mois de classement.
            annee_debut = info.get("annee_debut", "") or info.get("annee", "")
            mois_debut  = info.get("mois_debut", "") or info.get("mois", "")
            annee_mois_debut = f"{annee_debut}-{mois_debut}"
            jour_debut = info.get("date_debut", "")
            jour_fin   = info.get("date_fin", "") or jour_debut
            date_debut_str = f"{annee_mois_debut}-{jour_debut}" if jour_debut else ""
            date_fin_str   = f"{annee_mois}-{jour_fin}" if jour_fin else ""
            heures  = info.get("heures", "")
            salaire = info.get("salaire", info.get("salaire_brut", ""))
            statut  = "Prévisionnel" if c["previsionnel"] else "Classifié"
            tag     = "previsionnel" if c["previsionnel"] else "classifie"
            iid = self.tree.insert("", tk.END, tags=(tag,),
                                   values=(date_debut_str,
                                           date_fin_str,
                                           info.get("employeur", ""),
                                           f"{heures}h" if heures else "",
                                           f"{salaire}€" if salaire else "",
                                           statut))
            self._contrats[i]["_iid"] = iid

        # Reconstruire le mapping iid → index
        self._iid_index = {c["_iid"]: i
                           for i, c in enumerate(self._contrats)}

    def _scanner_doublons_mois(self):
        """Cherche les prévisionnels correspondant à des contrats réels du
        mois affiché (même logique que la déduplication automatique de
        Suivi/Récap, mais restreinte à ce seul mois)."""
        annee = self._annee_var.get()
        mois  = self._mois_num_courant()
        if not annee or not mois:
            return

        # _deduplication_previsionnels attend des dates ISO complètes
        # (comme _scanner_tous_docs) ; les info de Historique ne stockent
        # que le jour brut ("22") — les reconstruire avant l'appel.
        docs_reels = []
        for c in self._contrats:
            if c.get("previsionnel"):
                continue
            info = dict(c["info"])
            a, m = info.get("annee", ""), info.get("mois", "")
            jd = info.get("date_debut", "")
            jf = info.get("date_fin", "") or jd
            if a and m and jd and len(jd) == 2:
                info["date_debut"] = f"{a}-{m}-{jd}"
                info["date_fin"]   = f"{a}-{m}-{jf}" if jf and len(jf) == 2 else info["date_debut"]
            docs_reels.append(info)
        rapport = _deduplication_previsionnels(docs_reels)
        en_attente_mois = [
            p for p in rapport["en_attente"]
            if p.get("annee") == annee and p.get("mois") == mois
        ]

        if not rapport["supprimes"] and not rapport["conflits"] and not en_attente_mois:
            messagebox.showinfo(
                "Scan doublons",
                "Aucun doublon ni prévisionnel en attente pour ce mois.",
                parent=self)
        else:
            _DialogueRapportDedup(self, rapport["supprimes"], rapport["conflits"],
                                  en_attente_mois)

        if rapport["supprimes"] or rapport["conflits"]:
            self._actualiser_liste()

    @staticmethod
    def _info_depuis_nom(nom: str, annee: str, mois: str) -> dict:
        pat = re.compile(
            r"\[AEM\]\s*(\d{4})-(\d{2})-(\d{2})(?:_(\d{2}|\d{4}-\d{2}-\d{2}))?\s+"
            r"(.+?)\s+(\d+(?:[.,]\d+)?)h\s*(\d+(?:[.,]\d+)?)(?:EUR)?",
            re.IGNORECASE,
        )
        m = pat.search(nom)
        if m:
            annee_d, mois_d, jour_d = m.group(1), m.group(2), m.group(3)
            fin_brut = m.group(4)
            if fin_brut and len(fin_brut) == 10:
                # Contrat chevauchant deux mois : date de fin deja complete
                date_fin = fin_brut
                annee_f, mois_f = date_fin[:4], date_fin[5:7]
            else:
                date_fin = fin_brut or jour_d
                annee_f, mois_f = annee_d, mois_d
            chevauche = (annee_f, mois_f) != (annee_d, mois_d)
            return {
                "type": "AEM", "annee": annee_f, "mois": mois_f,
                "date_debut": jour_d, "date_fin": date_fin,
                "annee_debut": annee_d if chevauche else "",
                "mois_debut":  mois_d if chevauche else "",
                "employeur": m.group(5).strip(),
                "heures": m.group(6).replace(",", "."),
                "salaire": m.group(7).replace(",", "."),
            }
        return {"type": "AEM", "annee": annee, "mois": mois,
                "date_debut": "", "date_fin": "", "employeur": nom,
                "heures": "", "salaire": ""}

    # ── Sélection d'un contrat ───────────────────────────────────────────────

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return

        if len(sel) > 1:
            # Sélection multiple : pas d'édition détail, juste la suppression groupée.
            for var in self._vars_form.values():
                var.set("")
            self._var_note.set("")
            self._chemin_ouvert = ""
            self._btn_save.config(state=tk.DISABLED)
            contrats_sel = [self._contrats[self._iid_index[i]] for i in sel
                            if self._iid_index.get(i) is not None]
            nb_prev = sum(1 for c in contrats_sel if c.get("previsionnel"))
            self._btn_delete.config(state=tk.NORMAL if nb_prev else tk.DISABLED)
            self._lbl_status.config(
                text=f"{len(sel)} éléments sélectionnés ({nb_prev} prévisionnel(s) "
                     "supprimable(s))")
            self._menu_ctx.entryconfig(0, state=tk.DISABLED)
            self._menu_ctx.entryconfig(1, state=tk.DISABLED)
            self._menu_ctx.entryconfig(6, state=tk.NORMAL if nb_prev else tk.DISABLED)
            return

        iid = sel[0]
        idx = self._iid_index.get(iid)
        if idx is None:
            return
        contrat = self._contrats[idx]
        info    = contrat["info"]
        self._chemin_ouvert = contrat.get("chemin", "")

        # Remplir le formulaire
        self._vars_form["type"].set(info.get("type", "AEM"))
        self._vars_form["annee"].set(info.get("annee", ""))
        self._vars_form["mois"].set(info.get("mois", ""))
        self._vars_form["employeur"].set(info.get("employeur", ""))
        self._vars_form["date_debut"].set(info.get("date_debut", ""))
        self._vars_form["date_fin"].set(info.get("date_fin", ""))
        self._vars_form["heures"].set(info.get("heures", ""))
        self._vars_form["salaire"].set(
            info.get("salaire", info.get("salaire_brut", "")))
        self._var_note.set(info.get("note", ""))

        self._btn_save.config(state=tk.NORMAL)
        is_prev = contrat.get("previsionnel", False)
        self._btn_delete.config(
            state=tk.NORMAL if is_prev else tk.DISABLED)
        self._lbl_status.config(text="")
        # Mettre à jour l'état des entrées du menu contextuel
        a_fichier = bool(self._chemin_ouvert and Path(self._chemin_ouvert).exists())
        self._menu_ctx.entryconfig(0, state=tk.NORMAL if a_fichier else tk.DISABLED)
        self._menu_ctx.entryconfig(1, state=tk.NORMAL if a_fichier else tk.DISABLED)
        self._menu_ctx.entryconfig(6, state=tk.NORMAL if is_prev else tk.DISABLED)

    def _vider_detail(self):
        for var in self._vars_form.values():
            var.set("")
        self._var_note.set("")
        self._chemin_ouvert = ""
        self._btn_save.config(state=tk.DISABLED)
        self._btn_delete.config(state=tk.DISABLED)
        self._lbl_status.config(text="")

    # ── Interactions liste ───────────────────────────────────────────────────

    def _on_double_clic(self, _event=None):
        if self._chemin_ouvert and Path(self._chemin_ouvert).exists():
            FenetreApercu(self, self._chemin_ouvert, 0, titre="Contrat AEM")

    def _on_clic_droit(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self._on_select()
        try:
            self._menu_ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu_ctx.grab_release()

    def _ouvrir_pdf_fenetre(self, _event=None):
        if self._chemin_ouvert and Path(self._chemin_ouvert).exists():
            FenetreApercu(self, self._chemin_ouvert, 0, titre="Contrat AEM")

    def _ouvrir_dossier_explorateur(self):
        if not self._chemin_ouvert or not Path(self._chemin_ouvert).exists():
            return
        import subprocess
        subprocess.Popen(["explorer", "/select,", self._chemin_ouvert])

    def _dupliquer_contrat(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        idx = self._iid_index.get(iid)
        if idx is None:
            return
        contrat = self._contrats[idx]
        info    = contrat["info"]

        dlg = _DialogueDupliquerContrat(self, info)
        self.wait_window(dlg)
        if not dlg.dates_choisies:
            return

        for d in dlg.dates_choisies:
            nouveau = dict(info)
            nouveau.pop("id", None)
            nouveau["date_debut"]    = d.strftime("%d")
            nouveau["date_fin"]      = d.strftime("%d")
            nouveau["annee"]         = d.strftime("%Y")
            nouveau["mois"]          = d.strftime("%m")
            nouveau["previsionnel"]  = True
            _ajouter_previsionnel_hist(nouveau)

        # Naviguer vers le mois du premier contrat créé
        first = dlg.dates_choisies[0]
        a, m = first.strftime("%Y"), first.strftime("%m")
        annees = list(self._cb_annee["values"])
        if a not in annees:
            annees.append(a); annees.sort()
            self._cb_annee["values"] = annees
        self._annee_var.set(a)
        self._on_annee_change()
        self._mois_var.set(f"{m} {self.MOIS_NOMS.get(m, m)}")
        self._actualiser_liste()
        self._lbl_status.config(
            text=f"✓ {len(dlg.dates_choisies)} contrat(s) créé(s).", fg="green")

    # ── Sauvegarde ───────────────────────────────────────────────────────────

    def _sauvegarder(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        idx = self._iid_index.get(iid)
        if idx is None:
            return
        contrat = self._contrats[idx]

        info_nouv = {
            "type":       self._vars_form["type"].get().strip(),
            "annee":      self._vars_form["annee"].get().strip(),
            "mois":       self._vars_form["mois"].get().strip(),
            "employeur":  self._vars_form["employeur"].get().strip(),
            "date_debut": self._vars_form["date_debut"].get().strip(),
            "date_fin":   self._vars_form["date_fin"].get().strip(),
            "heures":     self._vars_form["heures"].get().strip(),
            "salaire":    self._vars_form["salaire"].get().strip(),
            "note":       self._var_note.get().strip(),
        }

        if contrat.get("previsionnel"):
            self._sauvegarder_previsionnel(contrat, info_nouv)
        else:
            self._sauvegarder_metadata_pdf(contrat, info_nouv)

    def _sauvegarder_metadata_pdf(self, contrat: dict, info: dict):
        chemin = contrat.get("chemin", "")
        if not chemin or not Path(chemin).exists():
            self._lbl_status.config(text="⚠ Fichier introuvable.", fg="red")
            return
        try:
            chemin_path = Path(chemin)
            # Normalise salaire key: ui uses 'salaire', classifier uses 'salaire_brut'
            info_clf = {
                "type":        info.get("type", ""),
                "annee":       info.get("annee", ""),
                "mois":        info.get("mois", ""),
                "employeur":   info.get("employeur", ""),
                "date_debut":  info.get("date_debut", ""),
                "date_fin":    info.get("date_fin", ""),
                "heures":      info.get("heures", ""),
                "salaire_brut": info.get("salaire_brut") or info.get("salaire", ""),
            }
            pdf_bytes = _injecter_metadata(chemin_path.read_bytes(), info_clf)
            nouveau_nom = construire_nom_fichier(info_clf)
            chemin_dest = chemin_path.parent / nouveau_nom

            if chemin_dest != chemin_path and chemin_dest.exists():
                self._lbl_status.config(
                    text="⚠ Un fichier avec ce nom existe déjà.", fg="orange")
                return

            chemin_path.write_bytes(pdf_bytes)
            if chemin_dest != chemin_path:
                chemin_path.replace(chemin_dest)
                contrat["chemin"] = str(chemin_dest)
                self._chemin_ouvert = str(chemin_dest)

            contrat["info"] = info
            self._lbl_status.config(text="✓ Métadonnées mises à jour.", fg="green")
            logger.info(f"[Historique] metadata updated: {chemin_dest}")
            self._actualiser_liste()
        except Exception as e:
            self._lbl_status.config(text=f"Erreur : {e}", fg="red")
            logger.error(f"[Historique] save error: {e}")

    def _sauvegarder_previsionnel(self, contrat: dict, info: dict):
        prev_id = contrat.get("id", "")
        info["id"] = prev_id
        info["previsionnel"] = True
        _supprimer_previsionnel_hist(prev_id)
        _ajouter_previsionnel_hist(info)
        contrat["info"] = info
        self._lbl_status.config(text="✓ Prévisionnel mis à jour.", fg="green")
        self._actualiser_liste()

    def _supprimer_previsionnel(self):
        sel = self.tree.selection()
        if not sel:
            return
        contrats = [self._contrats[self._iid_index[i]] for i in sel
                   if self._iid_index.get(i) is not None]
        a_supprimer = [c for c in contrats if c.get("previsionnel")]
        if not a_supprimer:
            return
        n = len(a_supprimer)
        question = ("Supprimer ce contrat prévisionnel ?" if n == 1 else
                    f"Supprimer ces {n} contrats prévisionnels ?")
        if not messagebox.askyesno("Supprimer", question):
            return
        for contrat in a_supprimer:
            _supprimer_previsionnel_hist(contrat.get("id", ""))
        self._actualiser_liste()

    # ── Import agenda Google (ICS) ───────────────────────────────────────────

    def _ouvrir_dialogue_agenda(self):
        dlg = _DialogueAgenda(self)
        self.wait_window(dlg)
        if dlg.a_importe:
            self._actualiser_liste()

    # ── Création contrat futur ───────────────────────────────────────────────

    def _creer_previsionnel(self):
        dlg = _DialogueContratFutur(self)
        self.wait_window(dlg)
        if dlg.resultat:
            info = dlg.resultat
            info["previsionnel"] = True
            _ajouter_previsionnel_hist(info)  # génère l'id automatiquement
            # Naviguer vers l'année/mois du nouveau contrat
            a, m = info.get("annee", ""), info.get("mois", "")
            if a:
                annees = list(self._cb_annee["values"])
                if a not in annees:
                    annees.append(a)
                    annees.sort()
                    self._cb_annee["values"] = annees
                self._annee_var.set(a)
                self._on_annee_change()
            if m:
                self._mois_var.set(f"{m} {self.MOIS_NOMS.get(m, m)}")
            self._actualiser_liste()

    # ── Rafraîchissement externe ─────────────────────────────────────────────

    def rafraichir(self):
        """Appelé depuis d'autres onglets après une classification."""
        annees = self._lister_annees()
        vals_actuels = list(self._cb_annee["values"])
        if set(annees) != set(vals_actuels):
            self._cb_annee["values"] = annees
        self._actualiser_liste()


class _DialogueDupliquerContrat(tk.Toplevel):
    """
    Calendrier multi-sélection pour dupliquer un contrat vers plusieurs dates.
    L'utilisateur clique les dates voulues, confirme — les dates cochées sont
    retournées dans self.dates_choisies (liste de datetime.date).
    """

    def __init__(self, parent, info_source: dict):
        super().__init__(parent)
        self.title("Dupliquer le contrat — choisir les dates")
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)
        self.dates_choisies: list = []
        self._info = info_source
        self._selections: set = set()   # datetime.date sélectionnées
        self._construire()

    def _construire(self):
        from datetime import date as _date
        try:
            from tkcalendar import Calendar as _Cal
            HAS_TKCAL = True
        except ImportError:
            HAS_TKCAL = False

        info = self._info
        # Mois de départ : celui du contrat source, ou mois courant
        try:
            annee = int(info.get("annee") or _date.today().year)
            mois  = int(info.get("mois")  or _date.today().month)
        except (ValueError, TypeError):
            annee, mois = _date.today().year, _date.today().month

        # En-tête récap du contrat source
        hdr = tk.LabelFrame(self,
                             text="  Contrat à dupliquer  ",
                             padx=10, pady=6)
        hdr.pack(fill=tk.X, padx=10, pady=(10, 4))
        recap = (
            f"Employeur : {info.get('employeur','—')}   |   "
            f"Heures : {info.get('heures','—')}h   |   "
            f"Salaire : {info.get('salaire','—')} €"
        )
        tk.Label(hdr, text=recap, font=("", 9)).pack(anchor="w")

        if HAS_TKCAL:
            # ── Calendrier tkcalendar ────────────────────────────────────────
            frame_cal = tk.Frame(self)
            frame_cal.pack(padx=10, pady=4)

            self._cal = _Cal(
                frame_cal,
                selectmode="day",
                year=annee, month=mois,
                locale="fr_FR",
                showweeknumbers=False,
                firstweekday="monday",
                font=("", 9),
                headersforeground="#1565C0",
            )
            self._cal.pack()
            self._cal.bind("<<CalendarSelected>>", self._on_day_click)
            self._cal.bind("<<CalendarMonth>>",    lambda e: self._redessiner_sel())

            tk.Label(self,
                     text="Cliquez les dates pour les sélectionner / désélectionner",
                     font=("", 8), fg="#555").pack()
        else:
            # ── Fallback : saisie manuelle si tkcalendar absent ──────────────
            tk.Label(self,
                     text="tkcalendar non disponible — saisissez les dates (YYYY-MM-DD)",
                     fg="orange").pack(padx=10, pady=4)
            self._txt_dates = scrolledtext.ScrolledText(self, height=6, width=30)
            self._txt_dates.pack(padx=10, pady=4)

        # ── Liste des dates sélectionnées ────────────────────────────────────
        frame_sel = tk.LabelFrame(self, text="  Dates sélectionnées  ",
                                  padx=6, pady=4)
        frame_sel.pack(fill=tk.X, padx=10, pady=4)

        self._lbl_sel = tk.Label(frame_sel, text="Aucune date sélectionnée",
                                  fg="#888", font=("", 9))
        self._lbl_sel.pack(anchor="w")

        # ── Boutons ──────────────────────────────────────────────────────────
        frame_btns = tk.Frame(self)
        frame_btns.pack(pady=(4, 10))

        tk.Button(frame_btns, text="🗑  Tout effacer",
                  command=self._tout_effacer,
                  width=14).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btns, text="✅  Créer les contrats",
                  bg="#1B5E20", fg="white", font=("", 9, "bold"),
                  command=self._valider,
                  width=18, pady=4).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btns, text="Annuler",
                  command=self.destroy,
                  width=10).pack(side=tk.LEFT, padx=6)

        self._has_tkcal = HAS_TKCAL

    def _on_day_click(self, _event=None):
        try:
            d = self._cal.selection_get()
        except Exception:
            return
        if d is None:
            return
        if d in self._selections:
            self._selections.discard(d)
        else:
            self._selections.add(d)
        self._redessiner_sel()
        self._maj_label()

    def _redessiner_sel(self):
        """Repeint les marqueurs sur le calendrier après changement de mois."""
        try:
            self._cal.calevent_remove("all")
            for d in self._selections:
                self._cal.calevent_create(d, "✓", "sel")
            self._cal.tag_config("sel", background="#1565C0", foreground="white")
        except Exception:
            pass

    def _maj_label(self):
        if not self._selections:
            self._lbl_sel.config(text="Aucune date sélectionnée", fg="#888")
            return
        dates_triees = sorted(self._selections)
        texte = "  |  ".join(d.strftime("%d/%m/%Y") for d in dates_triees)
        nb = len(dates_triees)
        self._lbl_sel.config(
            text=f"{nb} date(s) : {texte}", fg="#1B5E20")

    def _tout_effacer(self):
        self._selections.clear()
        if self._has_tkcal:
            try:
                self._cal.calevent_remove("all")
            except Exception:
                pass
        self._maj_label()

    def _valider(self):
        from datetime import date as _date

        if self._has_tkcal:
            if not self._selections:
                messagebox.showwarning("Aucune date",
                                       "Sélectionnez au moins une date.",
                                       parent=self)
                return
            self.dates_choisies = sorted(self._selections)
        else:
            # Fallback texte
            lignes = self._txt_dates.get("1.0", tk.END).strip().splitlines()
            dates = []
            for l in lignes:
                l = l.strip()
                if not l:
                    continue
                try:
                    dates.append(_date.fromisoformat(l))
                except ValueError:
                    messagebox.showwarning("Format invalide",
                                           f"Date invalide : {l}\nFormat attendu : YYYY-MM-DD",
                                           parent=self)
                    return
            if not dates:
                messagebox.showwarning("Aucune date",
                                       "Saisissez au moins une date.",
                                       parent=self)
                return
            self.dates_choisies = sorted(dates)

        self.destroy()


class _DialogueContratFutur(tk.Toplevel):
    """Dialogue de création d'un contrat prévisionnel."""

    MOIS_OPTIONS = [
        f"{m:02d} {n}" for m, n in [
            (1,"Janvier"),(2,"Février"),(3,"Mars"),(4,"Avril"),
            (5,"Mai"),(6,"Juin"),(7,"Juillet"),(8,"Août"),
            (9,"Septembre"),(10,"Octobre"),(11,"Novembre"),(12,"Décembre"),
        ]
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Nouveau contrat futur / prévisionnel")
        self.resizable(False, False)
        self.grab_set()
        self.resultat = None
        self._construire()
        self.transient(parent)

    def _construire(self):
        from config import charger_employeurs
        pad = {"padx": 8, "pady": 4}
        employeurs_connus = charger_employeurs()

        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # employeur : combobox éditable avec la liste des employeurs connus
        champs = [
            ("employeur", "Employeur *",    employeurs_connus or None),
            ("annee",     "Année *",        None),
            ("mois_str",  "Mois *",         self.MOIS_OPTIONS),
            ("date_debut","Date début",     None),
            ("date_fin",  "Date fin",       None),
            ("heures",    "Heures prévues", None),
            ("salaire",   "Salaire estimé", None),
            ("note",      "Note",           None),
        ]
        self._vars: dict[str, tk.StringVar] = {}
        for r, (key, label, opts) in enumerate(champs):
            tk.Label(frame, text=label + " :", anchor="e",
                     width=16).grid(row=r, column=0, sticky="e", **pad)
            var = tk.StringVar()
            self._vars[key] = var
            if opts:
                w = ttk.Combobox(frame, textvariable=var,
                                 values=opts, width=20, state="normal")
            else:
                w = tk.Entry(frame, textvariable=var, width=22)
            w.grid(row=r, column=1, sticky="w", **pad)

        # Valeurs par défaut
        today = _date_today.today()
        self._vars["annee"].set(str(today.year))
        self._vars["mois_str"].set(
            f"{today.month:02d} {self.MOIS_OPTIONS[today.month - 1].split(' ', 1)[1]}")

        # Boutons
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=len(champs), column=0, columnspan=2, pady=(10, 0))
        tk.Button(btn_frame, text="Créer", bg="#1565C0", fg="white",
                  font=("", 9, "bold"), width=10,
                  command=self._valider).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Annuler", width=10,
                  command=self.destroy).pack(side=tk.LEFT, padx=6)

    def _valider(self):
        employeur = self._vars["employeur"].get().strip()
        annee     = self._vars["annee"].get().strip()
        mois_str  = self._vars["mois_str"].get().strip()
        if not employeur or not annee or not mois_str:
            messagebox.showwarning("Champs manquants",
                                   "Employeur, Année et Mois sont obligatoires.",
                                   parent=self)
            return
        mois = mois_str.split(" ")[0].zfill(2)
        self.resultat = {
            "type":       "AEM",
            "annee":      annee,
            "mois":       mois,
            "employeur":  employeur,
            "date_debut": self._vars["date_debut"].get().strip(),
            "date_fin":   self._vars["date_fin"].get().strip(),
            "heures":     self._vars["heures"].get().strip(),
            "salaire":    self._vars["salaire"].get().strip(),
            "note":       self._vars["note"].get().strip(),
        }
        self.destroy()

    def _reset_dedup(self):
        global _dedup_en_cours
        _dedup_en_cours = False


class _DialogueAgenda(tk.Toplevel):
    """Configuration du lien agenda (ICS), des tags de repérage perso et des
    liaisons mot-clé → employeur/type, + lancement de l'import."""

    TYPES = ["AEM", "BP", "CS", "CT", "STC"]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Import agenda Google")
        self.resizable(False, False)
        self.grab_set()
        self.a_importe = False
        self._cfg = charger_config_agenda()
        self._construire()
        self.transient(parent)

    def _construire(self):
        pad = {"padx": 10, "pady": 4}

        # ── Connexion à Google Agenda ────────────────────────────────────────
        f_url = tk.LabelFrame(self, text="🔗 Connexion à Google Agenda", padx=10, pady=8)
        f_url.pack(fill=tk.X, padx=10, pady=(10, 4))
        tk.Label(f_url, text="1. Sur calendar.google.com → ⚙ Paramètres → "
                 "\"Paramètres de mes agendas\".\n"
                 "2. Cliquez sur l'agenda à partager (dans la colonne de gauche).\n"
                 "3. Section \"Intégrer l'agenda\" → copiez l'\"Adresse secrète au "
                 "format iCal\" (se termine par .ics).\n"
                 "4. Collez-la ci-dessous puis cliquez sur Tester la connexion.",
                 wraplength=440, justify="left", fg="#555").pack(anchor="w")
        self._var_url = tk.StringVar(value=self._cfg.get("url_ics", ""))
        tk.Entry(f_url, textvariable=self._var_url, width=60).pack(
            fill=tk.X, pady=(6, 2))
        tk.Label(f_url, text="Exemple : https://calendar.google.com/calendar/ical/"
                 "florent.olivier.revol%40gmail.com/private-3f8a1c9d2e7b4f56/basic.ics",
                 font=("", 8), fg="#888", wraplength=440,
                 justify="left").pack(anchor="w", pady=(0, 2))
        self._lbl_statut_connexion = tk.Label(f_url, text="", fg="#555")
        self._lbl_statut_connexion.pack(anchor="w")
        tk.Button(f_url, text="🔌 Tester la connexion",
                  command=self._tester_connexion).pack(anchor="w", pady=(4, 0))

        # ── Tags de repérage perso ──────────────────────────────────────────
        f_tags = tk.LabelFrame(self, text="Tags qui marquent un évènement de travail",
                                padx=10, pady=8)
        f_tags.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(f_tags, text="Seuls les évènements dont le titre contient un de ces "
                 "tags seront pris en compte (le reste est ignoré). "
                 "Ajoutez les vôtres, ce sont vos propres repères d'agenda.",
                 wraplength=440, justify="left", fg="#555").pack(anchor="w")

        ligne_tags = tk.Frame(f_tags)
        ligne_tags.pack(fill=tk.X, pady=(6, 0))
        self._liste_tags = tk.Listbox(ligne_tags, height=4, width=20)
        for tag in self._cfg.get("tags_travail", []):
            self._liste_tags.insert(tk.END, tag)
        self._liste_tags.pack(side=tk.LEFT)

        f_tags_btn = tk.Frame(ligne_tags)
        f_tags_btn.pack(side=tk.LEFT, padx=8, anchor="n")
        self._var_nouveau_tag = tk.StringVar()
        tk.Entry(f_tags_btn, textvariable=self._var_nouveau_tag,
                 width=14).pack(pady=(0, 4))
        tk.Button(f_tags_btn, text="+ Ajouter", command=self._ajouter_tag,
                  pady=1).pack(fill=tk.X, pady=(0, 2))
        tk.Button(f_tags_btn, text="− Retirer", command=self._retirer_tag,
                  pady=1).pack(fill=tk.X)

        # ── Liaisons mot-clé → employeur/type ───────────────────────────────
        f_liaisons = tk.LabelFrame(
            self, text="Liaisons mot-clé du titre → employeur / type",
            padx=10, pady=8)
        f_liaisons.pack(fill=tk.BOTH, padx=10, pady=4)

        cols = ("mot_cle", "employeur", "type", "heures", "salaire")
        self._tree = ttk.Treeview(f_liaisons, columns=cols, show="headings",
                                   height=5, selectmode="browse")
        for cid, label, w in [("mot_cle", "Mot-clé", 110),
                               ("employeur", "Employeur", 160),
                               ("type", "Type", 50),
                               ("heures", "Heures", 60),
                               ("salaire", "Salaire brut", 80)]:
            self._tree.heading(cid, text=label)
            self._tree.column(cid, width=w, anchor="w")
        self._tree.pack(fill=tk.X)
        for liaison in self._cfg.get("liaisons", []):
            self._tree.insert("", tk.END, values=(
                liaison.get("mot_cle", ""), liaison.get("employeur", ""),
                liaison.get("type", "AEM"), liaison.get("heures", ""),
                liaison.get("salaire", "")))

        f_liaison_form = tk.Frame(f_liaisons)
        f_liaison_form.pack(fill=tk.X, pady=(6, 0))
        from config import charger_employeurs
        employeurs_connus = charger_employeurs()

        tk.Label(f_liaison_form, text="Mot-clé :").grid(row=0, column=0, padx=2)
        self._var_mot_cle = tk.StringVar()
        tk.Entry(f_liaison_form, textvariable=self._var_mot_cle,
                 width=14).grid(row=0, column=1, padx=2)

        tk.Label(f_liaison_form, text="Employeur :").grid(row=0, column=2, padx=2)
        self._var_employeur = tk.StringVar()
        ttk.Combobox(f_liaison_form, textvariable=self._var_employeur,
                     values=employeurs_connus, width=16).grid(row=0, column=3, padx=2)

        tk.Label(f_liaison_form, text="Type :").grid(row=0, column=4, padx=2)
        self._var_type = tk.StringVar(value="AEM")
        ttk.Combobox(f_liaison_form, textvariable=self._var_type,
                     values=self.TYPES, width=6,
                     state="readonly").grid(row=0, column=5, padx=2)

        tk.Label(f_liaison_form, text="Heures :").grid(row=1, column=0, padx=2, pady=(4, 0))
        self._var_heures = tk.StringVar()
        tk.Entry(f_liaison_form, textvariable=self._var_heures,
                 width=14).grid(row=1, column=1, padx=2, pady=(4, 0))

        tk.Label(f_liaison_form, text="Salaire brut :").grid(row=1, column=2, padx=2, pady=(4, 0))
        self._var_salaire = tk.StringVar()
        tk.Entry(f_liaison_form, textvariable=self._var_salaire,
                 width=16).grid(row=1, column=3, padx=2, pady=(4, 0))
        tk.Label(f_liaison_form, text="(optionnel — si le contrat est toujours "
                 "le même, l'import n'aura plus qu'à les copier)",
                 font=("", 8), fg="#888").grid(row=1, column=4, columnspan=2,
                                                sticky="w", pady=(4, 0))

        tk.Button(f_liaison_form, text="+ Ajouter", command=self._ajouter_liaison,
                  pady=1).grid(row=2, column=0, columnspan=2, pady=(6, 0))
        tk.Button(f_liaison_form, text="− Retirer la sélection",
                  command=self._retirer_liaison, pady=1).grid(
            row=2, column=2, columnspan=2, pady=(6, 0))

        # ── Boutons bas ──────────────────────────────────────────────────────
        f_bas = tk.Frame(self, pady=10)
        f_bas.pack(fill=tk.X)
        tk.Button(f_bas, text="💾 Enregistrer", command=self._sauvegarder,
                  padx=10, pady=3).pack(side=tk.LEFT, padx=10)
        tk.Button(f_bas, text="📥 Enregistrer et importer maintenant",
                  bg="#00838F", fg="white", font=("", 9, "bold"),
                  command=self._importer, padx=10, pady=3).pack(side=tk.LEFT)
        tk.Button(f_bas, text="Fermer", command=self.destroy,
                  padx=10, pady=3).pack(side=tk.RIGHT, padx=10)

    def _tester_connexion(self):
        url = self._var_url.get().strip()
        if not url:
            messagebox.showwarning("Lien manquant", "Collez d'abord votre lien ICS.",
                                   parent=self)
            return
        self._lbl_statut_connexion.config(text="Connexion en cours...", fg="#555")
        self.update_idletasks()
        try:
            texte = telecharger_ics(url)
            nb = len(parser_ics(texte))
        except Exception as e:
            self._lbl_statut_connexion.config(
                text=f"❌ Échec de connexion : {e}", fg="#C62828")
            return
        self._lbl_statut_connexion.config(
            text=f"✅ Connecté — {nb} évènement(s) trouvé(s) dans l'agenda. "
                 "Comparaison avec vos prévisionnels...",
            fg="#2E7D32")
        self.update_idletasks()

        cfg = self._config_actuelle()
        cfg["url_ics"] = url
        try:
            rapport = importer_evenements(cfg, dry_run=True)
        except Exception as e:
            self._lbl_statut_connexion.config(
                text=f"⚠ Connecté, mais échec de la comparaison : {e}", fg="#C62828")
            return
        self._lbl_statut_connexion.config(
            text=f"✅ Connecté — {nb} évènement(s) dans l'agenda, "
                 f"{len(rapport['importes'])} nouveau(x) à importer depuis le mois en cours.",
            fg="#2E7D32")
        self._afficher_rapport(rapport, "Comparaison agenda ↔ prévisionnels")

    def _ajouter_tag(self):
        tag = self._var_nouveau_tag.get().strip()
        if not tag:
            return
        if tag not in self._liste_tags.get(0, tk.END):
            self._liste_tags.insert(tk.END, tag)
        self._var_nouveau_tag.set("")

    def _retirer_tag(self):
        sel = self._liste_tags.curselection()
        if sel:
            self._liste_tags.delete(sel[0])

    def _ajouter_liaison(self):
        mot_cle = self._var_mot_cle.get().strip()
        employeur = self._var_employeur.get().strip()
        type_ = self._var_type.get().strip() or "AEM"
        heures = self._var_heures.get().strip()
        salaire = self._var_salaire.get().strip()
        if not mot_cle or not employeur:
            messagebox.showwarning("Champs manquants",
                                   "Mot-clé et Employeur sont obligatoires.",
                                   parent=self)
            return
        self._tree.insert("", tk.END, values=(mot_cle, employeur, type_, heures, salaire))
        self._var_mot_cle.set("")
        self._var_employeur.set("")
        self._var_heures.set("")
        self._var_salaire.set("")

    def _retirer_liaison(self):
        sel = self._tree.selection()
        if sel:
            self._tree.delete(sel[0])

    def _config_actuelle(self) -> dict:
        return {
            "url_ics": self._var_url.get().strip(),
            "tags_travail": list(self._liste_tags.get(0, tk.END)),
            "liaisons": [
                {"mot_cle": v[0], "employeur": v[1], "type": v[2],
                 "heures": v[3], "salaire": v[4]}
                for v in (self._tree.item(iid, "values") for iid in self._tree.get_children())
            ],
        }

    def _sauvegarder(self):
        sauvegarder_config_agenda(self._config_actuelle())
        messagebox.showinfo("Enregistré", "Configuration agenda enregistrée.",
                            parent=self)

    def _importer(self):
        cfg = self._config_actuelle()
        sauvegarder_config_agenda(cfg)
        if not cfg["url_ics"]:
            messagebox.showwarning("Lien manquant",
                                   "Renseignez d'abord le lien ICS de votre agenda.",
                                   parent=self)
            return
        try:
            rapport = importer_evenements(cfg)
        except Exception as e:
            messagebox.showerror("Erreur d'import",
                                 f"Impossible de lire l'agenda :\n{e}", parent=self)
            return

        self.a_importe = bool(rapport["importes"])
        self._afficher_rapport(rapport, "Résultat de l'import", cree=True)

    def _afficher_rapport(self, rapport: dict, titre_fenetre: str, cree: bool = False):
        verbe = "créé(s)" if cree else "à créer"
        lignes = [f"✅ {len(rapport['importes'])} contrat(s) prévisionnel(s) {verbe}."]
        for titre, date_iso, employeur in rapport["importes"]:
            lignes.append(f"   • {date_iso} — {employeur} ({titre})")
        if rapport["deja_existants"]:
            lignes.append(f"\nℹ {len(rapport['deja_existants'])} déjà présent(s) dans vos "
                          "prévisionnels, ignoré(s).")
        if rapport["ignores_sans_lien"]:
            lignes.append(f"\n⚠ {len(rapport['ignores_sans_lien'])} évènement(s) de travail "
                          "sans mot-clé correspondant (ajoutez une liaison) :")
            for titre, date_iso in rapport["ignores_sans_lien"]:
                lignes.append(f"   • {date_iso} — {titre}")
        messagebox.showinfo(titre_fenetre, "\n".join(lignes), parent=self)


def _calculer_periodes_anniversaire(docs: list, cfg: dict) -> list:
    """
    Retourne la liste de périodes [(label, date_debut, date_fin), ...]
    basées sur la date anniversaire configurée (JJ/MM) — les "périodes ARE".
    Si non configurée, retourne des périodes par année calendaire.
    Partagée par Bilan par période et Revenus pour rester cohérente.
    """
    from datetime import date, timedelta
    anniv_str = cfg.get("date_anniversaire", "").strip()

    if not anniv_str or "/" not in anniv_str:
        annees = sorted({d.get("annee", "") for d in docs if d.get("annee")}, reverse=True)
        periodes = []
        for a in annees:
            debut = date(int(a), 1, 1)
            fin   = date(int(a), 12, 31)
            periodes.append((a, debut, fin))
        return periodes

    try:
        jour, mois = int(anniv_str.split("/")[0]), int(anniv_str.split("/")[1])
    except (ValueError, IndexError):
        return []

    dates_doc = []
    for d in docs:
        for cle in ("date_debut", "date_fin"):
            v = d.get(cle, "")
            if v and len(v) >= 10:
                try:
                    dates_doc.append(date.fromisoformat(v[:10]))
                except ValueError:
                    pass
    if not dates_doc:
        return []

    date_min = min(dates_doc)
    today    = date.today()

    anniv_annee = date_min.year
    try:
        anniv_test = date(anniv_annee, mois, jour)
    except ValueError:
        anniv_test = date(anniv_annee, mois, 28)
    if anniv_test > date_min:
        anniv_annee -= 1

    periodes = []
    while True:
        try:
            anniv_debut = date(anniv_annee, mois, jour)
            anniv_fin   = date(anniv_annee + 1, mois, jour)
        except ValueError:
            anniv_debut = date(anniv_annee, mois, 28)
            anniv_fin   = date(anniv_annee + 1, mois, 28)

        debut_periode = anniv_debut + timedelta(days=1)
        fin_periode   = anniv_fin

        if debut_periode > today:
            break

        label = f"{debut_periode.strftime('%d/%m/%Y')} → {fin_periode.strftime('%d/%m/%Y')}"
        if fin_periode >= today:
            label += "  (en cours)"
        periodes.append((label, debut_periode, fin_periode))
        anniv_annee += 1
        if debut_periode > today:
            break

    return list(reversed(periodes))


def _periode_de_doc_globale(doc: dict, periodes: list):
    """Retourne le label de la période à laquelle appartient un document."""
    from datetime import date
    v = doc.get("date_debut", "") or doc.get("date_fin", "")
    if not v or len(v) < 10:
        return None
    try:
        d = date.fromisoformat(v[:10])
    except ValueError:
        return None
    for label, debut, fin in periodes:
        if debut <= d <= fin:
            return label
    return None


# ---------------------------------------------------------------------------
# Onglet Récapitulatif annuel
# ---------------------------------------------------------------------------
class OngletRecap(tk.Frame):
    """
    Récapitulatif annuel de tous les documents classifiés.
    Affiche toutes les informations localement : année par année,
    total heures, salaire, employeurs, statut droits.
    """

    COL = [
        ("jour_debut","Jour début",    70),
        ("jour_fin",  "Jour fin",      70),
        ("mois",      "Mois",         80),
        ("annee",     "Année",        55),
        ("type",      "Type",         55),
        ("employeur", "Employeur",    160),
        ("heures",    "Heures",        60),
        ("salaire",   "Salaire brut",  90),
    ]

    def __init__(self, parent, cfg_getter):
        super().__init__(parent)
        self._cfg_getter = cfg_getter
        self._docs: list = []
        self._iid_docs: dict = {}
        self._construire()

    def _construire(self):
        # ── Barre du haut ──────────────────────────────────────────────────
        bar = tk.Frame(self, pady=6, padx=10)
        bar.pack(fill=tk.X)

        tk.Label(bar, text="Récapitulatif annuel", font=("", 11, "bold"),
                 fg="#1A237E").pack(side=tk.LEFT)

        tk.Button(bar, text="↻ Actualiser", command=self.actualiser,
                  bg="#1976D2", fg="white", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)
        tk.Button(bar, text="🗑 Supprimer la sélection",
                  command=self._supprimer_selection,
                  bg="#B71C1C", fg="white", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)

        # ── Sélecteurs de filtre ─────────────────────────────────────────────
        bar2 = tk.Frame(self, padx=10)
        bar2.pack(fill=tk.X)
        tk.Label(bar2, text="Filtrer par période :").pack(side=tk.LEFT)
        self.var_annee = tk.StringVar(value="Toutes")
        self._combo_annee = ttk.Combobox(bar2, textvariable=self.var_annee,
                                          width=26, state="readonly")
        self._combo_annee.pack(side=tk.LEFT, padx=(6, 16))
        self._combo_annee.bind("<<ComboboxSelected>>", lambda e: self._filtrer())

        tk.Label(bar2, text="Année civile :").pack(side=tk.LEFT)
        self.var_annee_cal = tk.StringVar(value="Toutes")
        self._combo_annee_cal = ttk.Combobox(bar2, textvariable=self.var_annee_cal,
                                              width=8, state="readonly")
        self._combo_annee_cal.pack(side=tk.LEFT, padx=(6, 16))
        self._combo_annee_cal.bind("<<ComboboxSelected>>", lambda e: self._filtrer())

        tk.Label(bar2, text="Mois :").pack(side=tk.LEFT)
        self.var_mois = tk.StringVar(value="Tous")
        self._combo_mois = ttk.Combobox(
            bar2, textvariable=self.var_mois, width=12, state="readonly",
            values=["Tous"] + [f"{num} {nom}" for num, nom in OngletHistorique.MOIS_LABELS])
        self._combo_mois.pack(side=tk.LEFT, padx=(6, 16))
        self._combo_mois.bind("<<ComboboxSelected>>", lambda e: self._filtrer())

        tk.Label(bar2, text="Type :").pack(side=tk.LEFT)
        self.var_type = tk.StringVar(value="Tous")
        self._combo_type = ttk.Combobox(
            bar2, textvariable=self.var_type, width=8, state="readonly",
            values=["Tous", "AEM", "BP", "CS", "CT", "STC"])
        self._combo_type.pack(side=tk.LEFT, padx=6)
        self._combo_type.bind("<<ComboboxSelected>>", lambda e: self._filtrer())

        # ── Cartes de synthèse ─────────────────────────────────────────────
        self._frame_cartes = tk.Frame(self, padx=10, pady=6)
        self._frame_cartes.pack(fill=tk.X)

        # ── Tableau détail + encart d'alertes ────────────────────────────────
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        frame_tree = tk.LabelFrame(paned, text="Détail des contrats", padx=4, pady=4)
        paned.add(frame_tree, minsize=420)

        frame_alertes = tk.LabelFrame(paned, text="⚠ BP sans AEM correspondant",
                                      padx=4, pady=4)
        paned.add(frame_alertes, minsize=220, width=260)

        self._txt_alertes = scrolledtext.ScrolledText(
            frame_alertes, wrap=tk.WORD, font=("", 9), state=tk.DISABLED,
            padx=6, pady=6)
        self._txt_alertes.pack(fill=tk.BOTH, expand=True)
        self._txt_alertes.tag_configure("titre", font=("", 9, "bold"), foreground="#B71C1C")
        self._txt_alertes.tag_configure("ligne", font=("", 9))

        sv = tk.Scrollbar(frame_tree, orient=tk.VERTICAL)
        sh = tk.Scrollbar(frame_tree, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            frame_tree,
            columns=[c[0] for c in self.COL],
            show="headings",
            yscrollcommand=sv.set,
            xscrollcommand=sh.set,
            height=14,
        )
        sv.config(command=self.tree.yview)
        sh.config(command=self.tree.xview)
        for col_id, col_titre, col_larg in self.COL:
            self.tree.column(col_id, width=col_larg, minwidth=40,
                             stretch=(col_id == "employeur"))
            self.tree.heading(col_id, text=col_titre)
        self.tree.tag_configure("aem",        background="#E3F2FD")
        self.tree.tag_configure("bp",         background="#E8F5E9")
        self.tree.tag_configure("cs",         background="#FFF8E1")
        self.tree.tag_configure("ct",         background="#FFF8E1")
        self.tree.tag_configure("stc",           background="#FCE4EC")
        self.tree.tag_configure("total",         background="#C5CAE9", font=("", 9, "bold"))
        self.tree.tag_configure("separateur",    background="#E8EAF6", font=("", 9, "bold"), foreground="#1A237E")
        self.tree.tag_configure("previsionnel",  background="#F3E5F5", foreground="#6A1B9A",
                                font=("", 9, "italic"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sv.grid(row=0, column=1, sticky="ns")
        sh.grid(row=1, column=0, sticky="ew")
        frame_tree.grid_rowconfigure(0, weight=1)
        frame_tree.grid_columnconfigure(0, weight=1)

        self._tri = _installer_tri(self.tree, [c[0] for c in self.COL])

        # ── Pied ───────────────────────────────────────────────────────────
        self._lbl_pied = tk.Label(self, text="", font=("", 8), fg="#555")
        self._lbl_pied.pack(pady=2)

    # ── Données ──────────────────────────────────────────────────────────────

    def rafraichir_depuis_dossier(self, dossier: str):
        self._docs = _scanner_tous_docs(dossier)
        self.actualiser()

    def actualiser(self):
        from previsionnel import charger_previsionnels
        cfg = self._cfg_getter()
        dossier = cfg.get("dossier_base", "")
        if dossier:
            self._docs = _scanner_tous_docs(dossier)

            # Déduplication prévisionnels vs AEM réels
            global _dedup_en_cours
            if not _dedup_en_cours:
                _dedup_en_cours = True
                self.after(60000, self._reset_dedup)
                rapport = _deduplication_previsionnels(self._docs)
                en_attente_visibles = _prevs_mois_courant_et_precedent(rapport["en_attente"])
                if rapport["supprimes"] or rapport["conflits"] or en_attente_visibles:
                    _DialogueRapportDedup(self, rapport["supprimes"],
                                          rapport["conflits"], en_attente_visibles)

        # Fusionner prévisionnels restants dans self._docs pour l'affichage
        prevs = charger_previsionnels()
        prevs_docs = []
        for p in prevs:
            d = dict(p)
            d.setdefault("type", "AEM")
            # Construire date_debut / date_fin complètes si absentes
            a = d.get("annee", "")
            m = d.get("mois", "")
            dd = d.get("date_debut", "")
            df = d.get("date_fin", dd)
            if a and m and dd and len(dd) == 2:
                d["date_debut"] = f"{a}-{m}-{dd}"
                d["date_fin"]   = f"{a}-{m}-{df}" if df and len(df) == 2 else d["date_debut"]
            d["_previsionnel"] = True
            prevs_docs.append(d)

        self._docs = self._docs + prevs_docs
        self._maj_combo()
        self._filtrer()

    # ── Logique périodes anniversaire ────────────────────────────────────────

    def _periodes_anniversaire(self) -> list:
        return _calculer_periodes_anniversaire(self._docs, self._cfg_getter())

    def _periode_de_doc(self, doc: dict, periodes: list):
        return _periode_de_doc_globale(doc, periodes)

    def _maj_combo(self):
        periodes = self._periodes_anniversaire()
        labels = [p[0] for p in periodes]
        self._combo_annee["values"] = ["Toutes"] + labels
        if self.var_annee.get() not in ["Toutes"] + labels:
            self.var_annee.set("Toutes")

        annees_cal = sorted(
            {d.get("annee", "") for d in self._docs if d.get("annee")}, reverse=True)
        self._combo_annee_cal["values"] = ["Toutes"] + annees_cal
        if self.var_annee_cal.get() not in ["Toutes"] + annees_cal:
            self.var_annee_cal.set("Toutes")

    def _filtrer(self):
        sel = self.var_annee.get()
        periodes = self._periodes_anniversaire()

        if sel == "Toutes":
            docs = self._docs
        else:
            docs = [d for d in self._docs
                    if self._periode_de_doc(d, periodes) == sel]

        sel_annee_cal = self.var_annee_cal.get()
        if sel_annee_cal != "Toutes":
            docs = [d for d in docs if d.get("annee", "") == sel_annee_cal]

        sel_mois = self.var_mois.get()
        if sel_mois != "Tous":
            mois_num = sel_mois.split(" ")[0]
            docs = [d for d in docs if d.get("mois", "") == mois_num]

        sel_type = self.var_type.get()
        if sel_type != "Tous":
            docs = [d for d in docs if d.get("type", "") == sel_type]

        self._maj_cartes(docs, sel, periodes)
        self._maj_tableau(docs, periodes)
        self._maj_alertes(docs)

    def _maj_alertes(self, docs):
        """Liste les BP (période filtrée) sans AEM correspondant (même
        année/mois/employeur, tolérant aux troncatures héritées)."""
        employeurs_aem = {
            (d.get("annee", ""), d.get("mois", ""),
             (d.get("employeur") or "").strip().lower())
            for d in docs if d.get("type") == "AEM" and not d.get("_previsionnel")
        }

        def _a_un_aem(bp):
            a, m = bp.get("annee", ""), bp.get("mois", "")
            emp  = (bp.get("employeur") or "").strip().lower()
            return any(
                a == ea and m == em and _employeurs_correspondent(emp, ee)
                for ea, em, ee in employeurs_aem
            )

        sans_aem = [
            d for d in docs
            if d.get("type") == "BP" and not d.get("_previsionnel")
            and not _a_un_aem(d)
        ]

        self._txt_alertes.config(state=tk.NORMAL)
        self._txt_alertes.delete("1.0", tk.END)
        if not sans_aem:
            self._txt_alertes.insert(tk.END, "✓ Aucun BP sans AEM sur la "
                                     "période affichée.\n", "ligne")
        else:
            self._txt_alertes.insert(
                tk.END, f"{len(sans_aem)} BP sans AEM correspondant :\n\n", "titre")
            sans_aem.sort(key=lambda d: d.get("date_debut", ""), reverse=True)
            for d in sans_aem:
                dd, df = d.get("date_debut", ""), d.get("date_fin", "")
                date_txt = f"{dd} → {df}" if df and df != dd else dd
                self._txt_alertes.insert(
                    tk.END,
                    f"• {date_txt} - {d.get('employeur','?')}\n", "ligne")
        self._txt_alertes.config(state=tk.DISABLED)

    def _maj_cartes(self, docs, sel, periodes):
        for w in self._frame_cartes.winfo_children():
            w.destroy()

        if not periodes:
            tk.Label(self._frame_cartes,
                     text="Aucun document trouvé — lancez une analyse ou vérifiez le dossier de base.",
                     fg="#888").pack(anchor="w")
            return

        # Grouper par période
        from collections import defaultdict
        par_periode = defaultdict(list)
        for d in docs:
            lbl = self._periode_de_doc(d, periodes) or "?"
            par_periode[lbl].append(d)

        # Afficher dans l'ordre des périodes (plus récente en premier)
        for label, debut, fin in periodes:
            lst = par_periode.get(label, [])
            total_h = sum(self._num(d.get("heures")) for d in lst)
            total_s = sum(self._num(d.get("salaire")) for d in lst)
            droits  = total_h >= 507
            emps    = sorted({d.get("employeur", "") for d in lst if d.get("employeur")})

            couleur = "#2E7D32" if total_h >= 720 else ("#1565C0" if droits else "#B71C1C")
            en_cours = "(en cours)" in label

            titre_carte = f"  {debut.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}{'  ◀' if en_cours else ''}  "
            card = tk.LabelFrame(self._frame_cartes, text=titre_carte,
                                  fg=couleur, font=("", 9, "bold"),
                                  padx=10, pady=6)
            card.pack(side=tk.LEFT, padx=6, pady=4, fill=tk.Y)

            if en_cours:
                tk.Label(card, text="▶ Période en cours", font=("", 8, "italic"),
                         fg="#E65100").grid(row=0, column=0, columnspan=2, sticky="w")

            statut_txt = "✓ Droits ouverts (≥507h)" if droits else "✗ Droits non ouverts (<507h)"
            tk.Label(card, text=statut_txt, font=("", 9, "bold"),
                     fg=couleur).grid(row=1, column=0, columnspan=2, sticky="w")

            for i, (lbl, val) in enumerate([
                ("Heures",     f"{total_h:.1f} h"),
                ("Salaire",    f"{total_s:.2f} €"),
                ("Contrats",   f"{len(lst)}"),
                ("Employeurs", f"{len(emps)}"),
            ], start=2):
                tk.Label(card, text=f"{lbl} :", anchor="w",
                         font=("", 8)).grid(row=i, column=0, sticky="w")
                tk.Label(card, text=val, font=("", 8, "bold"),
                         fg="#333").grid(row=i, column=1, sticky="w", padx=(6, 0))

            if emps:
                tk.Label(card, text=", ".join(emps[:3]) + ("…" if len(emps) > 3 else ""),
                         font=("", 7), fg="#555", wraplength=180, justify=tk.LEFT
                         ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 0))

            if total_s > SEUIL_SALAIRE_RENTABLE:
                tk.Label(card, text=f"⚠ +{total_s - SEUIL_SALAIRE_RENTABLE:.0f} € au-delà "
                         "de 14 400 € : plus rentable de déclarer en intermittent",
                         font=("", 7, "bold"), fg="#C62828", wraplength=180,
                         justify=tk.LEFT).grid(row=7, column=0, columnspan=2,
                                                sticky="w", pady=(3, 0))

    def _maj_tableau(self, docs, periodes):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._iid_docs = {}

        total_h = total_s = 0.0
        periode_courante = None

        docs_tries = sorted(docs, key=lambda d: (
            d.get("date_debut", "") or d.get("annee", ""),
            d.get("mois", ""),
        ), reverse=True)

        for d in docs_tries:
            per = self._periode_de_doc(d, periodes) or d.get("annee", "?")
            if per != periode_courante:
                if periode_courante is not None:
                    self.tree.insert("", tk.END, values=(
                        f"TOTAL période", "", "", "", "", "",
                        f"{total_h:.1f} h", f"{total_s:.2f} €"),
                        tags=("total",))
                    total_h = total_s = 0.0
                periode_courante = per
                # Ligne de séparateur de période
                self.tree.insert("", tk.END, values=(
                    "─── " + (per.replace("  (en cours)", " ◀ en cours") if per else ""),
                    "", "", "", "", "", "", ""),
                    tags=("separateur",))

            h = self._num(d.get("heures"))
            s = self._num(d.get("salaire"))
            total_h += h
            total_s += s
            tag = "previsionnel" if d.get("_previsionnel") else d.get("type", "").lower()
            dd, df = d.get("date_debut", ""), d.get("date_fin", "")
            jour_debut = dd[8:10] if len(dd) == 10 else dd
            jour_fin   = df[8:10] if len(df) == 10 else df
            iid = self.tree.insert("", tk.END, values=(
                jour_debut,
                jour_fin,
                OngletHistorique.MOIS_NOMS.get(d.get("mois", ""), d.get("mois", "")),
                d.get("annee", ""),
                d.get("type", "") + (" ⏳" if d.get("_previsionnel") else ""),
                d.get("employeur", ""),
                f"{h:.1f} h" if h else "—",
                f"{s:.2f} €" if s else "—",
            ), tags=(tag,))
            self._iid_docs[iid] = d

        if periode_courante:
            self.tree.insert("", tk.END, values=(
                f"TOTAL période", "", "", "", "", "",
                f"{total_h:.1f} h", f"{total_s:.2f} €"),
                tags=("total",))

        nb = len(docs)
        self._lbl_pied.config(text=f"{nb} contrat(s) affiché(s)")

    def _supprimer_selection(self):
        from previsionnel import supprimer_previsionnel
        sel = self.tree.selection()
        docs_sel = [self._iid_docs[i] for i in sel if i in self._iid_docs]
        a_supprimer = [d for d in docs_sel if d.get("_previsionnel") and d.get("id")]
        if not a_supprimer:
            messagebox.showinfo(
                "Rien à supprimer",
                "Sélectionnez un ou plusieurs contrats prévisionnels (⏳) — "
                "les documents classifiés ne peuvent pas être supprimés ici.",
                parent=self)
            return
        n = len(a_supprimer)
        question = ("Supprimer ce contrat prévisionnel ?" if n == 1 else
                    f"Supprimer ces {n} contrats prévisionnels ?")
        if not messagebox.askyesno("Supprimer", question, parent=self):
            return
        for d in a_supprimer:
            supprimer_previsionnel(d["id"])
        self.actualiser()

    @staticmethod
    def _num(v) -> float:
        try:
            return float(str(v).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return 0.0

    def _reset_dedup(self):
        global _dedup_en_cours
        _dedup_en_cours = False


# ---------------------------------------------------------------------------
# Onglet Revenus — vue pluriannuelle
# ---------------------------------------------------------------------------
class OngletRevenus(tk.Frame):
    """
    Vue transversale toutes périodes ARE confondues (mêmes périodes
    anniversaire que Bilan par période / Suivi, pas l'année calendaire) :
    évolution du salaire brut, répartition par employeur/type, estimation
    nette, historique du seuil de rentabilité (14 400€), export CSV.
    """

    COL = [
        ("periode",    "Période",       220),
        ("brut_reel",  "Brut réel",     90),
        ("brut_total", "Brut + prévi.", 90),
        ("net_estime", "Net estimé",    90),
        ("contrats",   "Contrats",      70),
        ("seuil",      "Seuil 14 400€", 160),
    ]

    def __init__(self, parent, cfg_getter):
        super().__init__(parent)
        self._cfg_getter = cfg_getter
        self._docs: list = []
        self._periodes: list = []
        self._stats_par_periode: dict = {}
        self._iid_periodes: dict = {}
        self._construire()

    # ── Construction UI ─────────────────────────────────────────────────────

    def _construire(self):
        bar = tk.Frame(self, pady=6, padx=10)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="💰 Revenus — vue par période ARE", font=("", 11, "bold"),
                 fg="#1A237E").pack(side=tk.LEFT)
        tk.Button(bar, text="↻ Actualiser", command=self.actualiser,
                  bg="#1976D2", fg="white", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)
        tk.Button(bar, text="📤 Exporter CSV", command=self._exporter_csv,
                  bg="#2E7D32", fg="white", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)

        bar2 = tk.Frame(self, padx=10)
        bar2.pack(fill=tk.X)
        tk.Label(bar2, text="Taux d'abattement estimé (brut → net) :").pack(side=tk.LEFT)
        self.var_taux = tk.StringVar(value=str(self._cfg_getter().get("taux_abattement_net", 10.0)))
        tk.Entry(bar2, textvariable=self.var_taux, width=6).pack(side=tk.LEFT, padx=(4, 4))
        tk.Label(bar2, text="%").pack(side=tk.LEFT)
        tk.Button(bar2, text="Appliquer", command=self._appliquer_taux,
                  padx=6, pady=1).pack(side=tk.LEFT, padx=8)

        # ── Graphique pluriannuel ────────────────────────────────────────────
        self._canvas_graph = tk.Canvas(self, height=170, bg="white",
                                       highlightthickness=0)
        self._canvas_graph.pack(fill=tk.X, padx=10, pady=(8, 4))
        self._canvas_graph.bind("<Configure>", lambda e: self._dessiner_graphique())

        # ── Corps : tableau années à gauche, détail à droite ─────────────────
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        frame_tableau = tk.Frame(paned)
        paned.add(frame_tableau, minsize=380)

        cols = [c[0] for c in self.COL]
        self.tree = ttk.Treeview(frame_tableau, columns=cols, show="headings",
                                 selectmode="browse", height=10)
        for cid, label, w in self.COL:
            self.tree.heading(cid, text=label)
            self.tree.column(cid, width=w, minwidth=40, anchor="w")
        self.tree.tag_configure("depasse", background="#FFEBEE")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select_periode())
        self._tri = _installer_tri(self.tree, cols)

        frame_detail = tk.Frame(paned, padx=8)
        paned.add(frame_detail, minsize=320)

        self._lbl_titre_detail = tk.Label(frame_detail, text="Détail — toutes périodes",
                                          font=("", 10, "bold"), fg="#1A237E")
        self._lbl_titre_detail.pack(anchor="w", pady=(4, 6))

        self._lbl_mensuel = tk.Label(frame_detail, text="", font=("", 9), fg="#333")
        self._lbl_mensuel.pack(anchor="w")
        self._lbl_net = tk.Label(frame_detail, text="", font=("", 9), fg="#333")
        self._lbl_net.pack(anchor="w")
        self._lbl_seuil = tk.Label(frame_detail, text="", font=("", 9, "bold"))
        self._lbl_seuil.pack(anchor="w", pady=(0, 8))

        tk.Label(frame_detail, text="Répartition par employeur",
                 font=("", 9, "bold"), fg="#555").pack(anchor="w")
        self._canvas_emp = tk.Canvas(frame_detail, height=140, bg="white",
                                     highlightthickness=0)
        self._canvas_emp.pack(fill=tk.X, pady=(2, 10))

        tk.Label(frame_detail, text="Répartition par type de document",
                 font=("", 9, "bold"), fg="#555").pack(anchor="w")
        self._canvas_type = tk.Canvas(frame_detail, height=60, bg="white",
                                      highlightthickness=0)
        self._canvas_type.pack(fill=tk.X, pady=(2, 4))

    # ── Données ──────────────────────────────────────────────────────────────

    def actualiser(self):
        from previsionnel import charger_previsionnels
        cfg = self._cfg_getter()
        dossier = cfg.get("dossier_base", "")
        docs = _scanner_tous_docs(dossier) if dossier else []

        prevs = charger_previsionnels()
        prevs_docs = []
        for p in prevs:
            d = dict(p)
            d.setdefault("type", "AEM")
            a, m = d.get("annee", ""), d.get("mois", "")
            dd = d.get("date_debut", "")
            df = d.get("date_fin", dd)
            if a and m and dd and len(dd) == 2:
                d["date_debut"] = f"{a}-{m}-{dd}"
                d["date_fin"] = f"{a}-{m}-{df}" if df and len(df) == 2 else d["date_debut"]
            d["_previsionnel"] = True
            prevs_docs.append(d)

        self._docs = docs + prevs_docs
        self._periodes = _calculer_periodes_anniversaire(self._docs, cfg)
        self._calculer_par_periode()
        self._dessiner_graphique()
        self._maj_tableau_periodes()
        self._on_select_periode()

    @staticmethod
    def _num(v) -> float:
        try:
            return float(str(v).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return 0.0

    def _calculer_par_periode(self):
        from collections import defaultdict
        par_periode = defaultdict(lambda: {
            "brut_reel": 0.0, "brut_total": 0.0, "contrats": 0,
            "employeurs": defaultdict(float), "types": defaultdict(float),
            "mois_actifs": set(),
        })
        for d in self._docs:
            periode = _periode_de_doc_globale(d, self._periodes)
            if not periode:
                continue
            s = self._num(d.get("salaire"))
            entry = par_periode[periode]
            if not d.get("_previsionnel"):
                entry["brut_reel"] += s
            entry["brut_total"] += s
            entry["contrats"] += 1
            emp = d.get("employeur", "")
            if emp:
                entry["employeurs"][emp] += s
            entry["types"][d.get("type", "?")] += s
            mois = d.get("mois", "")
            if mois:
                entry["mois_actifs"].add(mois)
        self._stats_par_periode = dict(par_periode)

    # ── Graphique pluriannuel ────────────────────────────────────────────────

    def _dessiner_graphique(self):
        c = self._canvas_graph
        c.delete("all")
        W = c.winfo_width() or 800
        H = 170

        # Ordre chronologique (self._periodes est renvoyé du plus récent au plus ancien)
        labels = [lbl for lbl, _, _ in reversed(self._periodes) if lbl in self._stats_par_periode]
        if not labels:
            c.create_text(W // 2, H // 2, text="Aucune donnée — cliquez Actualiser",
                          fill="#999", font=("", 9))
            return

        marge_g, marge_d, marge_h, marge_b = 50, 20, 16, 44
        largeur_utile = max(1, W - marge_g - marge_d)
        hauteur_utile = H - marge_h - marge_b
        n = len(labels)
        larg_barre = min(60, largeur_utile / n * 0.5)
        pas = largeur_utile / n

        max_val = max((self._stats_par_periode[lbl]["brut_total"] for lbl in labels), default=0)
        max_val = max(max_val, SEUIL_SALAIRE_RENTABLE, 1)

        # Ligne seuil 14 400€
        y_seuil = marge_h + hauteur_utile * (1 - SEUIL_SALAIRE_RENTABLE / max_val)
        c.create_line(marge_g, y_seuil, W - marge_d, y_seuil,
                      fill="#D32F2F", dash=(4, 2))
        c.create_text(W - marge_d, y_seuil - 8, text="14 400€", anchor="e",
                      font=("", 7), fill="#D32F2F")

        val_precedente = None
        for i, lbl in enumerate(labels):
            s = self._stats_par_periode[lbl]
            x_centre = marge_g + pas * i + pas / 2
            total = s["brut_total"]
            reel = s["brut_reel"]

            h_total = hauteur_utile * min(1.0, total / max_val)
            h_reel = hauteur_utile * min(1.0, reel / max_val)
            y_base = marge_h + hauteur_utile

            couleur_total = "#CE93D8" if total <= SEUIL_SALAIRE_RENTABLE else "#F8BBD0"
            couleur_reel = "#4A148C" if total <= SEUIL_SALAIRE_RENTABLE else "#B71C1C"

            c.create_rectangle(x_centre - larg_barre/2, y_base - h_total,
                               x_centre + larg_barre/2, y_base, fill=couleur_total, outline="")
            c.create_rectangle(x_centre - larg_barre/2, y_base - h_reel,
                               x_centre + larg_barre/2, y_base, fill=couleur_reel, outline="")

            c.create_text(x_centre, y_base - h_total - 10,
                          text=f"{total:.0f}€", font=("", 8, "bold"), fill="#333")

            if val_precedente and val_precedente > 0:
                evo = (total - val_precedente) / val_precedente * 100
                signe = "+" if evo >= 0 else ""
                c.create_text(x_centre, y_base - h_total - 22,
                              text=f"{signe}{evo:.0f}%",
                              font=("", 7), fill="#2E7D32" if evo >= 0 else "#C62828")
            val_precedente = total

            annee_courte = lbl.split("→")[1].strip()[6:10] if "→" in lbl else lbl
            c.create_text(x_centre, y_base + 14, text=annee_courte,
                          font=("", 9, "bold"), fill="#333")
            if "(en cours)" in lbl:
                c.create_text(x_centre, y_base + 28, text="◀ en cours",
                              font=("", 7, "italic"), fill="#E65100")

    # ── Tableau périodes ─────────────────────────────────────────────────────

    def _maj_tableau_periodes(self):
        self.tree.delete(*self.tree.get_children())
        self._iid_periodes = {}
        taux = self._taux_actuel()
        for lbl, _debut, _fin in self._periodes:
            if lbl not in self._stats_par_periode:
                continue
            s = self._stats_par_periode[lbl]
            total = s["brut_total"]
            net = total * (1 - taux / 100)
            depasse = total > SEUIL_SALAIRE_RENTABLE
            seuil_txt = (f"⚠ +{total - SEUIL_SALAIRE_RENTABLE:.0f}€"
                        if depasse else "✓ OK")
            iid = self.tree.insert("", tk.END, values=(
                lbl, f"{s['brut_reel']:.0f} €", f"{total:.0f} €",
                f"{net:.0f} €", s["contrats"], seuil_txt,
            ), tags=(("depasse",) if depasse else ()))
            self._iid_periodes[iid] = lbl

    def _on_select_periode(self):
        sel = self.tree.selection()
        periode = self._iid_periodes.get(sel[0]) if sel else None
        self._maj_detail(periode)

    # ── Détail (année sélectionnée ou global) ────────────────────────────────

    def _taux_actuel(self) -> float:
        try:
            return float(self.var_taux.get().replace(",", "."))
        except ValueError:
            return 10.0

    def _appliquer_taux(self):
        taux = self._taux_actuel()
        cfg = self._cfg_getter()
        cfg["taux_abattement_net"] = taux
        sauvegarder_config(cfg)
        self._maj_tableau_periodes()
        self._on_select_periode()

    def _maj_detail(self, periode):
        if periode and periode in self._stats_par_periode:
            s = self._stats_par_periode[periode]
            self._lbl_titre_detail.config(text=f"Détail — {periode}")
        elif self._stats_par_periode:
            s = {
                "brut_reel": sum(v["brut_reel"] for v in self._stats_par_periode.values()),
                "brut_total": sum(v["brut_total"] for v in self._stats_par_periode.values()),
                "contrats": sum(v["contrats"] for v in self._stats_par_periode.values()),
                "employeurs": defaultdict_sum(
                    [v["employeurs"] for v in self._stats_par_periode.values()]),
                "types": defaultdict_sum(
                    [v["types"] for v in self._stats_par_periode.values()]),
                "mois_actifs": set().union(
                    *[v["mois_actifs"] for v in self._stats_par_periode.values()]) or set(),
            }
            self._lbl_titre_detail.config(text="Détail — toutes périodes")
        else:
            self._lbl_titre_detail.config(text="Détail — aucune donnée")
            self._lbl_mensuel.config(text="")
            self._lbl_net.config(text="")
            self._lbl_seuil.config(text="")
            self._canvas_emp.delete("all")
            self._canvas_type.delete("all")
            return

        nb_mois = max(1, len(s["mois_actifs"]))
        moyenne_mensuelle = s["brut_total"] / nb_mois
        self._lbl_mensuel.config(
            text=f"Revenu mensuel moyen : {moyenne_mensuelle:.0f} € "
                 f"(sur {nb_mois} mois actif(s))")

        taux = self._taux_actuel()
        net = s["brut_total"] * (1 - taux / 100)
        self._lbl_net.config(
            text=f"Estimation nette ({taux:.0f}% d'abattement) : {net:.0f} €")

        depasse = s["brut_total"] > SEUIL_SALAIRE_RENTABLE
        if depasse:
            self._lbl_seuil.config(
                text=f"⚠ Dépasse le seuil de 14 400€ (+{s['brut_total']-SEUIL_SALAIRE_RENTABLE:.0f} €) "
                     "— plus rentable de déclarer en intermittent",
                fg="#C62828")
        else:
            self._lbl_seuil.config(
                text=f"✓ Sous le seuil de 14 400€ ({SEUIL_SALAIRE_RENTABLE - s['brut_total']:.0f} € de marge)",
                fg="#2E7D32")

        self._dessiner_repartition_employeur(s["employeurs"])
        self._dessiner_repartition_type(s["types"])

    def _dessiner_repartition_employeur(self, employeurs: dict):
        c = self._canvas_emp
        c.delete("all")
        c.update_idletasks()
        W = c.winfo_width() or 280
        if not employeurs:
            c.create_text(W // 2, 20, text="Aucun employeur", fill="#999", font=("", 8))
            return
        total = sum(employeurs.values()) or 1
        classement = sorted(employeurs.items(), key=lambda kv: kv[1], reverse=True)[:6]
        y = 6
        for emp, montant in classement:
            pct = montant / total
            c.create_text(4, y, text=f"{emp[:22]}", anchor="nw", font=("", 8), fill="#333")
            c.create_text(W - 4, y, text=f"{montant:.0f} € ({pct*100:.0f}%)",
                          anchor="ne", font=("", 8, "bold"), fill="#4A148C")
            y += 12
            largeur = max(2, int((W - 8) * pct))
            c.create_rectangle(4, y, 4 + largeur, y + 8, fill="#7B1FA2", outline="")
            y += 16

    def _dessiner_repartition_type(self, types: dict):
        c = self._canvas_type
        c.delete("all")
        c.update_idletasks()
        W = c.winfo_width() or 280
        if not types:
            c.create_text(W // 2, 20, text="Aucun document", fill="#999", font=("", 8))
            return
        total = sum(types.values()) or 1
        couleurs = {"AEM": "#1565C0", "BP": "#2E7D32", "CS": "#F9A825",
                   "CT": "#F9A825", "STC": "#AD1457"}
        y = 4
        for t, montant in sorted(types.items(), key=lambda kv: kv[1], reverse=True):
            pct = montant / total
            c.create_text(4, y, text=f"{t} : {montant:.0f} € ({pct*100:.0f}%)",
                          anchor="nw", font=("", 8), fill=couleurs.get(t, "#555"))
            largeur = max(2, int((W - 8) * pct))
            c.create_rectangle(4, y + 12, 4 + largeur, y + 20,
                               fill=couleurs.get(t, "#999"), outline="")
            y += 26

    # ── Export CSV ───────────────────────────────────────────────────────────

    def _exporter_csv(self):
        if not self._stats_par_periode:
            messagebox.showinfo("Rien à exporter", "Cliquez d'abord sur Actualiser.",
                                parent=self)
            return
        chemin = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[("Fichier CSV", "*.csv")],
            initialfile="revenus_intermitdoc.csv")
        if not chemin:
            return
        import csv
        taux = self._taux_actuel()
        try:
            with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Période ARE", "Brut réel (€)", "Brut réel + prévisionnel (€)",
                           f"Net estimé -{taux:.0f}% (€)", "Contrats", "Dépasse 14 400€"])
                for lbl, _debut, _fin in self._periodes:
                    if lbl not in self._stats_par_periode:
                        continue
                    s = self._stats_par_periode[lbl]
                    total = s["brut_total"]
                    net = total * (1 - taux / 100)
                    w.writerow([lbl, f"{s['brut_reel']:.2f}", f"{total:.2f}",
                               f"{net:.2f}", s["contrats"],
                               "Oui" if total > SEUIL_SALAIRE_RENTABLE else "Non"])
            messagebox.showinfo("Export réussi", f"Fichier enregistré :\n{chemin}",
                                parent=self)
        except OSError as e:
            messagebox.showerror("Erreur d'export", str(e), parent=self)


def defaultdict_sum(dicts: list) -> dict:
    """Fusionne une liste de dicts numériques en sommant les valeurs communes."""
    from collections import defaultdict
    resultat = defaultdict(float)
    for d in dicts:
        for k, v in d.items():
            resultat[k] += v
    return dict(resultat)


# ---------------------------------------------------------------------------
# Dialogue rapport d'erreur copiable
# ---------------------------------------------------------------------------
class DialogueRapport(tk.Toplevel):
    """
    Affiche un message avec un bouton 📋 Copier pour envoyer le rapport.
    Utiliser DialogueRapport.afficher(parent, titre, message).
    """
    def __init__(self, parent, titre: str, message: str):
        super().__init__(parent)
        self.title(titre)
        self.resizable(True, True)
        self.grab_set()

        tk.Label(self, text=titre, font=("", 11, "bold"), fg="#B71C1C",
                 wraplength=480).pack(padx=16, pady=(14, 6))

        frame_txt = tk.Frame(self)
        frame_txt.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
        sb = tk.Scrollbar(frame_txt)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._txt = tk.Text(frame_txt, wrap=tk.WORD, height=14, width=64,
                            yscrollcommand=sb.set, font=("Courier", 9))
        self._txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._txt.yview)
        self._txt.insert("1.0", message)
        self._txt.config(state=tk.DISABLED)

        self._copie_label = tk.StringVar(value="📋 Copier le rapport")
        frame_btn = tk.Frame(self)
        frame_btn.pack(pady=10)
        tk.Button(frame_btn, textvariable=self._copie_label,
                  command=self._copier, bg="#1565C0", fg="white",
                  padx=10).pack(side=tk.LEFT, padx=6)
        tk.Button(frame_btn, text="Fermer",
                  command=self.destroy, padx=10).pack(side=tk.LEFT, padx=6)

        self.update_idletasks()
        w, h = max(500, self.winfo_reqwidth()), max(380, self.winfo_reqheight())
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _copier(self):
        self.clipboard_clear()
        self.clipboard_append(self._txt.get("1.0", tk.END))
        self._copie_label.set("✅ Copié !")
        self.after(2000, lambda: self._copie_label.set("📋 Copier le rapport"))

    @classmethod
    def afficher(cls, parent, titre: str, message: str):
        cls(parent, titre, message)


# ---------------------------------------------------------------------------
# Dialogue saisie infos manquantes AEM
# ---------------------------------------------------------------------------
class DialogueInfosManquantes(tk.Toplevel):
    """
    Affiche les champs extraits d'un AEM et permet de compléter les manquants.
    Panneau gauche : preview PDF de la page.
    Panneau droit  : formulaire de saisie.
    Retourne l'analyse complétée ou None si annulé.
    """

    CHAMPS = [
        ("employeur",    "Employeur",    False),
        ("date_debut",   "Date début",   False),
        ("date_fin",     "Date fin",     False),
        ("heures",       "Heures",       True),
        ("salaire_brut", "Salaire brut", True),
    ]

    def __init__(self, parent, analyse: dict, numero_page: int,
                 page_pdf_bytes: bytes = b""):
        super().__init__(parent)
        self.title(f"AEM page {numero_page} — Compléter les informations")
        self.geometry("960x600")
        self.minsize(700, 450)
        self.resizable(True, True)
        self.grab_set()
        self._analyse        = dict(analyse)
        self._resultat       = None
        self._vars           = {}
        self._page_pdf_bytes = page_pdf_bytes
        self._photo          = None
        self._img_base       = None
        self._construire(numero_page)
        self._rendre_preview()
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")
        self.wait_window()

    def _construire(self, numero_page):
        main = tk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Panneau gauche : preview ──────────────────────────────────────────
        frame_prev = tk.Frame(main, bg="#444", width=480)
        frame_prev.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        frame_prev.pack_propagate(False)

        self.canvas_prev = tk.Canvas(frame_prev, bg="#555", cursor="crosshair",
                                     highlightthickness=0)
        sb_v = tk.Scrollbar(frame_prev, orient=tk.VERTICAL,
                             command=self.canvas_prev.yview)
        sb_h = tk.Scrollbar(frame_prev, orient=tk.HORIZONTAL,
                             command=self.canvas_prev.xview)
        self.canvas_prev.configure(yscrollcommand=sb_v.set,
                                   xscrollcommand=sb_h.set)
        sb_v.pack(side=tk.RIGHT,  fill=tk.Y)
        sb_h.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas_prev.pack(fill=tk.BOTH, expand=True)
        self.canvas_prev.bind("<Configure>", lambda e: self._afficher_preview())
        self.canvas_prev.bind("<MouseWheel>", self._on_scroll)

        # ── Panneau droit : formulaire ────────────────────────────────────────
        frame_form = tk.Frame(main, padx=20, pady=14, width=380)
        frame_form.pack(side=tk.LEFT, fill=tk.Y)
        frame_form.pack_propagate(False)

        tk.Label(frame_form, text=f"AEM — Page {numero_page}",
                 font=("", 11, "bold"), fg="#1A237E").pack(anchor="w")
        tk.Label(frame_form,
                 text="Complétez les champs manquants (en rouge) :",
                 fg="#555", font=("", 9)).pack(anchor="w", pady=(2, 10))

        grid = tk.Frame(frame_form)
        grid.pack(fill=tk.X)

        for row, (cle, libelle, obligatoire) in enumerate(self.CHAMPS):
            valeur   = self._analyse.get(cle, "").strip()
            manquant = not valeur and obligatoire
            couleur  = "#B71C1C" if manquant else "#333"

            tk.Label(grid, text=f"{libelle} :", width=14, anchor="e",
                     fg=couleur,
                     font=("", 9, "bold" if manquant else "normal")
                     ).grid(row=row, column=0, sticky="e", pady=4)

            var = tk.StringVar(value=valeur)
            self._vars[cle] = var
            e = tk.Entry(grid, textvariable=var, width=26,
                         bg="#FFEBEE" if manquant else "white",
                         font=("", 10))
            e.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=4)
            if row == 0 and manquant:
                e.focus_set()

        # Boutons
        frame_btn = tk.Frame(frame_form, pady=16)
        frame_btn.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(frame_btn, text="Valider", bg="#1976D2", fg="white",
                  font=("", 10, "bold"), width=13,
                  command=self._valider).pack(pady=4, fill=tk.X)
        tk.Button(frame_btn, text="Ignorer cette page", fg="#B71C1C",
                  width=13, command=self.destroy).pack(fill=tk.X)

    def _rendre_preview(self):
        if not self._page_pdf_bytes:
            self.canvas_prev.create_text(
                10, 10, anchor="nw", text="Aucune preview disponible",
                fill="#aaa", font=("", 10))
            return
        try:
            import fitz
            doc  = fitz.open(stream=self._page_pdf_bytes, filetype="pdf")
            page = doc[0]
            mat  = fitz.Matrix(150 / 72, 150 / 72)
            pix  = page.get_pixmap(matrix=mat, alpha=False)
            data = pix.tobytes("png")
            doc.close()
            self._img_base = Image.open(io.BytesIO(data))
            self.after(100, self._afficher_preview)
        except Exception as e:
            self.canvas_prev.create_text(
                10, 10, anchor="nw", text=f"Erreur preview : {e}",
                fill="red", font=("", 9))

    def _afficher_preview(self):
        if self._img_base is None:
            return
        cw = self.canvas_prev.winfo_width()
        ch = self.canvas_prev.winfo_height()
        if cw < 10 or ch < 10:
            return
        zoom = min(cw / self._img_base.width, ch / self._img_base.height) * 0.97
        w = int(self._img_base.width  * zoom)
        h = int(self._img_base.height * zoom)
        img = self._img_base.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.canvas_prev.delete("all")
        self.canvas_prev.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas_prev.configure(scrollregion=(0, 0, w, h))

    def _on_scroll(self, event):
        if event.delta > 0:
            self.canvas_prev.yview_scroll(-1, "units")
        else:
            self.canvas_prev.yview_scroll(1, "units")

    def _valider(self):
        for cle, libelle, obligatoire in self.CHAMPS:
            if obligatoire and not self._vars[cle].get().strip():
                messagebox.showwarning("Champ requis",
                    f"Le champ « {libelle} » est obligatoire.", parent=self)
                return
        for cle, _, _ in self.CHAMPS:
            val = self._vars[cle].get().strip()
            if val:
                self._analyse[cle] = val
        self._resultat = self._analyse
        self.destroy()

    @classmethod
    def demander(cls, parent, analyse: dict, numero_page: int,
                 page_pdf_bytes: bytes = b"") -> dict | None:
        dlg = cls(parent, analyse, numero_page, page_pdf_bytes)
        return dlg._resultat


# ---------------------------------------------------------------------------
# Dialogue Calcul ARE + Congés Spectacle
# ---------------------------------------------------------------------------
class DialogueCalculARE(tk.Toplevel):
    """
    Estimation ARE et Congés Spectacle — formule officielle France Travail 2025.
    Source : Guide pratique intermittents du spectacle (France Travail).
    """

    AJ_MIN      = 31.96   # Base de calcul AJ minimale (€) — juillet 2023
    PLAFOND_AJ  = 174.80  # Plafond absolu AJ brute (€/j)
    DUREE_JOURS = 243     # Durée maximale indemnisation (8 mois)
    CARENCE     = 7       # Jours de carence fixes
    SMIC_MENSUEL = 1801.80  # SMIC mensuel brut 2025 (€)
    CONGES_PCT  = 0.10    # Estimation congés spectacle (10% brut)

    # Paramètres par annexe : (coeff_SR1, seuil_SR, coeff_SR2,
    #                          coeff_NHT1, seuil_NHT, coeff_NHT2,
    #                          coeff_C, plancher)
    ANNEXE_PARAMS = {
        "8":  (0.42, 14400, 0.05,  0.26, 720, 0.08,  0.40, 38.00),
        "10": (0.36, 13700, 0.05,  0.26, 690, 0.08,  0.70, 44.00),
    }

    def __init__(self, parent, stats: dict, cfg: dict):
        super().__init__(parent)
        self.title("Estimation ARE & Congés Spectacle")
        self.geometry("680x720")
        self.minsize(600, 640)
        self.resizable(True, True)
        self._stats = stats
        self._cfg   = cfg
        self._construire()
        self._calculer()
        # Centrer
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    # ── Construction ─────────────────────────────────────────────────────────

    def _construire(self):
        # En-tête
        hdr = tk.Frame(self, bg="#E65100")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Estimation ARE & Congés Spectacle",
                 bg="#E65100", fg="white",
                 font=("", 13, "bold"), pady=10).pack(side=tk.LEFT, padx=14)
        annexe = self._cfg.get("annexe", "?")
        tk.Label(hdr, text=f"Annexe {annexe} — taux France Travail 2025",
                 bg="#E65100", fg="#FFE0CC",
                 font=("", 9)).pack(side=tk.RIGHT, padx=14)

        # Zone principale scrollable
        frame_scroll = tk.Frame(self)
        frame_scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        scroll = tk.Scrollbar(frame_scroll)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._canvas = tk.Canvas(frame_scroll, yscrollcommand=scroll.set,
                                  highlightthickness=0)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self._canvas.yview)

        self._frame_inner = tk.Frame(self._canvas)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._frame_inner, anchor="nw")

        self._frame_inner.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(
                self._canvas_window, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Pied
        frame_bas = tk.Frame(self, relief=tk.RIDGE, bd=1, pady=6)
        frame_bas.pack(fill=tk.X, padx=0)
        tk.Label(frame_bas,
                 text="⚠  Ces estimations sont indicatives. Seul France Travail peut calculer vos droits exacts.\n"
                      "Taux 2025 — peuvent évoluer. Vérifiez sur www.francetravail.fr",
                 font=("", 8), fg="#B71C1C", justify=tk.CENTER).pack()
        tk.Button(frame_bas, text="Fermer", command=self.destroy,
                  padx=14, pady=4).pack(pady=4)

    def _section(self, titre: str, couleur: str) -> tk.Frame:
        """Crée une section titrée dans le frame scrollable."""
        lbl_titre = tk.Label(self._frame_inner, text=titre,
                              font=("", 10, "bold"), fg="white",
                              bg=couleur, anchor="w", padx=8, pady=4)
        lbl_titre.pack(fill=tk.X, pady=(12, 0))
        frame = tk.Frame(self._frame_inner, relief=tk.GROOVE, bd=1,
                          padx=10, pady=8)
        frame.pack(fill=tk.X)
        return frame

    def _ligne(self, parent, label: str, valeur: str,
               couleur_val="#1565C0", gras_val=False, note: str = ""):
        """Ajoute une ligne label / valeur dans une section."""
        row = tk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=32, anchor="w",
                 font=("", 9)).pack(side=tk.LEFT)
        tk.Label(row, text=valeur, anchor="w",
                 font=("", 9, "bold") if gras_val else ("", 9),
                 fg=couleur_val).pack(side=tk.LEFT)
        if note:
            tk.Label(row, text=f"  ({note})", font=("", 8),
                     fg="#888").pack(side=tk.LEFT)

    def _separateur(self, parent):
        tk.Frame(parent, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=4)

    # ── Helpers calcul ───────────────────────────────────────────────────────

    @staticmethod
    def _calc_aj_brute(nht: float, sr: float, annexe: str,
                       params: tuple, aj_min: float, plafond: float) -> tuple:
        """Calcule l'AJ brute selon la formule officielle A+B+C."""
        a1, seuil_sr, a2, b1, seuil_nht, b2, coeff_c, plancher = params
        partie_a = aj_min * (a1 * min(sr, seuil_sr) + a2 * max(0.0, sr - seuil_sr)) / 5000
        partie_b = aj_min * (b1 * min(nht, seuil_nht) + b2 * max(0.0, nht - seuil_nht)) / 507
        partie_c = aj_min * coeff_c
        aj = partie_a + partie_b + partie_c
        aj = max(plancher, min(plafond, aj))
        return aj, partie_a, partie_b, partie_c

    @staticmethod
    def _calc_aj_nette(aj_brute: float, aj_min: float) -> tuple:
        """Calcule l'AJ nette avec les déductions par paliers."""
        if aj_brute < aj_min:
            return aj_brute, 0.0, 0.0, 0.0
        # Retraite complémentaire : 3% de l'AJ brute (tous cas ≥ AJ min)
        retraite = aj_brute * 0.03
        if aj_brute <= 60.0:
            return aj_brute - retraite, retraite, 0.0, 0.0
        # CSG 6,2% + CRDS 0,5% (assiette = 98,25% de l'AJ brute)
        csg  = aj_brute * 0.9825 * 0.062
        crds = aj_brute * 0.9825 * 0.005
        return aj_brute - retraite - csg - crds, retraite, csg, crds

    # ── Calcul ───────────────────────────────────────────────────────────────

    def _calculer(self):
        s         = self._stats
        total_h   = s.get("total_heures",  0.0)
        total_sal = s.get("total_salaire", 0.0)
        sjr       = s.get("sjr",           0.0)
        droits    = s.get("droits_ouverts", False)
        nb_jours  = s.get("nb_jours",      365)
        annexe    = self._cfg.get("annexe", "")

        # Déterminer quelle(s) annexe(s) calculer
        annexes_a_calculer = []
        if annexe in ("8", "10"):
            annexes_a_calculer = [annexe]
        elif annexe == "8+10":
            annexes_a_calculer = ["8", "10"]
        else:
            annexes_a_calculer = ["8"]  # défaut

        # ── Section 1 : Éligibilité ──────────────────────────────────────
        f1 = self._section("1 — Éligibilité", "#37474F")
        self._ligne(f1, "Heures travaillées sur la période",
                    f"{total_h:.0f} h",
                    couleur_val="#2E7D32" if total_h >= 507 else "#C62828", gras_val=True)
        self._ligne(f1, "Seuil minimum requis", "507 heures")
        if 338 <= total_h < 507:
            self._ligne(f1, "⚠ Clause de rattrapage possible",
                        "338-506h + 5 ans d'ancienneté → +6 mois",
                        couleur_val="#E65100")
        self._ligne(f1, "Statut",
                    "✓ Droits ouverts" if droits else "✗ Droits non ouverts — 507h non atteintes",
                    couleur_val="#2E7D32" if droits else "#C62828", gras_val=True)
        labels_annexe = {"8": "Annexe 8 (Technicien)", "10": "Annexe 10 (Artiste)",
                         "8+10": "Annexes 8 & 10"}
        self._ligne(f1, "Annexe", labels_annexe.get(annexe, "non définie"),
                    couleur_val="#1565C0")
        tk.Label(f1,
                 text="Date anniversaire = 365 jours après la fin de votre dernier contrat (FCT).",
                 font=("", 8), fg="#666").pack(anchor="w", pady=(4, 0))

        # ── Section 2 : SJR ─────────────────────────────────────────────
        f2 = self._section("2 — Salaire Journalier de Référence (SJR)", "#1565C0")
        self._ligne(f2, "Total salaire brut de la période", f"{total_sal:.2f} €")
        self._ligne(f2, "Jours calendaires de la période",  f"{nb_jours} jours")
        self._ligne(f2, "SJR = salaire ÷ jours calendaires",
                    f"{sjr:.2f} €/jour", gras_val=True)
        tk.Label(f2,
                 text="Le SJR sert à calculer la franchise salaires.",
                 font=("", 8), fg="#555").pack(anchor="w")

        # ── Sections AJR par annexe ──────────────────────────────────────
        # Mémoriser pour le récap
        resultats_annexe = {}
        for ann in annexes_a_calculer:
            params = self.ANNEXE_PARAMS[ann]
            plancher = params[7]
            label_ann = {"8": "Annexe 8 — Technicien", "10": "Annexe 10 — Artiste"}[ann]
            couleur_ann = "#E65100" if ann == "8" else "#6A1B9A"

            f3 = self._section(f"3 — AJR {label_ann}", couleur_ann)

            aj_brute, pa, pb, pc = self._calc_aj_brute(
                total_h, total_sal, ann, params, self.AJ_MIN, self.PLAFOND_AJ)
            aj_nette, retraite, csg, crds = self._calc_aj_nette(aj_brute, self.AJ_MIN)
            mensuel_brut = aj_brute * 30.4
            mensuel_net  = aj_nette * 30.4

            a1, seuil_sr, a2, b1, seuil_nht, b2, coeff_c, _ = params
            self._ligne(f3, f"AJ minimale (base de calcul)", f"{self.AJ_MIN:.2f} €")
            self._separateur(f3)
            self._ligne(f3,
                f"Partie A  [{a1*100:.0f}% × min(SR,{seuil_sr}€) + {a2*100:.0f}% × excédent] / 5000",
                f"{pa:.4f} €/jour", couleur_val="#555")
            self._ligne(f3,
                f"Partie B  [{b1*100:.0f}% × min(NHT,{seuil_nht}h) + {b2*100:.0f}% × excédent] / 507",
                f"{pb:.4f} €/jour", couleur_val="#555")
            self._ligne(f3,
                f"Partie C  {self.AJ_MIN:.2f} × {coeff_c:.2f}",
                f"{pc:.4f} €/jour", couleur_val="#555")
            self._separateur(f3)

            aj_mode = ""
            if aj_brute >= self.PLAFOND_AJ:
                aj_mode = f"plafonnée à {self.PLAFOND_AJ}€"
            elif aj_brute <= plancher:
                aj_mode = f"plancher {plancher}€ appliqué"
            self._ligne(f3, "AJR brute (A+B+C, entre plancher et plafond)",
                        f"{aj_brute:.2f} €/jour", gras_val=True,
                        couleur_val=couleur_ann, note=aj_mode)
            self._separateur(f3)

            # Déductions AJ nette
            if aj_brute < self.AJ_MIN:
                self._ligne(f3, "Déductions (AJ < AJ min)", "aucune", couleur_val="#555")
            elif aj_brute <= 60.0:
                self._ligne(f3, "Retraite complémentaire (3%)",
                            f"- {retraite:.2f} €/jour", couleur_val="#888")
                self._ligne(f3, "CSG/CRDS (AJ ≤ 60€)", "non applicable", couleur_val="#888")
            else:
                self._ligne(f3, "Retraite complémentaire (3%)",
                            f"- {retraite:.2f} €/jour", couleur_val="#888")
                self._ligne(f3, "CSG 6,2% + CRDS 0,5% (× 98,25%)",
                            f"- {csg+crds:.2f} €/jour", couleur_val="#888")
            self._ligne(f3, "AJR nette estimée",
                        f"{aj_nette:.2f} €/jour", gras_val=True,
                        couleur_val="#2E7D32")
            self._separateur(f3)
            self._ligne(f3, "Mensuel brut estimé (× 30,4 j)",
                        f"{mensuel_brut:.0f} €/mois")
            self._ligne(f3, "Mensuel net estimé",
                        f"{mensuel_net:.0f} €/mois", gras_val=True,
                        couleur_val="#2E7D32")
            resultats_annexe[ann] = {
                "aj_brute": aj_brute, "aj_nette": aj_nette,
                "mensuel_brut": mensuel_brut, "mensuel_net": mensuel_net,
                "plancher": plancher,
            }

        # Pour le récap, prendre la première annexe calculée
        res = resultats_annexe[annexes_a_calculer[0]]
        aj_brute  = res["aj_brute"]
        aj_nette  = res["aj_nette"]
        mensuel_brut = res["mensuel_brut"]
        mensuel_net  = res["mensuel_net"]

        # ── Section 4 : Durée & Franchise ───────────────────────────────
        f4 = self._section("4 — Durée d'indemnisation & Franchises", "#6A1B9A")

        # Franchise congés payés : (jours travaillés × 2,5) / 24, plafonnée 30j
        nb_jours_contrats = (total_h / 8.0) if total_h else 0  # approximation
        franchise_cp = min(30, (nb_jours_contrats * 2.5) / 24) if nb_jours_contrats else 0
        franchise_cp = round(franchise_cp)

        # Franchise salaires : max(0, total_sal/SJR - 27) × 3, plafonnée 75j
        smic_j = self.SMIC_MENSUEL / 30.5
        if sjr > 0:
            franchise_sal = max(0.0, (total_sal / sjr) - 27) * 3
        else:
            franchise_sal = 0.0
        franchise_sal = min(75, round(franchise_sal))

        total_attente = self.CARENCE + franchise_cp + franchise_sal
        duree_nette   = max(0, self.DUREE_JOURS - total_attente)
        total_are_brut = aj_brute * self.DUREE_JOURS
        total_are_net  = aj_nette * self.DUREE_JOURS

        self._ligne(f4, "Durée maximale d'indemnisation",
                    f"{self.DUREE_JOURS} jours (8 mois)")
        self._separateur(f4)
        self._ligne(f4, "Délai de carence fixe",
                    f"{self.CARENCE} jours")
        self._ligne(f4, "Franchise congés payés  (j_trav × 2,5 / 24, max 30j)",
                    f"{franchise_cp} jours",
                    note=f"≈ {nb_jours_contrats:.0f} jours de contrats estimés")
        self._ligne(f4, "Franchise salaires  (hors SMIC 27j, × 3, max 75j)",
                    f"{franchise_sal} jours")
        self._separateur(f4)
        self._ligne(f4, "Délai total avant 1er versement",
                    f"{total_attente} jours", gras_val=True,
                    couleur_val="#6A1B9A")
        self._ligne(f4, "Durée indemnisable nette estimée",
                    f"{duree_nette} jours (~{duree_nette//30} mois)")
        self._separateur(f4)
        self._ligne(f4, "Total ARE brut sur 243 jours",
                    f"{total_are_brut:.0f} €", gras_val=True)
        self._ligne(f4, "Total ARE net sur 243 jours",
                    f"{total_are_net:.0f} €", gras_val=True,
                    couleur_val="#2E7D32")

        # ── Section 5 : Congés Spectacle ────────────────────────────────
        f5 = self._section("5 — Congés Spectacle (Audiens / CCS)", "#2E7D32")

        conges_estim = total_sal * self.CONGES_PCT

        self._ligne(f5, "Total salaire brut de la période", f"{total_sal:.2f} €")
        self._ligne(f5, "Estimation (10% du brut — cotisation employeurs)",
                    f"≈ {conges_estim:.2f} €", gras_val=True,
                    couleur_val="#2E7D32")
        tk.Label(f5,
                 text=("Le montant exact dépend des déclarations de chaque employeur à la CCS.\n"
                       "Vérifiez votre solde réel sur : espacepersonnel.audiens.org"),
                 font=("", 8), fg="#555", justify=tk.LEFT, wraplength=580
                 ).pack(anchor="w", pady=(4, 0))

        # ── Section 6 : Récapitulatif ────────────────────────────────────
        f6 = self._section("6 — Récapitulatif", "#1A237E")

        recap = [
            ("AJR brute",          f"{aj_brute:.2f} €/jour"),
            ("AJR nette",          f"{aj_nette:.2f} €/jour"),
            ("Mensuel net ARE",    f"{mensuel_net:.0f} €/mois"),
            ("Total ARE net",      f"{total_are_net:.0f} € sur {self.DUREE_JOURS}j"),
            ("Congés Spectacle",   f"≈ {conges_estim:.2f} €"),
            ("Délai avant paiement", f"{total_attente} jours"),
        ]
        for label, val in recap:
            row = tk.Frame(f6, pady=2)
            row.pack(fill=tk.X)
            tk.Label(row, text=label, width=28, anchor="w",
                     font=("", 10)).pack(side=tk.LEFT)
            tk.Label(row, text=val, font=("", 11, "bold"),
                     fg="#1A237E").pack(side=tk.LEFT)

        # Barre visuelle AJR brute vs nette
        tk.Frame(f6, height=1, bg="#DDDDDD").pack(fill=tk.X, pady=6)
        tk.Label(f6, text="AJR journalière estimée :",
                 font=("", 9, "bold")).pack(anchor="w")

        canvas_recap = tk.Canvas(f6, height=50, highlightthickness=0, bg="white")
        canvas_recap.pack(fill=tk.X, pady=4)
        canvas_recap.update_idletasks()
        W = canvas_recap.winfo_width() or 560

        max_val  = max(aj_brute, 1)
        w_brut   = int((W - 8) * min(1.0, aj_brute / self.PLAFOND_AJ))
        w_net    = int((W - 8) * min(1.0, aj_nette  / self.PLAFOND_AJ))

        canvas_recap.create_rectangle(4, 6, 4+w_brut, 24,
                                       fill="#90CAF9", outline="")
        canvas_recap.create_text(4+w_brut+4, 15,
                                  text=f"{aj_brute:.2f}€/j brut",
                                  anchor="w", font=("", 8), fill="#555")
        canvas_recap.create_rectangle(4, 28, 4+w_net, 46,
                                       fill="#2E7D32", outline="")
        canvas_recap.create_text(4+w_net+4, 37,
                                  text=f"{aj_nette:.2f}€/j net",
                                  anchor="w", font=("", 8, "bold"),
                                  fill="#2E7D32")


# ---------------------------------------------------------------------------
# Dialogue de bienvenue / premier lancement
# ---------------------------------------------------------------------------
class DialogueBienvenue(tk.Toplevel):
    """
    Affiché au premier lancement (ou si annexe non définie).
    Demande sous quelle annexe l'utilisateur cotise.
    """

    ANNEXES = {
        "8":    {
            "label": "Annexe 8 — Technicien du spectacle",
            "desc":  (
                "Techniciens, ouvriers, machinistes, régisseurs,\n"
                "ingénieurs du son, éclairagistes, décorateurs…\n\n"
                "Période de référence : 12 mois\n"
                "Seuil d'ouverture des droits : 507 heures"
            ),
            "couleur": "#1565C0",
        },
        "10":   {
            "label": "Annexe 10 — Artiste du spectacle",
            "desc":  (
                "Comédiens, musiciens, chanteurs, danseurs,\n"
                "metteurs en scène, chorégraphes, réalisateurs…\n\n"
                "Période de référence : 12 mois\n"
                "Seuil d'ouverture des droits : 507 heures"
            ),
            "couleur": "#6A1B9A",
        },
        "8+10": {
            "label": "Les deux (Annexe 8 + Annexe 10)",
            "desc":  (
                "Vous exercez des activités techniques ET artistiques.\n"
                "Les heures des deux annexes sont cumulées pour\n"
                "atteindre le seuil de 507 heures.\n\n"
                "IntermitDoc suivra les deux types de contrats."
            ),
            "couleur": "#2E7D32",
        },
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Bienvenue dans IntermitDoc")
        self.resizable(False, False)
        self.annexe_choisie = ""
        self.dossier_choisi = ""
        self._var = tk.StringVar(value="")
        self._construire()
        self.grab_set()
        self.focus_set()
        # Centrer sur l'écran
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _construire(self):
        # ── En-tête ──────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg="#1A237E")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="IntermitDoc",
                 bg="#1A237E", fg="white",
                 font=("", 20, "bold"), pady=14).pack()
        tk.Label(hdr, text="Suivi des droits — Intermittent du Spectacle",
                 bg="#1A237E", fg="#C5CAE9",
                 font=("", 10), pady=0).pack()
        tk.Label(hdr, text="", bg="#1A237E").pack(pady=4)

        tk.Label(self,
                 text="Sous quelle annexe êtes-vous affilié ?",
                 font=("", 12, "bold"), pady=14).pack()

        # ── Cartes de choix ───────────────────────────────────────────────
        frame_cartes = tk.Frame(self, padx=20)
        frame_cartes.pack(fill=tk.X)

        for val, info in self.ANNEXES.items():
            self._carte(frame_cartes, val, info)

        # ── Dossier de base ──────────────────────────────────────────────────
        tk.Label(self, text="Dossier où seront classés vos documents",
                 font=("", 12, "bold"), pady=(14, 6)).pack()
        frame_dossier = tk.Frame(self, padx=20)
        frame_dossier.pack(fill=tk.X)
        self._var_dossier = tk.StringVar()
        tk.Entry(frame_dossier, textvariable=self._var_dossier, width=45).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(frame_dossier, text="Parcourir...",
                  command=self._choisir_dossier).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(self, text="Optionnel ici — configurable plus tard dans Paramètres.",
                 font=("", 8), fg="#777").pack(pady=(2, 0))

        # ── Note ──────────────────────────────────────────────────────────
        tk.Label(self,
                 text="Ces informations sont stockées dans votre configuration\n"
                      "et peuvent être modifiées à tout moment dans Outils → Paramètres\n"
                      "(qui donne aussi accès à Boost IA et à l'import agenda Google).",
                 font=("", 8), fg="#777", justify=tk.CENTER).pack(pady=(8, 4))

        # ── Bouton valider ────────────────────────────────────────────────
        self.btn_ok = tk.Button(self,
                                text="Démarrer IntermitDoc",
                                command=self._valider,
                                bg="#1A237E", fg="white",
                                font=("", 10, "bold"),
                                padx=20, pady=8,
                                state=tk.DISABLED)
        self.btn_ok.pack(pady=(4, 16))

    def _choisir_dossier(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            self._var_dossier.set(d)

    def _carte(self, parent, val: str, info: dict):
        """Crée une carte cliquable pour un choix d'annexe."""
        couleur = info["couleur"]

        frame = tk.Frame(parent, relief=tk.GROOVE, bd=2,
                         cursor="hand2", padx=12, pady=8)
        frame.pack(fill=tk.X, pady=6)

        # Indicateur radio
        rb = tk.Radiobutton(frame, variable=self._var, value=val,
                            command=lambda v=val: self._selectionner(v),
                            bg=frame.cget("bg"))
        rb.pack(side=tk.LEFT, padx=(0, 8))

        inner = tk.Frame(frame)
        inner.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_titre = tk.Label(inner, text=info["label"],
                             font=("", 10, "bold"), fg=couleur,
                             anchor="w")
        lbl_titre.pack(fill=tk.X)

        lbl_desc = tk.Label(inner, text=info["desc"],
                            font=("", 9), fg="#444",
                            justify=tk.LEFT, anchor="w")
        lbl_desc.pack(fill=tk.X)

        # Rendre toute la carte cliquable
        for widget in (frame, inner, lbl_titre, lbl_desc):
            widget.bind("<Button-1>", lambda e, v=val: self._clic_carte(v))

        # Stocker la frame pour changer sa bordure à la sélection
        if not hasattr(self, "_frames_cartes"):
            self._frames_cartes = {}
        self._frames_cartes[val] = (frame, couleur)

    def _clic_carte(self, val: str):
        self._var.set(val)
        self._selectionner(val)

    def _selectionner(self, val: str):
        self.annexe_choisie = val
        self.btn_ok.config(state=tk.NORMAL)
        # Mettre en évidence la carte sélectionnée
        for v, (frame, couleur) in self._frames_cartes.items():
            if v == val:
                frame.config(relief=tk.SOLID, bd=2,
                             bg="#F3F4FF" if val != "8+10" else "#F1FFF3")
            else:
                frame.config(relief=tk.GROOVE, bd=2, bg="SystemButtonFace")

    def _valider(self):
        if self.annexe_choisie:
            self.dossier_choisi = self._var_dossier.get().strip()
            self.destroy()


# ---------------------------------------------------------------------------
class FenetrePrincipale(TkinterDnD.Tk if DND_DISPONIBLE else tk.Tk):

    def __init__(self):
        super().__init__()
        self.geometry("1300x860")
        self.minsize(900, 620)

        # Apply modern theme before building any widgets
        TH.apply_theme(self)

        self.cfg            = charger_config()
        self._en_traitement = False
        self._thread        = None

        self._construire_menu()
        self._construire_interface()
        self.protocol("WM_DELETE_WINDOW", self._quitter)

        # Premier lancement : demander l'annexe si non définie
        self.after(100, self._verifier_annexe)

    def _verifier_annexe(self):
        """Affiche le dialogue de bienvenue si l'annexe n'est pas encore définie."""
        if not self.cfg.get("annexe"):
            dlg = DialogueBienvenue(self)
            self.wait_window(dlg)
            if dlg.annexe_choisie:
                self.cfg["annexe"] = dlg.annexe_choisie
                if dlg.dossier_choisi and not self.cfg.get("dossier_base"):
                    self.cfg["dossier_base"] = dlg.dossier_choisi
                sauvegarder_config(self.cfg)
        self._maj_titre()

    def _maj_titre(self):
        """Met à jour le titre et rafraîchit les bandeaux de l'onglet suivi."""
        annexe = self.cfg.get("annexe", "")
        labels = {"8": "Annexe 8 — Technicien", "10": "Annexe 10 — Artiste",
                  "8+10": "Annexes 8 & 10"}
        suffix = f"  [{labels.get(annexe, '')}]" if annexe else ""
        self.title(f"IntermitDoc — Intermittent du Spectacle{suffix}")
        try:
            self.tab_suivi._maj_lbl_annexe()
            self.tab_suivi._maj_lbl_anniversaire()
        except Exception:
            pass

    def _construire_menu(self):
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        menu_fichier = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fichier", menu=menu_fichier)
        menu_fichier.add_command(label="Ouvrir PDF...", command=self._choisir_fichier)
        menu_fichier.add_separator()
        menu_fichier.add_command(label="Quitter", command=self._quitter)

        menu_outils = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Outils", menu=menu_outils)
        menu_outils.add_command(label="Parametres...",      command=self._ouvrir_parametres)
        menu_outils.add_command(label="Boost IA...",        command=self._ouvrir_boost_ia)
        menu_outils.add_command(label="Creer la structure de dossiers", command=self._creer_dossiers)

        menu_theme = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🎨 Thème", menu=menu_theme)
        menu_theme.add_command(label="☀ Clair",       command=lambda: self._changer_theme("clair"))
        menu_theme.add_command(label="◑ Medium",      command=lambda: self._changer_theme("medium"))
        menu_theme.add_command(label="● Sombre",      command=lambda: self._changer_theme("sombre"))
        menu_theme.add_separator()
        menu_theme.add_command(label="🍷 Bourgogne",  command=lambda: self._changer_theme("bourgogne"))
        menu_theme.add_command(label="💜 Violet",     command=lambda: self._changer_theme("violet"))
        menu_theme.add_command(label="🎃 Citrouille", command=lambda: self._changer_theme("citrouille"))
        menu_theme.add_command(label="🌊 Océan",      command=lambda: self._changer_theme("ocean"))
        menu_theme.add_separator()
        menu_theme.add_command(label="🩵 Tiffany",    command=lambda: self._changer_theme("tiffany"))
        menu_theme.add_command(label="🪸 Corail",     command=lambda: self._changer_theme("corail"))
        menu_theme.add_command(label="💚 Cyber",      command=lambda: self._changer_theme("cyber"))
        menu_theme.add_command(label="🌿 Chypre",     command=lambda: self._changer_theme("chypre"))
        menu_theme.add_command(label="🍋 Limon",      command=lambda: self._changer_theme("limon"))
        menu_theme.add_command(label="🌱 Menthe",     command=lambda: self._changer_theme("menthe"))
        menu_theme.add_command(label="🌾 Curcuma",    command=lambda: self._changer_theme("curcuma"))
        menu_theme.add_command(label="🟢 Silver",     command=lambda: self._changer_theme("silver"))
        menu_theme.add_command(label="🌋 Volcan",     command=lambda: self._changer_theme("volcan"))
        menu_theme.add_command(label="🌸 Nacre",      command=lambda: self._changer_theme("nacre"))

        menu_aide = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aide", menu=menu_aide)
        menu_aide.add_command(label=f"Version {__version__}", state="disabled")
        menu_aide.add_separator()
        menu_aide.add_command(label="💾 Conseils de sauvegarde...", command=self._ouvrir_conseils_sauvegarde)
        menu_aide.add_command(label="Vérifier les mises à jour...", command=self._ouvrir_mises_a_jour)

    def _changer_theme(self, nom: str) -> None:
        TH.appliquer_theme(self, nom)

    def _ouvrir_mises_a_jour(self):
        FenetreMisesAJour(self)

    def _ouvrir_conseils_sauvegarde(self):
        DialogueSauvegarde(self, self.cfg)

    def _construire_interface(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # ---- Tab 1 : Analyse ----
        self.tab_analyse = tk.Frame(self.notebook)
        self.notebook.add(self.tab_analyse, text="  Analyser & Classer  ")
        self._construire_onglet_analyse(self.tab_analyse)

        # ---- Tab 2 : Employeurs ----
        self.tab_employeurs = OngletEmployeurs(self.notebook)
        self.notebook.add(self.tab_employeurs, text="  Employeurs  ")

        # ---- Tab 3 : Calcul ----
        self.tab_calcul = OngletCalcul(self.notebook)
        self.notebook.add(self.tab_calcul, text="  Calculatrice AEM/ARE  ")

        # ---- Tab 4 : Suivi Intermittent ----
        self.tab_suivi = OngletSuivi(self.notebook, cfg_getter=lambda: self.cfg)
        self.notebook.add(self.tab_suivi, text="  Suivi Intermittent  ")

        # ---- Tab 5 : Récapitulatif ----
        self.tab_recap = OngletRecap(self.notebook, cfg_getter=lambda: self.cfg)
        self.notebook.add(self.tab_recap, text="  Bilan par période  ")

        # ---- Tab 5b : Revenus ----
        self.tab_revenus = OngletRevenus(self.notebook, cfg_getter=lambda: self.cfg)
        self.notebook.add(self.tab_revenus, text="  💰 Revenus  ")

        # ---- Tab 6 : Scan & Déplacement ----
        self.tab_scan = OngletScan(self.notebook, cfg_getter=lambda: self.cfg)
        self.notebook.add(self.tab_scan, text="  Scan & Déplacement  ")

        # ---- Tab 7 : Historique ----
        self.tab_historique = OngletHistorique(self.notebook, cfg_getter=lambda: self.cfg)
        self.notebook.add(self.tab_historique, text="  Historique & Contrats futurs  ")

        # Auto-refresh Suivi / Récap when their tab is selected
        self.notebook.bind("<<NotebookTabChanged>>", self._on_changement_onglet)

    def _on_changement_onglet(self, _event=None):
        """Refresh contract data when Suivi or Récap tab becomes visible."""
        try:
            onglet = self.notebook.nametowidget(self.notebook.select())
        except (tk.TclError, KeyError):
            return
        # Skip auto-refresh when no folder is configured (avoids warning popup)
        if not self.cfg.get("dossier_base", "").strip():
            return
        if onglet is self.tab_suivi:
            self.tab_suivi._actualiser()
        elif onglet is self.tab_recap:
            self.tab_recap.actualiser()
        elif onglet is self.tab_revenus:
            self.tab_revenus.actualiser()

    def _construire_onglet_analyse(self, parent):
        # Zone de drop
        frame_drop = tk.Frame(parent, pady=4)
        frame_drop.pack(fill=tk.X, padx=10, pady=(8, 2))

        self.lbl_drop = tk.Label(
            frame_drop,
            text="  Glissez un PDF, plusieurs PDF ou un dossier ici  ·  ou  ·  cliquez Parcourir",
            relief=tk.FLAT, bd=0, pady=16,
            bg=TH.PRIMARY_LIGHT, fg=TH.PRIMARY_DARK,
            font=TH.FONT_BODY, cursor="hand2",
        )
        self.lbl_drop.pack(fill=tk.X)
        self.lbl_drop.bind("<Button-1>", lambda e: self._choisir_fichier())

        if DND_DISPONIBLE:
            self.lbl_drop.drop_target_register(DND_FILES)
            self.lbl_drop.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.lbl_drop.config(
                text="  Cliquez Parcourir pour choisir un ou plusieurs PDF",
                bg="#FFF9C4"
            )

        # Boutons d'action sous la zone de drop
        frame_btns = tk.Frame(parent)
        frame_btns.pack(fill=tk.X, padx=10, pady=(2, 4))
        tk.Button(frame_btns, text="Parcourir...",
                  command=self._choisir_fichier, width=14,
                  pady=6).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(frame_btns, text="📂  Scanner un dossier...",
                  command=self._scanner_dossier_recursif, width=22,
                  bg="#6A1B9A", fg="white",
                  pady=6).pack(side=tk.LEFT)

        # Fichier(s) selectionnes
        frame_pdf = tk.Frame(parent, pady=2)
        frame_pdf.pack(fill=tk.X, padx=10)
        tk.Label(frame_pdf, text="Fichier(s) :", width=16, anchor="w").pack(side=tk.LEFT)
        self.var_chemin = tk.StringVar()
        tk.Entry(frame_pdf, textvariable=self.var_chemin,
                 state="readonly", readonlybackground="white").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        # Dossier de sortie
        frame_sortie = tk.Frame(parent, pady=2)
        frame_sortie.pack(fill=tk.X, padx=10)
        tk.Label(frame_sortie, text="Dossier de sortie :", width=16, anchor="w").pack(side=tk.LEFT)
        self.var_dossier_sortie = tk.StringVar(
            value=self.cfg.get("dossier_base", "")
        )
        tk.Entry(frame_sortie, textvariable=self.var_dossier_sortie).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        tk.Button(frame_sortie, text="Choisir...",
                  command=self._choisir_dossier_sortie, width=11).pack(side=tk.LEFT)

        # Bouton analyser
        frame_action = tk.Frame(parent, pady=6)
        frame_action.pack(fill=tk.X, padx=10)
        self.btn_analyser = tk.Button(
            frame_action, text="Analyser le PDF",
            command=self._lancer_analyse,
            bg=TH.PRIMARY, fg="white",
            padx=16, pady=6,
            font=TH.FONT_HEADING,
            relief=tk.FLAT, cursor="hand2",
        )
        self.btn_analyser.pack(side=tk.LEFT)
        tk.Label(frame_action,
                 text="  Double-clic ou [ Editer ] pour corriger -- AEM : 2e analyse heures/salaire automatique",
                 fg="#555", font=("", 8)).pack(side=tk.LEFT, padx=10)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=2)

        # Tableau (gauche) + panneau d'actions (droite)
        frame_milieu = tk.Frame(parent)
        frame_milieu.pack(fill=tk.BOTH, expand=True, padx=10)

        frame_actions = tk.Frame(frame_milieu)
        frame_actions.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.btn_classifier = tk.Button(
            frame_actions, text="✓ Classifier tout",
            command=self._classifier_tout,
            bg=TH.BTN_SUCCESS[0], fg=TH.BTN_SUCCESS[1],
            font=TH.FONT_HEADING,
            padx=14, pady=10, width=18,
            relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_classifier.pack(fill=tk.X, pady=(4, 8))
        self.btn_classifier_sel = tk.Button(
            frame_actions, text="Classifier sélection",
            command=self._classifier_selection,
            font=TH.FONT_BODY,
            padx=14, pady=8, width=18,
            relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED,
        )
        self.btn_classifier_sel.pack(fill=tk.X, pady=8)
        tk.Button(frame_actions, text="Vider",
                  command=self._vider_tableau,
                  font=TH.FONT_BODY,
                  padx=14, pady=8, width=18).pack(fill=tk.X, pady=8)

        self.tableau = TableauPages(frame_milieu, app=self)
        self.tableau.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Progression
        frame_progress = tk.Frame(parent)
        frame_progress.pack(fill=tk.X, padx=10, pady=2)
        self.lbl_progress = tk.Label(frame_progress, text="Pret.", anchor="w")
        self.lbl_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress = ttk.Progressbar(frame_progress, mode="determinate", length=300)
        self.progress.pack(side=tk.RIGHT, padx=6)

        # Journal
        self.log = scrolledtext.ScrolledText(parent, height=5, state=tk.DISABLED,
                                             font=("Consolas", 9))
        self.log.pack(fill=tk.X, padx=10, pady=(0, 6))

    # ---- helpers UI ----

    def _log(self, message: str):
        def _ajouter():
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, message + "\n")
            self.log.see(tk.END)
            self.log.config(state=tk.DISABLED)
        self.after(0, _ajouter)

    def _on_drop(self, event):
        chemins = self._parser_chemins_drop(event.data)
        # Dossier déposé → scanner récursivement
        if len(chemins) == 1 and Path(chemins[0]).is_dir():
            self._scanner_dossier_recursif(chemins[0])
            return
        pdfs = [p for p in chemins if p.lower().endswith(".pdf") and Path(p).exists()]
        if not pdfs:
            messagebox.showwarning("Aucun PDF", "Aucun fichier PDF valide detecte.")
            return
        self._charger_fichiers(pdfs)

    def _parser_chemins_drop(self, data: str) -> list[str]:
        chemins = []
        reste   = data.strip()
        while reste:
            if reste.startswith("{"):
                fin = reste.find("}")
                if fin != -1:
                    chemins.append(reste[1:fin])
                    reste = reste[fin+1:].strip()
                else:
                    break
            else:
                parts = reste.split(None, 1)
                chemins.append(parts[0])
                reste = parts[1].strip() if len(parts) > 1 else ""
        return chemins

    def _choisir_fichier(self):
        chemins = filedialog.askopenfilenames(
            title="Ouvrir un ou plusieurs fichiers PDF",
            filetypes=[("Fichiers PDF", "*.pdf"), ("Tous les fichiers", "*.*")]
        )
        if chemins:
            self._charger_fichiers(list(chemins))

    EXTENSIONS_SCAN = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

    def _scanner_dossier_recursif(self, dossier: str = None):
        """Cherche récursivement tous les PDF/images dans un dossier à analyser.
        Si dossier est fourni (drop), utilise directement ce chemin sans dialogue."""
        if dossier is None:
            dossier = filedialog.askdirectory(
                title="Choisir le dossier à scanner (sous-dossiers inclus)",
                initialdir=self.cfg.get("dossier_base", "") or str(Path.home()),
            )
        if not dossier:
            return

        base = Path(dossier)
        fichiers = sorted(
            str(p) for p in base.rglob("*")
            if p.is_file() and p.suffix.lower() in self.EXTENSIONS_SCAN
        )

        if not fichiers:
            messagebox.showinfo(
                "Aucun document trouvé",
                f"Aucun PDF ou image trouvé dans :\n{dossier}\n(sous-dossiers inclus)"
            )
            return

        reponse = messagebox.askyesno(
            "Documents trouvés",
            f"{len(fichiers)} document(s) trouvé(s) dans ce dossier et ses sous-dossiers.\n\n"
            f"Les charger dans le tableau pour analyse ?"
        )
        if reponse:
            self._charger_fichiers(fichiers)
            self._log(f"[Scan] {len(fichiers)} fichier(s) trouvé(s) sous {dossier}")

    def _charger_fichiers(self, chemins: list[str], dossier_sortie: str = None):
        if len(chemins) == 1:
            affichage = chemins[0]
        else:
            affichage = f"{len(chemins)} fichiers : " + ", ".join(Path(p).name for p in chemins)

        self.var_chemin.set(affichage)
        self._fichiers_en_attente = chemins

        # Le dossier de sortie reste toujours celui configuré dans Paramètres.
        # On ne le modifie pas en fonction des fichiers chargés.

        noms = ", ".join(Path(p).name for p in chemins)
        self.lbl_drop.config(
            text=f"  {len(chemins)} fichier(s) : {noms[:80]}",
            bg="#E8F5E9", fg="#2E7D32"
        )

    def _choisir_dossier_sortie(self):
        dossier = filedialog.askdirectory(
            title="Choisir le dossier de sortie",
            initialdir=self.var_dossier_sortie.get() or str(Path.home()),
        )
        if dossier:
            self.var_dossier_sortie.set(dossier)
            self.cfg["dossier_base"] = dossier
            sauvegarder_config(self.cfg)

    def _lancer_analyse(self):
        fichiers = getattr(self, "_fichiers_en_attente", [])
        if not fichiers:
            messagebox.showwarning("Aucun fichier", "Glissez un PDF ou cliquez Parcourir.")
            return
        if self._en_traitement:
            return
        if not valider_config(self.cfg, self):
            return

        dossier_ui = self.var_dossier_sortie.get().strip()

        # Pre-check : fichiers deja traites
        fichiers_a_analyser = []
        for chemin in fichiers:
            info_traite = verifier_traite(chemin)
            if info_traite:
                dlg = DialogueDejaTraite(self, chemin, info_traite)
                self.wait_window(dlg)
                choix = dlg.choix
                if choix == "ignorer":
                    self._log(f"[~] Ignore (deja traite) : {Path(chemin).name}")
                    continue
                elif choix == "voir":
                    dest = info_traite.get("chemin_destination", "")
                    if dest and Path(dest).exists():
                        import os
                        os.startfile(str(Path(dest).parent))
                    else:
                        messagebox.showwarning("Introuvable", f"Dossier destination introuvable :\n{dest}")
                    continue
                elif choix == "reclasser":
                    # Marquer pour reclassement sans analyse
                    fichiers_a_analyser.append((chemin, "reclasser"))
                    continue
                # choix == "retraiter" : analyse normale
            fichiers_a_analyser.append((chemin, "analyser"))

        if not fichiers_a_analyser:
            return

        self.tableau.vider()
        self._en_traitement = True
        self.btn_analyser.config(state=tk.DISABLED)
        self.btn_classifier.config(state=tk.DISABLED)
        self.btn_classifier_sel.config(state=tk.DISABLED)
        self.progress["value"] = 0

        self._thread = threading.Thread(
            target=self._thread_analyse_multi, args=(fichiers_a_analyser,), daemon=True
        )
        self._thread.start()

    def _thread_analyse_multi(self, fichiers: list):
        total_pages = 0
        employeurs  = charger_employeurs()   # charge une fois pour tout le traitement
        try:
            import fitz
            for item in fichiers:
                chemin = item[0] if isinstance(item, tuple) else item
                try:
                    doc = fitz.open(chemin)
                    total_pages += len(doc)
                    doc.close()
                except Exception:
                    total_pages += 1

            self.after(0, lambda: self.progress.config(maximum=max(total_pages, 1), value=0))
            pages_traitees = 0

            for item in fichiers:
                chemin, mode_item = (item if isinstance(item, tuple) else (item, "analyser"))
                if not self._en_traitement:
                    break
                try:
                    with ExtracteurPDF(chemin, self.cfg) as extracteur:
                        nb = extracteur.nb_pages
                        self._log(f"--- {Path(chemin).name} ({nb} page(s)) ---")

                        for i, info_page in enumerate(extracteur.pages()):
                            if not self._en_traitement:
                                break

                            # Pré-parser le nom de fichier
                            info_nom = extraire_info_nom_fichier(info_page.get("nom_fichier_source", ""))

                            if mode_item == "reclasser":
                                self._log(f"  Page {i+1}/{nb} -- reclassement direct (sans analyse)")
                                analyse = dict(info_nom)
                                analyse.setdefault("type", "INCONNU")
                                analyse.setdefault("confiance", 0.5)
                            else:
                                mode   = "OCR" if info_page.get("est_ocr") else "natif"
                                self._log(f"  Page {i+1}/{nb} -- {mode}")
                                analyse  = analyser_document_multi(info_page["texte"], self.cfg, employeurs)
                                analyse  = fusionner_info_nom_analyse(info_nom, analyse)

                            # Second passage pour les AEM : heures + salaire brut
                            if analyse.get("type") == "AEM" and not analyse.get("erreur"):
                                self._log(f"  Page {i+1} AEM -- analyse details...")

                                # 1a. PDF natif : extraction par position (sans OCR)
                                if not info_page.get("est_ocr"):
                                    details = extraire_valeurs_aem_natif(extracteur.doc[i])
                                    self._log(f"  (natif pos) h={details.get('heures','?')}  s={details.get('salaire_brut','?')}")
                                # 1b. PDF scanne : OCR cible par coordonnees cellule
                                else:
                                    details = extraire_valeurs_aem_page(
                                        extracteur.doc[i], self.cfg
                                    )
                                    self._log(f"  (OCR cellule) h={details.get('heures','?')}  s={details.get('salaire_brut','?')}")

                                # 2. Compléter avec Claude si valeurs manquantes
                                if not details.get("heures") or not details.get("salaire_brut"):
                                    details_claude = analyser_details_aem(info_page["texte"], self.cfg)
                                    if not details.get("heures"):
                                        details["heures"]       = details_claude.get("heures", "")
                                    if not details.get("salaire_brut"):
                                        details["salaire_brut"] = details_claude.get("salaire_brut", "")

                                analyse["heures"]      = details.get("heures", "")
                                analyse["salaire_brut"]= details.get("salaire_brut", "")
                                if details.get("heures") or details.get("salaire_brut"):
                                    self._log(
                                        f"  -> {details.get('heures','?')}h  "
                                        f"{details.get('salaire_brut','?')} EUR"
                                    )

                            if analyse.get("erreur"):
                                self._log(f"  [!] {analyse['erreur']}")

                            # Auto-enregistrement de l'employeur détecté
                            emp = analyse.get("employeur", "").strip()
                            if emp and emp != "INCONNU":
                                emp_lower = emp.lower()
                                existant = next((e for e in employeurs if e.lower() == emp_lower), None)
                                if existant is None:
                                    employeurs.append(emp)
                                    employeurs.sort()
                                    sauvegarder_employeurs(employeurs)
                                    self._log(f"  [Employeur] Ajouté : {emp}")
                                elif existant != emp:
                                    # Variante casse différente — on garde la version déjà enregistrée
                                    self._log(f"  [Employeur] Déjà connu sous : {existant} (ignoré : {emp})")

                            ligne = LigneTableau(info_page, analyse)
                            self.after(0, lambda l=ligne: self.tableau.ajouter_ligne(l))
                            pages_traitees += 1
                            self.after(0, lambda v=pages_traitees: self.progress.config(value=v))

                except Exception as e:
                    self._log(f"[ERREUR] {Path(chemin).name} : {e}")

        finally:
            def _fin():
                self._en_traitement = False
                self.btn_analyser.config(state=tk.NORMAL)
                if len(self.tableau.lignes) > 0:
                    self.btn_classifier.config(state=tk.NORMAL)
                    self.btn_classifier_sel.config(state=tk.NORMAL)
                self.lbl_progress.config(
                    text=f"Termine -- {len(self.tableau.lignes)} page(s) analysee(s)."
                )
                self._log("Analyse terminee.")
                self._detecter_doublons()
            self.after(0, _fin)

    def _detecter_doublons(self):
        """Cherche les pages avec le meme nom de fichier prevu et propose de resoudre."""
        groupes: dict[str, list[int]] = {}
        for idx, ligne in enumerate(self.tableau.lignes):
            nom = ligne.nom_fichier_prevu()
            groupes.setdefault(nom, []).append(idx)

        for nom, indices in groupes.items():
            if len(indices) < 2:
                continue
            idx1, idx2 = indices[0], indices[1]
            ligne1 = self.tableau.lignes[idx1]
            ligne2 = self.tableau.lignes[idx2]
            dlg = DialogueDoublon(self, ligne1, ligne2, nom)
            self.wait_window(dlg)
            if dlg.choix == "page1":
                ligne2.statut = "Ignore (doublon)"
                self.tableau.mettre_a_jour_ligne(idx2)
                self._log(f"[doublon] Page {ligne2.numero} ignoree, page {ligne1.numero} conservee.")
            elif dlg.choix == "page2":
                ligne1.statut = "Ignore (doublon)"
                self.tableau.mettre_a_jour_ligne(idx1)
                self._log(f"[doublon] Page {ligne1.numero} ignoree, page {ligne2.numero} conservee.")
            else:
                self._log(f"[doublon] Pages {ligne1.numero} et {ligne2.numero} conservees toutes les deux.")

    def _classifier_ligne(self, idx: int):
        if idx >= len(self.tableau.lignes):
            return
        ligne = self.tableau.lignes[idx]

        if ligne.statut == "Ignore (doublon)":
            return

        if ligne.analyse.get("type") == "AEM":
            heures  = ligne.analyse.get("heures",      "").strip()
            salaire = ligne.analyse.get("salaire_brut", "").strip()
            if not heures or not salaire:
                nouveau = DialogueInfosManquantes.demander(
                    self.winfo_toplevel(), ligne.analyse, ligne.numero,
                    page_pdf_bytes=ligne.page_pdf_bytes)
                if nouveau is None:
                    return
                ligne.analyse = nouveau
                heures  = ligne.analyse.get("heures",      "").strip()
                salaire = ligne.analyse.get("salaire_brut", "").strip()
            try:
                if 1 <= float(heures) <= 4:
                    if not messagebox.askyesno(
                        "Heures suspectes",
                        f"Page {ligne.numero} (AEM) : {heures}h semble anormalement bas.\n"
                        "Classifier quand même ?",
                    ):
                        return
            except ValueError:
                pass

        chemin_source = ligne.info_page.get("chemin_source", "")
        res = copier_page_classifiee(ligne.page_pdf_bytes, ligne.analyse,
                                     self.cfg, chemin_source=chemin_source)
        if res["succes"]:
            if res.get("fallback"):
                ligne.statut       = "Non classe"
                ligne.chemin_copie = res["chemin_destination"]
                self._log(f"[?]   Page {ligne.numero} -> non classee, exportee : {res['nom_fichier']}")
            else:
                ligne.statut       = "Copie"
                ligne.chemin_copie = res["chemin_destination"]
                self._log(f"[OK]  Page {ligne.numero} -> {res['nom_fichier']}")
                logger.info(f"[Classif] {res['nom_fichier']}")
                # AEM/BP du même mois : compléter heures/salaire manquants
                if ligne.analyse.get("type") in ("AEM", "BP"):
                    try:
                        dossier_mois = Path(res["chemin_destination"]).parent.parent
                        _synchroniser_dossier_mois(dossier_mois)
                    except Exception as e:
                        logger.warning(f"[Sync AEM/BP] {e}")
                # Enregistrer l'empreinte pour ne pas retraiter
                chemin_src = ligne.info_page.get("chemin_source", "")
                if chemin_src:
                    try:
                        enregistrer_traite(chemin_src, {**ligne.analyse, "chemin_destination": res["chemin_destination"], "nom_fichier": res["nom_fichier"]})
                    except Exception:
                        pass
                # Generer total.txt si c est un AEM
                if ligne.analyse.get("type") == "AEM":
                    self._maj_total_txt_depuis_destination(res["chemin_destination"])
        else:
            ligne.statut = f"Erreur : {res['erreur'][:40]}"
            self._log(f"[ERR] Page {ligne.numero} : {res['erreur']}")
            logger.error(f"[Classif] Erreur page {ligne.numero} : {res['erreur']}")
        self.tableau.mettre_a_jour_ligne(idx)

    def _classifier_tout(self):
        if not self.tableau.lignes:
            return

        # Pre-check : AEM avec infos manquantes → dialogue de saisie
        for idx, l in enumerate(self.tableau.lignes):
            if l.analyse.get("type") == "AEM" and (
                not l.analyse.get("heures", "").strip()
                or not l.analyse.get("salaire_brut", "").strip()
            ):
                nouveau = DialogueInfosManquantes.demander(
                    self.winfo_toplevel(), l.analyse, l.numero,
                    page_pdf_bytes=l.page_pdf_bytes)
                if nouveau is not None:
                    l.analyse = nouveau
                else:
                    l.statut = "Info manquante"
                    self.tableau.mettre_a_jour_ligne(idx)

        nb_ok = nb_err = nb_fallback = nb_ignore = 0
        dossiers_a_synchroniser = set()
        for idx in range(len(self.tableau.lignes)):
            ligne = self.tableau.lignes[idx]

            if ligne.statut == "Ignore (doublon)":
                nb_ignore += 1
                continue

            if ligne.statut == "Info manquante":
                nb_err += 1
                self._log(f"[!]   Page {ligne.numero} AEM : heures ou salaire manquant(s)")
                continue

            chemin_source = ligne.info_page.get("chemin_source", "")
            res = copier_page_classifiee(ligne.page_pdf_bytes, ligne.analyse,
                                         self.cfg, chemin_source=chemin_source)
            if res["succes"]:
                if res.get("fallback"):
                    ligne.statut       = "Non classe"
                    ligne.chemin_copie = res["chemin_destination"]
                    nb_fallback += 1
                    self._log(f"[?]   Page {ligne.numero} -> non classee, exportee : {res['nom_fichier']}")
                else:
                    ligne.statut       = "Copie"
                    ligne.chemin_copie = res["chemin_destination"]
                    nb_ok += 1
                    self._log(f"[OK]  Page {ligne.numero} -> {res['nom_fichier']}")
                    if ligne.analyse.get("type") in ("AEM", "BP"):
                        dossiers_a_synchroniser.add(
                            str(Path(res["chemin_destination"]).parent.parent))
                    chemin_src = ligne.info_page.get("chemin_source", "")
                    if chemin_src:
                        try:
                            enregistrer_traite(chemin_src, {**ligne.analyse, "chemin_destination": res["chemin_destination"], "nom_fichier": res["nom_fichier"]})
                        except Exception:
                            pass
            else:
                ligne.statut = f"Erreur : {res['erreur'][:40]}"
                nb_err += 1
                self._log(f"[ERR] Page {ligne.numero} : {res['erreur']}")
            self.tableau.mettre_a_jour_ligne(idx)

        # AEM/BP du même mois : compléter heures/salaire manquants (une seule
        # passe par dossier mois, pas par page, pour éviter de le rescanner)
        for dossier_mois in dossiers_a_synchroniser:
            try:
                _synchroniser_dossier_mois(Path(dossier_mois))
            except Exception as e:
                logger.warning(f"[Sync AEM/BP] {e}")

        # Generer total.txt pour chaque dossier AEM concerne
        dossiers_aem = set()
        for ligne in self.tableau.lignes:
            if ligne.analyse.get("type") == "AEM" and ligne.chemin_copie:
                dossiers_aem.add(str(Path(ligne.chemin_copie).parent))
        for dossier in dossiers_aem:
            self._maj_total_txt_depuis_destination(str(Path(dossier) / "dummy.pdf"))

        msg = f"{nb_ok} page(s) classifiee(s)."
        if nb_fallback:
            msg += f"\n{nb_fallback} page(s) non classee(s) exportee(s) dans le dossier source."
        if nb_err:
            msg += f"\n{nb_err} page(s) ignoree(s) (AEM incomplets)."
        if nb_ignore:
            msg += f"\n{nb_ignore} page(s) ignoree(s) (doublons)."
        if dossiers_aem:
            msg += f"\ntotal.txt mis a jour ({len(dossiers_aem)} dossier(s) AEM)."
        if nb_err or nb_fallback:
            DialogueRapport.afficher(self, "Classification — rapport", msg)
        else:
            messagebox.showinfo("Classification terminee", msg)

    def _maj_total_txt_depuis_destination(self, chemin_fichier: str):
        """
        A partir du chemin d un fichier AEM copie, remonte au dossier AEM,
        scanne tous les fichiers et regenere total.txt silencieusement.
        Met aussi a jour l onglet Calcul si le meme dossier est ouvert.
        """
        try:
            dossier_aem = str(Path(chemin_fichier).parent)
            contrats    = _scanner_aem_dossier(dossier_aem)
            if contrats:
                _ecrire_total_txt(dossier_aem, contrats)
                self._log(f"[AEM] total.txt mis a jour : {dossier_aem}")
                # Rafraichir l onglet Calcul si c est le meme dossier
                if hasattr(self, "tab_calcul") and self.tab_calcul._dossier == dossier_aem:
                    self.tab_calcul.rafraichir_depuis_dossier(dossier_aem)
                # Rafraichir l onglet Suivi et Récapitulatif
                if hasattr(self, "tab_suivi"):
                    dossier_base = self.cfg.get("dossier_base", "")
                    if dossier_base:
                        self.tab_suivi.rafraichir_depuis_dossier(dossier_base)
                if hasattr(self, "tab_recap"):
                    dossier_base = self.cfg.get("dossier_base", "")
                    if dossier_base:
                        self.tab_recap.rafraichir_depuis_dossier(dossier_base)
                if hasattr(self, "tab_scan"):
                    dossier_base = self.cfg.get("dossier_base", "")
                    if dossier_base and not self.tab_scan.var_sortie.get().strip():
                        self.tab_scan.var_sortie.set(dossier_base)
        except Exception as e:
            self._log(f"[!] total.txt : {e}")

    def _classifier_selection(self):
        selection = self.tableau.tree.selection()
        if not selection:
            messagebox.showinfo("Aucune selection", "Selectionnez une ligne dans le tableau.")
            return
        item_id = selection[0]
        idx     = self.tableau._items.get(item_id)
        if idx is not None:
            self._classifier_ligne(idx)

    def _vider_tableau(self):
        self.tableau.vider()
        self.btn_classifier.config(state=tk.DISABLED)
        self.btn_classifier_sel.config(state=tk.DISABLED)
        self.lbl_progress.config(text="Pret.")
        self.progress["value"] = 0

    def _ouvrir_parametres(self):
        dlg = DialogueParametres(self, self.cfg)
        self.wait_window(dlg)
        self.cfg = charger_config()
        self.tab_employeurs.recharger()

    def _ouvrir_boost_ia(self):
        dlg = DialogueBoostIA(self, self.cfg)
        self.wait_window(dlg)
        self.cfg = charger_config()
        # Mettre a jour le titre avec les IA actives
        actifs = [
            IA_PROVIDERS[pid]["nom"].split(" ")[0]
            for pid, pcfg in self.cfg.get("ia_providers", {}).items()
            if pcfg.get("enabled") and pcfg.get("api_key")
        ]
        if len(actifs) > 1:
            self.title(f"IntermitDoc  [Boost IA :{', '.join(actifs)}]")
        else:
            self.title("IntermitDoc - Intermittent du Spectacle")

    def _creer_dossiers(self):
        n = creer_structure_dossiers(self.cfg)
        if n:
            messagebox.showinfo("Dossiers crees", f"{n} dossier(s) cree(s).")
        else:
            messagebox.showinfo("Dossiers", "Tous les dossiers existent deja.")

    def _quitter(self):
        self._en_traitement = False
        self.destroy()


# ---------------------------------------------------------------------------
# Fenêtre "Mises à jour"
# ---------------------------------------------------------------------------
class FenetreMisesAJour(tk.Toplevel):
    """Dialog to check for and apply updates from GitHub Releases."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Mises à jour — IntermitDoc")
        self.resizable(False, False)
        self.grab_set()

        self._release_info = None
        self._bat_path = None

        pad = {"padx": 16, "pady": 8}

        # Version actuelle
        frm_ver = tk.Frame(self)
        frm_ver.pack(fill=tk.X, **pad)
        tk.Label(frm_ver, text="Version installée :", font=("", 10)).pack(side=tk.LEFT)
        tk.Label(frm_ver, text=__version__, font=("", 10, "bold")).pack(side=tk.LEFT, padx=6)

        # Version disponible
        frm_dispo = tk.Frame(self)
        frm_dispo.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(frm_dispo, text="Version disponible :").pack(side=tk.LEFT)
        self._lbl_dispo = tk.Label(frm_dispo, text="—", font=("", 10, "bold"))
        self._lbl_dispo.pack(side=tk.LEFT, padx=6)

        # Notes de version
        self._txt_notes = scrolledtext.ScrolledText(
            self, height=8, width=52, state="disabled", wrap=tk.WORD
        )
        self._txt_notes.pack(padx=16, pady=4)

        # Barre de progression
        self._progress = ttk.Progressbar(self, length=380, mode="determinate")
        self._progress.pack(padx=16, pady=(4, 0))
        self._lbl_status = tk.Label(self, text="")
        self._lbl_status.pack(padx=16, pady=(2, 8))

        # Boutons
        frm_btn = tk.Frame(self)
        frm_btn.pack(pady=(0, 12))
        self._btn_check = ttk.Button(frm_btn, text="Vérifier",    command=self._verifier)
        self._btn_check.pack(side=tk.LEFT, padx=6)
        self._btn_update = ttk.Button(frm_btn, text="Mettre à jour", command=self._mettre_a_jour, state="disabled")
        self._btn_update.pack(side=tk.LEFT, padx=6)
        ttk.Button(frm_btn, text="Fermer", command=self.destroy).pack(side=tk.LEFT, padx=6)

        self._centrer()
        # Lancer la vérification automatiquement
        self.after(100, self._verifier)

    def _centrer(self):
        self.update_idletasks()
        x = self.master.winfo_x() + (self.master.winfo_width()  - self.winfo_width())  // 2
        y = self.master.winfo_y() + (self.master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _verifier(self):
        self._btn_check.config(state="disabled")
        self._lbl_status.config(text="Vérification en cours…")
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        try:
            info = updater.check_for_update()
            self.after(0, self._on_check_done, info, None)
        except Exception as exc:
            self.after(0, self._on_check_done, None, str(exc))

    def _on_check_done(self, info, error):
        self._btn_check.config(state="normal")
        if error:
            self._lbl_status.config(text=f"Erreur : {error}")
            return
        if info is None:
            self._lbl_dispo.config(text=__version__)
            self._lbl_status.config(text="Vous avez la dernière version.")
            return
        self._release_info = info
        self._lbl_dispo.config(text=info["version"])
        self._lbl_status.config(text="Mise à jour disponible !")
        self._btn_update.config(state="normal" if info["url"] else "disabled")
        notes = info.get("notes", "") or "Aucune note de version."
        self._txt_notes.config(state="normal")
        self._txt_notes.delete("1.0", tk.END)
        self._txt_notes.insert(tk.END, notes)
        self._txt_notes.config(state="disabled")

    def _mettre_a_jour(self):
        if not self._release_info or not self._release_info.get("url"):
            return
        self._btn_update.config(state="disabled")
        self._btn_check.config(state="disabled")
        self._lbl_status.config(text="Téléchargement…")
        self._progress["value"] = 0
        updater.download_and_apply(
            url=self._release_info["url"],
            progress_cb=self._on_progress,
            done_cb=self._on_done,
            error_cb=self._on_error,
        )

    def _on_progress(self, ratio: float):
        self.after(0, lambda: self._progress.config(value=int(ratio * 100)))

    def _on_done(self, bat_path: str):
        self._bat_path = bat_path
        self.after(0, self._proposer_redemarrage)

    def _on_error(self, msg: str):
        self.after(0, lambda: self._lbl_status.config(text=f"Erreur : {msg}"))
        self.after(0, lambda: self._btn_update.config(state="normal"))

    def _proposer_redemarrage(self):
        self._lbl_status.config(text="Téléchargement terminé.")
        ok = messagebox.askyesno(
            "Redémarrer",
            "La mise à jour est prête.\n\nL'application va se fermer et redémarrer automatiquement.\n\nContinuer ?",
            parent=self,
        )
        if ok:
            updater.launch_updater_and_exit(self._bat_path)
