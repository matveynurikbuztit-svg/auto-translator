"""
database.py - Управление локальной историей переводов в базе данных SQLite (history.db).
"""

import sqlite3
import os
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")


class HistoryDatabase:
    """Потокобезопасная обёртка для работы с базой SQLite."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Создаёт структуру таблиц, если они ещё не существуют."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS translations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        source_lang TEXT NOT NULL,
                        target_lang TEXT NOT NULL,
                        source_text TEXT NOT NULL,
                        translated_text TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_translations_created 
                    ON translations(created_at DESC)
                """)
                conn.commit()

    def add_entry(self, source_lang: str, target_lang: str, source_text: str, translated_text: str) -> Optional[int]:
        """Добавляет запись перевода в историю."""
        if not source_text or not translated_text:
            return None
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO translations (created_at, source_lang, target_lang, source_text, translated_text)
                        VALUES (?, ?, ?, ?, ?)
                    """, (now, source_lang, target_lang, source_text.strip(), translated_text.strip()))
                    conn.commit()
                    return cursor.lastrowid
            except Exception as e:
                print(f"[Database] Ошибка добавления записи в историю: {e}")
                return None

    def get_recent(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Возвращает список последних переводов."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, created_at, source_lang, target_lang, source_text, translated_text
                        FROM translations
                        ORDER BY id DESC
                        LIMIT ? OFFSET ?
                    """, (limit, offset))
                    return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"[Database] Ошибка получения истории: {e}")
                return []

    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Ищет записи в истории по исходному или переведённому тексту."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    q = f"%{query}%"
                    cursor.execute("""
                        SELECT id, created_at, source_lang, target_lang, source_text, translated_text
                        FROM translations
                        WHERE source_text LIKE ? OR translated_text LIKE ?
                        ORDER BY id DESC
                        LIMIT ?
                    """, (q, q, limit))
                    return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"[Database] Ошибка поиска в истории: {e}")
                return []

    def delete_entry(self, entry_id: int) -> bool:
        """Удаляет запись по id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM translations WHERE id = ?", (entry_id,))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                print(f"[Database] Ошибка удаления записи {entry_id}: {e}")
                return False

    def clear_all(self) -> bool:
        """Очищает всю историю переводов."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM translations")
                    conn.commit()
                    return True
            except Exception as e:
                print(f"[Database] Ошибка очистки истории: {e}")
                return False

    def count(self) -> int:
        """Возвращает общее количество записей."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM translations")
                    res = cursor.fetchone()
                    return res[0] if res else 0
            except Exception as e:
                print(f"[Database] Ошибка подсчёта записей: {e}")
                return 0


# Экземпляр базы данных
db = HistoryDatabase()
