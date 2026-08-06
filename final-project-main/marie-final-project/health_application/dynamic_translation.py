"""Translation support for human-readable text stored in the database.

Static interface text belongs in Django's gettext catalog. Database content is
not known when ``compilemessages`` runs, so it needs a runtime translator.  The
runtime backends are deliberately optional: Argos Translate can run completely
locally, while LibreTranslate can be configured for a self-hosted server.
"""

import hashlib
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext, get_language


logger = logging.getLogger(__name__)

# High-frequency clinical/system values remain deterministic even when a model
# is unavailable. Arbitrary sentences are handled by Argos/LibreTranslate.
SWAHILI_GLOSSARY = {
    "Female": "Mwanamke",
    "Male": "Mwanamume",
    "Other": "Nyingine",
    "Stable": "Imara",
    "Needs Attention": "Anahitaji Uangalizi",
    "Critical": "Mahututi",
    "Recovering": "Anapata Nafuu",
    "Taken": "Imetumika",
    "Missed": "Imepitwa",
    "Pending": "Inasubiri",
    "Text": "Maandishi",
    "Voice": "Sauti",
    "Text and Voice": "Maandishi na Sauti",
    "Once": "Mara moja",
    "Daily": "Kila siku",
    "Weekly": "Kila wiki",
    "Custom days": "Siku maalum",
    "Normal User / Patient / Caregiver": "Mtumiaji wa Kawaida / Mgonjwa / Mlezi",
    "Doctor / Health Provider": "Daktari / Mtoa Huduma za Afya",
    "Admin": "Msimamizi",
    "Health user": "Mtumiaji wa afya",
    "No condition listed": "Hakuna hali iliyoorodheshwa",
}


def _argos_translate(text, source, target):
    try:
        import argostranslate.translate  # Optional open-source local model.
    except ImportError:
        return None
    try:
        installed = argostranslate.translate.get_installed_languages()
        source_language = next((item for item in installed if item.code == source), None)
        target_language = next((item for item in installed if item.code == target), None)
        if not source_language or not target_language:
            return None
        translation = source_language.get_translation(target_language)
        return translation.translate(text) if translation else None
    except Exception:
        logger.exception("Argos Translate failed")
        return None


def _libretranslate(text, source, target):
    endpoint = getattr(settings, "LIBRETRANSLATE_URL", "").rstrip("/")
    if not endpoint:
        return None
    payload = {"q": text, "source": source, "target": target, "format": "text"}
    api_key = getattr(settings, "LIBRETRANSLATE_API_KEY", "")
    if api_key:
        payload["api_key"] = api_key
    request = urllib.request.Request(
        f"{endpoint}/translate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.loads(response.read().decode("utf-8")).get("translatedText")
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        logger.warning("LibreTranslate request failed", exc_info=True)
        return None


def translate_dynamic(value, target_language=None, source_language="en"):
    """Translate database text without changing the value stored by its author."""
    if value is None:
        return ""
    text = str(value)
    target = (target_language or get_language() or settings.LANGUAGE_CODE).split("-")[0]
    source = source_language.split("-")[0]
    if not text.strip() or target == source:
        return text

    # Reuse the normal catalog when a database value is also a known UI choice.
    catalog_value = gettext(text)
    if catalog_value != text:
        return catalog_value
    if target == "sw" and text in SWAHILI_GLOSSARY:
        return SWAHILI_GLOSSARY[text]

    digest = hashlib.sha256(f"{source}:{target}:{text}".encode("utf-8")).hexdigest()
    cache_key = f"dynamic-translation:v1:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    translated = _argos_translate(text, source, target) or _libretranslate(text, source, target)
    result = translated.strip() if translated and translated.strip() else text
    cache.set(cache_key, result, timeout=60 * 60 * 24 * 30)
    return result
