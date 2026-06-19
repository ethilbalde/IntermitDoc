# -*- coding: utf-8 -*-
"""
Analyse des documents via les APIs IA (Claude, OpenAI, Gemini, Mistral).
Classe le type de document et extrait les informations cles.
"""
import json
import re
import urllib.request
import urllib.error
from anthropic import Anthropic

PROMPT_SYSTEME = """Tu es un assistant specialise dans la classification de documents administratifs francais pour les intermittents du spectacle.

Tu dois analyser le texte extrait d'une page PDF et identifier :
1. Le TYPE de document parmi : AEM, BP, CS, CT, STC, INCONNU
2. Les informations cles du document

TYPES DE DOCUMENTS :
- AEM : Attestation Employeur Mensuelle - contient "attestation employeur mensuelle", "AEM", "Unedic". PRIORITE ABSOLUE sur tous les autres types.
- BP : Bulletin de Paie / Fiche de Salaire - contient "bulletin de paie", "fiche de paie", cotisations sociales, net a payer. ATTENTION : un BP peut mentionner "conges spectacles" comme cotisation, ca reste un BP.
- CS : Contrat CDDU dans le spectacle OU document emis par l organisme Conges Spectacles (www.conges-spectacles.com). Classifier CS uniquement si le document provient de conges-spectacles.com ou est un contrat d engagement intermittent.
- CT : Contrat de travail ou Certificat de travail - contient "contrat de travail", "certificat de travail", CDI/CDD, avenant.
- STC : Solde de Tout Compte - contient "solde de tout compte", recu pour solde.
- INCONNU : Aucun des types precedents identifiables.

REGLES D EXTRACTION :
- Employeur : nom de l entreprise/association qui emploie (pas le salarie).
- Annee : format YYYY
- Mois : format MM sur 2 chiffres (01-12)
- Date debut : format DD sur 2 chiffres
- Date fin : format DD sur 2 chiffres (dernier jour si periode)
- Confiance : valeur entre 0.0 et 1.0

REPONSE OBLIGATOIREMENT EN JSON valide, aucun texte avant ou apres :
{
  "type": "BP",
  "annee": "2024",
  "mois": "03",
  "date_debut": "01",
  "date_fin": "31",
  "employeur": "Productions XYZ",
  "confiance": 0.95,
  "notes": "Bulletin de paie Mars 2024"
}"""


PROMPT_DETAILS_AEM = """Tu es un assistant specialise dans l analyse d attestations employeur mensuelle (AEM) pour les intermittents du spectacle francais.

Extrais UNIQUEMENT ces deux valeurs du document en cherchant les libelles EXACTS suivants :

1. HEURES TRAVAILLEES :
   Cherche le libelle exact (avec ou sans accents/majuscules) :
   "Nombre d HEURES effectuees" ou "Nombre d'HEURES effectuees"
   Prends le nombre qui se trouve juste en face ou juste apres ce libelle.
   NE PAS confondre avec des horaires de journee (ex: "10h00", "22h30").

2. SALAIRE BRUT :
   Cherche le libelle exact (avec ou sans accents/majuscules) :
   "salaire brut soumis a la contribution d assurance chomage"
   ou "salaires bruts soumis a la contribution d assurance chomage"
   ou "salaire bruts soumis aux contributions d assurance chomage"
   Prends le montant numerique qui se trouve juste en face ou juste apres.

REPONSE OBLIGATOIREMENT EN JSON valide, rien d autre :
{
  "heures": "12",
  "salaire_brut": "180.52"
}

Si une valeur est introuvable, utilise "" (chaine vide).
Heures : nombre entier ou decimal sans unite (ex: "12", "35.5").
Salaire brut : nombre decimal avec point sans symbole (ex: "180.52", "2500.00")."""


_RE_NOM_CLASSIFIE = re.compile(
    r'^\[(?P<type>AEM|BP|CS|CT|STC|INCONNU)\]\s+'
    r'(?P<annee>\d{4})-(?P<mois>\d{2})-(?P<debut>\d{2})'
    r'(?:_(?P<fin>\d{2}))?'
    r'\s+(?P<employeur>.+?)'
    r'(?:\s+(?P<heures>\d+(?:\.\d+)?)h)?'
    r'(?:\s+(?P<salaire>\d+(?:\.\d+)?)EUR)?'
    r'\.pdf$',
    re.IGNORECASE,
)


def analyser_nom_fichier(nom_fichier: str) -> dict | None:
    """
    Si le nom de fichier correspond deja a notre convention de nommage,
    retourne directement les infos extraites sans appel IA.
    Retourne None si le nom ne correspond pas.
    """
    m = _RE_NOM_CLASSIFIE.match(nom_fichier.strip())
    if not m:
        return None
    return {
        "type":        m.group("type").upper(),
        "annee":       m.group("annee"),
        "mois":        m.group("mois"),
        "date_debut":  m.group("debut"),
        "date_fin":    m.group("fin") or m.group("debut"),
        "employeur":   m.group("employeur").strip(),
        "heures":      m.group("heures") or "",
        "salaire_brut":m.group("salaire") or "",
        "confiance":   1.0,
        "notes":       f"[Nom conforme] extrait depuis le nom de fichier",
        "erreur":      None,
    }


def extraire_info_nom_fichier(nom: str) -> dict:
    """
    Extrait les informations disponibles dans le nom de fichier.
    Retourne un dict partiel — les champs non trouves sont vides.
    Les dates ne sont JAMAIS utilisees directement : elles restent pour
    cross-validation uniquement (l IA verifie toujours dans le contenu).
    """
    from pathlib import Path as _Path
    base = _Path(nom).stem

    info = {
        "type": "", "annee": "", "mois": "",
        "date_debut": "", "date_fin": "", "employeur": "",
        "heures": "", "salaire_brut": "",
        "_source_nom": True,   # marqueur : ces infos viennent du nom
    }

    # Format IntermitDoc : [BP] 2025-03-01_31 Productions XYZ 10h 500EUR
    m = re.match(
        r'\[(\w+)\]\s+(\d{4})-(\d{2})-(\d{2})(?:_(\d{2}))?'
        r'\s+(.*?)(?:\s+(\d+(?:\.\d+)?)h)?(?:\s+(\d+(?:\.\d+)?)EUR)?$',
        base, re.IGNORECASE
    )
    if m:
        info["type"]        = m.group(1).upper()
        info["annee"]       = m.group(2)
        info["mois"]        = m.group(3)
        info["date_debut"]  = m.group(4)
        info["date_fin"]    = m.group(5) or m.group(4)
        info["employeur"]   = m.group(6).strip()
        info["heures"]      = m.group(7) or ""
        info["salaire_brut"]= m.group(8) or ""
        return info

    # Recherche generique : annee YYYY
    m = re.search(r'(20\d{2})', base)
    if m:
        info["annee"] = m.group(1)

    # Mois MM entre separateurs
    m = re.search(r'[-_\s](0[1-9]|1[0-2])[-_\s]', base)
    if m:
        info["mois"] = m.group(1)

    # Type de document dans le nom
    for t in ["AEM", "BP", "STC", "CS", "CT"]:
        if re.search(rf'\b{t}\b', base, re.IGNORECASE):
            info["type"] = t
            break

    return info


def fusionner_info_nom_analyse(info_nom: dict, analyse: dict) -> dict:
    """
    Complete l analyse IA avec les infos du nom de fichier pour les champs vides.
    Les dates de l analyse (contenu document) ont TOUJOURS priorite.
    """
    resultat = dict(analyse)
    for champ in ("type", "annee", "mois", "employeur", "heures", "salaire_brut"):
        if not resultat.get(champ) and info_nom.get(champ):
            resultat[champ] = info_nom[champ]
    # Les dates (date_debut, date_fin) viennent toujours du contenu — ne pas ecraser
    return resultat


def _normaliser_texte(s: str) -> str:
    """Supprime accents et met en minuscules pour comparaison."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def chercher_employeur_connu(texte: str, employeurs: list) -> str:
    """
    Cherche si un employeur connu apparait dans le texte.
    Retourne le nom de l employeur tel que stocke dans la liste, ou "".
    """
    texte_norm = _normaliser_texte(texte)
    for emp in employeurs:
        if not emp.strip():
            continue
        emp_norm = _normaliser_texte(emp)
        if emp_norm and emp_norm in texte_norm:
            return emp
    return ""


def analyser_document(texte: str, config: dict, employeurs: list | None = None) -> dict:
    """
    Envoie le texte a l API Claude pour classification.
    Retourne un dict avec les champs du document ou un dict d erreur.
    """
    api_key = config.get("api_key", "")
    if not api_key:
        return _resultat_inconnu("Cle API manquante")

    texte_tronque = texte[:4000] if len(texte) > 4000 else texte
    if not texte_tronque.strip():
        return _resultat_inconnu(
            "Texte vide -- PDF scanne sans Tesseract installe."
        )

    texte_lower = texte_tronque.lower()

    # Regles locales prioritaires (ordre important : AEM avant CS)
    REGLES_PRIORITAIRES = [
        ("AEM", [
            "attestation employeur mensuelle",
            "attestation d'employeur mensuelle",
            "unedic",
            "unedic",
            "aem",
        ]),
        ("CS", [
            "www.conges-spectacles.com",
            "conges-spectacles.com",
            "audiens conges spectacles",
        ]),
    ]

    type_force = None
    for type_doc, mots_cles in REGLES_PRIORITAIRES:
        if any(mot in texte_lower for mot in mots_cles):
            type_force = type_doc
            break

    try:
        client = Anthropic(api_key=api_key)
        modele = config.get("modele_claude", "claude-sonnet-4-6")

        message = client.messages.create(
            model=modele,
            max_tokens=512,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user",
                       "content": f"Analyse ce document et reponds uniquement en JSON :\n\n{texte_tronque}"}]
        )

        resultat = _parser_reponse(message.content[0].text.strip())

        if type_force and resultat["type"] != type_force:
            resultat["type"]  = type_force
            resultat["notes"] = f"[Force {type_force}] " + resultat.get("notes", "")

        # Priorite aux employeurs connus
        if employeurs:
            emp_connu = chercher_employeur_connu(texte, employeurs)
            if emp_connu:
                resultat["employeur"] = emp_connu

        return resultat

    except Exception as e:
        return _resultat_inconnu(f"Erreur API : {str(e)[:100]}")


def analyser_details_aem(texte: str, config: dict) -> dict:
    """
    Second passage pour les AEM : extrait heures travaillees et salaire brut.
    Retourne {"heures": "151", "salaire_brut": "2500.00"}
    Claude est toujours appele en priorite ; la regex locale sert de fallback.
    """
    api_key = config.get("api_key", "")
    if not texte.strip():
        return {"heures": "", "salaire_brut": ""}

    texte_tronque = texte[:4000] if len(texte) > 4000 else texte

    # Claude en priorite
    if api_key:
        try:
            client = Anthropic(api_key=api_key)
            modele = config.get("modele_claude", "claude-sonnet-4-6")

            message = client.messages.create(
                model=modele,
                max_tokens=256,
                system=PROMPT_DETAILS_AEM,
                messages=[{"role": "user",
                           "content": f"Extrais les heures et le salaire brut de ce document AEM :\n\n{texte_tronque}"}]
            )

            contenu = message.content[0].text.strip()
            match   = re.search(r'\{.*\}', contenu, re.DOTALL)
            if match:
                data         = json.loads(match.group(0))
                heures       = _nettoyer_nombre(data.get("heures", ""))
                salaire_brut = _nettoyer_nombre(data.get("salaire_brut", ""))
                if heures or salaire_brut:
                    return {"heures": heures, "salaire_brut": salaire_brut}
        except Exception:
            pass

    # Fallback regex locale (moins fiable, uniquement si Claude echoue)
    return _detecter_details_local(texte_tronque)


def _detecter_details_local(texte: str) -> dict:
    """Tentative d extraction rapide par regex sans appel API."""
    heures       = ""
    salaire_brut = ""

    # Patterns heures : "151 h", "151h", "151,50 heures", etc.
    m = re.search(
        r'(?:nb\s*)?(?:nombre\s+d.?heures?|total\s+heures?|heures?\s+travail\w*)'
        r'[\s:]*(\d+(?:[.,]\d+)?)',
        texte, re.IGNORECASE
    )
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*h(?:eures?)?\b', texte, re.IGNORECASE)
    if m:
        heures = _nettoyer_nombre(m.group(1))

    # Patterns salaire brut
    m = re.search(
        r'(?:salaire\s+brut|remuneration\s+brute?|total\s+brut|brut\s+total)'
        r'[\s:]*(\d[\d\s.,]+)',
        texte, re.IGNORECASE
    )
    if m:
        salaire_brut = _nettoyer_nombre(m.group(1))

    return {"heures": heures, "salaire_brut": salaire_brut}


def _nettoyer_nombre(val: str) -> str:
    """Normalise un nombre : supprime espaces, remplace virgule par point."""
    if not val:
        return ""
    val = str(val).strip().replace(" ", "").replace(",", ".")
    # Garder uniquement chiffres et point
    val = re.sub(r"[^\d.]", "", val)
    # Supprimer les points en double
    parts = val.split(".")
    if len(parts) > 2:
        val = parts[0] + "." + "".join(parts[1:])
    return val.strip(".") or ""


def _parser_reponse(contenu: str) -> dict:
    match = re.search(r'\{.*\}', contenu, re.DOTALL)
    if not match:
        return _resultat_inconnu("Reponse non-JSON de Claude")

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _resultat_inconnu("JSON invalide")

    from config import TYPES_DOCUMENTS
    type_doc = data.get("type", "INCONNU").upper()
    if type_doc not in TYPES_DOCUMENTS:
        type_doc = "INCONNU"

    annee      = _valider_annee(data.get("annee", ""))
    mois       = _valider_mois(data.get("mois", ""))
    date_debut = _valider_jour(data.get("date_debut", ""))
    date_fin   = _valider_jour(data.get("date_fin", date_debut))
    employeur  = _nettoyer_nom_employeur(data.get("employeur", ""))
    confiance  = _valider_confiance(data.get("confiance", 0.5))
    notes      = str(data.get("notes", ""))[:200]

    return {
        "type": type_doc, "annee": annee, "mois": mois,
        "date_debut": date_debut, "date_fin": date_fin,
        "employeur": employeur, "confiance": confiance,
        "notes": notes, "erreur": None,
        "heures": "", "salaire_brut": "",
    }


def _resultat_inconnu(raison: str) -> dict:
    return {
        "type": "INCONNU", "annee": "", "mois": "", "date_debut": "", "date_fin": "",
        "employeur": "", "confiance": 0.0, "notes": "", "erreur": raison,
        "heures": "", "salaire_brut": "",
    }


def _valider_annee(val) -> str:
    val = str(val).strip()
    return val if re.fullmatch(r'20\d{2}', val) else ""

def _valider_mois(val) -> str:
    val = str(val).strip().zfill(2)
    return val if re.fullmatch(r'0[1-9]|1[0-2]', val) else ""

def _valider_jour(val) -> str:
    val = str(val).strip().zfill(2)
    return val if re.fullmatch(r'0[1-9]|[12]\d|3[01]', val) else ""

def _valider_confiance(val) -> float:
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return 0.5

def _nettoyer_nom_employeur(nom: str) -> str:
    import unicodedata
    if not nom:
        return ""
    nom = unicodedata.normalize("NFD", str(nom))
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn")
    nom = re.sub(r'[\\/:*?"<>|]', '', nom)
    nom = re.sub(r"['\`]", '', nom)
    nom = re.sub(r'\s+', ' ', nom).strip()
    return nom[:40]


# ---------------------------------------------------------------------------
# Adaptateurs IA externes
# ---------------------------------------------------------------------------

def _appel_http(url: str, headers: dict, body: dict) -> str:
    """Appel HTTP POST generique, retourne le texte brut de la reponse."""
    data = json.dumps(body).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _analyser_openai(texte: str, api_key: str, modele: str = "gpt-4o-mini") -> dict:
    """Appel OpenAI Chat Completions."""
    try:
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        body = {
            "model": modele,
            "max_tokens": 512,
            "messages": [
                {"role": "system",  "content": PROMPT_SYSTEME},
                {"role": "user",    "content": f"Analyse ce document et reponds uniquement en JSON :\n\n{texte[:4000]}"},
            ],
        }
        raw  = _appel_http("https://api.openai.com/v1/chat/completions", headers, body)
        data = json.loads(raw)
        contenu = data["choices"][0]["message"]["content"].strip()
        return _parser_reponse(contenu)
    except Exception as e:
        return _resultat_inconnu(f"OpenAI : {str(e)[:80]}")


def _analyser_gemini(texte: str, api_key: str, modele: str = "gemini-1.5-flash") -> dict:
    """Appel Google Gemini generateContent."""
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{modele}:generateContent?key={api_key}"
        )
        headers = {"Content-Type": "application/json"}
        prompt  = f"{PROMPT_SYSTEME}\n\nAnalyse ce document et reponds uniquement en JSON :\n\n{texte[:4000]}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 512},
        }
        raw     = _appel_http(url, headers, body)
        data    = json.loads(raw)
        contenu = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return _parser_reponse(contenu)
    except Exception as e:
        return _resultat_inconnu(f"Gemini : {str(e)[:80]}")


def _analyser_mistral(texte: str, api_key: str, modele: str = "mistral-small-latest") -> dict:
    """Appel Mistral Chat Completions."""
    try:
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        body = {
            "model": modele,
            "max_tokens": 512,
            "messages": [
                {"role": "system",  "content": PROMPT_SYSTEME},
                {"role": "user",    "content": f"Analyse ce document et reponds uniquement en JSON :\n\n{texte[:4000]}"},
            ],
        }
        raw  = _appel_http("https://api.mistral.ai/v1/chat/completions", headers, body)
        data = json.loads(raw)
        contenu = data["choices"][0]["message"]["content"].strip()
        return _parser_reponse(contenu)
    except Exception as e:
        return _resultat_inconnu(f"Mistral : {str(e)[:80]}")


def tester_connexion_ia(provider_id: str, api_key: str) -> tuple[bool, str]:
    """
    Teste la connexion a un fournisseur IA avec un texte minimal.
    Retourne (succes, message).
    """
    texte_test = "Bulletin de paie Mars 2024 Productions XYZ net a payer 1500 EUR"
    try:
        if provider_id == "claude":
            client = Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=10,
                messages=[{"role": "user", "content": "ping"}]
            )
        elif provider_id == "openai":
            _analyser_openai(texte_test, api_key)
        elif provider_id == "gemini":
            _analyser_gemini(texte_test, api_key)
        elif provider_id == "mistral":
            _analyser_mistral(texte_test, api_key)
        else:
            return False, "Fournisseur inconnu"
        return True, "Connexion reussie"
    except Exception as e:
        return False, str(e)[:120]


# ---------------------------------------------------------------------------
# Analyse multi-IA avec consensus
# ---------------------------------------------------------------------------

def analyser_document_multi(texte: str, config: dict, employeurs: list | None = None) -> dict:
    """
    Analyse le document avec toutes les IA activees.
    Si une seule IA est activee : retourne son resultat directement.
    Si plusieurs : vote majoritaire sur le type, meilleure confiance pour les champs.
    """
    providers = config.get("ia_providers", {})
    actifs = [pid for pid, cfg in providers.items() if cfg.get("enabled") and cfg.get("api_key")]

    if not actifs:
        return _resultat_inconnu("Aucune IA activee avec une cle API.")

    # Si Claude seul (cas par defaut) : chemin rapide
    if actifs == ["claude"] or len(actifs) == 1:
        return analyser_document(texte, config, employeurs)

    resultats = {}
    for pid in actifs:
        cle = providers[pid]["api_key"]
        modele = providers[pid].get("modele", "")
        if pid == "claude":
            r = analyser_document(texte, config, employeurs)
        elif pid == "openai":
            r = _analyser_openai(texte, cle, modele or "gpt-4o-mini")
        elif pid == "gemini":
            r = _analyser_gemini(texte, cle, modele or "gemini-1.5-flash")
        elif pid == "mistral":
            r = _analyser_mistral(texte, cle, modele or "mistral-small-latest")
        else:
            continue
        if not r.get("erreur"):
            resultats[pid] = r

    if not resultats:
        return _resultat_inconnu("Toutes les IA ont echoue.")

    if len(resultats) == 1:
        return next(iter(resultats.values()))

    # Vote majoritaire sur le type
    from collections import Counter
    votes_type = Counter(r["type"] for r in resultats.values())
    type_gagnant, nb_votes = votes_type.most_common(1)[0]
    nb_total = len(resultats)

    # Resultat de base : prendre celui avec la meilleure confiance
    meilleur = max(resultats.values(), key=lambda r: r.get("confiance", 0))
    meilleur = dict(meilleur)
    meilleur["type"] = type_gagnant

    # Confiance ajustee selon le consensus
    ratio_accord = nb_votes / nb_total
    confiance_base = meilleur.get("confiance", 0.5)
    meilleur["confiance"] = round(confiance_base * ratio_accord, 2)

    # Note de consensus
    detail = ", ".join(f"{pid}={r['type']}" for pid, r in resultats.items())
    meilleur["notes"] = f"[Consensus {nb_votes}/{nb_total}] {detail}"

    # Recherche employeur connu
    if employeurs:
        emp = chercher_employeur_connu(texte, employeurs)
        if emp:
            meilleur["employeur"] = emp

    return meilleur
