import uuid
import winsound
import time
import threading
import pyaudio
import wave
import sys
import logging
import re
import platform
import subprocess
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
import shutil
import io
import base64
import os
import json
from tkinter import (
    Canvas,
    ttk,
    messagebox,
    simpledialog,
    filedialog,
    colorchooser,
    scrolledtext,
)
import tkinter as tk
import webbrowser

try:
    import pyperclip
except ImportError:
    pyperclip = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("notes_app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

try:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = self.y = 0

    def show_tip(self):
        self.x, self.y, _, _ = self.widget.bbox("insert")
        self.x += self.widget.winfo_rootx() + 25
        self.y += self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{self.x}+{self.y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide_tip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

    def schedule_show(self):
        self.unschedule()
        self.id = self.widget.after(500, self.show_tip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def bind_events(self):
        self.widget.bind("<Enter>", lambda e: self.schedule_show())
        self.widget.bind("<Leave>", lambda e: (
            self.unschedule(), self.hide_tip()))
        self.widget.bind("<ButtonPress>", lambda e: self.hide_tip())


class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio = pyaudio.PyAudio()
        self.stream = None

    def start_recording(self):
        self.recording = True
        self.frames = []
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,
            input=True,
            frames_per_buffer=1024,
        )
        threading.Thread(target=self._record).start()

    def _record(self):
        while self.recording:
            data = self.stream.read(1024)
            self.frames.append(data)

    def stop_recording(self):
        self.recording = False
        self.stream.stop_stream()
        self.stream.close()
        return self.frames

    def save_recording(self, filename):
        wf = wave.open(filename, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b"".join(self.frames))
        wf.close()


class NotesApp:
    def __init__(self):
        self.root = tk.Tk()
        self._init_colors()
        self._setup_main_window()
        self._setup_data()
        self.sort_mapping = {
            "По дате изменения (убыв.)": "по_дате_изменения_убыв",
            "По дате изменения (возр.)": "по_дате_изменения_возр",
            "По заголовку (А-Я)": "по_заголовку_а_я",
            "По заголовку (Я-А)": "по_заголовку_я_а",
            "По дате создания (убыв.)": "по_дате_создания_убыв",
            "По дате создания (возр.)": "по_дате_создания_возр",
        }
        self.tables = {}
        self.table_frames = {}
        self._initialize_ui()
        self._setup_autosave()
        self._bind_events()
        self.current_images = []
        self.image_cache = {}
        self.editing_image = None
        self.edit_mode = None
        self.recorder = AudioRecorder()
        self.color_tags = {}
        logger.info("Приложение инициализировано")

    def _init_colors(self):
        self.colors = {
            "bg": "#f8f9fa",
            "sidebar": "#e9ecef",
            "primary": "#007bff",
            "secondary": "#6c757d",
            "success": "#28a745",
            "danger": "#dc3545",
            "text": "#343a40",
            "text_light": "#6c757d",
            "white": "#ffffff",
            "border": "#dee2e6",
            "info": "#17a2b8",
            "toolbar": "#e2e6ea",
            "highlight": "#ffc107",
        }

    def _setup_main_window(self):
        self.root.title("Мои заметки")
        self.root.geometry("1200x800")
        self.root.minsize(800, 700)
        self.root.configure(bg=self.colors["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_data(self):
        self.notes_file = "notes.json"
        self.settings_file = "settings.json"
        self.attachments_base_dir = "attachments"
        self.notes = self._load_data()
        self.current_note = None
        self.search_var = tk.StringVar()
        self.autosave_timer = None
        self.clipboard_content = None
        self.autosave_interval = self._load_settings().get("autosave_interval", 10000)
        self.reminder_check_active = True

        if not os.path.exists(self.attachments_base_dir):
            os.makedirs(self.attachments_base_dir)
        logger.info("Данные приложения инициализированы")

    def _get_note_attachments_dir(self, note_id: str) -> str:
        return os.path.join(self.attachments_base_dir, f"note_{note_id}")

    def _ensure_note_attachments_dir(self, note_id: str) -> str:
        note_dir = self._get_note_attachments_dir(note_id)
        if not os.path.exists(note_dir):
            os.makedirs(note_dir)
            logger.info(f"Создана директория для вложений: {note_dir}")
        return note_dir

    def _initialize_ui(self):
        self._setup_styles()
        self._create_header()
        self._create_main_interface()
        self._setup_editor_bindings()
        self._load_notes_list()
        self._setup_file_link_tags()
        logger.info("Пользовательский интерфейс инициализирован")

    def _setup_file_link_tags(self):
        self.text_area.tag_configure(
            "file_link", foreground="blue", underline=1)
        self.text_area.tag_bind(
            "file_link", "<Double-Button-1>", self._on_file_link_click
        )
        self.text_area.tag_configure(
            "hyperlink", foreground="blue", underline=1)
        self.text_area.tag_bind(
            "hyperlink", "<Button-1>", self._on_hyperlink_click)
        self.text_area.tag_bind(
            "hyperlink", "<Enter>", lambda e: self.text_area.config(
                cursor="hand2")
        )
        self.text_area.tag_bind(
            "hyperlink", "<Leave>", lambda e: self.text_area.config(cursor="")
        )

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 10))
        for color in ["Primary", "Success", "Danger"]:
            style.configure(
                f"{color}.TButton",
                background=self.colors[color.lower()],
                foreground="white",
            )
        style.configure(
            "CustomPrimary.TButton",
            background=self.colors["primary"],
            foreground="black",
        )
        style.configure(
            "Help.TButton",
            background=self.colors["info"],
            foreground=self.colors["text"],
        )
        style.configure(
            "Tool.TButton",
            background=self.colors["toolbar"],
            foreground=self.colors["text"],
            borderwidth=1,
            relief="raised",
        )
        style.map(
            "Tool.TButton",
            background=[
                ("active", self.colors["border"]),
                ("pressed", self.colors["secondary"]),
            ],
            relief=[("pressed", "sunken"), ("active", "raised")],
        )
        style.configure("ActiveTool.TButton",
                        background="Gray", foreground="black")

    def _load_settings(self) -> Dict[str, Any]:
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                return {}
        return {}

    def _save_settings(self):
        try:
            settings = {"autosave_interval": self.autosave_interval}
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info("Настройки сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось сохранить настройки: {str(e)}")

    def _create_header(self):
        header = tk.Frame(self.root, bg=self.colors["white"], height=60)
        header.pack(fill=tk.X, padx=10, pady=5)
        buttons = [
            ("➕", "primary", self.create_note, "Создать (Ctrl+N)"),
            ("💾", "success", self.save_current_note, "Сохранить (Ctrl+S)"),
            ("🗑️", "danger", self.delete_current_note, "Удалить (Del)"),
            ("📎", "info", self.attach_file, "Прикрепить файл (Ctrl+O)"),
            ("🔊", "info", self.record_audio, "Записать аудио (Ctrl+R)"),
            ("📤", "primary", self.export_note, "Экспорт заметки"),
            ("📥", "primary", self.import_note, "Импорт заметки"),
            ("⏰", "info", self.set_reminder, "Установить напоминание"),
            ("🔗", "info", self.insert_link, "Вставить ссылку"),
        ]
        for text, color, command, tooltip in buttons:
            btn = ttk.Button(
                header, text=text, command=command, style=f"{color}.TButton", width=3
            )
            btn.pack(side=tk.LEFT, padx=5)
            ToolTip(btn, tooltip).bind_events()
        settings_btn = ttk.Button(
            header,
            text="⚙️",
            command=self.show_autosave_settings,
            style="Help.TButton",
            width=3,
        )
        settings_btn.pack(side=tk.RIGHT, padx=5)
        ToolTip(settings_btn, "Настройки автосохранения").bind_events()
        help_btn = ttk.Button(
            header, text="❓", command=self.show_help, style="Help.TButton", width=3
        )
        help_btn.pack(side=tk.RIGHT, padx=5)
        ToolTip(help_btn, "Помощь (F1)").bind_events()

    def _create_main_interface(self):
        main_frame = tk.Frame(self.root, bg=self.colors["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self._create_sidebar(main_frame)
        self._create_editor(main_frame)

    def _create_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=self.colors["sidebar"], width=300)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)
        title_label = tk.Label(
            sidebar,
            text="📝 Мои Заметки",
            font=("Segoe UI", 16, "bold"),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        )
        title_label.pack(pady=20)
        search_frame = tk.Frame(sidebar, bg=self.colors["sidebar"])
        search_frame.pack(fill=tk.X, padx=20, pady=10)
        search_label = tk.Label(
            search_frame,
            text="🔍 Поиск (Ctrl+F):",
            font=("Segoe UI", 10),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        )
        search_label.pack(anchor=tk.W)
        self.search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var, font=("Segoe UI", 10)
        )
        self.search_entry.pack(fill=tk.X, pady=(5, 0))
        self.search_var.trace("w", lambda *_: self._load_notes_list())
        self.search_content_var = tk.BooleanVar(value=True)
        search_content_cb = ttk.Checkbutton(
            search_frame,
            text="Искать в содержимом",
            variable=self.search_content_var,
            command=self._load_notes_list,
        )
        search_content_cb.pack(anchor=tk.W, pady=(5, 0))
        sort_frame = tk.Frame(sidebar, bg=self.colors["sidebar"])
        sort_frame.pack(fill=tk.X, padx=20, pady=(5, 0))
        sort_label = tk.Label(
            sort_frame,
            text="Сортировка:",
            font=("Segoe UI", 10),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        )
        sort_label.pack(anchor=tk.W)
        self.sort_var = tk.StringVar(value="по_дате_изменения_убыв")
        sort_options = [
            ("По дате изменения (убыв.)", "по_дате_изменения_убыв"),
            ("По дате изменения (возр.)", "по_дате_изменения_возр"),
            ("По заголовку (А-Я)", "по_заголовку_а_я"),
            ("По заголовку (Я-А)", "по_заголовку_я_а"),
            ("По дате создания (убыв.)", "по_дате_создания_убыв"),
            ("По дате создания (возр.)", "по_дате_создания_возр"),
        ]
        sort_menu = ttk.Combobox(
            sort_frame,
            textvariable=self.sort_var,
            values=[opt[1] for opt in sort_options],
            state="readonly",
            font=("Segoe UI", 10),
        )
        sort_menu["values"] = [opt[0] for opt in sort_options]
        sort_menu.pack(fill=tk.X, pady=(5, 0))
        sort_menu.bind("<<ComboboxSelected>>",
                       lambda e: self._load_notes_list())
        notes_frame = tk.Frame(sidebar, bg=self.colors["sidebar"])
        notes_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        scrollbar = tk.Scrollbar(notes_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.notes_listbox = tk.Listbox(
            notes_frame,
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 10),
            bg="white",
            selectbackground=self.colors["primary"],
            selectforeground="white",
            height=20,
        )
        self.notes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.notes_listbox.yview)
        self._setup_listbox_bindings()

    def _setup_listbox_bindings(self):
        bindings = [
            ("<<ListboxSelect>>", self.select_note),
            ("<Delete>", self.delete_selected_note),
            ("<BackSpace>", self.delete_selected_note),
            ("<Button-3>", self.show_context_menu),
            ("<Return>", self.select_note),
            ("<Double-Button-1>", self.select_note),
        ]
        for sequence, handler in bindings:
            self.notes_listbox.bind(sequence, handler)

    def _create_editor(self, parent):
        editor = tk.Frame(
            parent, bg=self.colors["white"], relief="raised", bd=1)
        editor.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.empty_label = tk.Label(
            editor,
            text="📝 Выберите заметку или создайте новую\n\nГорячие клавиши:\nCtrl+N - Новая\nCtrl+S - Сохранить\nCtrl+F - Поиск\nCtrl+V - Вставить\nF1 - Помощь",
            font=("Segoe UI", 12),
            bg=self.colors["white"],
            fg=self.colors["text_light"],
        )
        self.empty_label.pack(expand=True)
        self.editor_frame = tk.Frame(editor, bg=self.colors["white"])
        self._create_attachments_section(self.editor_frame)
        self._create_title_field(self.editor_frame)
        self._create_content_field(self.editor_frame)
        self._create_info_label(self.editor_frame)

    def _create_title_field(self, parent):
        self.title_frame = tk.Frame(parent, bg=self.colors["white"])
        self.title_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        title_label = tk.Label(
            self.title_frame,
            text="Заголовок:",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["white"],
            fg=self.colors["text"],
        )
        title_label.pack(anchor=tk.W)
        self.title_entry = tk.Text(
            self.title_frame,
            font=("Segoe UI", 14, "bold"),
            height=1,
            wrap=tk.WORD,
            relief="solid",
            bd=1,
            undo=True,
            fg="black",
        )
        self.title_entry.pack(fill=tk.X, pady=(5, 0))
        self._setup_placeholder(self.title_entry, "Введите заголовок...")

    def _create_content_field(self, parent):
        content_frame = tk.Frame(parent, bg=self.colors["white"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        content_label = tk.Label(
            content_frame,
            text="Содержимое:",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["white"],
            fg=self.colors["text"],
        )
        content_label.pack(anchor=tk.W)
        self.toolbar_frame = tk.Frame(
            content_frame, bg=self.colors["toolbar"], height=30
        )
        self.toolbar_frame.pack(fill=tk.X, pady=(0, 5))
        self.bold_btn = ttk.Button(
            self.toolbar_frame,
            text="Ж",
            width=2,
            command=self.toggle_bold,
            style="Tool.TButton",
        )
        self.bold_btn.pack(side=tk.LEFT, padx=2)
        self.italic_btn = ttk.Button(
            self.toolbar_frame,
            text="К",
            width=2,
            command=self.toggle_italic,
            style="Tool.TButton",
        )
        self.italic_btn.pack(side=tk.LEFT, padx=2)
        self.underline_btn = ttk.Button(
            self.toolbar_frame,
            text="Ч",
            width=2,
            command=self.toggle_underline,
            style="Tool.TButton",
        )
        self.underline_btn.pack(side=tk.LEFT, padx=2)
        self.bullet_list_btn = ttk.Button(
            self.toolbar_frame,
            text="•",
            width=2,
            command=lambda: self.insert_list("bullet"),
            style="Tool.TButton",
        )
        self.bullet_list_btn.pack(side=tk.LEFT, padx=2)
        self.numbered_list_btn = ttk.Button(
            self.toolbar_frame,
            text="1.",
            width=2,
            command=lambda: self.insert_list("numbered"),
            style="Tool.TButton",
        )
        self.numbered_list_btn.pack(side=tk.LEFT, padx=2)
        self.color_btn = ttk.Button(
            self.toolbar_frame,
            text="🎨",
            width=2,
            command=self.change_text_color,
            style="Tool.TButton",
        )
        self.color_btn.pack(side=tk.LEFT, padx=2)
        self.font_size = tk.StringVar(value="11")
        size_menu = ttk.Combobox(
            self.toolbar_frame,
            textvariable=self.font_size,
            values=["8", "9", "10", "11", "12",
                    "14", "16", "18", "20", "22", "24"],
            width=3,
            state="readonly",
        )
        size_menu.pack(side=tk.LEFT, padx=2)
        size_menu.bind("<<ComboboxSelected>>", self.change_font_size)
        self.table_btn = ttk.Button(
            self.toolbar_frame,
            text="▦",
            width=2,
            command=self.insert_table,
            style="Tool.TButton",
        )
        self.table_btn.pack(side=tk.LEFT, padx=2)
        ttk.Separator(self.toolbar_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, padx=5, fill=tk.Y
        )
        self.undo_btn = ttk.Button(
            self.toolbar_frame,
            text="↩",
            width=2,
            command=self.undo_action,
            style="Tool.TButton",
        )
        self.undo_btn.pack(side=tk.LEFT, padx=2)
        self.redo_btn = ttk.Button(
            self.toolbar_frame,
            text="↪",
            width=2,
            command=self.redo_action,
            style="Tool.TButton",
        )
        self.redo_btn.pack(side=tk.LEFT, padx=2)
        text_frame = tk.Frame(content_frame, bg=self.colors["white"])
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area = tk.Text(
            text_frame,
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 11),
            wrap=tk.WORD,
            relief="solid",
            bd=1,
            undo=True,
            fg="black",
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text_area.yview)
        self.text_area.bind("<Double-1>", self._on_double_click)
        self.text_area.tag_configure("bold", font=("Segoe UI", 11, "bold"))
        self.text_area.tag_configure("italic", font=("Segoe UI", 11, "italic"))
        self.text_area.tag_configure(
            "underline", font=("Segoe UI", 11, "underline"))
        self.text_area.tag_configure("red", foreground="red")
        self.text_area.tag_configure("blue", foreground="blue")
        self.text_area.tag_configure("green", foreground="green")
        self.text_area.tag_configure("highlight", background="yellow")
        self._setup_font_size_tags()
        self.text_area.bind("<ButtonRelease-1>", self._update_button_states)
        self.text_area.bind("<KeyRelease>", self._update_button_states)

    def _create_attachments_section(self, parent):
        self.attachments_frame = tk.Frame(parent, bg=self.colors["white"])
        attachments_label = tk.Label(
            self.attachments_frame,
            text="Вложения:",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["white"],
            fg=self.colors["text"],
        )
        attachments_label.pack(anchor=tk.W)
        container = tk.Frame(self.attachments_frame, bg=self.colors["white"])
        container.pack(fill=tk.X, expand=True)
        scrollbar_v = tk.Scrollbar(container, orient=tk.VERTICAL)
        scrollbar_h = tk.Scrollbar(container, orient=tk.HORIZONTAL)
        self.attachments_canvas = tk.Canvas(
            container,
            bg=self.colors["white"],
            highlightthickness=0,
            yscrollcommand=scrollbar_v.set,
            xscrollcommand=scrollbar_h.set,
            height=100,
        )
        scrollbar_v.config(command=self.attachments_canvas.yview)
        scrollbar_h.config(command=self.attachments_canvas.xview)
        self.attachments_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_v.grid(row=0, column=1, sticky="ns")
        scrollbar_h.grid(row=1, column=0, sticky="ew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.attachments_content = tk.Frame(
            self.attachments_canvas, bg=self.colors["white"]
        )
        self.attachments_canvas.create_window(
            (0, 0), window=self.attachments_content, anchor="nw", tags="content_frame"
        )
        self.attachments_content.bind(
            "<Configure>",
            lambda e: self.attachments_canvas.configure(
                scrollregion=self.attachments_canvas.bbox("all")
            ),
        )

    def _create_info_label(self, parent):
        self.info_label = tk.Label(
            parent,
            text="",
            font=("Segoe UI", 9),
            bg=self.colors["white"],
            fg=self.colors["text_light"],
        )
        self.info_label.pack(anchor=tk.W, padx=20, pady=(0, 20))

    def _setup_placeholder(self, widget, placeholder):
        widget.insert("1.0", placeholder)
        widget.config(fg=self.colors["text_light"])

        def on_focus_in(event):
            self._clear_placeholder(widget, placeholder)

        def on_focus_out(event):
            self._set_placeholder(widget, placeholder)

        widget.bind("<FocusIn>", on_focus_in)
        widget.bind("<FocusOut>", on_focus_out)

    def _clear_placeholder(self, widget, placeholder):
        if widget.get("1.0", "end-1c") == placeholder:
            widget.delete("1.0", tk.END)
            widget.config(fg="black")

    def _set_placeholder(self, widget, placeholder):
        if not widget.get("1.0", "end-1c").strip():
            widget.insert("1.0", placeholder)
            widget.config(fg=self.colors["text_light"])

    def _setup_editor_bindings(self):
        self.title_entry.bind(
            "<KeyRelease>", lambda e: self._handle_text_change("title")
        )
        self.text_area.bind(
            "<KeyRelease>", lambda e: self._handle_text_change("content")
        )
        self.title_entry.bind(
            "<FocusIn>",
            lambda e: self._on_text_focus_in(
                e, self.title_entry, "Введите заголовок..."
            ),
        )
        self.title_entry.bind(
            "<FocusOut>",
            lambda e: self._on_text_focus_out(
                e, self.title_entry, "Введите заголовок..."
            ),
        )
        self.text_area.bind(
            "<FocusIn>",
            lambda e: self._on_text_focus_in(
                e, self.text_area, "Введите текст заметки..."
            ),
        )
        self.text_area.bind(
            "<FocusOut>",
            lambda e: self._on_text_focus_out(
                e, self.text_area, "Введите текст заметки..."
            ),
        )
        self.text_area.bind("<<Selection>>", self._update_button_states)
        self.text_area.bind("<<Modified>>", self._on_text_modified)

    def _on_text_modified(self, event):
        if self.text_area.edit_modified():
            self.text_area.edit_modified(False)
            self._update_button_states()

    def _on_text_focus_in(self, event, widget, placeholder):
        self._clear_placeholder(widget, placeholder)

    def _on_text_focus_out(self, event, widget, placeholder):
        self._set_placeholder(widget, placeholder)

    def _bind_events(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Escape>", self._handle_escape)
        self._setup_hotkeys()
        self.check_reminders()

    def _load_data(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.notes_file):
            return {}
        try:
            with open(self.notes_file, "r", encoding="utf-8") as f:
                notes = json.load(f)
                if not isinstance(notes, dict):
                    return {}
                corrected_notes = {}
                for note_id, note_data in notes.items():
                    if not isinstance(note_data, dict):
                        continue
                    if "content" not in note_data or not isinstance(
                        note_data.get("content"), list
                    ):
                        note_data["content"] = [{"type": "text", "value": ""}]
                    if "title" not in note_data or not isinstance(
                        note_data["title"], str
                    ):
                        note_data["title"] = ""
                    if "created" not in note_data or not isinstance(
                        note_data.get("created"), str
                    ):
                        note_data["created"] = datetime.now().isoformat()
                    if "modified" not in note_data or not isinstance(
                        note_data.get("modified"), str
                    ):
                        note_data["modified"] = note_data.get(
                            "created", datetime.now().isoformat()
                        )
                    corrected_notes[note_id] = note_data
                return corrected_notes
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            messagebox.showerror(
                "Ошибка", "Не удалось загрузить заметки. Создан новый файл."
            )
            return {}

    def _save_data(self):
        try:
            if os.path.exists(self.notes_file):
                shutil.copy(self.notes_file, self.notes_file + ".bak")
            with open(self.notes_file, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=2)
            logger.info("Данные успешно сохранены")
        except Exception as e:
            logger.error(f"Не удалось сохранить данные: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось сохранить данные: {str(e)}")

    def _load_notes_list(self):
        self.notes_listbox.delete(0, tk.END)
        search_term = self.search_var.get().lower()
        search_content = self.search_content_var.get()
        sort_display = self.sort_var.get()
        sort_key = self.sort_mapping.get(
            sort_display, "по_дате_изменения_убыв")

        def get_sort_key(note):
            note_id, note_data = note
            if not isinstance(note_data, dict):
                return (datetime.min, "")
            try:
                if sort_key == "по_заголовку_а_я" or sort_key == "по_заголовку_я_а":
                    title = note_data.get("title", "")
                    return (datetime.min, title.lower() if title else "")
                elif sort_key in ["по_дате_создания_возр", "по_дате_создания_убыв"]:
                    created = note_data.get("created", "2000-01-01T00:00:00")
                    return (datetime.fromisoformat(created), "")
                elif sort_key in ["по_дате_изменения_возр", "по_дате_изменения_убыв"]:
                    modified = note_data.get("modified", "2000-01-01T00:00:00")
                    return (datetime.fromisoformat(modified), "")
            except (ValueError, TypeError):
                return (datetime.min, "")

        reverse = sort_key in [
            "по_заголовку_я_а",
            "по_дате_создания_убыв",
            "по_дате_изменения_убыв",
        ]
        valid_notes = [
            (note_id, note_data)
            for note_id, note_data in self.notes.items()
            if isinstance(note_data, dict)
        ]
        sorted_notes = sorted(valid_notes, key=get_sort_key, reverse=reverse)
        for note_id, note_data in sorted_notes:
            if search_term and not self._match_search(
                note_data, search_term, search_content
            ):
                continue
            title = note_data.get("title", "").strip() or "Без названия"
            date_str = self._format_date(note_data.get("created"))
            content = note_data.get("content", [])
            indicators = []
            if any(item["type"] == "image" for item in content):
                indicators.append("🖼️")
            if note_data.get("attachments"):
                indicators.append("📎")
            if note_data.get("reminder"):
                indicators.append("⏰")
            if any(item["type"] == "table" for item in content):
                indicators.append("📊")
            display_text = f"{title}"
            if indicators:
                display_text = f" {' '.join(indicators)} {display_text}"
            if date_str:
                display_text += f" ({date_str})"
            self.notes_listbox.insert(tk.END, display_text)

    def _match_search(self, note_data, term, search_content) -> bool:
        title = note_data.get("title", "").lower()
        if term in title:
            return True
        if search_content:
            content = " ".join(
                item["value"] if item["type"] == "text" else ""
                for item in note_data.get("content", [])
            ).lower()
            return term in content
        return False

    def _format_date(self, date_str: Optional[str]) -> str:
        if not date_str:
            return ""
        try:
            return datetime.fromisoformat(date_str).strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return ""

    def create_note(self):
        note_id = 1
        if self.notes:
            max_id = max(int(k) for k in self.notes.keys() if k.isdigit())
            note_id = max_id + 1
        note_id = str(note_id)
        timestamp = datetime.now().isoformat()
        self.notes[note_id] = {
            "title": "",
            "content": [],
            "created": timestamp,
            "modified": timestamp,
            "attachments": [],
        }
        self._ensure_note_attachments_dir(note_id)
        self._load_notes_list()
        self.select_note_by_id(note_id)
        self.title_entry.focus_set()
        logger.info(f"Создана новая заметка: ID {note_id}")

    def select_note_by_id(self, note_id: str):
        all_notes = self._get_filtered_notes()
        for i, (nid, _) in enumerate(all_notes):
            if nid == note_id:
                self.notes_listbox.selection_clear(0, tk.END)
                self.notes_listbox.selection_set(i)
                self.notes_listbox.see(i)
                self.load_note(note_id)
                return

    def _get_filtered_notes(self) -> List[Tuple[str, Dict]]:
        search_term = self.search_var.get().lower()
        search_content = self.search_content_var.get()
        sorted_notes = sorted(
            self.notes.items(),
            key=lambda x: datetime.fromisoformat(
                x[1].get("modified", "2000-01-01")),
            reverse=True,
        )
        if not search_term:
            return sorted_notes
        return [
            (note_id, note_data)
            for note_id, note_data in sorted_notes
            if self._match_search(note_data, search_term, search_content)
        ]

    def select_note(self, event=None):
        selection = self.notes_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        filtered_notes = self._get_filtered_notes()
        if index < len(filtered_notes):
            note_id = filtered_notes[index][0]
            self.load_note(note_id)

    def load_note(self, note_id: str):
        if note_id not in self.notes:
            return
        self.tables.clear()
        self.table_frames.clear()
        self.current_images.clear()
        self.image_cache.clear()
        self.current_note = note_id
        note_data = self.notes[note_id]
        self.empty_label.pack_forget()
        self.editor_frame.pack(fill=tk.BOTH, expand=True)
        self._update_field(self.title_entry, note_data.get("title", ""))
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.edit_reset()
        self.text_area.edit_modified(False)
        self.text_area.mark_set(tk.INSERT, "1.0")
        color_tags = note_data.get("color_tags", {})
        self.color_tags.update(color_tags)
        for tag, color in color_tags.items():
            self.text_area.tag_configure(tag, foreground=color)
        content = note_data.get("content", [])
        for item in content:
            if item["type"] == "text":
                start_pos = self.text_area.index(tk.INSERT)
                self.text_area.insert(tk.INSERT, item["value"])
                for tag in item.get("tags", {}):
                    self.text_area.tag_add(tag, start_pos, tk.INSERT)
            elif item["type"] == "image":
                self._insert_image(
                    self.current_note, item["filename"], position=tk.INSERT
                )
            elif item["type"] == "table":
                self._insert_table(
                    item["id"], item["headers"], item["rows"], position=tk.INSERT
                )
            elif item["type"] == "hyperlink":
                self._insert_hyperlink(
                    item["text"], item["url"], position=tk.INSERT)
        self._load_attachments()
        created_date = self._format_date(note_data.get("created"))
        modified_date = self._format_date(note_data.get("modified"))
        info_text = f"Создано: {created_date}"
        if modified_date and modified_date != created_date:
            info_text += f" | Изменено: {modified_date}"
        if "reminder" in note_data:
            reminder_date = self._format_date(note_data["reminder"])
            info_text += f" | ⏰ Напомнить: {reminder_date}"
        self.info_label.config(text=info_text)
        self._update_button_states()
        logger.info(f"Загружена заметка: ID {note_id}")

    def _insert_image(self, note_id: str, filename: str, position=tk.END):
        attachments_dir = self._get_note_attachments_dir(note_id)
        base_name = os.path.splitext(filename)[0]
        thumbnail_path = os.path.join(
            attachments_dir, f"{base_name}_thumb.png")
        if not os.path.exists(thumbnail_path):
            original_path = os.path.join(attachments_dir, filename)
            if os.path.exists(original_path):
                self._generate_thumbnail(original_path)
        if thumbnail_path in self.image_cache:
            photo = self.image_cache[thumbnail_path]
        else:
            try:
                img = Image.open(thumbnail_path)
                photo = ImageTk.PhotoImage(img)
                self.image_cache[thumbnail_path] = photo
            except Exception as e:
                error_img = Image.new("RGB", (100, 100), color="gray")
                photo = ImageTk.PhotoImage(error_img)
                self.text_area.insert(position, f"[ошибка: {str(e)}]")
                logger.error(f"Ошибка загрузки изображения: {e}")
                return
        insert_index = self.text_area.index(position)
        self.text_area.image_create(insert_index, image=photo, name=filename)
        self.current_images.append(photo)
        self.text_area.mark_set(tk.INSERT, f"{insert_index} + 1c")
        self.text_area.see(tk.INSERT)

    def _insert_file_link(self, display_name: str, filename: str, position=tk.END):
        link_text = f"[{display_name}]"
        start_index = self.text_area.index(position)
        self.text_area.insert(position, link_text, ("file_link",))
        end_index = self.text_area.index(f"{start_index}+{len(link_text)}c")
        tag_name = f"filelink_{filename}"
        self.text_area.tag_add(tag_name, start_index, end_index)
        self.text_area.mark_set(tk.INSERT, end_index)
        self.text_area.see(end_index)

    def _insert_hyperlink(self, text: str, url: str, position=tk.END):
        tag_name = f"hyperlink_{url}"
        self.text_area.insert(position, text, (tag_name, "hyperlink"))
        self.text_area.tag_bind(
            tag_name, "<Button-1>", lambda e: webbrowser.open_new(url)
        )

    def insert_link(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для вставки ссылки"
            )
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Вставить ссылку")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Текст ссылки:").pack(pady=5)
        text_var = tk.StringVar()
        text_entry = tk.Entry(dialog, textvariable=text_var)
        text_entry.pack(pady=5)
        tk.Label(dialog, text="URL:").pack(pady=5)
        url_var = tk.StringVar()
        url_entry = tk.Entry(dialog, textvariable=url_var)
        url_entry.pack(pady=5)

        def insert():
            text = text_var.get().strip()
            url = url_var.get().strip()
            if not text or not url:
                messagebox.showerror("Ошибка", "Введите текст и URL")
                return
            self._insert_hyperlink(text, url, position=tk.INSERT)
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        ok_btn = tk.Button(btn_frame, text="Вставить", command=insert)
        ok_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = tk.Button(btn_frame, text="Отмена",
                               command=dialog.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

    def _insert_table(self, table_id, headers, rows, position):
        frame = tk.Frame(self.root)
        treeview = ttk.Treeview(
            frame, columns=headers, show="headings", height=len(rows)
        )
        treeview.pack(fill=tk.BOTH, expand=True)
        for header in headers:
            treeview.heading(header, text=header)
            treeview.column(header, width=100)
        for row in rows:
            treeview.insert("", "end", values=row)
        self.text_area.window_create(position, window=frame)
        self.table_frames[table_id] = frame
        self.tables[table_id] = treeview
        treeview.bind(
            "<Double-1>", lambda e, tid=table_id: self._edit_table_cell(e, tid)
        )
        treeview.bind(
            "<Button-3>", lambda e, tid=table_id: self._show_table_context_menu(
                e, tid)
        )
        self.text_area.insert(position, "\n")
        self.text_area.mark_set(tk.INSERT, f"{position} + 1c")

    def _edit_table_cell(self, event, table_id):
        treeview = self.tables[table_id]
        item = treeview.identify_row(event.y)
        column = treeview.identify_column(event.x)
        if not item or not column:
            return
        column_index = int(column[1:]) - 1
        values = treeview.item(item, "values")
        current_value = values[column_index]
        entry = tk.Entry(treeview)
        entry.insert(0, current_value)
        entry.select_range(0, tk.END)
        entry.focus_set()
        x, y, width, height = treeview.bbox(item, column)
        entry.place(x=x, y=y, width=width, height=height)

        def save_edit(e=None):
            new_value = entry.get()
            values = list(treeview.item(item, "values"))
            values[column_index] = new_value
            treeview.item(item, values=values)
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)

    def _show_table_context_menu(self, event, table_id):
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(
            label="Удалить таблицу", command=lambda: self._delete_table(table_id)
        )
        context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_table(self, table_id):
        if table_id in self.table_frames:
            frame = self.table_frames[table_id]
            self.text_area.delete(frame)
            del self.table_frames[table_id]
            del self.tables[table_id]
            content = self.notes[self.current_note]["content"]
            self.notes[self.current_note]["content"] = [
                item
                for item in content
                if not (item["type"] == "table" and item["id"] == table_id)
            ]
            self._save_data()
            logger.info(f"Таблица удалена: {table_id}")

    def _update_field(self, widget, content: str):
        widget.delete("1.0", tk.END)
        if content:
            widget.insert("1.0", content)
            widget.config(fg="black")
        else:
            placeholder = (
                "Введите заголовок..."
                if widget == self.title_entry
                else "Введите текст заметки..."
            )
            self._set_placeholder(widget, placeholder)

    def _load_attachments(self):
        for widget in self.attachments_content.winfo_children():
            widget.destroy()
        if not self.current_note:
            if (
                hasattr(self, "attachments_frame")
                and self.attachments_frame.winfo_ismapped()
            ):
                self.attachments_frame.pack_forget()
            return
        attachments = self.notes[self.current_note].get("attachments", [])
        if not attachments:
            if (
                hasattr(self, "attachments_frame")
                and self.attachments_frame.winfo_ismapped()
            ):
                self.attachments_frame.pack_forget()
            return
        if not self.attachments_frame.winfo_ismapped():
            self.attachments_frame.pack(
                fill=tk.X, padx=20, pady=(10, 0), before=self.title_frame
            )
        for i, attachment in enumerate(attachments):
            self._create_attachment_widget(attachment, i)
        self.attachments_content.update_idletasks()
        content_height = self.attachments_content.winfo_reqheight()
        new_height = min(max(100, content_height), 300)
        self.attachments_canvas.config(height=new_height)
        self.attachments_canvas.configure(
            scrollregion=self.attachments_canvas.bbox("all")
        )

    def _create_attachment_widget(self, attachment: Dict, index: int):
        widget_frame = tk.Frame(
            self.attachments_content, bg=self.colors["border"], relief="solid", bd=1
        )
        widget_frame.pack(side=tk.LEFT, padx=5, pady=5)
        if attachment["type"] == "image":
            self._create_image_widget(widget_frame, attachment, index)
        elif attachment["type"] == "audio":
            self._create_audio_widget(widget_frame, attachment, index)
        else:
            self._create_file_widget(widget_frame, attachment, index)

    def _edit_image(self, filename: str):
        image_path = os.path.join(
            self._get_note_attachments_dir(self.current_note), filename
        )
        if not os.path.exists(image_path):
            logger.error(f"Файл изображения не найден: {image_path}")
            messagebox.showerror(
                "Ошибка", f"Файл изображения не найден:\n{image_path}")
            return
        try:
            image = Image.open(image_path)
            self.editing_image = image_path
            edit_window = tk.Toplevel(self.root)
            edit_window.title("Редактирование изображения")
            edit_window.geometry("800x600")
            edit_window.state("zoomed")
            control_frame = tk.Frame(edit_window)
            control_frame.pack(fill=tk.X, padx=10, pady=5)
            crop_btn = tk.Button(
                control_frame,
                text="Обрезать",
                command=lambda: self._start_crop(canvas, edit_window),
            )
            crop_btn.pack(side=tk.LEFT, padx=5)
            resize_btn = tk.Button(
                control_frame,
                text="Изменить размер",
                command=lambda: self._resize_image(edit_window, image_path),
            )
            resize_btn.pack(side=tk.LEFT, padx=5)
            zoom_in_btn = tk.Button(
                control_frame,
                text="+ Увеличить",
                command=lambda: self._change_scale(
                    1.2, canvas, image, edit_window),
            )
            zoom_in_btn.pack(side=tk.LEFT, padx=5)
            zoom_out_btn = tk.Button(
                control_frame,
                text="- Уменьшить",
                command=lambda: self._change_scale(
                    0.8, canvas, image, edit_window),
            )
            zoom_out_btn.pack(side=tk.LEFT, padx=5)
            reset_btn = tk.Button(
                control_frame,
                text="Сбросить масштаб",
                command=lambda: self._reset_scale(canvas, image, edit_window),
            )
            reset_btn.pack(side=tk.LEFT, padx=5)
            save_btn = tk.Button(
                control_frame,
                text="Сохранить",
                command=lambda: self._save_edited_image(
                    image_path, edit_window),
            )
            save_btn.pack(side=tk.RIGHT, padx=5)
            frame = tk.Frame(edit_window)
            frame.pack(fill=tk.BOTH, expand=True)
            hbar = tk.Scrollbar(frame, orient=tk.HORIZONTAL)
            vbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
            canvas = tk.Canvas(
                frame, xscrollcommand=hbar.set, yscrollcommand=vbar.set, bg="gray20"
            )
            canvas.grid(row=0, column=0, sticky="nsew")
            hbar.grid(row=1, column=0, sticky="ew")
            vbar.grid(row=0, column=1, sticky="ns")
            hbar.config(command=canvas.xview)
            vbar.config(command=canvas.yview)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            edit_window.original_image = image
            edit_window.current_scale = 1.0
            edit_window.image_path = image_path
            self._show_scaled_image(canvas, image, edit_window)
            canvas.bind(
                "<MouseWheel>",
                lambda e: self._on_mousewheel(e, canvas, image, edit_window),
            )
            canvas.bind(
                "<Button-4>",
                lambda e: self._on_linux_scroll(
                    e, canvas, image, 1.2, edit_window),
            )
            canvas.bind(
                "<Button-5>",
                lambda e: self._on_linux_scroll(
                    e, canvas, image, 0.8, edit_window),
            )
            canvas.bind("<ButtonPress-1>",
                        lambda e: canvas.scan_mark(e.x, e.y))
            canvas.bind("<B1-Motion>",
                        lambda e: canvas.scan_dragto(e.x, e.y, gain=1))
            logger.info(f"Открыто редактирование изображения: {image_path}")
        except Exception as e:
            logger.error(f"Ошибка открытия редактора изображения: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось открыть редактор изображения: {str(e)}"
            )

    def _save_edited_image(self, image_path: str, window):
        try:
            if hasattr(window, "original_image"):
                window.original_image.save(image_path)
                self._generate_thumbnail(image_path)
                self._load_attachments()
                self.load_note(self.current_note)
                logger.info(
                    f"Отредактированное изображение сохранено: {image_path}")
                messagebox.showinfo("Успех", "Изменения сохранены")
                window.destroy()
            else:
                raise ValueError("Нет изображения для сохранения")
        except Exception as e:
            logger.error(f"Ошибка сохранения изображения: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось сохранить изображение: {str(e)}"
            )

    def _create_image_widget(self, parent, attachment: Dict, index: int):
        try:
            filename = attachment["filename"]
            image_path = os.path.join(
                self._get_note_attachments_dir(self.current_note), filename
            )
            if not os.path.exists(image_path):
                raise FileNotFoundError("Файл не найден")
            img = Image.open(image_path)
            img.thumbnail((100, 100), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            image_label = tk.Label(parent, image=photo,
                                   bg=self.colors["white"])
            image_label.image = photo
            image_label.pack(padx=5, pady=5)
            image_label.bind("<Double-Button-1>",
                             lambda e: self._open_image(filename))
            name_label = tk.Label(
                parent,
                text=attachment.get("original_name", "image.png")[:15],
                font=("Segoe UI", 8),
                bg=self.colors["border"],
            )
            name_label.pack()
            edit_btn = tk.Button(
                parent,
                text="✏️",
                font=("Arial", 10),
                bg=self.colors["info"],
                fg="white",
                width=2,
                command=lambda: self._edit_image(filename),
            )
            edit_btn.pack(side=tk.LEFT, padx=2)
            delete_btn = tk.Button(
                parent,
                text="×",
                font=("Arial", 12, "bold"),
                bg=self.colors["danger"],
                fg="white",
                width=2,
                command=lambda: self._remove_attachment(index),
            )
            delete_btn.pack(side=tk.LEFT, padx=2)
        except Exception as e:
            error_label = tk.Label(
                parent,
                text="Ошибка\nзагрузки",
                font=("Segoe UI", 8),
                bg=self.colors["border"],
            )
            error_label.pack(padx=5, pady=5)
            delete_btn = tk.Button(
                parent,
                text="×",
                font=("Arial", 12, "bold"),
                bg=self.colors["danger"],
                fg="white",
                width=2,
                command=lambda: self._remove_attachment(index),
            )
            delete_btn.pack()
            logger.error(f"Ошибка создания виджета изображения: {e}")

    def _create_audio_widget(self, parent, attachment: Dict, index: int):
        file_label = tk.Label(
            parent, text="🔊", font=("Arial", 24), bg=self.colors["border"]
        )
        file_label.pack(padx=5, pady=(5, 0))
        name_label = tk.Label(
            parent,
            text=attachment.get("original_name", "audio.wav")[:15],
            font=("Segoe UI", 8),
            bg=self.colors["border"],
        )
        name_label.pack()
        buttons_frame = tk.Frame(parent, bg=self.colors["border"])
        buttons_frame.pack(pady=5)
        play_btn = tk.Button(
            buttons_frame,
            text="▶",
            width=3,
            command=lambda: self._play_audio(attachment["filename"]),
        )
        play_btn.pack(side=tk.LEFT, padx=2)
        delete_btn = tk.Button(
            buttons_frame,
            text="×",
            width=3,
            font=("Arial", 10, "bold"),
            bg=self.colors["danger"],
            fg="white",
            command=lambda: self._remove_attachment(index),
        )
        delete_btn.pack(side=tk.LEFT, padx=2)

    def _create_file_widget(self, parent, attachment: Dict, index: int):
        file_label = tk.Label(
            parent, text="📄", font=("Arial", 24), bg=self.colors["border"]
        )
        file_label.pack(padx=5, pady=(5, 0))
        name_label = tk.Label(
            parent,
            text=attachment.get("original_name", "file")[:15],
            font=("Segoe UI", 8),
            bg=self.colors["border"],
        )
        name_label.pack()
        name_label.bind(
            "<Double-Button-1>", lambda e: self._open_file(
                attachment["filename"])
        )
        buttons_frame = tk.Frame(parent, bg=self.colors["border"])
        buttons_frame.pack(pady=5)
        open_btn = tk.Button(
            buttons_frame,
            text="📂",
            width=3,
            command=lambda: self._open_file(attachment["filename"]),
        )
        open_btn.pack(side=tk.LEFT, padx=2)
        delete_btn = tk.Button(
            buttons_frame,
            text="×",
            width=3,
            font=("Arial", 10, "bold"),
            bg=self.colors["danger"],
            fg="white",
            command=lambda: self._remove_attachment(index),
        )
        delete_btn.pack(side=tk.LEFT, padx=2)

    def _open_image(self, filename: str):
        image_path = os.path.join(
            self._get_note_attachments_dir(self.current_note), filename
        )
        if not os.path.exists(image_path):
            logger.error(f"Файл изображения не найден: {image_path}")
            messagebox.showerror(
                "Ошибка", f"Файл изображения не найден:\n{image_path}")
            return
        try:
            image = Image.open(image_path)
            image_window = tk.Toplevel(self.root)
            image_window.title("Просмотр изображения")
            image_window.geometry("800x600")
            image_window.state("zoomed")
            control_frame = tk.Frame(image_window)
            control_frame.pack(fill=tk.X, padx=10, pady=5)
            edit_btn = tk.Button(
                control_frame,
                text="Редактировать",
                command=lambda: [
                    image_window.destroy(), self._edit_image(filename)],
            )
            edit_btn.pack(side=tk.LEFT, padx=5)
            canvas = tk.Canvas(image_window, bg="gray20")
            canvas.pack(fill=tk.BOTH, expand=True)
            photo = ImageTk.PhotoImage(image)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.config(scrollregion=canvas.bbox("all"))
            canvas.image = photo
            image_window.bind("<Escape>", lambda e: image_window.destroy())
            logger.info(f"Изображение открыто: {filename}")
        except Exception as e:
            logger.error(f"Ошибка открытия изображения: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось открыть изображение: {str(e)}")

    def _show_scaled_image(self, canvas, image: Image.Image, window):
        canvas.delete("all")
        scale = getattr(window, "current_scale", 1.0)
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        scaled_image = image.resize(
            (new_width, new_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(scaled_image)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.config(scrollregion=canvas.bbox("all"))
        canvas.tk_image = photo

    def _on_mousewheel(self, event, canvas, image: Image.Image, window):
        scale_factor = 1.1 if event.delta > 0 else 0.9
        self._change_scale(scale_factor, canvas, image, window)

    def _on_linux_scroll(
        self, event, canvas, image: Image.Image, scale_factor: float, window
    ):
        self._change_scale(scale_factor, canvas, image, window)

    def _change_scale(self, scale_factor: float, canvas, image: Image.Image, window):
        if not hasattr(window, "current_scale"):
            window.current_scale = 1.0
        window.current_scale *= scale_factor
        window.current_scale = max(0.1, min(window.current_scale, 10.0))
        self._show_scaled_image(canvas, window.original_image, window)

    def _reset_scale(self, canvas, image: Image.Image, window):
        window.current_scale = 1.0
        self._show_scaled_image(canvas, window.original_image, window)

    def _open_file(self, filename: str):
        file_path = os.path.join(
            self._get_note_attachments_dir(self.current_note), filename
        )
        logger.info(f"Открытие файла: {file_path}")
        if not os.path.exists(file_path):
            logger.error(f"Файл не найден: {file_path}")
            messagebox.showerror("Ошибка", f"Файл не найден:\n{file_path}")
            return
        try:
            if platform.system() == "Darwin":
                subprocess.call(("open", file_path))
            elif platform.system() == "Windows":
                os.startfile(file_path)
            else:
                subprocess.call(("xdg-open", file_path))
            logger.info(f"Файл открыт: {filename}")
        except Exception as e:
            logger.error(f"Не удалось открыть файл: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось открыть файл: {str(e)}")

    def _play_audio(self, filename: str):
        file_path = os.path.join(
            self._get_note_attachments_dir(self.current_note), filename
        )
        if not os.path.exists(file_path):
            logger.error(f"Аудиофайл не найден: {file_path}")
            messagebox.showerror(
                "Ошибка", f"Аудиофайл не найден:\n{file_path}")
            return
        try:
            if platform.system() == "Windows":
                winsound.PlaySound(file_path, winsound.SND_FILENAME)
            else:
                subprocess.call(("aplay", file_path))
            logger.info(f"Воспроизведение аудио: {filename}")
        except Exception as e:
            logger.error(f"Ошибка воспроизведения аудио: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось воспроизвести аудио: {str(e)}")

    def _remove_attachment(self, index: int):
        if not self.current_note:
            return
        confirm = messagebox.askyesno("Подтверждение", "Удалить это вложение?")
        if not confirm:
            return
        attachments = self.notes[self.current_note].get("attachments", [])
        if index >= len(attachments):
            return
        attachment = attachments[index]
        filename = attachment["filename"]
        file_path = os.path.join(
            self._get_note_attachments_dir(self.current_note), filename
        )
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Не удалось удалить файл: {e}")
                messagebox.showerror(
                    "Ошибка", f"Не удалось удалить файл: {str(e)}")
        if attachment["type"] == "image":
            base_name, ext = os.path.splitext(filename)
            thumbnail_path = os.path.join(
                self._get_note_attachments_dir(self.current_note),
                f"{base_name}_thumb.png",
            )
            if os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except Exception as e:
                    logger.error(f"Не удалось удалить миниатюру: {e}")
        del attachments[index]
        self.notes[self.current_note]["modified"] = datetime.now().isoformat()
        self._load_attachments()
        self._save_data()
        logger.info(f"Вложение удалено: {filename}")

    def _sanitize_filename(self, name: str) -> str:
        name = re.sub(r"[^\w\-_. ]", "", name)
        return name.strip()[:50]

    def attach_file(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для прикрепления файла"
            )
            return
        file_path = filedialog.askopenfilename(
            title="Выберите файл для прикрепления",
            filetypes=[
                ("Все файлы", "*.*"),
                ("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("Документы", "*.pdf *.doc *.docx *.txt"),
                ("Архивы", "*.zip *.rar *.7z"),
                ("Аудио", "*.mp3 *.wav *.ogg"),
            ],
        )
        if not file_path:
            return
        try:
            original_name = os.path.basename(file_path)
            file_extension = os.path.splitext(original_name)[1].lower()
            safe_name = self._sanitize_filename(original_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{safe_name}"
            destination = os.path.join(
                self._ensure_note_attachments_dir(self.current_note), filename
            )
            shutil.copy2(file_path, destination)
            image_extensions = {".png", ".jpg",
                                ".jpeg", ".gif", ".bmp", ".tiff"}
            audio_extensions = {".mp3", ".wav", ".ogg"}
            if file_extension in image_extensions:
                self._generate_thumbnail(destination)
                self._insert_image(self.current_note,
                                   filename, position="insert")
                attachment_type = "image"
            elif file_extension in audio_extensions:
                attachment_type = "audio"
            else:
                attachment_type = "file"
            if "attachments" not in self.notes[self.current_note]:
                self.notes[self.current_note]["attachments"] = []
            attachment = {
                "type": attachment_type,
                "filename": filename,
                "original_name": original_name,
                "added": datetime.now().isoformat(),
            }
            self.notes[self.current_note]["attachments"].append(attachment)
            if attachment_type != "image":
                self._insert_file_link(
                    original_name, filename, position="insert")
            self.notes[self.current_note]["modified"] = datetime.now().isoformat()
            self._load_attachments()
            self._load_notes_list()
            self._save_data()
            logger.info(f"Файл прикреплен: {original_name}")
            messagebox.showinfo(
                "Успешно", f"Файл '{original_name}' прикреплен!")
        except Exception as e:
            logger.error(f"Ошибка прикрепления файла: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось прикрепить файл: {str(e)}")

    def record_audio(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для записи аудио"
            )
            return
        recording_window = tk.Toplevel(self.root)
        recording_window.title("Запись аудио")
        recording_window.geometry("300x150")
        recording_window.resizable(False, False)
        recording_window.grab_set()
        status_label = tk.Label(
            recording_window, text="Готов к записи", font=("Segoe UI", 12)
        )
        status_label.pack(pady=10)
        btn_frame = tk.Frame(recording_window)
        btn_frame.pack(pady=10)
        record_btn = tk.Button(
            btn_frame,
            text="● Запись",
            width=10,
            command=lambda: self._start_recording(
                status_label, record_btn, stop_btn),
        )
        record_btn.pack(side=tk.LEFT, padx=5)
        stop_btn = tk.Button(
            btn_frame,
            text="■ Стоп",
            width=10,
            state=tk.DISABLED,
            command=lambda: self._stop_recording(
                recording_window, status_label),
        )
        stop_btn.pack(side=tk.LEFT, padx=5)

    def _start_recording(self, label, record_btn, stop_btn):
        label.config(text="Идет запись...", fg="red")
        record_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)
        self.recorder.start_recording()

    def _stop_recording(self, window, label):
        self.recorder.recording = False
        frames = self.recorder.stop_recording()
        label.config(text="Запись завершена", fg="green")
        try:
            attachments_dir = self._ensure_note_attachments_dir(
                self.current_note)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"audio_{timestamp}.wav"
            filepath = os.path.join(attachments_dir, filename)
            self.recorder.save_recording(filepath)
            attachment = {
                "type": "audio",
                "filename": filename,
                "original_name": "audio_recording.wav",
                "added": datetime.now().isoformat(),
            }
            self.notes[self.current_note]["attachments"].append(attachment)
            self._load_attachments()
            self._save_data()
            messagebox.showinfo("Успех", "Аудиозапись сохранена!")
            window.destroy()
        except Exception as e:
            messagebox.showerror(
                "Ошибка", f"Не удалось сохранить аудио: {str(e)}")
            window.destroy()

    def save_current_note(self):
        if not self.current_note:
            return
        title = self.title_entry.get("1.0", "end-1c").strip()
        if not title:
            messagebox.showwarning(
                "Предупреждение", "Заголовок не может быть пустым")
            return
        content_list = []
        current_text = ""
        current_tags = set()
        for kind, value, pos in self.text_area.dump(
            "1.0", "end-1c", text=True, window=True, image=True, tag=True
        ):
            if kind == "text":
                current_text += value
            elif kind == "tagon":
                if current_text:
                    content_list.append(
                        {
                            "type": "text",
                            "value": current_text,
                            "tags": list(current_tags),
                        }
                    )
                    current_text = ""
                current_tags.add(value)
            elif kind == "tagoff":
                if current_text:
                    content_list.append(
                        {
                            "type": "text",
                            "value": current_text,
                            "tags": list(current_tags),
                        }
                    )
                    current_text = ""
                current_tags.discard(value)
            elif kind == "window":
                if current_text:
                    content_list.append(
                        {
                            "type": "text",
                            "value": current_text,
                            "tags": list(current_tags),
                        }
                    )
                    current_text = ""
                frame_path = value
                frame = self.root.nametowidget(frame_path)
                for tid, f in self.table_frames.items():
                    if f == frame:
                        treeview = self.tables[tid]
                        headers = treeview["columns"]
                        rows = [
                            treeview.item(item, "values")
                            for item in treeview.get_children()
                        ]
                        content_list.append(
                            {
                                "type": "table",
                                "id": tid,
                                "headers": headers,
                                "rows": rows,
                            }
                        )
                        break
            elif kind == "image":
                if current_text:
                    content_list.append(
                        {
                            "type": "text",
                            "value": current_text,
                            "tags": list(current_tags),
                        }
                    )
                    current_text = ""
                content_list.append({"type": "image", "filename": value})
        if current_text:
            content_list.append(
                {"type": "text", "value": current_text,
                    "tags": list(current_tags)}
            )
        used_color_tags = set()
        for item in content_list:
            if item["type"] == "text":
                for tag in item.get("tags", []):
                    if tag.startswith("color_"):
                        used_color_tags.add(tag)
        color_tags = {
            tag: self.text_area.tag_cget(tag, "foreground")
            for tag in used_color_tags
            if tag in self.text_area.tag_names()
        }
        self.notes[self.current_note]["title"] = title
        self.notes[self.current_note]["content"] = content_list
        self.notes[self.current_note]["color_tags"] = color_tags
        self.notes[self.current_note]["modified"] = datetime.now().isoformat()
        self._load_notes_list()
        self._save_data()

    def delete_current_note(self):
        if not self.current_note or self.current_note not in self.notes:
            return
        note_title = self.notes[self.current_note].get("title", "Без названия")
        confirm = messagebox.askyesno(
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить заметку '{note_title}'?",
        )
        if confirm:
            self._delete_note_attachments(self.current_note)
            del self.notes[self.current_note]
            self.current_note = None
            self.editor_frame.pack_forget()
            self.empty_label.pack(expand=True)
            self._save_data()
            self._load_notes_list()
            logger.info(f"Заметка удалена: {note_title}")

    def delete_selected_note(self, event=None):
        selection = self.notes_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        filtered_notes = self._get_filtered_notes()
        if index >= len(filtered_notes):
            self.notes_listbox.selection_clear(0, tk.END)
            return
        note_id = filtered_notes[index][0]
        note_title = self.notes[note_id].get("title", "Без названия")
        confirm = messagebox.askyesno(
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить заметку '{note_title}'?",
        )
        if not confirm:
            return
        self._delete_note_attachments(note_id)
        del self.notes[note_id]
        if self.current_note == note_id:
            self.current_note = None
            self.editor_frame.pack_forget()
            self.empty_label.pack(expand=True)
        self._save_data()
        self._load_notes_list()
        logger.info(f"Заметка удалена: {note_title}")
        self.notes_listbox.selection_clear(0, tk.END)

    def _delete_note_attachments(self, note_id: str):
        attachments_dir = self._get_note_attachments_dir(note_id)
        if os.path.exists(attachments_dir):
            try:
                shutil.rmtree(attachments_dir)
            except Exception as e:
                logger.error(f"Не удалось удалить вложения: {e}")
                messagebox.showerror(
                    "Ошибка", f"Не удалось удалить вложения: {str(e)}")

    def show_context_menu(self, event):
        selection = self.notes_listbox.curselection()
        if not selection:
            return
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="Открыть", command=self.select_note)
        context_menu.add_separator()
        context_menu.add_command(
            label="Удалить", command=self.delete_selected_note)
        context_menu.add_command(
            label="Дублировать", command=self.duplicate_note)
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _handle_text_change(self, field_type: str):
        if field_type == "content":
            self.text_area.edit_modified(True)
            self.text_area.after_idle(self._delayed_edit_separator)

    def _delayed_edit_separator(self):
        if self.text_area.edit_modified():
            self.text_area.edit_separator()
            self.text_area.edit_modified(False)
        if not self.current_note:
            return
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        self.autosave_timer = self.root.after(
            self.autosave_interval, self._autosave)

    def _autosave(self):
        if self.current_note and self.current_note in self.notes:
            try:
                self.save_current_note()
                logger.info("Автосохранение выполнено")
            except Exception as e:
                logger.error(f"Ошибка автосохранения: {e}")
        self.autosave_timer = None

    def _setup_autosave(self):
        self.autosave_timer = None

    def _on_closing(self):
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        if self.current_note:
            self.save_current_note()
            self._autosave()
        self.reminder_check_active = False
        self.root.destroy()
        logger.info("Приложение закрыто")

    def run(self):
        self.empty_label.pack(expand=True)
        self.root.mainloop()

    def _generate_thumbnail(self, original_path: str) -> str:
        try:
            thumbnail_size = (300, 300)
            image = Image.open(original_path)
            image.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
            base_name = os.path.splitext(original_path)[0]
            thumbnail_path = f"{base_name}_thumb.png"
            image.save(thumbnail_path, "PNG")
            logger.info(f"Миниатюра создана: {thumbnail_path}")
            return thumbnail_path
        except Exception as e:
            logger.error(f"Ошибка создания миниатюры: {e}")
            base_name = os.path.splitext(original_path)[0]
            thumbnail_path = f"{base_name}_thumb.png"
            error_thumb = Image.new("RGB", (100, 100), color="red")
            error_thumb.save(thumbnail_path, "PNG")
            return thumbnail_path

    def _on_double_click(self, event):
        index = self.text_area.index(f"@{event.x},{event.y}")
        try:
            image_name = self.text_area.image_cget(index, "name")
            if image_name:
                self._open_image(image_name)
        except tk.TclError:
            pass

    def _on_file_link_click(self, event):
        index = self.text_area.index(f"@{event.x},{event.y}")
        tags = self.text_area.tag_names(index)
        for tag in tags:
            if tag.startswith("filelink_"):
                filename = tag.split("_", 1)[1]
                self._open_file(filename)
                return "break"
        return None

    def _on_hyperlink_click(self, event):
        index = self.text_area.index(f"@{event.x},{event.y}")
        tags = self.text_area.tag_names(index)
        for tag in tags:
            if tag.startswith("hyperlink_"):
                url = tag.split("_", 1)[1]
                webbrowser.open_new(url)
                return "break"
        return None

    def _setup_hotkeys(self):
        self.root.bind("<Control-n>", lambda e: self.create_note())
        self.root.bind("<Control-N>", lambda e: self.create_note())
        self.root.bind("<Control-s>", lambda e: self.save_current_note())
        self.root.bind("<Control-S>", lambda e: self.save_current_note())
        self.root.bind("<Control-o>", lambda e: self.attach_file())
        self.root.bind("<Control-O>", lambda e: self.attach_file())
        self.root.bind("<Control-f>", lambda e: self.focus_search())
        self.root.bind("<Control-F>", lambda e: self.focus_search())
        self.root.bind("<Control-d>", lambda e: self.duplicate_note())
        self.root.bind("<Control-D>", lambda e: self.duplicate_note())
        self.root.bind("<Control-Up>", lambda e: self.select_previous_note())
        self.root.bind("<Control-Down>", lambda e: self.select_next_note())
        self.root.bind("<Control-Home>", lambda e: self.select_first_note())
        self.root.bind("<Control-End>", lambda e: self.select_last_note())
        self.root.bind("<F1>", lambda e: self.show_help())
        self.root.bind("<Control-q>", lambda e: self._on_closing())
        self.root.bind("<Control-Q>", lambda e: self._on_closing())
        self.root.bind("<Escape>", self._handle_escape)
        self.root.bind("<Delete>", lambda e: self.delete_current_note())
        self.root.bind("<Control-r>", lambda e: self.record_audio())
        self.root.bind("<Control-R>", lambda e: self.record_audio())
        for widget in [self.title_entry, self.text_area]:
            widget.bind("<Control-a>", self.select_all_text)
            widget.bind("<Control-A>", self.select_all_text)
            widget.bind("<Control-z>", self.undo_text)
            widget.bind("<Control-Z>", self.undo_text)
            widget.bind("<Control-y>", self.redo_text)
            widget.bind("<Control-Y>", self.redo_text)
            widget.bind("<Control-v>", self._handle_paste)
            widget.bind("<Control-V>", self._handle_paste)
            widget.bind("<Control-c>", self._handle_copy)
            widget.bind("<Control-C>", self._handle_copy)
        self.text_area.bind("<Control-b>", lambda e: self.toggle_bold())
        self.text_area.bind("<Control-B>", lambda e: self.toggle_bold())
        self.text_area.bind("<Control-i>", lambda e: self.toggle_italic())
        self.text_area.bind("<Control-I>", lambda e: self.toggle_italic())
        self.text_area.bind("<Control-u>", lambda e: self.toggle_underline())
        self.text_area.bind("<Control-U>", lambda e: self.toggle_underline())
        for widget in [self.title_entry, self.text_area]:
            widget.bind("<Key>", self._handle_key_press)

    def _handle_key_press(self, event):
        if event.keysym in {"BackSpace", "Delete"}:
            self.text_area.edit_separator()
        elif len(event.char) == 1:
            self.text_area.edit_separator()

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def clear_search(self):
        self.search_var.set("")
        self._load_notes_list()

    def copy_note(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Нет выбранной заметки для копирования"
            )
            return
        note_data = self.notes[self.current_note].copy()
        note_data["note_id"] = self.current_note
        self.clipboard_content = note_data
        messagebox.showinfo("Успешно", "Заметка скопирована")
        logger.info(f"Заметка ID {self.current_note} скопирована в буфер")

    def paste_note(self):
        if not self.clipboard_content:
            messagebox.showwarning(
                "Предупреждение", "Нет скопированной заметки")
            return
        self.create_note()
        if self.current_note:
            self.notes[self.current_note]["title"] = (
                self.clipboard_content.get("title", "") + " (копия)"
            )
            import copy

            self.notes[self.current_note]["content"] = copy.deepcopy(
                self.clipboard_content.get("content", [])
            )
            self.notes[self.current_note]["created"] = datetime.now().isoformat()
            self.notes[self.current_note]["modified"] = datetime.now().isoformat()
            self.notes[self.current_note]["attachments"] = []
            source_note_id = self.clipboard_content.get("note_id")
            if source_note_id and "attachments" in self.clipboard_content:
                self._copy_attachments(source_note_id, self.current_note)
            self.load_note(self.current_note)
            self.save_current_note()
            logger.info(
                f"Заметка вставлена из буфера, новая ID {self.current_note}")

    def _copy_attachments(self, source_note_id: str, target_note_id: str):
        source_dir = self._get_note_attachments_dir(source_note_id)
        target_dir = self._ensure_note_attachments_dir(target_note_id)
        if not os.path.exists(source_dir):
            logger.warning(
                f"Директория исходных вложений не найдена: {source_dir}")
            return
        filename_map = {}
        for attachment in self.clipboard_content.get("attachments", []):
            source_file = os.path.join(source_dir, attachment["filename"])
            if not os.path.exists(source_file):
                logger.warning(f"Файл вложения не найден: {source_file}")
                continue
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name, ext = os.path.splitext(attachment["filename"])
            new_filename = f"{timestamp}_{base_name}{ext}"
            target_file = os.path.join(target_dir, new_filename)
            try:
                shutil.copy2(source_file, target_file)
            except Exception as e:
                logger.error(f"Ошибка копирования файла {source_file}: {e}")
                continue
            if attachment["type"] == "image":
                source_thumb = os.path.join(
                    source_dir, f"{base_name}_thumb.png")
                target_thumb = os.path.join(
                    target_dir, f"{timestamp}_{base_name}_thumb.png"
                )
                if os.path.exists(source_thumb):
                    try:
                        shutil.copy2(source_thumb, target_thumb)
                    except Exception as e:
                        logger.error(
                            f"Ошибка копирования миниатюры {source_thumb}: {e}"
                        )
                else:
                    self._generate_thumbnail(target_file)
            filename_map[attachment["filename"]] = new_filename
            new_attachment = attachment.copy()
            new_attachment["filename"] = new_filename
            new_attachment["added"] = datetime.now().isoformat()
            self.notes[target_note_id]["attachments"].append(new_attachment)
        for item in self.notes[target_note_id]["content"]:
            if item["type"] == "image" and item["filename"] in filename_map:
                item["filename"] = filename_map[item["filename"]]
        logger.info(
            f"Скопировано {len(filename_map)} вложений для заметки {target_note_id}"
        )

    def _handle_copy(self, event=None):
        focused_widget = self.root.focus_get()
        if focused_widget in [self.title_entry, self.text_area]:
            try:
                focused_widget.event_generate("<<Copy>>")
            except:
                pass
        else:
            self.copy_note()
        return "break"

    def _handle_paste(self, event=None):
        focused_widget = self.root.focus_get()
        if focused_widget == self.title_entry:
            try:
                self.title_entry.event_generate("<<Paste>>")
                return "break"
            except:
                pass
        if self._has_clipboard_image() and focused_widget == self.text_area:
            self.paste_image_from_clipboard()
            return "break"
        if focused_widget in [self.text_area]:
            try:
                self.text_area.event_generate("<<Paste>>")
            except:
                pass
        else:
            self.paste_note()
        return "break"

    def _has_clipboard_image(self) -> bool:
        try:
            if platform.system() == "Windows":
                from PIL import ImageGrab

                return ImageGrab.grabclipboard() is not None
            elif platform.system() == "Linux":
                if pyperclip:
                    data = pyperclip.paste()
                    return data.startswith("data:image")
                return False
            else:
                try:
                    self.root.clipboard_get(type="image/png")
                    return True
                except tk.TclError:
                    return False
        except Exception:
            return False

    def paste_image_from_clipboard(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для прикрепления изображения"
            )
            return
        try:
            image = None
            if platform.system() == "Windows":
                from PIL import ImageGrab

                image = ImageGrab.grabclipboard()
                if not isinstance(image, Image.Image):
                    raise ValueError("В буфере обмена нет изображения")
            elif platform.system() == "Darwin":
                try:
                    image_data = self.root.clipboard_get(type="image/png")
                    if image_data:
                        image = Image.open(io.BytesIO(image_data))
                except tk.TclError:
                    pass
            else:
                if pyperclip:
                    data = pyperclip.paste()
                    if data.startswith("data:image/png;base64,"):
                        image_data = base64.b64decode(data.split(",")[1])
                        image = Image.open(io.BytesIO(image_data))
                    else:
                        raise ValueError("В буфере обмена нет изображения")
                else:
                    logger.error(
                        "Для вставки изображений в Linux установите pyperclip")
                    messagebox.showerror(
                        "Ошибка", "Для вставки изображений в Linux установите pyperclip"
                    )
                    return
            if not image:
                raise ValueError("Не удалось получить изображение из буфера")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"clipboard_{timestamp}.png"
            attachments_dir = self._ensure_note_attachments_dir(
                self.current_note)
            destination = os.path.join(attachments_dir, filename)
            image.save(destination, "PNG")
            thumbnail_path = self._generate_thumbnail(destination)
            cursor_position = self.text_area.index(tk.INSERT)
            self._insert_image(self.current_note, filename,
                               position=cursor_position)
            if "attachments" not in self.notes[self.current_note]:
                self.notes[self.current_note]["attachments"] = []
            self.notes[self.current_note]["attachments"].append(
                {
                    "type": "image",
                    "filename": filename,
                    "original_name": "clipboard.png",
                    "added": datetime.now().isoformat(),
                }
            )
            self.notes[self.current_note]["modified"] = datetime.now().isoformat()
            self._save_data()
            self._load_attachments()
            logger.info("Изображение из буфера обмена прикреплено")
            messagebox.showinfo(
                "Успешно", "Изображение из буфера обмена прикреплено!")
        except Exception as e:
            logger.error(f"Ошибка вставки изображения: {e}")
            messagebox.showerror(
                "Ошибка", f"Не удалось вставить изображение: {str(e)}")

    def duplicate_note(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Нет выбранной заметки для дублирования"
            )
            return
        self.copy_note()
        self.paste_note()
        logger.info("Заметка продублирована")

    def select_previous_note(self):
        current_selection = self.notes_listbox.curselection()
        if not current_selection:
            if self.notes_listbox.size() > 0:
                self.notes_listbox.selection_set(0)
                self.select_note()
            return
        current_index = current_selection[0]
        if current_index > 0:
            self.notes_listbox.selection_clear(current_index)
            self.notes_listbox.selection_set(current_index - 1)
            self.notes_listbox.see(current_index - 1)
            self.select_note()

    def select_next_note(self):
        current_selection = self.notes_listbox.curselection()
        if not current_selection:
            if self.notes_listbox.size() > 0:
                self.notes_listbox.selection_set(0)
                self.select_note()
            return
        current_index = current_selection[0]
        if current_index < self.notes_listbox.size() - 1:
            self.notes_listbox.selection_clear(current_index)
            self.notes_listbox.selection_set(current_index + 1)
            self.notes_listbox.see(current_index + 1)
            self.select_note()

    def select_first_note(self):
        if self.notes_listbox.size() > 0:
            self.notes_listbox.selection_clear(0, tk.END)
            self.notes_listbox.selection_set(0)
            self.notes_listbox.see(0)
            self.select_note()

    def select_last_note(self):
        if self.notes_listbox.size() > 0:
            last_index = self.notes_listbox.size() - 1
            self.notes_listbox.selection_clear(0, tk.END)
            self.notes_listbox.selection_set(last_index)
            self.notes_listbox.see(last_index)
            self.select_note()

    def close_current_note(self):
        if self.current_note:
            if self.autosave_timer:
                self.root.after_cancel(self.autosave_timer)
                self.autosave_timer = None
            self.current_note = None
            self.editor_frame.pack_forget()
            self.empty_label.pack(expand=True)
            self.notes_listbox.selection_clear(0, tk.END)

    def select_all_text(self, event=None):
        widget = event.widget
        if widget in [self.title_entry, self.text_area]:
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"

    def _handle_escape(self, event=None):
        if self.current_note:
            self.close_current_note()
        else:
            self.clear_search()

    def undo_text(self, event=None):
        widget = self.root.focus_get()
        if widget in [self.title_entry, self.text_area]:
            try:
                if widget.edit_modified():
                    widget.edit_undo()
                    widget.edit_modified(False)
            except tk.TclError:
                pass
        return "break"

    def redo_text(self, event=None):
        widget = self.root.focus_get()
        if widget in [self.title_entry, self.text_area]:
            try:
                widget.edit_redo()
            except tk.TclError:
                pass
        return "break"

    def toggle_bold(self, event=None):
        self._toggle_text_tag("bold")

    def toggle_italic(self, event=None):
        self._toggle_text_tag("italic")

    def toggle_underline(self, event=None):
        self._toggle_text_tag("underline")

    def change_text_color(self):
        color = colorchooser.askcolor(title="Выберите цвет текста")
        if color[1]:
            tag_name = f"color_{color[1]}"
            self.text_area.tag_configure(tag_name, foreground=color[1])
            self.color_tags[tag_name] = color[1]
            try:
                sel_start = self.text_area.index(tk.SEL_FIRST)
                sel_end = self.text_area.index(tk.SEL_LAST)
                self.text_area.tag_add(tag_name, sel_start, sel_end)
            except tk.TclError:
                cursor_pos = self.text_area.index(tk.INSERT)
                self.text_area.insert(cursor_pos, " ", (tag_name,))

    def change_font_size(self, event=None):
        try:
            size = int(self.font_size.get())
            new_tag = f"size_{size}"
            sel_start = self.text_area.index(tk.SEL_FIRST)
            sel_end = self.text_area.index(tk.SEL_LAST)
            for tag in self.text_area.tag_names():
                if tag.startswith("size_"):
                    self.text_area.tag_remove(tag, sel_start, sel_end)
            self.text_area.tag_add(new_tag, sel_start, sel_end)
        except tk.TclError:
            pass
        except ValueError:
            pass

    def insert_list(self, list_type: str):
        try:
            sel_start = self.text_area.index(tk.SEL_FIRST)
            sel_end = self.text_area.index(tk.SEL_LAST)
            text = self.text_area.get(sel_start, sel_end)
            lines = text.split("\n")
            new_lines = []
            if list_type == "bullet":
                for line in lines:
                    if line.strip():
                        new_lines.append(f"• {line}")
            else:
                for i, line in enumerate(lines):
                    if line.strip():
                        new_lines.append(f"{i+1}. {line}")
            new_text = "\n".join(new_lines)
            self.text_area.replace(sel_start, sel_end, new_text)
        except tk.TclError:
            cursor_pos = self.text_area.index(tk.INSERT)
            if list_type == "bullet":
                self.text_area.insert(cursor_pos, "• ")
            else:
                self.text_area.insert(cursor_pos, "1. ")

    def insert_table(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для вставки таблицы"
            )
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Создать таблицу")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Количество строк:").grid(
            row=0, column=0, padx=5, pady=5)
        rows_var = tk.StringVar(value="3")
        rows_entry = tk.Entry(dialog, textvariable=rows_var)
        rows_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Label(dialog, text="Количество столбцов:").grid(
            row=1, column=0, padx=5, pady=5
        )
        cols_var = tk.StringVar(value="3")
        cols_entry = tk.Entry(dialog, textvariable=cols_var)
        cols_entry.grid(row=1, column=1, padx=5, pady=5)
        tk.Label(dialog, text="Заголовки столбцов (через запятую):").grid(
            row=2, column=0, padx=5, pady=5
        )
        headers_var = tk.StringVar()
        headers_entry = tk.Entry(dialog, textvariable=headers_var)
        headers_entry.grid(row=2, column=1, padx=5, pady=5)

        def create_table():
            try:
                rows = int(rows_var.get())
                cols = int(cols_var.get())
                headers_str = headers_var.get()
                headers = [h.strip()
                           for h in headers_str.split(",") if h.strip()]
                if len(headers) != cols:
                    messagebox.showerror(
                        "Ошибка",
                        "Количество заголовков не совпадает с количеством столбцов",
                    )
                    return
                frame = tk.Frame(self.root)
                treeview = ttk.Treeview(
                    frame, columns=headers, show="headings", height=rows
                )
                treeview.pack(fill=tk.BOTH, expand=True)
                for header in headers:
                    treeview.heading(header, text=header)
                    treeview.column(header, width=100)
                for _ in range(rows):
                    treeview.insert("", "end", values=[""] * len(headers))
                position = self.text_area.index(tk.INSERT)
                table_id = str(uuid.uuid4())
                self.text_area.window_create(position, window=frame)
                self.table_frames[table_id] = frame
                self.tables[table_id] = treeview
                treeview.bind(
                    "<Double-1>", lambda e, tid=table_id: self._edit_table_cell(
                        e, tid)
                )
                treeview.bind(
                    "<Button-3>",
                    lambda e, tid=table_id: self._show_table_context_menu(
                        e, tid),
                )
                self.text_area.insert(position, "\n")
                self.text_area.mark_set(tk.INSERT, f"{position} + 1c")
                content = self.notes[self.current_note].get("content", [])
                content.append(
                    {
                        "type": "table",
                        "id": table_id,
                        "headers": headers,
                        "rows": [[""] * len(headers) for _ in range(rows)],
                    }
                )
                self.notes[self.current_note]["content"] = content
                dialog.destroy()
                messagebox.showinfo("Успех", "Таблица создана")
            except ValueError:
                messagebox.showerror(
                    "Ошибка", "Введите корректные числовые значения")

        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ok_btn = tk.Button(btn_frame, text="Создать", command=create_table)
        ok_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = tk.Button(btn_frame, text="Отмена",
                               command=dialog.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

    def _toggle_text_tag(self, tag_name):
        self.text_area.edit_separator()
        try:
            sel_start = self.text_area.index(tk.SEL_FIRST)
            sel_end = self.text_area.index(tk.SEL_LAST)
            if tag_name in self.text_area.tag_names(sel_start):
                self.text_area.tag_remove(tag_name, sel_start, sel_end)
            else:
                self.text_area.tag_add(tag_name, sel_start, sel_end)
        except tk.TclError:
            pass
        self.text_area.edit_separator()
        self._update_button_states()

    def _update_button_states(self, event=None):
        try:
            if self.text_area.tag_ranges(tk.SEL):
                start_index = self.text_area.index(tk.SEL_FIRST)
                tags = set(self.text_area.tag_names(start_index))
                self.bold_btn.configure(
                    style="ActiveTool.TButton" if "bold" in tags else "Tool.TButton"
                )
                self.italic_btn.configure(
                    style="ActiveTool.TButton" if "italic" in tags else "Tool.TButton"
                )
                self.underline_btn.configure(
                    style=(
                        "ActiveTool.TButton" if "underline" in tags else "Tool.TButton"
                    )
                )
        except (
            tk.TclError
        ):  # Указываем конкретное исключение для случая, когда нет выделения
            self.bold_btn.configure(style="Tool.TButton")
            self.italic_btn.configure(style="Tool.TButton")
            self.underline_btn.configure(style="Tool.TButton")

    def undo_action(self):
        try:
            self.text_area.edit_undo()
            self._update_button_states()
        except tk.TclError:
            pass

    def redo_action(self):
        try:
            self.text_area.edit_redo()
            self._update_button_states()
        except tk.TclError:
            pass

    def set_reminder(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для напоминания")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Установить напоминание")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Дата и время напоминания:").pack(pady=5)
        date_frame = tk.Frame(dialog)
        date_frame.pack(pady=5)
        tk.Label(date_frame, text="День:").grid(row=0, column=0)
        day_var = tk.StringVar(value=str(datetime.now().day))
        day_entry = tk.Entry(date_frame, textvariable=day_var, width=3)
        day_entry.grid(row=0, column=1)
        tk.Label(date_frame, text="Месяц:").grid(row=0, column=2)
        month_var = tk.StringVar(value=str(datetime.now().month))
        month_entry = tk.Entry(date_frame, textvariable=month_var, width=3)
        month_entry.grid(row=0, column=3)
        tk.Label(date_frame, text="Год:").grid(row=0, column=4)
        year_var = tk.StringVar(value=str(datetime.now().year))
        year_entry = tk.Entry(date_frame, textvariable=year_var, width=5)
        year_entry.grid(row=0, column=5)
        time_frame = tk.Frame(dialog)
        time_frame.pack(pady=5)
        tk.Label(time_frame, text="Часы:").grid(row=0, column=0)
        hour_var = tk.StringVar(value="12")
        hour_entry = tk.Entry(time_frame, textvariable=hour_var, width=3)
        hour_entry.grid(row=0, column=1)
        tk.Label(time_frame, text="Минуты:").grid(row=0, column=2)
        minute_var = tk.StringVar(value="00")
        minute_entry = tk.Entry(time_frame, textvariable=minute_var, width=3)
        minute_entry.grid(row=0, column=3)

        def set_reminder_time():
            try:
                day = int(day_var.get())
                month = int(month_var.get())
                year = int(year_var.get())
                hour = int(hour_var.get())
                minute = int(minute_var.get())
                reminder_time = datetime(year, month, day, hour, minute)
                if reminder_time < datetime.now():
                    messagebox.showerror(
                        "Ошибка", "Указанное время уже прошло")
                    return
                self.notes[self.current_note]["reminder"] = reminder_time.isoformat()
                self._save_data()
                self.load_note(self.current_note)
                dialog.destroy()
                messagebox.showinfo("Успех", "Напоминание установлено")
            except ValueError:
                messagebox.showerror("Ошибка", "Некорректные данные")

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        ok_btn = tk.Button(btn_frame, text="Установить",
                           command=set_reminder_time)
        ok_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = tk.Button(btn_frame, text="Отмена",
                               command=dialog.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

    def check_reminders(self):
        if not self.reminder_check_active:
            return
        now = datetime.now()
        for note_id, note_data in self.notes.items():
            if "reminder" in note_data:
                try:
                    reminder_time = datetime.fromisoformat(
                        note_data["reminder"])
                    if now >= reminder_time:
                        title = note_data.get("title", "Без названия")
                        messagebox.showinfo("Напоминание", f"Заметка: {title}")
                        del self.notes[note_id]["reminder"]
                        self._save_data()
                        self._load_notes_list()
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка обработки напоминания: {e}")
        self.root.after(60000, self.check_reminders)

    def export_note(self):
        if not self.current_note:
            messagebox.showwarning(
                "Предупреждение", "Выберите заметку для экспорта")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Текстовые файлы", "*.txt")]
        )
        if not file_path:
            return
        try:
            note_data = self.notes[self.current_note]
            title = note_data.get("title", "Без названия")
            content = ""
            for item in note_data.get("content", []):
                if item["type"] == "text":
                    content += item["value"] + "\n"
                elif item["type"] == "image":
                    content += f"[Изображение: {item['filename']}]\n"
                elif item["type"] == "table":
                    content += "Таблица:\n"
                    content += " | ".join(item["headers"]) + "\n"
                    content += "- | " * (len(item["headers"]) - 1) + "-\n"
                    for row in item["rows"]:
                        content += " | ".join(row) + "\n"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"{title}\n\n")
                f.write(content)
            messagebox.showinfo(
                "Успех", "Заметка экспортирована в текстовый файл")
        except Exception as e:
            messagebox.showerror(
                "Ошибка", f"Не удалось экспортировать заметку: {str(e)}"
            )

    def _setup_font_size_tags(self):
        sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24]
        for size in sizes:
            tag_name = f"size_{size}"
            self.text_area.tag_configure(tag_name, font=("Segoe UI", size))

    def import_note(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Текстовые файлы", "*.txt")])
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.create_note()
            if not self.current_note:
                return
            lines = content.splitlines()
            title = lines[0] if lines else "Импортированная заметка"
            body = "\n".join(lines[2:]) if len(lines) > 2 else ""
            self.title_entry.delete("1.0", tk.END)
            self.title_entry.insert("1.0", title)
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", body)
            self.save_current_note()
            messagebox.showinfo(
                "Успех", "Заметка импортирована из текстового файла")
        except Exception as e:
            messagebox.showerror(
                "Ошибка", f"Не удалось импортировать заметку: {str(e)}"
            )

    def show_help(self):
        help_text = (
            "📝 Мои Заметки - Руководство пользователя\n\n"
            "Горячие клавиши:\n"
            "- Ctrl+N: Создать новую заметку\n"
            "- Ctrl+S: Сохранить заметку\n"
            "- Ctrl+F: Поиск заметок\n"
            "- Ctrl+O: Прикрепить файл\n"
            "- Ctrl+R: Записать аудио\n"
            "- Ctrl+D: Дублировать заметку\n"
            "- Ctrl+V: Вставить текст или изображение\n"
            "- Ctrl+C: Копировать текст или заметку\n"
            "- Ctrl+B: Жирный текст\n"
            "- Ctrl+I: Курсив\n"
            "- Ctrl+U: Подчеркнутый текст\n"
            "- Ctrl+Z: Отменить\n"
            "- Ctrl+Y: Повторить\n"
            "- Delete: Удалить заметку\n"
            "- Esc: Очистить поиск или закрыть заметку\n"
            "- F1: Показать эту справку\n\n"
            "Функции:\n"
            "- Создание и редактирование заметок с форматированием текста\n"
            "- Вставка таблиц, изображений и файлов\n"
            "- Запись аудио\n"
            "- Установка напоминаний\n"
            "- Экспорт/импорт заметок в текстовые файлы\n"
            "- Автосохранение с настраиваемым интервалом\n"
            "- Поиск по заголовкам и содержимому\n"
        )
        help_window = tk.Toplevel(self.root)
        help_window.title("Справка")
        help_window.geometry("500x600")
        help_window.resizable(False, False)
        help_window.transient(self.root)
        help_window.grab_set()
        text_area = scrolledtext.ScrolledText(
            help_window, wrap=tk.WORD, font=("Segoe UI", 10), padx=10, pady=10
        )
        text_area.insert(tk.END, help_text)
        text_area.config(state=tk.DISABLED)
        text_area.pack(fill=tk.BOTH, expand=True)
        close_btn = ttk.Button(
            help_window,
            text="Закрыть",
            command=help_window.destroy,
            style="Primary.TButton",
        )
        close_btn.pack(pady=10)
        logger.info("Открыто окно справки")

    def show_autosave_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Настройки автосохранения")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Интервал автосохранения (мс):").pack(pady=5)
        interval_var = tk.StringVar(value=str(self.autosave_interval))
        interval_entry = tk.Entry(dialog, textvariable=interval_var)
        interval_entry.pack(pady=5)

        def save_settings():
            try:
                interval = int(interval_var.get())
                if interval < 1000:
                    messagebox.showerror(
                        "Ошибка", "Интервал должен быть не менее 1000 мс"
                    )
                    return
                self.autosave_interval = interval
                self._save_settings()
                dialog.destroy()
                messagebox.showinfo("Успех", "Настройки сохранены")
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное число")

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        ok_btn = ttk.Button(
            btn_frame, text="Сохранить", command=save_settings, style="Primary.TButton"
        )
        ok_btn.pack(side=tk.LEFT, padx=5)
        ok_btn.configure(style="CustomPrimary.TButton")
        cancel_btn = ttk.Button(
            btn_frame, text="Отмена", command=dialog.destroy, style="Secondary.TButton"
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)

    def _start_crop(self, canvas, edit_window):
        if not hasattr(edit_window, "original_image"):
            return
        canvas.bind(
            "<Button-1>", lambda e: self._start_crop_selection(
                e, canvas, edit_window)
        )
        canvas.bind(
            "<B1-Motion>", lambda e: self._update_crop_selection(
                e, canvas, edit_window)
        )
        canvas.bind(
            "<ButtonRelease-1>",
            lambda e: self._finish_crop_selection(e, canvas, edit_window),
        )
        self.edit_mode = "crop"
        canvas.config(cursor="crosshair")

    def _start_crop_selection(self, event, canvas, edit_window):
        edit_window.crop_start_x = canvas.canvasx(
            event.x) / edit_window.current_scale
        edit_window.crop_start_y = canvas.canvasy(
            event.y) / edit_window.current_scale
        edit_window.crop_rect = canvas.create_rectangle(
            0, 0, 0, 0, outline="red", dash=(4, 4)
        )

    def _update_crop_selection(self, event, canvas, edit_window):
        current_x = canvas.canvasx(event.x) / edit_window.current_scale
        current_y = canvas.canvasy(event.y) / edit_window.current_scale
        canvas.coords(
            edit_window.crop_rect,
            edit_window.crop_start_x * edit_window.current_scale,
            edit_window.crop_start_y * edit_window.current_scale,
            current_x * edit_window.current_scale,
            current_y * edit_window.current_scale,
        )

    def _finish_crop_selection(self, event, canvas, edit_window):
        if not hasattr(edit_window, "crop_start_x") or not hasattr(
            edit_window, "crop_start_y"
        ):
            return
        current_x = canvas.canvasx(event.x) / edit_window.current_scale
        current_y = canvas.canvasy(event.y) / edit_window.current_scale
        x1 = min(edit_window.crop_start_x, current_x)
        y1 = min(edit_window.crop_start_y, current_y)
        x2 = max(edit_window.crop_start_x, current_x)
        y2 = max(edit_window.crop_start_y, current_y)
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(edit_window.original_image.width, int(x2))
        y2 = min(edit_window.original_image.height, int(y2))
        if x2 > x1 and y2 > y1:
            cropped_image = edit_window.original_image.crop((x1, y1, x2, y2))
            edit_window.original_image = cropped_image
            self._show_scaled_image(canvas, cropped_image, edit_window)
        canvas.delete(edit_window.crop_rect)
        canvas.config(cursor="")
        self.edit_mode = None
        canvas.unbind("<Button-1>")
        canvas.unbind("<B1-Motion>")
        canvas.unbind("<ButtonRelease-1>")
        del edit_window.crop_start_x, edit_window.crop_start_y, edit_window.crop_rect

    def _resize_image(self, edit_window, image_path):
        dialog = tk.Toplevel(self.root)
        dialog.title("Изменить размер изображения")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Новый размер:").pack(pady=5)
        width_var = tk.StringVar(value=str(edit_window.original_image.width))
        height_var = tk.StringVar(value=str(edit_window.original_image.height))

        tk.Label(dialog, text="Ширина (пиксели):").pack()
        width_entry = tk.Entry(dialog, textvariable=width_var)
        width_entry.pack(pady=0.5)

        tk.Label(dialog, text="Высота (пиксели):").pack()
        height_entry = tk.Entry(dialog, textvariable=height_var)
        height_entry.pack(pady=5)

        def apply_resize():
            try:
                new_width = int(width_var.get())
                new_height = int(height_var.get())
                if new_width <= 0 or new_height <= 0:
                    messagebox.showerror(
                        "Ошибка", "Ширина и высота должны быть положительными"
                    )
                    return
                edit_window.original_image = edit_window.original_image.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )
                self._show_scaled_image(
                    Canvas, edit_window.original_image, edit_window)
                dialog.destroy()
                messagebox.showinfo("Успех", "Размер изображения изменен")
            except ValueError:
                messagebox.showerror(
                    "Ошибка", "Введите корректные числовые значения")

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        ok_btn = tk.Button(btn_frame, text="Применить", command=apply_resize)
        ok_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = tk.Button(btn_frame, text="Отмена",
                               command=dialog.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)


if __name__ == "__main__":
    try:
        app = NotesApp()
        app.run()
    except Exception as e:
        logger.critical(
            f"Критическая ошибка при запуске приложения: {e}", exc_info=True
        )
        messagebox.showerror(
            "Критическая ошибка", f"Не удалось запустить приложение: {str(e)}"
        )
