"""
overlay.py - Компактное всплывающее окно быстрого автоперевода с тёмной темой,
предпросмотром в реальном времени, поддержкой перетаскивания и авто-вставкой по Enter.
"""

import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes
import time
import threading
from typing import Optional, Tuple

import pyperclip
import keyboard

from settings import settings, LANGUAGES
from translator import translator_service, TranslationResult
from database import db
from history_window import HistoryWindow

# Константы Win32
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


class TranslatorOverlay:
    """Всплывающее окно автопереводчика поверх всех окон."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.history_window = HistoryWindow(root)

        # Создаём Toplevel окно
        self.win = tk.Toplevel(root)
        self.win.withdraw()  # Скрыто по умолчанию
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#3f3f46")  # Цвет внешней рамки

        self.width = settings.get("window_width", 480)
        self.height = settings.get("window_height", 270)

        self.previous_hwnd: Optional[int] = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._debounce_job: Optional[str] = None
        self._last_req_id = 0
        self._last_translated_text = ""

        self._build_ui()
        self._bind_keys()

    def _build_ui(self) -> None:
        # Внутренний контейнер с тёмным фоном (даёт аккуратную 1px рамку снаружи)
        self.main_frame = tk.Frame(self.win, bg="#18181b", padx=1, pady=1)
        self.main_frame.pack(fill="both", expand=True, padx=1, pady=1)

        # 1. Шапка окна (Header) — перетаскиваемая
        self.header = tk.Frame(self.main_frame, bg="#202024", height=34, padx=10, pady=4)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        # Иконка и заголовок
        title_lbl = tk.Label(
            self.header,
            text="🌐 AutoTranslator",
            fg="#f4f4f5",
            bg="#202024",
            font=("Segoe UI", 9, "bold"),
            cursor="fleur"
        )
        title_lbl.pack(side="left")
        self._make_draggable(title_lbl)
        self._make_draggable(self.header)

        # Кнопка закрытия ✕
        btn_close = tk.Label(
            self.header,
            text="✕",
            fg="#a1a1aa",
            bg="#202024",
            font=("Segoe UI", 10),
            padx=8,
            cursor="hand2"
        )
        btn_close.pack(side="right")
        btn_close.bind("<Button-1>", lambda e: self.hide())
        btn_close.bind("<Enter>", lambda e: btn_close.config(fg="#ffffff", bg="#ef4444"))
        btn_close.bind("<Leave>", lambda e: btn_close.config(fg="#a1a1aa", bg="#202024"))

        # Выпадающий список выбора языка
        lang_frame = tk.Frame(self.header, bg="#202024")
        lang_frame.pack(side="right", padx=(0, 10))

        lang_lbl = tk.Label(lang_frame, text="Язык:", fg="#a1a1aa", bg="#202024", font=("Segoe UI", 8))
        lang_lbl.pack(side="left", padx=(0, 4))

        self.lang_var = tk.StringVar(value=settings.get("target_language"))
        self.lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.lang_var,
            values=settings.get_language_names(),
            state="readonly",
            width=22,
            font=("Segoe UI", 9)
        )
        self.lang_combo.pack(side="left")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        # Стилизация ttk элементов
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground="#27272a",
            background="#3f3f46",
            foreground="#f4f4f5",
            darkcolor="#27272a",
            lightcolor="#27272a",
            bordercolor="#3f3f46",
            arrowcolor="#f4f4f5"
        )
        self.win.option_add("*TCombobox*Listbox.background", "#27272a")
        self.win.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.win.option_add("*TCombobox*Listbox.selectBackground", "#2563eb")
        self.win.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.win.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

        # 2. Тело окна (Центральная зона ввода и предпросмотра)
        body = tk.Frame(self.main_frame, bg="#18181b", padx=10, pady=8)
        body.pack(fill="both", expand=True)

        # Поле ввода текста (Русский)
        input_label_row = tk.Frame(body, bg="#18181b")
        input_label_row.pack(fill="x", pady=(0, 2))
        
        lbl_in = tk.Label(input_label_row, text="🇷🇺 Ввод (русский):", fg="#a1a1aa", bg="#18181b", font=("Segoe UI", 8, "bold"))
        lbl_in.pack(side="left")

        # Текстовое поле ввода
        self.input_frame = tk.Frame(body, bg="#27272a", highlightthickness=1, highlightbackground="#3f3f46", highlightcolor="#38bdf8")
        self.input_frame.pack(fill="both", expand=True, pady=(0, 6))

        self.input_text = tk.Text(
            self.input_frame,
            height=3,
            bg="#27272a",
            fg="#f4f4f5",
            insertbackground="#38bdf8",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
            padx=8,
            pady=6
        )
        self.input_text.pack(fill="both", expand=True)

        # Полоса статуса / разделитель со стрелочкой
        status_row = tk.Frame(body, bg="#18181b")
        status_row.pack(fill="x", pady=(0, 2))

        self.status_arrow = tk.Label(status_row, text="✨ Перевод:", fg="#38bdf8", bg="#18181b", font=("Segoe UI", 8, "bold"))
        self.status_arrow.pack(side="left")

        self.status_indicator = tk.Label(status_row, text="Готов", fg="#71717a", bg="#18181b", font=("Segoe UI", 8))
        self.status_indicator.pack(side="right")

        # Поле предпросмотра перевода
        self.preview_frame = tk.Frame(body, bg="#202024", highlightthickness=1, highlightbackground="#3f3f46", highlightcolor="#2563eb")
        self.preview_frame.pack(fill="both", expand=True, pady=(0, 4))

        self.preview_text = tk.Text(
            self.preview_frame,
            height=3,
            bg="#202024",
            fg="#38bdf8",
            insertbackground="#38bdf8",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
            padx=8,
            pady=6,
            state="disabled"
        )
        self.preview_text.pack(fill="both", expand=True)

        # 3. Нижняя панель действий (Footer)
        footer = tk.Frame(self.main_frame, bg="#202024", height=36, padx=10, pady=4)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        # Подсказка по клавишам
        hint_lbl = tk.Label(
            footer,
            text="⏎ Вставить • Esc Отмена • Shift+Enter Перенос",
            fg="#71717a",
            bg="#202024",
            font=("Segoe UI", 8)
        )
        hint_lbl.pack(side="left")

        # Кнопки справа
        btn_paste = tk.Button(
            footer,
            text="⏎ Вставить",
            command=self.insert_and_close,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        btn_paste.pack(side="right", padx=(4, 0))

        btn_copy = tk.Button(
            footer,
            text="📋 Копировать",
            command=self.copy_only,
            bg="#3f3f46",
            fg="#f4f4f5",
            activebackground="#52525b",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 8),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        btn_copy.pack(side="right", padx=(4, 0))

        btn_history = tk.Button(
            footer,
            text="🕒 История",
            command=self.show_history,
            bg="#27272a",
            fg="#a1a1aa",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 8),
            padx=6,
            pady=2,
            cursor="hand2"
        )
        btn_history.pack(side="right")

    def _make_draggable(self, widget: tk.Widget) -> None:
        """Позволяет перетаскивать окно мышью за шапку."""
        def on_down(event):
            self._drag_start_x = event.x_root - self.win.winfo_x()
            self._drag_start_y = event.y_root - self.win.winfo_y()

        def on_motion(event):
            nx = event.x_root - self._drag_start_x
            ny = event.y_root - self._drag_start_y
            self.win.geometry(f"+{nx}+{ny}")

        widget.bind("<ButtonPress-1>", on_down)
        widget.bind("<B1-Motion>", on_motion)

    def _bind_keys(self) -> None:
        # Enter -> вставить и закрыть
        self.input_text.bind("<Return>", self._on_enter_pressed)
        # Shift+Enter или Ctrl+Enter -> перенос строки
        self.input_text.bind("<Shift-Return>", self._on_shift_enter)
        self.input_text.bind("<Control-Return>", lambda e: self.insert_and_close())
        # Esc -> закрыть без вставки
        self.win.bind("<Escape>", lambda e: self.hide())
        self.input_text.bind("<Escape>", lambda e: self.hide())
        # Реакция на ввод текста (debounce)
        self.input_text.bind("<KeyRelease>", self._on_key_release)
        # Ctrl+A -> выделить всё
        self.input_text.bind("<Control-a>", self._select_all)
        self.input_text.bind("<Control-A>", self._select_all)

    def _select_all(self, event=None):
        self.input_text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _on_enter_pressed(self, event):
        # Обычный Enter вставляет перевод
        self.insert_and_close()
        return "break"

    def _on_shift_enter(self, event):
        # Shift+Enter переносит строку
        self.input_text.insert(tk.INSERT, "\n")
        return "break"

    def _on_key_release(self, event):
        # Игнорируем чисто служебные клавиши
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Escape", "Caps_Lock"):
            return
        
        # Отменяем предыдущий таймер debounce
        if self._debounce_job:
            self.root.after_cancel(self._debounce_job)
        
        delay = settings.get("debounce_delay_ms", 300)
        self._debounce_job = self.root.after(delay, self._trigger_translation)

    def _on_language_changed(self, event=None):
        new_lang = self.lang_var.get()
        settings.set("target_language", new_lang)
        self._trigger_translation()

    def _trigger_translation(self) -> None:
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            self._set_preview("", status="Готов")
            self._last_translated_text = ""
            return

        self._set_status("⏳ Перевод...", color="#f59e0b")
        target_lang = self.lang_var.get()

        # Запускаем асинхронный перевод
        self._last_req_id = translator_service.translate_async(
            text=text,
            target_lang_name=target_lang,
            callback=self._on_translation_complete
        )

    def _on_translation_complete(self, result: TranslationResult, req_id: int) -> None:
        # Если пришёл результат для устаревшего запроса — отбрасываем
        if req_id != self._last_req_id:
            return

        # Планируем обновление UI в главном потоке Tkinter
        self.root.after(0, lambda: self._apply_translation_result(result))

    def _apply_translation_result(self, result: TranslationResult) -> None:
        if result.success:
            self._last_translated_text = result.text
            provider_label = f" ({result.provider})" if result.provider else ""
            self._set_preview(result.text, status=f"✓ Переведено{provider_label}", status_color="#10b981")
        else:
            if result.error_type == "network":
                self._set_status("⚠️ Нет сети", color="#ef4444")
                self._set_preview("", status="Ошибка подключения к интернету", status_color="#ef4444")
            elif result.error_type == "rate_limit":
                self._set_status("⚠️ Лимит API", color="#f97316")
                self._set_preview("", status="Лимит запросов API. Подождите пару секунд", status_color="#f97316")
            else:
                msg = result.error_message or "Ошибка перевода"
                self._set_status("⚠️ Сбой", color="#ef4444")
                self._set_preview("", status=msg[:40], status_color="#ef4444")

    def _set_preview(self, text: str, status: str = "", status_color: str = "#71717a") -> None:
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.config(state="disabled")

        if status:
            self._set_status(status, color=status_color)

    def _set_status(self, text: str, color: str = "#71717a") -> None:
        self.status_indicator.config(text=text, fg=color)

    def _get_cursor_pos(self) -> Tuple[int, int]:
        """Возвращает экранные координаты курсора мыши."""
        try:
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                if pt.x > 0 or pt.y > 0:
                    return pt.x, pt.y
        except Exception:
            pass

        # Fallback на центр экрана
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        return sw // 2, sh // 2

    def show(self) -> None:
        """Показывает окно рядом с текущим положением курсора."""
        # Сохраняем HWND активного в данный момент окна (куда будем вставлять текст)
        try:
            self.previous_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            self.previous_hwnd = None

        cur_x, cur_y = self._get_cursor_pos()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()

        # Размещаем окно чуть правее и ниже курсора
        offset_x = 12
        offset_y = 16
        pos_x = cur_x + offset_x
        pos_y = cur_y + offset_y

        # Защита от выхода за границы экрана
        if pos_x + self.width > sw - 10:
            pos_x = cur_x - self.width - offset_x
        if pos_x < 10:
            pos_x = 10

        if pos_y + self.height > sh - 50:
            pos_y = cur_y - self.height - offset_y
        if pos_y < 10:
            pos_y = 10

        self.win.geometry(f"{self.width}x{self.height}+{pos_x}+{pos_y}")

        # Сбрасываем поля
        self.input_text.delete("1.0", "end")
        self._set_preview("", status="Готов")
        self._last_translated_text = ""

        # Отображаем и захватываем фокус
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.input_text.focus_force()

    def hide(self) -> None:
        """Скрывает окно без вставки."""
        if self._debounce_job:
            self.root.after_cancel(self._debounce_job)
            self._debounce_job = None
        self.win.withdraw()

    def copy_only(self) -> None:
        """Копирует переведённый текст в буфер обмена без автоматической вставки."""
        text = self._last_translated_text.strip()
        if text:
            pyperclip.copy(text)
            self._set_status("📋 Скопировано в буфер!", color="#10b981")
            # Сохраняем в историю
            src = self.input_text.get("1.0", "end-1c").strip()
            if settings.get("save_history", True):
                db.add_entry("Russian", self.lang_var.get(), src, text)
            # Закрываем через 400 мс
            self.root.after(400, self.hide)
        else:
            self._set_status("Нечего копировать", color="#f59e0b")

    def insert_and_close(self) -> None:
        """Вставляет переведённый текст в исходное поле ввода и закрывает окно."""
        text_to_paste = self._last_translated_text.strip()
        src_text = self.input_text.get("1.0", "end-1c").strip()

        # Если пользователь не успел дождаться автоперевода или ввёл текст и сразу нажал Enter:
        if not text_to_paste and src_text:
            self._set_status("⏳ Перевод перед вставкой...", color="#f59e0b")
            res = translator_service.translate_sync(src_text, self.lang_var.get())
            if res.success and res.text:
                text_to_paste = res.text.strip()
            else:
                self._apply_translation_result(res)
                return

        if not text_to_paste:
            self.hide()
            return

        # 1. Сохраняем в историю
        if settings.get("save_history", True):
            db.add_entry("Russian", self.lang_var.get(), src_text, text_to_paste)

        # 2. Копируем в буфер обмена
        try:
            pyperclip.copy(text_to_paste)
        except Exception as e:
            print(f"[Overlay] Ошибка копирования в буфер: {e}")

        # 3. Скрываем окно переводчика
        self.hide()

        # 4. В отдельном потоке возвращаем фокус исходному окну и отправляем Ctrl+V
        prev_hwnd = self.previous_hwnd
        threading.Thread(target=self._simulate_paste, args=(prev_hwnd,), daemon=True).start()

    def _simulate_paste(self, target_hwnd: Optional[int]) -> None:
        """Возвращает фокус окну приложения и симулирует нажатие Ctrl+V."""
        time.sleep(0.08)

        # Активируем предыдущее окно
        if target_hwnd:
            try:
                ctypes.windll.user32.SetForegroundWindow(target_hwnd)
            except Exception:
                pass

        time.sleep(0.06)

        # Отправляем комбинацию Ctrl + V
        try:
            keyboard.send("ctrl+v")
        except Exception:
            # Прямая низкоуровневая отправка через Win32 API
            try:
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            except Exception as e:
                print(f"[Overlay] Ошибка симуляции Ctrl+V: {e}")

    def show_history(self) -> None:
        """Открывает окно истории переводов."""
        self.history_window.show()
