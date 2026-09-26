"""
history_window.py - Окно просмотра, поиска и управления историей переводов.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pyperclip
from typing import Optional

from database import db
from settings import settings


class HistoryWindow:
    """Окно истории переводов с поиском и управлением записями."""

    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.window: Optional[tk.Toplevel] = None
        self._entries = []

    def show(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            self.refresh()
            return

        self.window = tk.Toplevel(self.parent)
        self.window.title("История переводов — AutoTranslator")
        self.window.geometry("750x520")
        self.window.minsize(600, 400)
        self.window.configure(bg="#18181b")
        self.window.attributes("-topmost", True)

        # Центрируем окно
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = max(50, (sw - 750) // 2)
        y = max(50, (sh - 520) // 2)
        self.window.geometry(f"750x520+{x}+{y}")

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        # Верхняя панель поиска
        search_frame = tk.Frame(self.window, bg="#27272a", padx=12, pady=10)
        search_frame.pack(fill="x")

        search_lbl = tk.Label(search_frame, text="🔍 Поиск:", fg="#a1a1aa", bg="#27272a", font=("Segoe UI", 10))
        search_lbl.pack(side="left", padx=(0, 8))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._on_search())
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg="#18181b",
            fg="#f4f4f5",
            insertbackground="#38bdf8",
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground="#3f3f46",
            highlightcolor="#38bdf8"
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        count_lbl = tk.Label(search_frame, text="", fg="#a1a1aa", bg="#27272a", font=("Segoe UI", 9))
        count_lbl.pack(side="right")
        self.count_lbl = count_lbl

        # Стиль для Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "History.Treeview",
            background="#1e1e24",
            foreground="#f4f4f5",
            fieldbackground="#1e1e24",
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "History.Treeview.Heading",
            background="#27272a",
            foreground="#f4f4f5",
            relief="flat",
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "History.Treeview",
            background=[("selected", "#2563eb")],
            foreground=[("selected", "#ffffff")]
        )

        # Контейнер для таблицы
        tree_frame = tk.Frame(self.window, bg="#18181b")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=8)

        columns = ("id", "time", "target", "source_text", "translated_text")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="History.Treeview",
            selectmode="browse"
        )

        self.tree.heading("id", text="ID")
        self.tree.heading("time", text="Время")
        self.tree.heading("target", text="Язык")
        self.tree.heading("source_text", text="Оригинал (Русский)")
        self.tree.heading("translated_text", text="Перевод")

        self.tree.column("id", width=45, minwidth=35, anchor="center")
        self.tree.column("time", width=125, minwidth=110)
        self.tree.column("target", width=100, minwidth=80)
        self.tree.column("source_text", width=220, minwidth=140)
        self.tree.column("translated_text", width=240, minwidth=140)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_item_select)

        # Детальный просмотр выбранной записи
        detail_frame = tk.Frame(self.window, bg="#202024", padx=12, pady=8)
        detail_frame.pack(fill="x", padx=12, pady=(0, 8))

        lbl_s = tk.Label(detail_frame, text="Оригинал:", fg="#a1a1aa", bg="#202024", font=("Segoe UI", 9, "bold"))
        lbl_s.grid(row=0, column=0, sticky="nw", padx=(0, 6), pady=2)
        self.detail_src = tk.Label(detail_frame, text="—", fg="#e4e4e7", bg="#202024", font=("Segoe UI", 9), anchor="w", justify="left", wraplength=650)
        self.detail_src.grid(row=0, column=1, sticky="w", pady=2)

        lbl_t = tk.Label(detail_frame, text="Перевод:", fg="#38bdf8", bg="#202024", font=("Segoe UI", 9, "bold"))
        lbl_t.grid(row=1, column=0, sticky="nw", padx=(0, 6), pady=2)
        self.detail_trg = tk.Label(detail_frame, text="—", fg="#38bdf8", bg="#202024", font=("Segoe UI", 9), anchor="w", justify="left", wraplength=650)
        self.detail_trg.grid(row=1, column=1, sticky="w", pady=2)

        # Нижняя панель действий
        bottom_frame = tk.Frame(self.window, bg="#18181b", padx=12, pady=10)
        bottom_frame.pack(fill="x")

        btn_copy = tk.Button(
            bottom_frame,
            text="📋 Копировать перевод",
            command=self._copy_translation,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            cursor="hand2"
        )
        btn_copy.pack(side="left", padx=(0, 8))

        btn_delete = tk.Button(
            bottom_frame,
            text="🗑 Удалить запись",
            command=self._delete_selected,
            bg="#3f3f46",
            fg="#f4f4f5",
            activebackground="#ef4444",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
            cursor="hand2"
        )
        btn_delete.pack(side="left", padx=(0, 8))

        btn_clear = tk.Button(
            bottom_frame,
            text="🧹 Очистить всё",
            command=self._clear_all,
            bg="#3f3f46",
            fg="#f4f4f5",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=4,
            cursor="hand2"
        )
        btn_clear.pack(side="left", padx=(0, 8))

        btn_close = tk.Button(
            bottom_frame,
            text="Закрыть",
            command=self.window.destroy,
            bg="#27272a",
            fg="#a1a1aa",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=4,
            cursor="hand2"
        )
        btn_close.pack(side="right")

    def refresh(self) -> None:
        """Перезагружает записи из базы данных."""
        q = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        if q:
            self._entries = db.search(q, limit=150)
        else:
            self._entries = db.get_recent(limit=150)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in self._entries:
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["id"],
                    row["created_at"],
                    row["target_lang"],
                    row["source_text"][:60].replace("\n", " "),
                    row["translated_text"][:60].replace("\n", " ")
                )
            )

        total = db.count()
        shown = len(self._entries)
        self.count_lbl.config(text=f"Показано: {shown} из {total}")
        self.detail_src.config(text="—")
        self.detail_trg.config(text="—")

    def _on_search(self) -> None:
        self.refresh()

    def _on_item_select(self, event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        entry_id = int(selected[0])
        entry = next((e for e in self._entries if e["id"] == entry_id), None)
        if entry:
            self.detail_src.config(text=entry["source_text"])
            self.detail_trg.config(text=entry["translated_text"])

    def _copy_translation(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("История", "Выберите запись для копирования.")
            return
        entry_id = int(selected[0])
        entry = next((e for e in self._entries if e["id"] == entry_id), None)
        if entry:
            pyperclip.copy(entry["translated_text"])

    def _delete_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        entry_id = int(selected[0])
        if db.delete_entry(entry_id):
            self.refresh()

    def _clear_all(self) -> None:
        if messagebox.askyesno("Очистка истории", "Вы действительно хотите удалить ВСЮ историю переводов?"):
            db.clear_all()
            self.refresh()
