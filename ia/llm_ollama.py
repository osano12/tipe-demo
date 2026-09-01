from __future__ import annotations
import base64
import io
import json
import logging
import time
from typing import Any
"""Client Ollama Vision local pour la classification de déchets (JSON strict + robustesse)."""
"""Ici on utilise Ollama Vision en local pour classer les déchets à partir d'images.
Le client envoie une image encodée en base64 dans un prompt détaillé avec des instructions strictes pour obtenir une réponse JSON structurée. 
On gère les cas où Ollama pourrait répondre hors format (ex: texte libre, markdown) en appliquant une extraction du JSON et un repair pass pour tenter de reformater la réponse. 
Si tout échoue, on retourne une classification par défaut "inconnu" avec une confiance de 0, et on loggue les erreurs pour analyse."""


try:
    import requests  # type: ignore
except Exception as exc:  # pragma: no cover
    requests = None  # type: ignore[assignment]
    _REQUESTS_IMPORT_ERROR = exc
else:
    _REQUESTS_IMPORT_ERROR = None

try:
    from PIL import Image  # type: ignore
except Exception as exc:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    _PIL_IMPORT_ERROR = exc
else:
    _PIL_IMPORT_ERROR = None


LOGGER = logging.getLogger("ia.llm_ollama")

# ---- Config ----
CONFIDENCE_THRESHOLD = 0.70
DEFAULT_OLLAMA_MODEL = "llava"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 180.0
DEFAULT_OLLAMA_MAX_IMAGE_SIDE = 768
DEFAULT_OLLAMA_JPEG_QUALITY = 80
DEFAULT_PROMPT_MODE = "complet"

ALLOWED_CATEGORIES = {"bio", "recyclable", "waste", "inconnu"}
ALLOWED_MATERIALS = {
    "papier",
    "carton",
    "plastique",
    "metal",
    "verre",
    "organique",
    "textile",
    "composite",
    "inconnue",
}

MATIERE_MAP = {
    "paper": "papier",
    "cardboard": "carton",
    "plastic": "plastique",
    "metal": "metal",
    "glass": "verre",
    "organic": "organique",
    "unknown": "inconnue",
    "composite": "composite",
    "fabric": "textile",
    "cloth": "textile",
}


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests manquant (`pip install requests`).") from _REQUESTS_IMPORT_ERROR


def _require_pil() -> None:
    if Image is None:
        raise RuntimeError("pillow manquant (`pip install pillow`).") from _PIL_IMPORT_ERROR


def build_prompt(mode: str = DEFAULT_PROMPT_MODE) -> str:
    """Prompt robuste + few-shots.
    NOTE: mÃªme si `format=json` est demandé Ã  Ollama, llava peut dévier,
    donc on reste trÃ¨s strict dans le texte + on gÃ¨re un repair pass.
    """
    if str(mode).lower() == "court":
        return (
            "Tu es un classificateur de déchets. "
            "Réponds avec UN SEUL JSON sur UNE ligne, sans texte autour, sans markdown. "
            'Schéma exact: {"objet":"...","matiere":"...","categorie_tri":"bio|recyclable|waste|inconnu","confiance":0.0-1.0,"incertain":true|false}. '
            "Matières autorisées: papier|carton|plastique|metal|verre|organique|textile|composite|inconnue. "
            f"Règle: si confiance < {CONFIDENCE_THRESHOLD:.2f} => categorie_tri=inconnu et incertain=true. "
            "recyclable = papier/carton/plastique/metal/verre ; bio = organique ; waste = sale/non recyclable/composite."
        )

    prompt = f"""
Tu es un classificateur de déchets pour une poubelle intelligente.

REGLE ABSOLUE :
- Tu DOIS répondre avec UN SEUL JSON valide, sur UNE SEULE ligne.
- Aucun texte avant/après. Pas de markdown. Pas de bloc ```.

SCHEMA JSON OBLIGATOIRE (toutes les clés doivent exister) :
{{"objet":"...","matiere":"...","categorie_tri":"bio|recyclable|waste|inconnu","confiance":0.0-1.0,"incertain":true|false}}

DÉFINITIONS DES CATÉGORIES :
- recyclable : papier, carton, plastique, métal, verre (plutôt propres/triables)
- bio : restes alimentaires / épluchures / marc de café / coquilles d’oeuf / déchets organiques
- waste : non recyclable ou souillé (mouchoirs, sopalin sale, masques, couches, objets composites, plastique très sale)
- inconnu : si l’image est floue, partielle, ou si tu n’es pas sûr

RÈGLES DE CONFIANCE :
- confiance âˆˆ [0,1]
- Si confiance < {CONFIDENCE_THRESHOLD:.2f} => incertain=true ET categorie_tri="inconnu"
- Si tu es sûr => incertain=false

RÈGLES DE MATIÈRE (valeurs simples) :
papier | carton | plastique | metal | verre | organique | textile | composite | inconnue

FEW-SHOTS (exemples, à imiter exactement) :

1) Entrée: "boule de papier blanche froissée"
Sortie: {{"objet":"boule de papier froissée","matiere":"papier","categorie_tri":"recyclable","confiance":0.88,"incertain":false}}

2) Entrée: "feuille A4 propre"
Sortie: {{"objet":"feuille de papier","matiere":"papier","categorie_tri":"recyclable","confiance":0.90,"incertain":false}}

3) Entrée: "carton d'emballage brun"
Sortie: {{"objet":"carton d'emballage","matiere":"carton","categorie_tri":"recyclable","confiance":0.86,"incertain":false}}

4) Entrée: "bouteille plastique transparente"
Sortie: {{"objet":"bouteille en plastique","matiere":"plastique","categorie_tri":"recyclable","confiance":0.87,"incertain":false}}

5) Entrée: "bouchon plastique"
Sortie: {{"objet":"bouchon en plastique","matiere":"plastique","categorie_tri":"recyclable","confiance":0.78,"incertain":false}}

6) Entrée: "sachet plastique propre"
Sortie: {{"objet":"sachet plastique","matiere":"plastique","categorie_tri":"recyclable","confiance":0.74,"incertain":false}}

7) Entrée: "canette boisson"
Sortie: {{"objet":"canette","matiere":"metal","categorie_tri":"recyclable","confiance":0.89,"incertain":false}}

8) Entrée: "boÃ®te de conserve vide"
Sortie: {{"objet":"boÃ®te de conserve","matiere":"metal","categorie_tri":"recyclable","confiance":0.86,"incertain":false}}

9) Entrée: "bocal en verre"
Sortie: {{"objet":"bocal en verre","matiere":"verre","categorie_tri":"recyclable","confiance":0.86,"incertain":false}}

10) Entrée: "bouteille en verre"
Sortie: {{"objet":"bouteille en verre","matiere":"verre","categorie_tri":"recyclable","confiance":0.88,"incertain":false}}

11) Entrée: "épluchures de banane"
Sortie: {{"objet":"épluchures","matiere":"organique","categorie_tri":"bio","confiance":0.90,"incertain":false}}

12) Entrée: "reste de nourriture (pÃ¢tes/salade)"
Sortie: {{"objet":"restes alimentaires","matiere":"organique","categorie_tri":"bio","confiance":0.86,"incertain":false}}

13) Entrée: "marc de café"
Sortie: {{"objet":"marc de café","matiere":"organique","categorie_tri":"bio","confiance":0.84,"incertain":false}}

14) Entrée: "coquilles d'Å“uf"
Sortie: {{"objet":"coquilles d'Å“uf","matiere":"organique","categorie_tri":"bio","confiance":0.82,"incertain":false}}

15) Entrée: "mouchoir usagé"
Sortie: {{"objet":"mouchoir","matiere":"papier","categorie_tri":"waste","confiance":0.83,"incertain":false}}

16) Entrée: "sopalin/essuie-tout sale"
Sortie: {{"objet":"papier essuie-tout","matiere":"papier","categorie_tri":"waste","confiance":0.82,"incertain":false}}

17) Entrée: "masque chirurgical"
Sortie: {{"objet":"masque","matiere":"composite","categorie_tri":"waste","confiance":0.84,"incertain":false}}

18) Entrée: "couche bébé"
Sortie: {{"objet":"couche","matiere":"composite","categorie_tri":"waste","confiance":0.88,"incertain":false}}

19) Entrée: "objet plastique trÃ¨s sale / gras"
Sortie: {{"objet":"plastique sale","matiere":"plastique","categorie_tri":"recyclable","confiance":0.75,"incertain":false}}

20) Entrée: "image floue / sombre / objet partiellement visible"
Sortie: {{"objet":"objet inconnu","matiere":"inconnue","categorie_tri":"inconnu","confiance":0.50,"incertain":true}}

21) Entrée: "Ring"
Sortie: {{"objet":"Ring","matiere":"Metal","categorie_tri":"waste","confiance":0.90,"incertain":false}}

22) Entrée: "Humain"
Sortie: {{"objet":"Humain","matiere":"Organique","categorie_tri":"bio","confiance":0.90,"incertain":false}}


MAINTENANT :
Analyse l'image fournie (un déchet dans une poubelle) et réponds UNIQUEMENT avec le JSON final au format ci-dessus.
""".strip()
    return prompt


def image_to_base64_jpeg(
    image: Any,
    *,
    max_side: int = DEFAULT_OLLAMA_MAX_IMAGE_SIDE,
    jpeg_quality: int = DEFAULT_OLLAMA_JPEG_QUALITY,
) -> str:
    """Encode une image PIL en JPEG base64 (sans retours à la ligne)."""
    _require_pil()
    img = image.copy() if hasattr(image, "copy") else image
    if getattr(img, "mode", "RGB") != "RGB":
        img = img.convert("RGB")

    width, height = getattr(img, "size", (0, 0))
    if int(max_side) > 0 and max(width, height) > int(max_side):
        img.thumbnail((int(max_side), int(max_side)))

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=int(jpeg_quality), optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def extract_first_json(text: str) -> str:
    """Extrait le premier objet JSON {...} d'une réponse potentiellement bruitée."""
    t = (text or "").strip()
    if t.startswith("{") and t.endswith("}"):
        return t

    start = t.find("{")
    if start < 0:
        raise ValueError("Aucun JSON détecté dans la réponse Ollama.")

    depth = 0
    for idx in range(start, len(t)):
        char = t[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return t[start : idx + 1]
    raise ValueError("JSON incomplet dans la réponse Ollama.")


def fallback_result(reason: str) -> dict[str, Any]:
    """Retour de secours si Ollama répond hors format attendu."""
    return {
        "objet": "objet inconnu",
        "matiere": "inconnue",
        "categorie_brute": "inconnu",
        "categorie": "inconnu",
        "confiance": 0.0,
        "incertain": True,
        "threshold_applied": False,
        "erreur_parse": reason,
        "raw": None,
    }


def _safe_float(x: Any, default: float = 0.5) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_bool(x: Any, default: bool = True) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        return x.strip().lower() in {"true", "1", "yes", "oui"}
    return default


def validate_ollama_json(data: dict[str, Any]) -> dict[str, Any]:
    """Validation 'soft' : normalise et applique le seuil.
    Ne lÃ¨ve pas d'exception sur champs manquants.
    """
    objet = str(data.get("objet", "")).strip() or "objet inconnu"
    matiere = str(data.get("matiere", "")).strip().lower() or "inconnue"
    categorie_brute = str(data.get("categorie_tri", "")).strip().lower() or "inconnu"
    confiance = max(0.0, min(1.0, _safe_float(data.get("confiance", 0.5), 0.5)))
    incertain = _safe_bool(data.get("incertain", True), True)

    # Normalisation matiÃ¨re (anglais -> FR)
    matiere = MATIERE_MAP.get(matiere, matiere)
    if matiere not in ALLOWED_MATERIALS:
        matiere = "inconnue"

    # Normalisation catégorie
    if categorie_brute not in ALLOWED_CATEGORIES:
        categorie_brute = "inconnu"
        incertain = True

    categorie = categorie_brute
    threshold_applied = False
    if confiance < CONFIDENCE_THRESHOLD:
        categorie = "inconnu"
        incertain = True
        threshold_applied = True

    return {
        "objet": objet,
        "matiere": matiere,
        "categorie_brute": categorie_brute,
        "categorie": categorie,
        "confiance": confiance,
        "incertain": incertain,
        "threshold_applied": threshold_applied,
    }


class OllamaVisionClient:
    """Client minimal pour Ollama Vision via l'endpoint local `/api/chat`."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_OLLAMA_MODEL,
        endpoint_url: str = DEFAULT_OLLAMA_URL,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        max_image_side: int = DEFAULT_OLLAMA_MAX_IMAGE_SIDE,
        jpeg_quality: int = DEFAULT_OLLAMA_JPEG_QUALITY,
        prompt_mode: str = DEFAULT_PROMPT_MODE,
        logger: logging.Logger | None = None,
    ) -> None:
        _require_requests()
        _require_pil()
        self.model = str(model)
        self.endpoint_url = str(endpoint_url)
        self.timeout_seconds = float(timeout_seconds)
        self.max_image_side = int(max_image_side)
        self.jpeg_quality = int(jpeg_quality)
        self.prompt_mode = str(prompt_mode)
        self.logger = logger or LOGGER

    def _post_chat(self, messages: list[dict[str, Any]], *, num_predict: int) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # Certains modÃ¨les ignorent "format": "json", mais Ã§a ne coÃ»te rien.
            "format": "json",
            "options": {
                "temperature": 0,
                "num_predict": int(num_predict),
                "num_thread": 4, # Ajuste selon ton nombre de coeurs CPU
                "num_ctx": 2048
            },
            "keep_alive": "10m",
        }

        resp = requests.post(  # type: ignore[union-attr]
            self.endpoint_url,
            json=payload,
            timeout=(5, self.timeout_seconds),
        )
        resp.raise_for_status()
        body = resp.json()
        msg = body.get("message") if isinstance(body, dict) else None
        if isinstance(msg, dict):
            return str(msg.get("content", "") or "")
        return str(body)

    def _repair_json(self, raw_text: str) -> dict[str, Any] | None:
        """2e passe: demander Ã  Ollama de reformater en JSON strict (sans image)."""
        repair_prompt = (
            "Convertis le texte suivant en UN SEUL JSON valide sur une ligne, sans aucun autre texte. "
            'Schéma exact: {"objet":"...","matiere":"...","categorie_tri":"bio|recyclable|waste|inconnu","confiance":0.0-1.0,"incertain":true|false}. '
            f"RÃ¨gle: si confiance < {CONFIDENCE_THRESHOLD:.2f} => categorie_tri=inconnu et incertain=true. "
            "Texte:\n<<<" + (raw_text or "") + ">>>"
        )
        try:
            content = self._post_chat([{"role": "user", "content": repair_prompt}], num_predict=180)
            parsed = json.loads(extract_first_json(content))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def classify_image(self, image: Any) -> dict[str, Any]:
        started = time.perf_counter()
        b64_jpeg = image_to_base64_jpeg(
            image, max_side=self.max_image_side, jpeg_quality=self.jpeg_quality
        )

        messages = [
            {
                "role": "user",
                "content": build_prompt(self.prompt_mode),
                "images": [b64_jpeg],
            }
        ]

        self.logger.info("Appel Ollama Vision (%s)", self.model)

        try:
            content = self._post_chat(messages, num_predict=220)
        except Exception as exc:
            nom_exception = type(exc).__name__.lower()
            if "timeout" in nom_exception:
                raise RuntimeError(
                    "Délai dépassé en attendant la réponse d'Ollama. "
                    "Le premier appel peut être long (chargement du modèle). "
                    "Vérifie que `ollama serve` tourne et que le modèle est téléchargé (`ollama pull llava`). "
                    "Tu peux augmenter `--ollama-timeout` si besoin."
                ) from exc
            raise

        # 1) parsing normal
        try:
            parsed = json.loads(extract_first_json(content))
            if not isinstance(parsed, dict):
                raise ValueError("Le JSON Ollama n'est pas un objet.")
            result = validate_ollama_json(parsed)
            result["raw"] = content
            result["llm_time_seconds"] = round(time.perf_counter() - started, 3)
            return result
        except Exception as exc:
            self.logger.warning("Parsing JSON Ollama KO (%s) -> tentative repair JSON", exc)

        # 2) repair pass
        repaired = self._repair_json(content)
        if isinstance(repaired, dict):
            try:
                result = validate_ollama_json(repaired)
                result["raw"] = content
                result["repaired"] = True
                result["llm_time_seconds"] = round(time.perf_counter() - started, 3)
                return result
            except Exception as exc2:
                self.logger.warning("Repair JSON reçu mais invalide (%s)", exc2)

        # 3) fallback
        self.logger.warning("Repair JSON échoué -> fallback 'inconnu'")
        fb = fallback_result("repair_failed")
        fb["raw"] = content
        fb["llm_time_seconds"] = round(time.perf_counter() - started, 3)
        return fb

