"""
Construction des noms de fichiers et copie vers les dossiers de destination.
Convention : [TYPE]-YYYY-MM-DDauDD-NOM_EMPLOYEUR.pdf

Logique de destination :
  Le PDF source est dans un dossier mois (ex: "01 Janvier").
  Les pages classifiees vont dans un sous-dossier TYPE de ce meme dossier mois.
  Exemple : 01 Janvier/BP/[BP]-2024-01-01au31-NOM.pdf
"""
from datetime import date as _date
from pathlib import Path

from config import MOIS_DOSSIERS, TYPES_DOCUMENTS, resoudre_dossier_base

METADATA_KEY = "IntermitDoc"   # valeur dans le champ 'subject' du PDF


def _injecter_metadata(pdf_bytes: bytes, info: dict) -> bytes:
    """
    Ouvre les bytes PDF avec fitz, écrit les métadonnées IntermitDoc
    dans les champs standard (subject, keywords), retourne les bytes modifiés.
    Si fitz n'est pas disponible ou échoue, retourne les bytes d'origine.
    """
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        meta = doc.metadata or {}
        type_doc = info.get("type", "")
        annee    = info.get("annee", "")
        mois     = info.get("mois", "")
        emp      = info.get("employeur", "")
        heures   = info.get("heures", "")
        salaire  = info.get("salaire_brut", "")
        date_trait = str(_date.today())
        doc.set_metadata({
            "author":   meta.get("author", ""),
            "title":    meta.get("title", ""),
            "creator":  meta.get("creator", ""),
            "producer": meta.get("producer", ""),
            "subject":  f"IntermitDoc:{type_doc}:{annee}-{mois}",
            "keywords": (
                f"IntermitDoc type={type_doc} annee={annee} mois={mois} "
                f"employeur={emp} heures={heures} salaire={salaire} "
                f"traite={date_trait}"
            ),
        })
        result = doc.tobytes(deflate=True)
        doc.close()
        return result
    except Exception:
        return pdf_bytes


def lire_metadata_intermitdoc(chemin_pdf: str) -> dict | None:
    """
    Lit les métadonnées IntermitDoc d'un PDF.
    Retourne un dict ou None si le fichier n'a pas été traité par IntermitDoc.
    """
    try:
        import fitz
        doc = fitz.open(chemin_pdf)
        meta = doc.metadata or {}
        doc.close()
        subject  = meta.get("subject", "")
        keywords = meta.get("keywords", "")
        if not subject.startswith("IntermitDoc:"):
            return None
        # Parser les keywords
        result = {}
        for part in keywords.split():
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v
        return result
    except Exception:
        return None


def construire_nom_fichier(info: dict) -> str:
    """
    Construit le nom de fichier selon la convention.
    Ex : [BP] 2024-03-01_31 Productions XYZ.pdf
         [AEM] 2026-05-01_31 LaVouivre 151h 2500EUR.pdf
    """
    type_doc   = info.get("type", "INCONNU")
    annee      = info.get("annee", "XXXX")
    mois       = info.get("mois", "XX")
    date_debut = info.get("date_debut", "")
    date_fin   = info.get("date_fin", date_debut)
    employeur  = info.get("employeur", "INCONNU")

    # Partie date : YYYY-MM-DD ou YYYY-MM-DD_DD (periode)
    if date_debut and date_fin and date_debut != date_fin:
        partie_date = f"{annee}-{mois}-{date_debut}_{date_fin}"
    elif date_debut:
        partie_date = f"{annee}-{mois}-{date_debut}"
    else:
        partie_date = f"{annee}-{mois}"

    nom = f"[{type_doc}] {partie_date} {employeur}"

    # Pour les AEM : ajouter heures et salaire brut si disponibles
    if type_doc == "AEM":
        heures       = info.get("heures", "").strip()
        salaire_brut = info.get("salaire_brut", "").strip()
        if heures:
            # Afficher entier si possible (ex: "151.0" -> "151")
            try:
                h = float(heures)
                heures = str(int(h)) if h == int(h) else heures
            except ValueError:
                pass
            nom += f" {heures}h"
        if salaire_brut:
            try:
                s = float(salaire_brut)
                salaire_brut = str(int(s)) if s == int(s) else salaire_brut
            except ValueError:
                pass
            nom += f" {salaire_brut}EUR"

    return nom + ".pdf"


def resoudre_dossier_destination(info: dict, chemin_source: str) -> Path | None:
    """
    Resout le dossier de destination a partir du dossier parent du PDF source.

    Logique :
      - Le PDF source est dans  .../01 Janvier/fichier.pdf
      - La destination devient  .../01 Janvier/TYPE/
      - Le sous-dossier TYPE est cree si absent.

    Retourne None si le type est INCONNU.
    """
    type_doc = info.get("type", "INCONNU")
    if type_doc == "INCONNU":
        return None

    dossier_mois = Path(chemin_source).parent
    return dossier_mois / type_doc


def copier_page_classifiee(
    page_pdf_bytes: bytes,
    info: dict,
    config: dict,
    chemin_source: str = "",
) -> dict:
    """
    Copie une page PDF vers son dossier de destination.

    Priorite :
      1. Si chemin_source fourni : destination = dossier_parent(source)/TYPE/
      2. Sinon : destination = dossier_base_config / MM MoisNom / TYPE/
    """
    nom_fichier = construire_nom_fichier(info)
    type_doc    = info.get("type", "INCONNU")

    if type_doc == "INCONNU":
        # Exporter dans le dossier du PDF source avec un nom horodaté
        if chemin_source:
            dossier_fallback = Path(chemin_source).parent
        else:
            dossier_fallback = resoudre_dossier_base(config)

        dossier_fallback.mkdir(parents=True, exist_ok=True)
        nom_fallback   = nom_fichier  # contient deja [INCONNU]-...
        chemin_fallback = dossier_fallback / nom_fallback

        try:
            chemin_fallback.write_bytes(page_pdf_bytes)
            return {
                "succes": True,
                "chemin_destination": str(chemin_fallback),
                "nom_fichier": chemin_fallback.name,
                "erreur": None,
                "fallback": True,
            }
        except OSError as e:
            return {
                "succes": False,
                "chemin_destination": "",
                "nom_fichier": nom_fallback,
                "erreur": f"Erreur ecriture fallback : {e}",
            }

    # Determiner le dossier de destination — toujours la structure complete depuis dossier_base
    mois = info.get("mois", "")
    nom_dossier_mois = MOIS_DOSSIERS.get(mois)
    if not nom_dossier_mois:
        return {
            "succes": False,
            "chemin_destination": "",
            "nom_fichier": nom_fichier,
            "erreur": "Mois manquant -- corrigez le mois dans le formulaire.",
        }
    annee = info.get("annee", "")
    if not annee:
        from datetime import date as _date
        annee = str(_date.today().year)
    dossier = resoudre_dossier_base(config) / annee / nom_dossier_mois / type_doc

    # Creer le sous-dossier si absent
    dossier.mkdir(parents=True, exist_ok=True)

    chemin_dest = dossier / nom_fichier

    try:
        # Injecter les métadonnées IntermitDoc dans le PDF avant écriture
        pdf_bytes_final = _injecter_metadata(page_pdf_bytes, info)
        chemin_dest.write_bytes(pdf_bytes_final)
        return {
            "succes": True,
            "chemin_destination": str(chemin_dest),
            "nom_fichier": chemin_dest.name,
            "erreur": None,
        }
    except OSError as e:
        return {
            "succes": False,
            "chemin_destination": "",
            "nom_fichier": nom_fichier,
            "erreur": f"Erreur ecriture : {e}",
        }


def creer_sous_dossiers_mois(dossier_mois: str | Path) -> int:
    """
    Cree les sous-dossiers TYPE (AEM/BP/CS/CT/STC) dans un dossier mois donne.
    Retourne le nombre de dossiers crees.
    """
    base  = Path(dossier_mois)
    crees = 0
    for type_doc in TYPES_DOCUMENTS:
        if type_doc == "INCONNU":
            continue
        d = base / type_doc
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            crees += 1
    return crees


def creer_structure_dossiers(config: dict) -> int:
    """
    Cree la structure ANNEE/mois/type dans dossier_base.
    Cree toujours l'annee en cours.
    Cree aussi les annees anterieures si des PDFs classes sont trouves.
    """
    import re as _re
    from datetime import date as _date
    base  = resoudre_dossier_base(config)
    crees = 0

    # Annees a creer : annee courante + annees trouvees dans les docs existants
    annee_courante = str(_date.today().year)
    annees = {annee_courante}

    pat_annee = _re.compile(r"\[(?:AEM|BP|CS|CT|STC)\]\s*(\d{4})-")
    for pdf in base.rglob("*.pdf"):
        m = pat_annee.search(pdf.name)
        if m:
            annees.add(m.group(1))

    for annee in sorted(annees):
        for nom_mois in MOIS_DOSSIERS.values():
            for type_doc in TYPES_DOCUMENTS:
                if type_doc == "INCONNU":
                    continue
                d = base / annee / nom_mois / type_doc
                if not d.exists():
                    d.mkdir(parents=True, exist_ok=True)
                    crees += 1
    return crees
