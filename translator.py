"""
translator.py - Модуль перевода на базе deep-translator с поддержкой GoogleTranslator,
автоматическим отказоустойчивым переключением (fallback на MyMemory), кэшированием
и асинхронной обработкой.
"""

import threading
import time
from typing import Dict, Any, Optional, Callable
from collections import OrderedDict

from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TooManyRequests, LanguageNotSupportedException, RequestError
import requests

from settings import LANGUAGES, settings


class TranslationResult:
    """Результат операции перевода."""
    def __init__(
        self,
        success: bool,
        text: str = "",
        provider: str = "",
        error_type: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.text = text
        self.provider = provider
        self.error_type = error_type          # 'network', 'rate_limit', 'empty', 'error'
        self.error_message = error_message

    def __repr__(self) -> str:
        return f"<TranslationResult success={self.success} text='{self.text[:30]}' error={self.error_type}>"


class TranslatorService:
    """Сервис перевода с кэшированием, защитой от сбоев и асинхронным выполнением."""

    def __init__(self, cache_size: int = 256):
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self._cache_lock = threading.Lock()
        self._current_request_id = 0
        self._req_lock = threading.Lock()

    def _get_cache(self, key: tuple) -> Optional[TranslationResult]:
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _set_cache(self, key: tuple, result: TranslationResult) -> None:
        with self._cache_lock:
            self._cache[key] = result
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def translate_sync(self, text: str, target_lang_name: str) -> TranslationResult:
        """Синхронный перевод с цепочкой провайдеров и обработкой ошибок."""
        stripped = text.strip()
        if not stripped:
            return TranslationResult(success=True, text="", error_type="empty")

        lang_info = LANGUAGES.get(target_lang_name, LANGUAGES["English (🇬🇧 Английский)"])
        google_code = lang_info.get("google", "en")
        mymemory_code = lang_info.get("mymemory", "en-US")
        cache_key = (stripped, google_code)

        cached = self._get_cache(cache_key)
        if cached:
            return cached

        preferred_provider = settings.get("provider", "google")
        deepl_key = settings.get("deepl_api_key", "").strip()

        # 1. Попытка через GoogleTranslator
        if preferred_provider == "google":
            try:
                translator = GoogleTranslator(source="auto", target=google_code)
                translated = translator.translate(stripped)
                if translated:
                    res = TranslationResult(success=True, text=translated, provider="Google")
                    self._set_cache(cache_key, res)
                    return res
            except TooManyRequests:
                print("[Translator] GoogleTranslator вернул 429 TooManyRequests. Переключаемся на MyMemory fallback.")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                return TranslationResult(
                    success=False,
                    error_type="network",
                    error_message="Нет подключения к интернету."
                )
            except Exception as e:
                print(f"[Translator] Ошибка GoogleTranslator ({e}). Пробуем запасной провайдер.")

        # 2. Запасной провайдер: MyMemoryTranslator
        try:
            # MyMemory поддерживает языковые имена ("russian" -> "english") или локали ("ru-RU" -> "en-US")
            mm_translator = MyMemoryTranslator(source="ru-RU", target=mymemory_code)
            translated = mm_translator.translate(stripped)
            if translated:
                res = TranslationResult(success=True, text=translated, provider="MyMemory")
                self._set_cache(cache_key, res)
                return res
        except TooManyRequests:
            return TranslationResult(
                success=False,
                error_type="rate_limit",
                error_message="Превышен лимит запросов API. Попробуйте через несколько секунд."
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return TranslationResult(
                success=False,
                error_type="network",
                error_message="Нет подключения к интернету."
            )
        except Exception as e:
            err_str = str(e)
            print(f"[Translator] Ошибка MyMemory ({err_str}).")
            if "quota" in err_str.lower() or "limit" in err_str.lower():
                return TranslationResult(
                    success=False,
                    error_type="rate_limit",
                    error_message="Лимит запросов API исчерпан."
                )
            return TranslationResult(
                success=False,
                error_type="error",
                error_message=f"Ошибка перевода: {err_str[:60]}"
            )

        return TranslationResult(
            success=False,
            error_type="error",
            error_message="Не удалось перевести текст."
        )

    def translate_async(
        self,
        text: str,
        target_lang_name: str,
        callback: Callable[[TranslationResult, int], None]
    ) -> int:
        """
        Асинхронный перевод. Принимает callback(result, request_id).
        Возвращает request_id, позволяющий вызывающей стороне отбрасывать устаревшие результаты.
        """
        with self._req_lock:
            self._current_request_id += 1
            req_id = self._current_request_id

        def _worker():
            res = self.translate_sync(text, target_lang_name)
            # Вызываем callback с результатом и идентификатором запроса
            callback(res, req_id)

        threading.Thread(target=_worker, daemon=True).start()
        return req_id


# Синглтон переводчика
translator_service = TranslatorService()
