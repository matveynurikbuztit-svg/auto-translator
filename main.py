"""
main.py - Точка входа в приложение AutoTranslator.
Фоновый слушатель хоткеев (клавиша Ctrl), системный трей (pystray) и интеграция с Tkinter.
"""

import sys
import os
import time
import threading
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as item, Menu
from pynput import keyboard as pk

from settings import settings, TRIGGER_MODES
from overlay import TranslatorOverlay


def create_tray_image() -> Image.Image:
    """Генерирует аккуратную минималистичную иконку переводчика для трея."""
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Синий скругленный квадрат
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill="#2563eb", outline="#60a5fa", width=2)
    
    # Стилизованная буква 'T' и акцентный символ перевода
    # Горизонтальная перекладина T
    draw.rectangle((16, 16, 48, 22), fill="#ffffff")
    # Вертикальная стойка T
    draw.rectangle((29, 22, 35, 48), fill="#ffffff")
    # Маленькая точка-акцент (символ глобальности)
    draw.ellipse((42, 38, 48, 44), fill="#38bdf8")
    return img


class GlobalHotkeyManager:
    """Глобальный перехватчик клавиш для вызова всплывающего окна."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self._ctrl_pressed = False
        self._ctrl_press_time = 0.0
        self._has_other_key = False
        self._last_tap_time = 0.0
        self._listener: Optional[pk.Listener] = None

    def _is_ctrl(self, key) -> bool:
        return key in (pk.Key.ctrl, pk.Key.ctrl_l, pk.Key.ctrl_r)

    def on_press(self, key) -> None:
        mode = settings.get("trigger_mode", "ctrl_tap")

        if self._is_ctrl(key):
            if not self._ctrl_pressed:
                self._ctrl_pressed = True
                self._ctrl_press_time = time.time()
                self._has_other_key = False

                # Мгновенный вызов по нажатию (если включен режим)
                if mode == "ctrl_press":
                    self.on_trigger()
        else:
            if self._ctrl_pressed:
                self._has_other_key = True
                # Если режим Ctrl+Space и нажат пробел
                if mode == "ctrl_space" and key == pk.Key.space:
                    self.on_trigger()

    def on_release(self, key) -> None:
        mode = settings.get("trigger_mode", "ctrl_tap")

        if self._is_ctrl(key):
            now = time.time()
            duration = now - self._ctrl_press_time
            had_other = self._has_other_key
            self._ctrl_pressed = False

            # Если была нажата и отпущена ТОЛЬКО клавиша Ctrl (без других клавиш)
            if not had_other and duration < 0.45:
                if mode == "ctrl_tap":
                    # Одиночный быстрый тап по Ctrl
                    self.on_trigger()
                elif mode == "double_ctrl":
                    # Двойной тап по Ctrl (интервал < 350мс)
                    if (now - self._last_tap_time) < 0.35:
                        self.on_trigger()
                        self._last_tap_time = 0.0
                    else:
                        self._last_tap_time = now

    def start(self) -> None:
        """Запуск слушателя клавиатуры в фоновом потоке."""
        self._listener = pk.Listener(on_press=self.on_press, on_release=self.on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Остановка слушателя."""
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass


class AutoTranslatorApp:
    """Главный класс приложения AutoTranslator."""

    def __init__(self):
        # Корневой скрытый инстанс Tkinter
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("AutoTranslator Service")

        # Окно оверлея
        self.overlay = TranslatorOverlay(self.root)

        # Менеджер горячих клавиш
        self.hotkey_mgr = GlobalHotkeyManager(on_trigger=self.trigger_show)

        # Трей
        self.tray_icon: Optional[pystray.Icon] = None

    def trigger_show(self) -> None:
        """Безопасный вызов оверлея в главном UI-потоке Tkinter."""
        self.root.after(0, self._do_show_overlay)

    def _do_show_overlay(self) -> None:
        # Если окно уже показано, просто переводим фокус
        if self.overlay.win.winfo_viewable():
            self.overlay.input_text.focus_force()
        else:
            self.overlay.show()

    def show_overlay_action(self, icon=None, item=None) -> None:
        self.trigger_show()

    def show_history_action(self, icon=None, item=None) -> None:
        self.root.after(0, self.overlay.show_history)

    def set_trigger_mode(self, mode: str) -> None:
        settings.set("trigger_mode", mode)

    def get_trigger_mode(self) -> str:
        return settings.get("trigger_mode", "ctrl_tap")

    def set_target_language(self, lang_name: str) -> None:
        settings.set("target_language", lang_name)
        self.overlay.lang_var.set(lang_name)

    def get_target_language(self) -> str:
        return settings.get("target_language", "English (🇬🇧 Английский)")

    def _build_tray_menu(self) -> Menu:
        # Подменю режимов активации
        mode_items = []
        for mode_key, mode_title in TRIGGER_MODES.items():
            mode_items.append(item(
                mode_title,
                (lambda m: lambda icon, it: self.set_trigger_mode(m))(mode_key),
                checked=(lambda m: lambda it: self.get_trigger_mode() == m)(mode_key),
                radio=True
            ))

        # Подменю целевых языков
        lang_items = []
        for lang_name in settings.get_language_names():
            lang_items.append(item(
                lang_name,
                (lambda l: lambda icon, it: self.set_target_language(l))(lang_name),
                checked=(lambda l: lambda it: self.get_target_language() == l)(lang_name),
                radio=True
            ))

        return Menu(
            item("🌐 Открыть переводчик (Ctrl)", self.show_overlay_action, default=True),
            item("🕒 История переводов", self.show_history_action),
            Menu.SEPARATOR,
            item("⚙️ Режим вызова (Хоткей)", Menu(*mode_items)),
            item("🌐 Язык перевода", Menu(*lang_items)),
            Menu.SEPARATOR,
            item("❌ Выход", self.quit)
        )

    def start_tray(self) -> None:
        """Запускает иконку в трее в фоновом потоке."""
        image = create_tray_image()
        menu = self._build_tray_menu()
        self.tray_icon = pystray.Icon("AutoTranslator", image, "AutoTranslator (Нажмите Ctrl в поле ввода)", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def quit(self, icon=None, item=None) -> None:
        """Корректное завершение приложения."""
        print("[AutoTranslator] Завершение работы...")
        self.hotkey_mgr.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def run(self) -> None:
        """Запуск слушателя хоткеев, трея и главного цикла Tkinter."""
        print("=" * 60)
        print(" AutoTranslator запущен в фоновом режиме")
        print(" Установите курсор в любое поле ввода и нажмите Ctrl")
        print(" Иконка приложения доступна в системном трее Windows")
        print("=" * 60)

        # Запуск фонового слушателя клавиатуры
        self.hotkey_mgr.start()

        # Запуск системного трея
        self.start_tray()

        # Запуск главного цикла Tkinter
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


if __name__ == "__main__":
    app = AutoTranslatorApp()
    app.run()
