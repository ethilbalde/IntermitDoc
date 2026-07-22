"""
Extraction de texte depuis des PDFs.
Supporte les PDFs natifs (via PyMuPDF) et les PDFs scannés (via OCR Tesseract).
"""
import io
from pathlib import Path
from typing import Generator

import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    TESSERACT_DISPONIBLE = True
except ImportError:
    TESSERACT_DISPONIBLE = False

SEUIL_TEXTE_NATIF = 50  # Nombre de caractères minimum pour considérer le texte natif


def configurer_tesseract(chemin: str) -> None:
    """Configure le chemin de l'exécutable Tesseract."""
    if TESSERACT_DISPONIBLE and chemin:
        pytesseract.pytesseract.tesseract_cmd = chemin


def extraire_texte_page(page: fitz.Page) -> str:
    """Extrait le texte natif d'une page PyMuPDF."""
    return page.get_text("text").strip()


def page_vers_image_pil(page: fitz.Page, dpi: int = 200) -> "Image.Image":
    """Convertit une page PDF en image PIL pour l'OCR."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def ocr_page(page: fitz.Page, langue: str = "fra+eng") -> str:
    """Effectue l'OCR sur une page et retourne le texte."""
    if not TESSERACT_DISPONIBLE:
        return ""
    try:
        img = page_vers_image_pil(page)
        # Prétraitement : convertir en niveaux de gris
        img = img.convert("L")
        texte = pytesseract.image_to_string(img, lang=langue, config="--psm 3")
        return texte.strip()
    except Exception as e:
        print(f"[OCR] Erreur sur la page : {e}")
        return ""


def extraire_texte_complet(page: fitz.Page, langue_ocr: str = "fra+eng") -> tuple[str, bool]:
    """
    Extrait le texte d'une page, en utilisant l'OCR si nécessaire.

    Retourne : (texte, est_ocr)
    """
    texte_natif = extraire_texte_page(page)

    if len(texte_natif) >= SEUIL_TEXTE_NATIF:
        return texte_natif, False

    # Texte insuffisant : tenter l'OCR si Tesseract est disponible
    if TESSERACT_DISPONIBLE:
        texte_ocr = ocr_page(page, langue_ocr)
        if texte_ocr.strip():
            return texte_ocr, True

    # Fallback : renvoyer le texte natif même s'il est court
    # (Claude peut quand même tenter une classification partielle)
    return texte_natif, False


def generer_miniature(page: fitz.Page, largeur: int = 120) -> bytes:
    """
    Génère une miniature PNG d'une page PDF.
    Retourne les bytes PNG.
    """
    rect = page.rect
    hauteur = int(rect.height * largeur / rect.width) if rect.width > 0 else 160
    mat = fitz.Matrix(largeur / rect.width, hauteur / rect.height) if rect.width > 0 else fitz.Matrix(1, 1)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def extraire_page_comme_pdf(doc_source: fitz.Document, numero_page: int) -> bytes:
    """
    Extrait une seule page d'un PDF et la retourne en bytes PDF.
    Utile pour sauvegarder une page individuelle.
    """
    doc_dest = fitz.open()
    doc_dest.insert_pdf(doc_source, from_page=numero_page, to_page=numero_page)
    data = doc_dest.tobytes()
    doc_dest.close()
    return data


def extraire_valeurs_aem_natif(page: fitz.Page) -> dict:
    """
    Extraction par ancrage sur les libellés du formulaire AEM (recherche de
    texte), pour les PDF natifs (non scannes).

    Une version antérieure repérait heures/salaire par position pure
    (colonne gauche, ordre d'apparition) sans jamais lire le texte des
    libellés. Elle confondait parfois les numéros de section du formulaire
    ("1 ATTESTATION (AEM)", "2 EMPLOYEUR"...) — des chiffres isolés en marge
    gauche — avec les vraies valeurs, quand ils tombaient par coïncidence
    sur la même ligne qu'un autre nombre (ex: les cases jour/année du champ
    MOIS). Ancrer sur le texte du libellé ("effectuées", "SALAIRES BRUTS
    ... soumis") élimine ce risque : on ne regarde que les nombres proches
    du bon libellé, peu importe le reste de la page.
    """
    import re

    def _nombres_isoles() -> list:
        out = []
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                txt = " ".join(s["text"] for s in line["spans"]).strip()
                if txt and re.fullmatch(r'\d+([.,]\d+)?', txt):
                    out.append((line["bbox"][0], line["bbox"][1], txt))
        return out

    def _nombre_proche(label_rect, nombres, x_tol=40, y_max=40) -> str:
        """Nombre isolé le plus proche juste en dessous du libellé (même x)."""
        candidats = []
        for x, y, txt in nombres:
            dy = y - label_rect.y1
            dx = abs(x - label_rect.x0)
            if 0 <= dy <= y_max and dx <= x_tol:
                candidats.append((dy, dx, txt))
        if not candidats:
            return ""
        candidats.sort()
        return candidats[0][2].replace(",", ".")

    nombres = _nombres_isoles()
    if not nombres:
        return {"heures": "", "salaire_brut": ""}

    heures = ""
    rects_heures = page.search_for("effectu")  # "Nombre d'HEURES effectuées"
    if rects_heures:
        heures = _nombre_proche(rects_heures[0], nombres)

    salaire_brut = ""
    rects_salaires = page.search_for("SALAIRES BRUTS")
    if len(rects_salaires) >= 2:
        # 2e colonne = "... soumis à contributions d'assurance chômage"
        salaire_brut = _nombre_proche(rects_salaires[1], nombres)

    return {"heures": heures, "salaire_brut": salaire_brut}


def extraire_valeurs_aem_page(page: fitz.Page, config: dict) -> dict:
    """
    Extraction specialisee pour les AEM scannees.
    Utilise des coordonnees fixes (formulaire AEM standardise a 300 dpi) en priorite,
    puis recherche par libelle comme fallback.

    Retourne {"heures": "10", "salaire_brut": "192.62"} ou valeurs vides.
    """
    if not TESSERACT_DISPONIBLE:
        return {"heures": "", "salaire_brut": ""}

    tesseract_path = config.get("tesseract_path", "")
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    try:
        dpi = 300
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")

        # Coordonnees fixes du formulaire AEM standardise (300 dpi, A4)
        CROP_HEURES  = (202, 2088, 492, 2280)
        CROP_SALAIRE = (840, 2374, 1318, 2624)

        heures       = ""
        salaire_brut = ""

        # Essai 1 : coordonnees fixes — OCR direct sans suppression de bordures
        for psm in [7, 8, 6]:
            texte  = _ocr_direct(img.crop(CROP_HEURES), psm=psm, charlist=True)
            nombre = _premier_entier_isole(texte)
            if nombre:
                heures = nombre
                break

        for psm in [6, 3, 7]:
            texte  = _ocr_direct(img.crop(CROP_SALAIRE), psm=psm, charlist=False)
            nombre = _premier_montant(texte)
            if nombre:
                salaire_brut = nombre
                break

        if heures and salaire_brut:
            return {"heures": heures, "salaire_brut": salaire_brut}

        # Essai 2 (fallback) : recherche par libelle si les coords fixes echouent
        data = pytesseract.image_to_data(
            img, lang=config.get("langue_ocr", "fra+eng"),
            config="--psm 3",
            output_type=pytesseract.Output.DICT,
        )
        mots    = data["text"]
        tops    = data["top"]
        lefts   = data["left"]
        widths  = data["width"]
        heights = data["height"]

        if not heures:
            heures = _chercher_valeur_cellule(
                img, mots, tops, lefts, widths, heights,
                libelles_cles=["effectu", "effectuees", "effectuées"],
                direction="droite",
            )

        if not salaire_brut:
            salaire_brut = _chercher_valeur_cellule(
                img, mots, tops, lefts, widths, heights,
                libelles_cles=["soumis", "chômage", "chomage", "chómage"],
                direction="gauche_nombre",
            )

        return {"heures": heures, "salaire_brut": salaire_brut}

    except Exception:
        return {"heures": "", "salaire_brut": ""}


def _chercher_valeur_cellule(
    img: "Image.Image",
    mots, tops, lefts, widths, heights,
    libelles_cles: list,
    direction: str,
) -> str:
    """
    Trouve un libelle-cle dans la liste de mots OCR,
    puis recadre la zone adjacente et lance un OCR cible.
    """
    idx_ref = None
    for i, mot in enumerate(mots):
        if mot.strip():
            mot_norm = mot.lower().strip(".,:-")
            for cle in libelles_cles:
                if cle in mot_norm:
                    idx_ref = i
                    break
        if idx_ref is not None:
            break

    if idx_ref is None:
        return ""

    y_ref  = tops[idx_ref]
    x_ref  = lefts[idx_ref]
    h_ref  = max(heights[idx_ref], 40) if heights[idx_ref] > 0 else 40
    w_ref  = widths[idx_ref]
    img_w, img_h = img.size

    if direction == "droite":
        import re as _re

        y_min = max(0,     y_ref - 80)
        y_max = min(img_h, y_ref + h_ref + 120)

        # Essai 1 : a droite du libelle (cellule separee)
        x_apres = max(0, x_ref + w_ref + 5)
        for x_max in [x_apres + 250, x_apres + 450, x_apres + 700]:
            crop = img.crop((x_apres, y_min, min(x_max, img_w), y_max))
            for psm in [7, 8, 6]:
                texte  = _ocr_cellule(crop, psm=psm)
                nombre = _premier_entier_isole(texte)
                if nombre:
                    return nombre

        # Essai 2 : SOUS le libelle (meme colonne, ligne suivante)
        y_sous_min = max(0,     y_ref + h_ref - 10)
        y_sous_max = min(img_h, y_ref + h_ref + 160)
        x_col_max  = min(img_w, x_ref + w_ref + 250)
        crop_sous = img.crop((max(0, x_ref - 30), y_sous_min, x_col_max, y_sous_max))
        for psm in [7, 8, 6]:
            texte  = _ocr_cellule(crop_sous, psm=psm)
            nombre = _premier_entier_isole(texte)
            if nombre:
                return nombre

        # Essai 3 : pleine largeur MAIS limitee a la colonne gauche du libelle
        # (evite de capturer "Nombre de JOURS" qui est dans la colonne droite)
        x_limite_col = min(img_w, max(x_ref + w_ref + 300, img_w // 2))
        crop_ligne = img.crop((0, y_min, x_limite_col, y_max))
        for psm in [6, 11, 3]:
            texte = _ocr_cellule(crop_ligne, psm=psm, charlist=False)
            for m in _re.finditer(r'\b(\d{1,3})\b', texte):
                val   = m.group(1)
                apres = texte[m.end():m.end()+4]
                if _re.match(r'h\d{2}', apres):
                    continue
                try:
                    f = float(val)
                    if 1 <= f <= 500:
                        return str(int(f))
                except ValueError:
                    pass

        return ""

    elif direction == "gauche_nombre":
        y_min = max(0,     y_ref - 40)
        y_max = min(img_h, y_ref + h_ref + 80)
        crop  = img.crop((0, y_min, min(900, img_w), y_max))
        for psm in [7, 6]:
            texte = _ocr_cellule(crop, psm=psm, charlist=False)
            nombre = _premier_nombre(texte)
            if nombre:
                return nombre
        return ""

    return ""


def _ocr_direct(crop: "Image.Image", psm: int = 7, charlist: bool = True) -> str:
    """OCR sur un crop fixe sans suppression de bordures, avec agrandissement minimal."""
    try:
        w, h = crop.size
        if w < 5 or h < 5:
            return ""
        scale = max(1, min(4, 400 // max(h, 1)))
        if scale > 1:
            crop = crop.resize((w * scale, h * scale), Image.LANCZOS)
        cfg = f"--psm {psm}"
        if charlist:
            cfg += " -c tessedit_char_whitelist=0123456789.,"
        return pytesseract.image_to_string(crop, lang="fra+eng", config=cfg).strip()
    except Exception:
        return ""


def _ocr_cellule(crop: "Image.Image", psm: int = 7, charlist: bool = True) -> str:
    """OCR sur une petite zone recadree avec pretraitement et agrandissement."""
    try:
        import pytesseract
        import numpy as np

        w, h = crop.size
        if w < 5 or h < 5:
            return ""

        # Agrandir si trop petit
        scale = max(1, min(4, 150 // max(h, 1)))
        if scale > 1:
            crop = crop.resize((w * scale, h * scale), Image.LANCZOS)

        # Pretraitement : supprimer les traits de tableau (lignes h/v longues)
        crop = _supprimer_lignes_tableau(crop)

        cfg = f"--psm {psm}"
        if charlist:
            cfg += " -c tessedit_char_whitelist=0123456789.,"
        return pytesseract.image_to_string(crop, lang="fra+eng", config=cfg).strip()
    except Exception:
        return ""


def _supprimer_lignes_tableau(img: "Image.Image") -> "Image.Image":
    """
    Efface les lignes horizontales et verticales longues (bordures de tableau)
    en les remplacant par du blanc, pour faciliter l OCR des nombres dans les cellules.
    """
    try:
        import numpy as np

        arr = np.array(img)
        h, w = arr.shape

        sombre = (arr < 128).astype(np.uint8)

        # Lignes HORIZONTALES : une ligne est "longue" si la convolution glissante
        # sur seuil_h pixels consécutifs atteint seuil_h (tous sombres).
        seuil_h = max(10, w // 5)
        kernel_h = np.ones(seuil_h, dtype=np.uint8)
        # convolve chaque rangée — si max >= seuil_h, la rangée contient un trait long
        conv_h = np.apply_along_axis(
            lambda row: np.convolve(row, kernel_h, mode="valid").max(), axis=1, arr=sombre
        )
        arr[conv_h >= seuil_h, :] = 255

        # Lignes VERTICALES : idem sur les colonnes
        seuil_v = max(8, h // 7)
        kernel_v = np.ones(seuil_v, dtype=np.uint8)
        conv_v = np.apply_along_axis(
            lambda col: np.convolve(col, kernel_v, mode="valid").max(), axis=0, arr=sombre
        )
        arr[:, conv_v >= seuil_v] = 255

        return Image.fromarray(arr)
    except Exception:
        return img


def _premier_entier_isole(texte: str) -> str:
    """Extrait le premier entier isole (pas partie d un horaire type 10h00)."""
    import re as _re
    for m in _re.finditer(r'\b(\d{1,3})\b', texte):
        val   = m.group(1)
        apres = texte[m.end():m.end()+4]
        if _re.match(r'h\d{2}', apres):
            continue   # horaire "10h00" -> ignorer
        try:
            f = float(val)
            if 1 <= f <= 500:
                return str(int(f))
        except ValueError:
            pass
    return ""


def _premier_montant(texte: str) -> str:
    """Extrait le premier montant decimal credible (>= 100) dans une chaine."""
    import re
    for m in re.finditer(r'\b(\d{3,}(?:[.,]\d{1,2})?)\b', texte):
        val = m.group(1).replace(",", ".")
        try:
            f = float(val)
            if f >= 100:
                return str(int(f)) if f == int(f) else val
        except ValueError:
            pass
    return _premier_nombre(texte)


def _premier_nombre(texte: str) -> str:
    """Extrait le premier nombre decimal dans une chaine."""
    import re
    m = re.search(r"\d+(?:[.,]\d+)?", texte)
    if not m:
        return ""
    val = m.group(0).replace(",", ".")
    try:
        f = float(val)
        if f > 0:
            return str(int(f)) if f == int(f) else val
    except ValueError:
        pass
    return ""


class ExtracteurPDF:
    """Gère l'ouverture d'un PDF et l'extraction page par page."""

    def __init__(self, chemin_pdf: str | Path, config: dict):
        self.chemin = Path(chemin_pdf)
        self.config = config
        self.doc: fitz.Document | None = None

        tesseract_path = config.get("tesseract_path", "")
        if tesseract_path:
            configurer_tesseract(tesseract_path)

    def ouvrir(self) -> None:
        self.doc = fitz.open(str(self.chemin))

    def fermer(self) -> None:
        if self.doc:
            self.doc.close()
            self.doc = None

    def __enter__(self):
        self.ouvrir()
        return self

    def __exit__(self, *args):
        self.fermer()

    @property
    def nb_pages(self) -> int:
        return len(self.doc) if self.doc else 0

    def info_page(self, numero: int) -> dict:
        """
        Extrait toutes les informations d'une page.

        Retourne un dict avec :
            - numero : int (0-indexé)
            - texte : str
            - est_ocr : bool
            - miniature_bytes : bytes (PNG)
            - page_pdf_bytes : bytes (PDF page individuelle)
        """
        page = self.doc[numero]
        langue = self.config.get("langue_ocr", "fra+eng")

        texte, est_ocr = extraire_texte_complet(page, langue)
        miniature = generer_miniature(page)
        page_bytes = extraire_page_comme_pdf(self.doc, numero)

        return {
            "numero": numero,
            "texte": texte,
            "est_ocr": est_ocr,
            "miniature_bytes": miniature,
            "page_pdf_bytes": page_bytes,
            "chemin_source": str(self.chemin),
            "nom_fichier_source": self.chemin.name,
        }

    def pages(self) -> Generator[dict, None, None]:
        """Itère sur toutes les pages et retourne leurs informations."""
        for i in range(self.nb_pages):
            yield self.info_page(i)
