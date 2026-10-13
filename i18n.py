import json
import os

DEFAULT_LANG = "fr"
SUPPORTED_LANGS = ["fr", "en", "ar", "pt", "es"]

TRANSLATIONS = {}

for lang in SUPPORTED_LANGS:
    path = f"locales/{lang}.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            TRANSLATIONS[lang] = json.load(f)


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Traduit une clé dans la langue donnée, avec fallback FR."""
    lang = lang if lang in TRANSLATIONS else DEFAULT_LANG
    text = (
        TRANSLATIONS.get(lang, {}).get(key)
        or TRANSLATIONS.get(DEFAULT_LANG, {}).get(key)
        or key
    )
    return text.format(**kwargs) if kwargs else text


def get_user_lang(update) -> str:
    """Détecte la langue via Telegram language_code."""
    if not update.effective_user:
        return DEFAULT_LANG
    code = (update.effective_user.language_code or DEFAULT_LANG)[:2]
    return code if code in TRANSLATIONS else DEFAULT_LANG
