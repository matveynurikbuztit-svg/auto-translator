"""
settings.py - Управление настройками и списком языков приложения AutoTranslator.
"""

import json
import os
from typing import Dict, Any, List

# Список поддерживаемых языков с кодами для Google Translate и MyMemory
LANGUAGES: Dict[str, Dict[str, str]] = {
    "English (🇬🇧 Английский)": {
        "google": "en",
        "mymemory": "en-US",
        "code": "en",
        "name": "english"
    },
    "German (🇩🇪 Немецкий)": {
        "google": "de",
        "mymemory": "de-DE",
        "code": "de",
        "name": "german"
    },
    "French (🇫🇷 Французский)": {
        "google": "fr",
        "mymemory": "fr-FR",
        "code": "fr",
        "name": "french"
    },
    "Spanish (🇪🇸 Испанский)": {
        "google": "es",
        "mymemory": "es-ES",
        "code": "es",
        "name": "spanish"
    },
    "Italian (🇮🇹 Итальянский)": {
        "google": "it",
        "mymemory": "it-IT",
        "code": "it",
        "name": "italian"
    },
    "Chinese (🇨🇳 Китайский)": {
        "google": "zh-CN",
        "mymemory": "zh-CN",
        "code": "zh-CN",
        "name": "chinese simplified"
    },
    "Japanese (🇯🇵 Японский)": {
        "google": "ja",
        "mymemory": "ja-JP",
        "code": "ja",
        "name": "japanese"
    },
    "Turkish (🇹🇷 Турецкий)": {
        "google": "tr",
        "mymemory": "tr-TR",
        "code": "tr",
        "name": "turkish"
    },
    "Polish (🇵🇱 Польский)": {
        "google": "pl",
        "mymemory": "pl-PL",
        "code": "pl",
        "name": "polish"
    },
    "Portuguese (🇵🇹 Португальский)": {
        "google": "pt",
        "mymemory": "pt-PT",
        "code": "pt",
        "name": "portuguese"
    },
    "Arabic (🇸🇦 Арабский)": {
        "google": "ar",
        "mymemory": "ar-SA",
        "code": "ar",
        "name": "arabic"
    },
    "Russian (🇷🇺 Русский)": {
        "google": "ru",
        "mymemory": "ru-RU",
        "code": "ru",
        "name": "russian"
    }
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "target_language": "English (🇬🇧 Английский)",
    "source_language": "auto",
    "trigger_mode": "ctrl_tap",       # "ctrl_tap", "double_ctrl", "ctrl_press", "ctrl_space"
    "debounce_delay_ms": 300,
    "provider": "google",             # "google" (с авто-переходом на mymemory при 429)
    "deepl_api_key": "",
    "window_width": 480,
    "window_height": 260,
    "save_history": True,
    "auto_paste_on_enter": True,
    "theme": "dark"
}

TRIGGER_MODES: Dict[str, str] = {
    "ctrl_tap": "Одиночное нажатие Ctrl (быстрый тап)",
    "double_ctrl": "Двойное нажатие Ctrl (как в DeepL)",
    "ctrl_press": "Любое нажатие Ctrl (мгновенно)",
    "ctrl_space": "Комбинация Ctrl + Space"
}

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


class SettingsManager:
    """Менеджер сохранения и загрузки настроек приложения."""

    def __init__(self, filepath: str = SETTINGS_FILE):
        self.filepath = filepath
        self._settings = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Объединяем с дефолтными для гарантии наличия всех ключей
                    merged = dict(DEFAULT_SETTINGS)
                    merged.update(data)
                    return merged
            except Exception as e:
                print(f"[Settings] Ошибка загрузки конфига: {e}, используем значения по умолчанию.")
        return dict(DEFAULT_SETTINGS)

    def save(self) -> bool:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[Settings] Ошибка сохранения конфига: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        self._settings[key] = value
        if auto_save:
            self.save()

    def get_language_names(self) -> List[str]:
        return list(LANGUAGES.keys())

    def get_language_info(self, lang_name: str) -> Dict[str, str]:
        return LANGUAGES.get(lang_name, LANGUAGES["English (🇬🇧 Английский)"])


# Синглтон настроек для удобного доступа
settings = SettingsManager()
