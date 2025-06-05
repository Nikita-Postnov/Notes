import glob
import tkinter as tk
from tkinter import (
    ttk, messagebox, simpledialog, filedialog, 
    colorchooser, scrolledtext
)
import json
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image, ImageTk
import subprocess
import platform
import re
import logging
import sys
import wave
import threading
import uuid
import webbrowser

# Проверка доступности дополнительных библиотек
try:
    import pyaudio
    pyaudio_available = True
except ImportError:
    pyaudio_available = False
    logging.warning("Pyaudio не установлен, запись аудио недоступна")

try:
    if platform.system() == "Windows":
        import winsound
        winsound_available = True
    else:
        winsound_available = False
except ImportError:
    winsound_available = False

try:
    import tkinterdnd2 as tkdnd
    from tkinterdnd2 import DND_FILES
    dnd_supported = True
except ImportError:
    dnd_supported = False
    logging.warning("TkinterDnD2 не установлен, перетаскивание файлов недоступно")

# Настройка системы логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("notes_app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

class ToolTip:
    """Всплывающие подсказки для элементов интерфейса"""
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = self.y = 0

    def show_tip(self):
        if self.tip_window:
            return
        self.x, self.y = self.widget.winfo_pointerxy()
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{self.x + 10}+{self.y + 10}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            bg="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide_tip(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

    def schedule_show(self):
        self.unschedule()
        self.id = self.widget.after(500, self.show_tip)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def bind_events(self):
        self.widget.bind("<Enter>", lambda e: self.schedule_show())
        self.widget.bind("<Leave>", lambda e: (self.unschedule(), self.hide_tip()))
        self.widget.bind("<ButtonPress>", lambda e: self.hide_tip())

class AudioRecorder:
    """Класс для записи аудио заметок"""
    
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio = pyaudio.PyAudio() if pyaudio_available else None
        self.stream = None

    def start_recording(self):
        if not pyaudio_available:
            return
        self.recording = True
        self.frames = []
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                frames_per_buffer=1024,
            )
            threading.Thread(target=self._record, daemon=True).start()
        except Exception as e:
            logger.error(f"Ошибка начала записи: {e}")
            self.recording = False

    def _record(self):
        while self.recording and self.stream:
            try:
                data = self.stream.read(1024, exception_on_overflow=False)
                self.frames.append(data)
            except Exception as e:
                logger.error(f"Ошибка записи: {e}")
                self.recording = False
                break

    def stop_recording(self):
        if not pyaudio_available or not self.stream:
            return []
        self.recording = False
        try:
            self.stream.stop_stream()
            self.stream.close()
            return self.frames
        except Exception as e:
            logger.error(f"Ошибка остановки записи: {e}")
            return []

    def save_recording(self, filename):
        try:
            wf = wave.open(filename, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"".join(self.frames))
            wf.close()
            logger.info(f"Аудиозапись сохранена: {filename}")
        except Exception as e:
            logger.error(f"Ошибка сохранения аудио: {e}")

    def __del__(self):
        if self.audio and pyaudio_available:
            self.audio.terminate()

class SettingsWindow:
    """Окно настроек приложения"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Настройки")
        self.window.geometry("400x300")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        
        self._create_widgets()

    def _create_widgets(self):
        # Фон заметки
        tk.Label(self.window, text="Цвет фона заметки:").pack(pady=(10, 5))
        self.bg_color_var = tk.StringVar(value=self.app.settings.get("note_bg", "#FFFFFF"))
        bg_frame = tk.Frame(self.window)
        bg_frame.pack(fill=tk.X, padx=20)
        tk.Entry(bg_frame, textvariable=self.bg_color_var, width=10).pack(side=tk.LEFT)
        ttk.Button(bg_frame, text="Выбрать", command=self._choose_bg_color).pack(
            side=tk.LEFT, padx=5
        )

        # Цвет текста
        tk.Label(self.window, text="Цвет текста:").pack(pady=(10, 5))
        self.text_color_var = tk.StringVar(value=self.app.settings.get("text_color", "#000000"))
        text_frame = tk.Frame(self.window)
        text_frame.pack(fill=tk.X, padx=20)
        tk.Entry(text_frame, textvariable=self.text_color_var, width=10).pack(side=tk.LEFT)
        ttk.Button(text_frame, text="Выбрать", command=self._choose_text_color).pack(
            side=tk.LEFT, padx=5
        )

        # Размер шрифта
        tk.Label(self.window, text="Размер шрифта:").pack(pady=(10, 5))
        self.font_size_var = tk.StringVar(value=self.app.settings.get("font_size", 11))
        ttk.Combobox(
            self.window,
            textvariable=self.font_size_var,
            values=["8", "9", "10", "11", "12", "14", "16", "18", "20"],
            state="readonly",
            width=10,
        ).pack()

        # Кнопки сохранения/отмены
        btn_frame = tk.Frame(self.window)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Сохранить", command=self.save_settings).pack(
            side=tk.LEFT, padx=10
        )
        ttk.Button(btn_frame, text="Отмена", command=self.window.destroy).pack(
            side=tk.LEFT
        )

    def _choose_bg_color(self):
        color = colorchooser.askcolor(title="Выберите цвет фона")[1]
        if color:
            self.bg_color_var.set(color)

    def _choose_text_color(self):
        color = colorchooser.askcolor(title="Выберите цвет текста")[1]
        if color:
            self.text_color_var.set(color)

    def save_settings(self):
        self.app.settings = {
            "note_bg": self.bg_color_var.get(),
            "text_color": self.text_color_var.get(),
            "font_size": int(self.font_size_var.get()),
        }
        self.app._save_settings()
        self.app._apply_settings()
        self.window.destroy()

class NotesApp:
    """Главное приложение для работы с заметками"""
    
    def __init__(self):
        self.notes = {}
        self.current_note = None
        self.format_timer = None
        self.root = tkdnd.TkinterDnD.Tk() if dnd_supported else tk.Tk()
        self.root.title("Мои заметки")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        self._init_defaults()
        self._setup_data()
        self._initialize_ui()
        self._setup_autosave()
        self._setup_backups()
        self._bind_events()
        self.text_area.tag_configure("hidden_image", elide=True)
        self.recorder = AudioRecorder()
        self.templates = self._load_templates()
        self.notification_sound = "notification.wav"
        self._schedule_reminder_check()
        
        logger.info("Приложение инициализировано")

    def _init_defaults(self):
        """Инициализация настроек по умолчанию"""
        self.colors = {
            "bg": "#f8f9fa",
            "sidebar": "#e9ecef",
            "primary": "#007bff",
            "secondary": "#6c757d",
            "text": "#343a40",
            "text_light": "#6c757d",
            "toolbar": "#e2e6ea",
            "accent": "#0078D4",
        }
        
        # Загрузка пользовательских настроек
        self.settings = self._load_settings()

    def _load_settings(self):
        """Загрузка настроек из файла"""
        settings_file = "settings.json"
        default_settings = {
            "note_bg": "#FFFFFF",
            "text_color": "#000000",
            "font_size": 11,
        }
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
        
        return default_settings

    def _save_settings(self):
        """Сохранение настроек в файл"""
        try:
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")

    def _apply_settings(self):
        """Применение настроек к интерфейсу"""
        # Обновляем цвет фона редактора
        if hasattr(self, 'text_area') and self.text_area:
            self.text_area.configure(
                bg=self.settings["note_bg"],
                fg=self.settings["text_color"],
                font=("Segoe UI", self.settings["font_size"]),
            )

        # Обновляем цвет заголовка
        if hasattr(self, 'title_entry') and self.title_entry:
            self.title_entry.configure(
                bg=self.settings["note_bg"],
                fg=self.settings["text_color"],
            )

    def _setup_data(self):
        """Инициализация данных приложения"""
        self.notes_file = "notes.json"
        self.attachments_base_dir = "attachments"
        self.backups_dir = "backups"
        self.notes = self._load_data()
        self.search_var = tk.StringVar()
        self.tag_filter = tk.StringVar(value="")
        self.autosave_timer = None
        self.autosave_interval = 3000  # 3 секунды
        self.backup_interval = 3600000  # 1 час
        self.reminder_check_active = True
        
        # Создаем необходимые директории
        for dir_path in [self.attachments_base_dir, self.backups_dir]:
            os.makedirs(dir_path, exist_ok=True)

    def _setup_backups(self):
        """Настройка системы резервного копирования"""
        self._create_backup()
        self.root.after(self.backup_interval, self._schedule_backup)

    def _schedule_backup(self):
        """Планирование регулярного резервного копирования"""
        if self.reminder_check_active:
            self._create_backup()
            self.root.after(self.backup_interval, self._schedule_backup)

    def _create_backup(self):
        """Создание резервной копии данных"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(
                self.backups_dir, f"notes_backup_{timestamp}.json"
            )
            if os.path.exists(self.notes_file):
                shutil.copy(self.notes_file, backup_file)
                self._clean_old_backups()
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")

    def _clean_old_backups(self):
        """Удаление старых резервных копий"""
        backups = sorted(
            glob.glob(os.path.join(self.backups_dir, "notes_backup_*.json")))
        max_backups = 10
        for old_backup in backups[:-max_backups]:
            try:
                os.remove(old_backup)
            except Exception as e:
                logger.error(f"Ошибка удаления резервной копии: {e}")

    def _get_note_attachments_dir(self, note_id: str) -> str:
        """Получение пути к папке с вложениями заметки"""
        return os.path.join(self.attachments_base_dir, f"note_{note_id}")

    def _ensure_note_attachments_dir(self, note_id: str) -> str:
        """Создание папки для вложений заметки"""
        note_dir = self._get_note_attachments_dir(note_id)
        os.makedirs(note_dir, exist_ok=True)
        return note_dir

    def _on_file_link_click(self, event):
        """Обработка клика по ссылке на файл"""
        self._open_attachment_by_name(self._get_link_text(event))

    def _on_video_link_click(self, event):
        """Обработка клика по ссылке на видео"""
        self._open_attachment_by_name(self._get_link_text(event))

    def _on_audio_link_click(self, event):
        """Обработка клика по ссылке на аудио"""
        self._open_attachment_by_name(self._get_link_text(event))

    def _on_web_link_click(self, event):
        """Обработка клика по веб-ссылке"""
        url = self._get_link_text(event)
        webbrowser.open(url)

    def _get_link_text(self, event):
        """Получение текста ссылки по позиции клика"""
        index = self.text_area.index(f"@{event.x},{event.y}")
        tags = self.text_area.tag_names(index)
        
        for tag in ["file_link", "video_link", "audio_link", "web_link", "image_link"]:
            if tag in tags:
                start_idx = self.text_area.tag_prevrange(tag, index)[0]
                end_idx = self.text_area.tag_nextrange(tag, index)[0]
                return self.text_area.get(start_idx, end_idx)
        return ""

    def _open_attachment_by_name(self, filename):
        """Открытие вложения по имени файла"""
        if not self.current_note:
            return
            
        attachments = self.notes[self.current_note].get("attachments", [])
        for idx, attachment in enumerate(attachments):
            if attachment.get("name") == filename:
                self._open_attachment_by_index(idx)
                return
        messagebox.showerror("Ошибка", f"Файл не найден: {filename}")

    def _open_attachment_by_index(self, idx):
        """Открытие вложения по индексу"""
        attachment = self.notes[self.current_note]["attachments"][idx]
        file_path = attachment.get("path", "")
        
        if not os.path.exists(file_path):
            messagebox.showerror("Ошибка", f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            logger.error(f"Ошибка открытия вложения: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {str(e)}")

    def _save_data(self):
        """Сохранение данных в файл"""
        try:
            if os.path.exists(self.notes_file):
                shutil.copy(self.notes_file, self.notes_file + ".bak")
            with open(self.notes_file, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=2)
            logger.info(f"Данные успешно сохранены в {self.notes_file}")
        except Exception as e:
            logger.error(f"Не удалось сохранить данные: {e}", exc_info=True)
            self.root.after(
                0,
                lambda error=e: messagebox.showerror(
                    "Ошибка",
                    f"Не удалось сохранить данные: {str(error)}. Проверьте права доступа к файлу.",
                ),
            )

    def _load_data(self) -> Dict[str, Dict[str, Any]]:
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.notes_file):
                with open(self.notes_file, "r", encoding="utf-8") as f:
                    notes = json.load(f)
                    if not isinstance(notes, dict):
                        logger.error("Некорректный формат файла заметок")
                        return {}
                    
                    # Конвертация старых форматов данных
                    for note_id, note_data in notes.items():
                        # Конвертация старого формата контента
                        if "content" in note_data and isinstance(note_data["content"], list):
                            # Преобразуем в новый строковый формат
                            content_parts = []
                            for item in note_data["content"]:
                                text = item.get("text", "")
                                tags = item.get("tags", [])
                                
                                # Применяем теги форматирования
                                formatted_text = text
                                for tag in tags:
                                    if tag == "bold":
                                        formatted_text = f"**{formatted_text}**"
                                    elif tag == "italic":
                                        formatted_text = f"_{formatted_text}_"
                                    elif tag == "underline":
                                        formatted_text = f"__{formatted_text}__"
                                
                                content_parts.append(formatted_text)
                            
                            note_data["content"] = "\n".join(content_parts)
                        
                        # Установка значений по умолчанию
                        note_data.setdefault("content", "")
                        note_data.setdefault("tags", [])
                        note_data.setdefault("reminder_recurring", "none")
                        note_data.setdefault("attachments", [])
                    
                    return notes
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            messagebox.showerror(
                "Ошибка", "Не удалось загрузить заметки. Создан новый файл."
            )
            return {}

    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Загрузка шаблонов заметок"""
        templates_file = "templates.json"
        try:
            if os.path.exists(templates_file):
                with open(templates_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблонов: {e}")
        
        return {
            "default": {
                "title": "Новая заметка",
                "content": "",
                "tags": [],
            },
            "todo": {
                "title": "Список дел",
                "content": "• Сделать задачу 1\n• Сделать задачу 2\n• Сделать задачу 3",
                "tags": ["todo", "tasks"],
            },
            "meeting": {
                "title": "Встреча",
                "content": "Дата: \nУчастники: \nПовестка: \n\nЗаметки:",
                "tags": ["meeting", "work"],
            }
        }

    def _save_templates(self):
        """Сохранение шаблонов заметок"""
        try:
            with open("templates.json", "w", encoding="utf-8") as f:
                json.dump(self.templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения шаблонов: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить шаблоны: {str(e)}")

    def _initialize_ui(self):
        """Инициализация пользовательского интерфейса"""
        self._setup_styles()
        self._create_header()
        self._create_main_interface()
        self._apply_settings()
        self._load_notes_list()
        
        if dnd_supported:
            self._setup_drop_target()
        
        # Центрирование окна
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_drop_target(self):
        """Настройка поддержки перетаскивания файлов"""
        try:
            self.text_area.drop_target_register(DND_FILES)
            self.attachments_listbox.drop_target_register(DND_FILES)
            self.text_area.dnd_bind("<<Drop>>", self._handle_drop)
            self.attachments_listbox.dnd_bind("<<Drop>>", self._handle_drop)
        except Exception as e:
            logger.error(f"Ошибка настройки перетаскивания: {e}")

    def _schedule_formatting(self, event=None):
        if self.format_timer:
            self.root.after_cancel(self.format_timer)
        self.format_timer = self.root.after(500, self._apply_markdown_formatting)

    def _apply_markdown_formatting(self):
        """Применяет форматирование на основе Markdown-разметки, удаляя символы форматирования"""
        if not self.current_note:
            return

        # Удаляем все существующие теги форматирования
        self.text_area.tag_remove("bold", "1.0", "end")
        self.text_area.tag_remove("italic", "1.0", "end")
        self.text_area.tag_remove("underline", "1.0", "end")

        # Получаем весь текст
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для жирного текста: **текст**
        bold_pattern = r"\*\*(.*?)\*\*"
        for match in reversed(list(re.finditer(bold_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 2} chars"
            content_end = f"1.0 + {match.end() - 2} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("bold", content_start, content_end)
            # Удаляем символы ** перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем текст после удаления
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для курсива: _текст_
        italic_pattern = r"_(.*?)_"
        for match in reversed(list(re.finditer(italic_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 1} chars"
            content_end = f"1.0 + {match.end() - 1} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("italic", content_start, content_end)
            # Удаляем символы _ перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем текст после удаления
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для подчеркнутого текста: __текст__
        underline_pattern = r"__(.*?)__"
        for match in reversed(list(re.finditer(underline_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 2} chars"
            content_end = f"1.0 + {match.end() - 2} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("underline", content_start, content_end)
            # Удаляем символы __ перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем содержимое заметки после форматирования
        content = self.text_area.get("1.0", "end-1c")
        self.notes[self.current_note]["content"] = content

    def _handle_drop(self, event):
        """Обработка перетаскивания файлов"""
        files = self.root.splitlist(event.data)
        if files:
            self.attach_files(files)

    def _setup_file_link_tags(self):
        """Настройка тегов для ссылок на файлы"""
        self.text_area.tag_configure("file_link", foreground="blue", underline=1)
        self.text_area.tag_bind(
            "file_link", "<Double-Button-1>", self._on_file_link_click
        )
        self.text_area.tag_configure("video_link", foreground="purple", underline=1)
        self.text_area.tag_bind(
            "video_link", "<Double-Button-1>", self._on_video_link_click
        )
        self.text_area.tag_configure("audio_link", foreground="green", underline=1)
        self.text_area.tag_bind(
            "audio_link", "<Double-Button-1>", self._on_audio_link_click
        )
        self.text_area.tag_configure("web_link", foreground="blue", underline=1)
        self.text_area.tag_bind("web_link", "<Button-1>", self._on_web_link_click
        )
        self.text_area.tag_configure("image_link", foreground="orange", underline=1)
        self.text_area.tag_bind(
            "image_link", "<Double-Button-1>", self._on_file_link_click)

    def _setup_styles(self):
        """Настройка стилей элементов интерфейса"""
        style = ttk.Style()
        style.configure(
            "TButton",
            font=("Segoe UI", 9),
            background=self.colors.get("toolbar", "#E8E8E8"),
            foreground=self.colors["text"],
        )
        style.map(
            "TButton",
            background=[("active", self.colors.get("accent", "#0078D4"))],
            foreground=[("active", "white")],
        )
        style.configure(
            "Tool.TButton",
            font=("Segoe UI", 9),
            background=self.colors.get("toolbar", "#E8E8E8"),
            foreground=self.colors["text"],
        )
        style.configure(
            "ActiveTool.TButton",
            font=("Segoe UI", 9),
            background=self.colors.get("accent", "#0078D4"),
            foreground="white",
        )
        style.configure(
            "TCombobox",
            font=("Segoe UI", 9),
            background=self.colors.get("toolbar", "#E8E8E8"),
            foreground=self.colors["text"],
        )
        style.configure(
            "Treeview",
            font=("Segoe UI", 10),
            background=self.colors["bg"],
            foreground=self.colors["text"],
            fieldbackground=self.colors["bg"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=self.colors["sidebar"],
            foreground=self.colors["text"],
        )

    def _create_header(self):
        header = tk.Frame(self.root, bg=self.colors["bg"], height=60)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)
        title_frame = tk.Frame(header, bg=self.colors["bg"])
        title_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        tk.Label(title_frame, text="NotesApp", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"]).pack(side=tk.LEFT)
        buttons_frame = tk.Frame(header, bg=self.colors["bg"])
        buttons_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        buttons = [
            ("✨ Новая", self.create_note),
            ("💾 Сохранить", self.save_current_note),
            ("📤 Экспорт", self.export_note),
            ("📎 Вложения", self.attach_files),
            ("⏰ Напоминание", self.set_reminder),
            ("⚙️ Настройки", self.open_settings),
        ]
        for text, command in buttons:
            btn = ttk.Button(buttons_frame, text=text, style="TButton", command=command)
            btn.pack(side=tk.LEFT, padx=5)

    def open_settings(self):
        SettingsWindow(self.root, self)

    def _create_main_interface(self):
        """Создание основного интерфейса"""
        main_frame = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Боковая панель
        sidebar_frame = tk.Frame(main_frame, width=300, bg=self.colors["sidebar"])
        sidebar_frame.pack_propagate(False)
        self._create_sidebar(sidebar_frame)
        main_frame.add(sidebar_frame)
        
        # Основная область
        self.editor_frame = tk.Frame(main_frame, bg=self.colors["bg"])
        self._create_editor(self.editor_frame)
        main_frame.add(self.editor_frame, stretch="always")
        
        # Заглушка при отсутствии выбранной заметки
        self.empty_label = tk.Label(
            self.editor_frame,
            text="Выберите или создайте заметку",
            font=("Segoe UI", 14),
            bg=self.colors["bg"],
            fg=self.colors["text_light"],
        )
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _create_sidebar(self, parent):
        """Создание боковой панели со списком заметок"""
        parent.configure(bg=self.colors["sidebar"])
        
        # Поиск заметок
        search_frame = tk.Frame(parent, bg=self.colors["sidebar"])
        search_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            search_frame,
            text="🔍 Поиск:",
            font=("Segoe UI", 10),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        ).pack(anchor=tk.W, pady=(0, 5))
        
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
        )
        search_entry.pack(fill=tk.X, pady=(0, 5))
        self.search_entry = search_entry
        self.search_var.trace("w", lambda *_: self._load_notes_list())
        
        # Фильтр по тегам
        tk.Label(
            search_frame,
            text="🏷️ Теги:",
            font=("Segoe UI", 10),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        ).pack(anchor=tk.W, pady=(10, 5))
        
        self.tag_entry = tk.Entry(
            search_frame,
            textvariable=self.tag_filter,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
        )
        self.tag_entry.pack(fill=tk.X, pady=(0, 5))
        self.tag_filter.trace("w", lambda *_: self._load_notes_list())
        
        # Список заметок
        notes_container = tk.Frame(parent, bg=self.colors["sidebar"])
        notes_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        scrollbar = tk.Scrollbar(notes_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.notes_listbox = tk.Listbox(
            notes_container,
            font=("Segoe UI", 11),
            relief="flat",
            bd=0,
            highlightthickness=0,
            selectbackground=self.colors.get("accent", "#0078D4"),
            selectforeground="white",
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
            yscrollcommand=scrollbar.set,
            height=20
        )
        self.notes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.notes_listbox.yview)
        
        self._setup_listbox_bindings()
        
        # Сортировка
        sort_frame = tk.Frame(parent, bg=self.colors["sidebar"])
        sort_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(
            sort_frame,
            text="Сортировка:",
            font=("Segoe UI", 10),
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
        ).pack(anchor=tk.W, pady=(0, 5))
        
        self.sort_options = {
            "Изменено (убыв.)": "modified_desc",
            "Изменено (возр.)": "modified_asc",
            "Создано (убыв.)": "created_desc",
            "Создано (возр.)": "created_asc",
            "Заголовок (А-Я)": "title_asc",
            "Заголовок (Я-А)": "title_desc",
        }
        
        self.sort_var = tk.StringVar(value="Изменено (убыв.)")
        sort_menu = ttk.Combobox(
            sort_frame,
            textvariable=self.sort_var,
            values=list(self.sort_options.keys()),
            state="readonly",
            font=("Segoe UI", 9),
        )
        sort_menu.pack(fill=tk.X, pady=(0, 5))
        sort_menu.bind("<<ComboboxSelected>>", lambda e: self._load_notes_list())

    def _setup_listbox_bindings(self):
        """Настройка обработчиков событий для списка заметок"""
        self.notes_listbox.bind("<<ListboxSelect>>", self.select_note)
        self.notes_listbox.bind("<Delete>", self.delete_selected_note)
        self.notes_listbox.bind("<Button-3>", self.show_context_menu)
        self.notes_listbox.bind("<Return>", self.select_note)
        self.notes_listbox.bind("<Double-Button-1>", self.select_note)

    def _create_editor(self, parent):
        """Создание редактора заметок"""
        parent.configure(bg=self.colors["bg"])
        
        # Область вложений
        self.attachments_frame = tk.LabelFrame(
            parent, 
            text=" 📎 Вложения ",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        )
        self.attachments_frame.pack(fill=tk.X, padx=10, pady=5)
        
        attachments_inner_frame = tk.Frame(self.attachments_frame, bg=self.colors["bg"])
        attachments_inner_frame.pack(fill=tk.BOTH, padx=5, pady=5)
        
        self.attachments_listbox = tk.Listbox(
            attachments_inner_frame,
            font=("Segoe UI", 10),
            height=3,
            relief="solid",
            bd=1,
            highlightthickness=0,
            selectbackground=self.colors.get("accent", "#0078D4"),
            selectforeground="white",
            bg=self.settings["note_bg"],
            fg=self.settings["text_color"],
        )
        self.attachments_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(
            attachments_inner_frame,
            orient=tk.VERTICAL,
            command=self.attachments_listbox.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.attachments_listbox.config(yscrollcommand=scrollbar.set)
        
        self.attachments_listbox.bind("<Double-1>", self._open_attachment)
        self.attachments_listbox.bind("<Button-3>", self._show_attachment_context_menu)
        
        # Область заголовка
        self.title_frame = tk.LabelFrame(
            parent, 
            text=" Заголовок ",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        )
        self.title_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.title_entry = tk.Text(
            self.title_frame,
            height=1,
            font=("Segoe UI", 14),
            relief="solid",
            bd=1,
            wrap=tk.WORD,
            fg=self.settings["text_color"],
            bg=self.settings["note_bg"],
            padx=5,
            pady=5
        )
        self.title_entry.pack(fill=tk.X, padx=5, pady=5)
        self.title_entry.bind("<KeyRelease>", lambda e: self._handle_text_change("title"))
        self.title_entry.bind("<Control-a>", self._select_all_text)
        
        # Область тегов
        tags_frame = tk.LabelFrame(
            parent, 
            text=" 🏷️ Теги ",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        )
        tags_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.tags_entry = tk.Entry(
            tags_frame,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
            fg=self.settings["text_color"],
            bg=self.settings["note_bg"],
        )
        self.tags_entry.pack(fill=tk.X, padx=5, pady=5)
        self.tags_entry.bind("<KeyRelease>", lambda e: self._handle_text_change("tags"))
        
        # Область текста
        text_frame = tk.LabelFrame(
            parent, 
            text=" Содержимое ",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        )
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Панель инструментов
        toolbar_frame = tk.Frame(text_frame, bg=self.colors["toolbar"], height=30)
        toolbar_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Кнопки форматирования
        tools = [
            ("Ж", self.toggle_bold, "Жирный текст (Ctrl+B)"),
            ("К", self.toggle_italic, "Курсив (Ctrl+I)"),
            ("Ч", self.toggle_underline, "Подчеркнутый текст (Ctrl+U)"),
            ("•", lambda: self.insert_list("bullet"), "Маркированный список"),
            ("1.", lambda: self.insert_list("numbered"), "Нумерованный список"),
            ("🎨", self.change_text_color, "Изменить цвет текста"),
            ("🔗", self.insert_link, "Вставить ссылку"),
            ("🖼️", self.insert_image, "Вставить изображение"),
        ]
        
        for text, command, tip in tools:
            btn = ttk.Button(
                toolbar_frame,
                text=text,
                width=3,
                command=command,
                style="Tool.TButton",
            )
            btn.pack(side=tk.LEFT, padx=2, pady=2)
            ToolTip(btn, tip).bind_events()
            
            # Сохраняем ссылки на кнопки форматирования
            if text == "Ж":
                self.bold_btn = btn
            elif text == "К":
                self.italic_btn = btn
            elif text == "Ч":
                self.underline_btn = btn
        
        # Разделитель
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, padx=5, fill=tk.Y
        )
        
        # Отменить/Повторить
        self.undo_btn = ttk.Button(
            toolbar_frame,
            text="↩",
            width=3,
            command=self.undo_action,
            style="Tool.TButton",
        )
        self.undo_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.undo_btn, "Отменить (Ctrl+Z)").bind_events()
        
        self.redo_btn = ttk.Button(
            toolbar_frame,
            text="↪",
            width=3,
            command=self.redo_action,
            style="Tool.TButton",
        )
        self.redo_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.redo_btn, "Повторить (Ctrl+Y)").bind_events()
        
        # Текстовое поле
        text_frame_inner = tk.Frame(text_frame, bg=self.colors["bg"])
        text_frame_inner.pack(fill=tk.BOTH, expand=True)
        
        scroll_y = tk.Scrollbar(text_frame_inner)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        scroll_x = tk.Scrollbar(text_frame_inner, orient=tk.HORIZONTAL)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.text_area = tk.Text(
            text_frame_inner,
            wrap=tk.WORD,
            font=("Segoe UI", self.settings["font_size"]),
            relief="solid",
            bd=1,
            undo=True,
            maxundo=-1,
            fg=self.settings["text_color"],
            bg=self.settings["note_bg"],
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
            padx=5,
            pady=5
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._setup_image_bindings()
        
        scroll_y.config(command=self.text_area.yview)
        scroll_x.config(command=self.text_area.xview)
        
        # Настройка тегов форматирования
        self._setup_text_tags()
        self._setup_file_link_tags()
        
        # Привязка событий
        self.text_area.bind("<KeyRelease>", self._update_button_states)
        self.text_area.bind("<ButtonRelease-1>", self._update_button_states)
        self.text_area.bind("<Control-z>", lambda e: self.undo_action())
        self.text_area.bind("<Control-y>", lambda e: self.redo_action())
        self.text_area.bind("<Control-b>", lambda e: self.toggle_bold())
        self.text_area.bind("<Control-i>", lambda e: self.toggle_italic())
        self.text_area.bind("<Control-u>", lambda e: self.toggle_underline())
        self.text_area.bind("<Button-3>", self.show_text_context_menu)
        
        # Информационная панель
        self.info_frame = tk.Frame(parent, bg=self.colors["bg"], height=20)
        self.info_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.text_area.bind("<KeyRelease>", self._schedule_formatting)
        
        self.info_label = tk.Label(
            self.info_frame,
            text="",
            font=("Segoe UI", 9),
            fg=self.colors["text_light"],
            bg=self.colors["bg"],
            anchor=tk.W
        )
        self.info_label.pack(fill=tk.X)

    def _setup_text_tags(self):
        """Настройка тегов форматирования текста"""
        self.text_area.tag_configure("bold", font=("Segoe UI", 11, "bold"))
        self.text_area.tag_configure("italic", font=("Segoe UI", 11, "italic"))
        self.text_area.tag_configure("underline", underline=True)
        self.text_area.tag_configure("highlight", background="yellow")
        
        # Теги для ссылок
        self.text_area.tag_configure("link", foreground="blue", underline=1)
        self.text_area.tag_bind("link", "<Button-1>", self._on_link_click)

    def _bind_events(self):
        """Привязка глобальных горячих клавиш"""
        self.root.bind("<Control-n>", lambda e: self.create_note())
        self.root.bind("<Control-s>", lambda e: self.save_current_note())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.root.bind("<Control-o>", lambda e: self.attach_files())
        self.root.bind("<Control-r>", lambda e: self.record_audio())
        self.root.bind("<Delete>", lambda e: self.delete_selected_note())
        self.root.bind("<F1>", lambda e: self.show_help())
        self.root.bind("<Escape>", lambda e: self.clear_editor())
        
        self.notes_listbox.bind("<Up>", lambda e: self._navigate_list(-1))
        self.notes_listbox.bind("<Down>", lambda e: self._navigate_list(1))

    def _navigate_list(self, direction: int):
        """Навигация по списку заметок"""
        if not self.notes_listbox.size():
            return
        selection = self.notes_listbox.curselection()
        index = selection[0] + direction if selection else 0
        index = max(0, min(index, self.notes_listbox.size() - 1))
        self.notes_listbox.selection_clear(0, tk.END)
        self.notes_listbox.selection_set(index)
        self.notes_listbox.see(index)
        self.select_note()

    def _load_notes_list(self):
        """Загрузка списка заметок с учетом фильтров"""
        self.notes_listbox.delete(0, tk.END)
        search_term = self.search_var.get().lower()
        tag_input = self.tag_filter.get().lower().strip()
        
        if tag_input:
            tag_terms = [t.strip() for t in tag_input.split(",") if t.strip()]
        else:
            tag_terms = []
        
        sort_key_value = self.sort_options.get(self.sort_var.get(), "modified_desc")
        reverse = "desc" in sort_key_value
        
        # Функции для сортировки
        sort_funcs = {
            "modified_desc": lambda x: datetime.fromisoformat(x[1].get("modified", "2000-01-01")),
            "modified_asc": lambda x: datetime.fromisoformat(x[1].get("modified", "2000-01-01")),
            "created_desc": lambda x: datetime.fromisoformat(x[1].get("created", "2000-01-01")),
            "created_asc": lambda x: datetime.fromisoformat(x[1].get("created", "2000-01-01")),
            "title_asc": lambda x: x[1].get("title", "").lower(),
            "title_desc": lambda x: x[1].get("title", "").lower(),
        }
        
        sort_func = sort_funcs[sort_key_value]
        sorted_notes = sorted(self.notes.items(), key=sort_func, reverse=reverse)
        
        # Фильтрация заметок
        for note_id, note_data in sorted_notes:
            # Фильтр по поиску
            if search_term:
                title_match = search_term in note_data.get("title", "").lower()
                content_match = search_term in note_data.get("content", "").lower()
                if not (title_match or content_match):
                    continue
            
            # Фильтр по тегам
            if tag_terms:
                note_tags = set(tag.lower() for tag in note_data.get("tags", []))
                if not all(tag in note_tags for tag in tag_terms):
                    continue
            
            # Добавление заметки в список
            title = note_data.get("title", "").strip() or "Без названия"
            date_str = self._format_date(note_data.get("modified"))
            tags = note_data.get("tags", [])
            tag_str = ", ".join(tags) if tags else ""
            
            display_text = f"{title}  ({date_str})"
            if tag_str:
                display_text += f"  [{tag_str}]"
            
            self.notes_listbox.insert(tk.END, display_text)
        
        # Автовыбор первой заметки
        if self.notes_listbox.size() > 0 and not self.current_note:
            self.notes_listbox.selection_set(0)
            self.notes_listbox.see(0)
            self.select_note()
        
        # Обновление информации
        notes_count = self.notes_listbox.size()
        self.info_label.config(text=f"Найдено заметок: {notes_count}")

    def _format_date(self, date_str: str) -> str:
        """Форматирование даты для отображения"""
        if not date_str:
            return "Нет даты"
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%d.%m.%Y %H:%M")
        except:
            return "Некорректная дата"

    def select_note(self, event=None):
        """Выбор заметки из списка"""
        selection = self.notes_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        filtered_notes = [
            note_id for note_id in self.notes 
            if self.notes_listbox.get(index).startswith(self.notes[note_id].get("title", ""))
        ]
        
        if filtered_notes:
            note_id = filtered_notes[0]
            self.select_note_by_id(note_id)

    def select_note_by_id(self, note_id: str):
        """Выбор заметки по идентификатору"""
        if note_id not in self.notes:
            logger.warning(f"Заметка с ID {note_id} не найдена")
            return
        
        self.current_note = note_id
        note_data = self.notes[note_id]
        
        # Показываем редактор
        self.empty_label.place_forget()
        
        # Загрузка заголовка
        self.title_entry.delete("1.0", tk.END)
        title = note_data.get("title", "")
        if title:
            self.title_entry.insert("1.0", title)
            self.title_entry.config(fg=self.settings["text_color"])
        
        # Загрузка тегов
        self.tags_entry.delete(0, tk.END)
        self.tags_entry.insert(0, ", ".join(note_data.get("tags", [])))
        self.tags_entry.config(fg=self.settings["text_color"])
        
        # Загрузка содержимого
        self.text_area.delete("1.0", tk.END)
        content = note_data.get("content", "")
        if content:
            self.text_area.insert("1.0", content)
            self.text_area.config(fg=self.settings["text_color"])
        
        # Восстановление миниатюр
        image_positions = note_data.get("image_positions", [])
        for pos_info in reversed(image_positions):  # Обратный порядок для корректной вставки
            path = pos_info["path"]
            if os.path.exists(path):
                img = Image.open(path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                self.text_area.image_create(pos_info["index"], image=photo)
                if not hasattr(self, 'images'):
                    self.images = []
                self.images.append(photo)
            else:
                logger.error(f"Файл не найден при восстановлении: {path}")
        
        # Загрузка вложений
        self._update_attachments()
        
        # Обновление информации
        created = self._format_date(note_data.get("created"))
        modified = self._format_date(note_data.get("modified"))
        reminder = note_data.get("reminder")
        reminder_text = f", Напоминание: {self._format_date(reminder)}" if reminder else ""
        self.info_label.config(
            text=f"Создано: {created}, Изменено: {modified}{reminder_text}"
        )

    def _restore_images_from_content(self):
        """Восстановление миниатюр из содержимого заметки"""
        content = self.text_area.get("1.0", "end-1c")
        import re
        positions = [(m.start(), m.end()) for m in re.finditer(r'!\[image\]\((.*?)\)', content)]
        for start, end in reversed(positions):  # Обратный порядок для корректной вставки
            path = re.search(r'!\[image\]\((.*?)\)', content[start:end]).group(1)
            if os.path.exists(path):
                img = Image.open(path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                index = f"1.0 + {start} chars"
                self.text_area.image_create(index, image=photo)
                if not hasattr(self, 'images'):
                    self.images = []
                self.images.append(photo)
            else:
                logger.error(f"Файл не найден при восстановлении: {path}")

    def _update_attachments(self):
        """Обновление списка вложений"""
        self.attachments_listbox.delete(0, tk.END)
        if not self.current_note:
            return
        
        attachments = self.notes[self.current_note].get("attachments", [])
        for attachment in attachments:
            filename = os.path.basename(attachment.get("path", "Unknown"))
            self.attachments_listbox.insert(tk.END, filename)

    def _open_attachment(self, event):
        """Открытие вложения"""
        selection = self.attachments_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        attachment = self.notes[self.current_note]["attachments"][idx]
        file_path = attachment.get("path", "")
        
        if not os.path.exists(file_path):
            messagebox.showerror("Ошибка", f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            logger.error(f"Ошибка открытия вложения: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {str(e)}")

    def _show_attachment_context_menu(self, event):
        """Контекстное меню для вложений"""
        selection = self.attachments_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(
            label="Открыть", 
            command=lambda: self._open_attachment(None)
        )
        context_menu.add_command(
            label="Удалить", 
            command=lambda: self._delete_attachment(idx)
        )
        context_menu.add_command(
            label="Показать в папке", 
            command=lambda: self._reveal_attachment(idx)
        )
        context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_attachment(self, idx: int):
        """Удаление вложения"""
        if not self.current_note:
            return
        
        attachments = self.notes[self.current_note]["attachments"]
        if idx >= len(attachments):
            return
        
        attachment = attachments[idx]
        file_path = attachment.get("path", "")
        
        if messagebox.askyesno("Подтверждение", "Удалить выбранное вложение?"):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                attachments.pop(idx)
                self._save_data()
                self._update_attachments()
            except Exception as e:
                logger.error(f"Ошибка удаления вложения: {e}")
                messagebox.showerror("Ошибка", f"Не удалось удалить файл: {str(e)}")

    def _reveal_attachment(self, idx: int):
        """Показать вложение в проводнике"""
        if not self.current_note:
            return
        
        attachments = self.notes[self.current_note]["attachments"]
        if idx >= len(attachments):
            return
        
        attachment = attachments[idx]
        file_path = attachment.get("path", "")
        
        if not os.path.exists(file_path):
            messagebox.showerror("Ошибка", f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                subprocess.run(f'explorer /select,"{file_path}"', shell=True)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            logger.error(f"Ошибка открытия папки: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть папку: {str(e)}")

    def clear_editor(self):
        """Очистка редактора и закрытие заметки"""
        self.current_note = None
        self.title_entry.delete("1.0", tk.END)
        self.title_entry.insert("1.0", "Введите заголовок...")
        self.title_entry.config(fg=self.colors["text_light"])
        
        self.tags_entry.delete(0, tk.END)
        self.tags_entry.insert(0, "Введите теги через запятую...")
        self.tags_entry.config(fg=self.colors["text_light"])
        
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", "Введите текст заметки...")
        self.text_area.config(fg=self.colors["text_light"])
        
        self.attachments_listbox.delete(0, tk.END)
        self.info_label.config(text="")
        
        # Показываем заглушку
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def create_note(self, template_name="default"):
        """Создание новой заметки"""
        template = self.templates.get(template_name, self.templates["default"])
        note_id = str(uuid.uuid4())
        
        self.notes[note_id] = {
            "title": template.get("title", "Новая заметка"),
            "content": template.get("content", ""),
            "tags": template.get("tags", []),
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "attachments": [],
            "reminder": None,
            "reminder_recurring": "none",
        }
        
        self._save_data()
        self._load_notes_list()
        self.select_note_by_id(note_id)
        
        # Фокусируемся на заголовке
        self.title_entry.focus_set()
        self.title_entry.tag_add(tk.SEL, "1.0", tk.END)

    def save_current_note(self):
        """Сохранение текущей заметки"""
        if not self.current_note:
            logger.warning("Попытка сохранения без выбранной заметки")
            messagebox.showwarning("Предупреждение", "Нет выбранной заметки для сохранения")
            return
        
        try:
            # Получаем данные из интерфейса
            title = self.title_entry.get("1.0", "end-1c").strip()
            if title == "Введите заголовок...":
                title = ""
            
            tags_str = self.tags_entry.get().strip()
            if tags_str == "Введите теги через запятую...":
                tags = []
            else:
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            
            content = self.text_area.get("1.0", "end-1c").strip()
            
            # Обновляем данные заметки
            self.notes[self.current_note].update({
                "title": title,
                "content": content,
                "tags": tags,
                "modified": datetime.now().isoformat(),
            })
            
            # Сохраняем
            self._save_data()
            self._load_notes_list()
            
            # Обновление информации
            self.info_label.config(text=f"Заметка сохранена: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении заметки: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось сохранить заметку: {str(e)}")

    def delete_selected_note(self, event=None):
        """Удаление выбранной заметки"""
        if not self.current_note:
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить выбранную заметку?"):
            # Удаляем вложения
            note_dir = self._get_note_attachments_dir(self.current_note)
            if os.path.exists(note_dir):
                try:
                    shutil.rmtree(note_dir)
                except Exception as e:
                    logger.error(f"Ошибка удаления папки вложений: {e}")
            
            # Удаляем заметку
            del self.notes[self.current_note]
            self._save_data()
            self.clear_editor()
            self._load_notes_list()

    def export_note(self):
        """Экспорт заметки в файл"""
        if not self.current_note:
            messagebox.showwarning("Предупреждение", "Выберите заметку для экспорта")
            return
        
        note_data = self.notes[self.current_note]
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("Markdown files", "*.md"),
                ("All files", "*.*")
            ],
            title="Экспорт заметки"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"Заголовок: {note_data.get('title', '')}\n")
                f.write(f"Теги: {', '.join(note_data.get('tags', []))}\n")
                f.write(f"Создано: {self._format_date(note_data.get('created'))}\n")
                f.write(f"Изменено: {self._format_date(note_data.get('modified'))}\n")
                
                if note_data.get("reminder"):
                    f.write(f"Напоминание: {self._format_date(note_data.get('reminder'))}\n")
                
                f.write("\n" + "-" * 50 + "\n\n")
                f.write(note_data.get("content", ""))
            
            messagebox.showinfo("Успех", "Заметка успешно экспортирована")
        except Exception as e:
            logger.error(f"Ошибка экспорта заметки: {e}")
            messagebox.showerror("Ошибка", f"Не удалось экспортировать заметку: {str(e)}")

    def attach_files(self, files=None):
        """Прикрепление файлов к заметке"""
        if not self.current_note:
            messagebox.showwarning("Предупреждение", "Выберите заметку")
            return
        
        if not files:
            files = filedialog.askopenfilenames(
                title="Выберите файлы для прикрепления"
            )
        
        if not files:
            return
        
        note_dir = self._ensure_note_attachments_dir(self.current_note)
        self.notes[self.current_note].setdefault("attachments", [])
        
        for file_path in files:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(note_dir, filename)
                
                # Проверяем существование файла
                if os.path.exists(dest_path):
                    if not messagebox.askyesno(
                        "Подтверждение", 
                        f"Файл '{filename}' уже существует. Заменить?"
                    ):
                        continue
                
                # Копируем файл
                shutil.copy(file_path, dest_path)
                
                # Добавляем в список вложений
                self.notes[self.current_note]["attachments"].append({
                    "path": dest_path,
                    "name": filename,
                    "added": datetime.now().isoformat()
                })
                
                # Сохраняем
                self._save_data()
                self._update_attachments()
                
            except Exception as e:
                logger.error(f"Ошибка добавления вложения: {e}")
                messagebox.showerror("Ошибка", f"Не удалось добавить файл: {str(e)}")

    def record_audio(self):
        """Запись аудио заметки"""
        if not self.current_note:
            messagebox.showwarning("Предупреждение", "Выберите заметку")
            return
        
        if not pyaudio_available:
            messagebox.showerror("Ошибка", "PyAudio не установлен")
            return
        
        if self.recorder.recording:
            # Остановка записи
            frames = self.recorder.stop_recording()
            note_dir = self._ensure_note_attachments_dir(self.current_note)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_file = os.path.join(note_dir, f"audio_{timestamp}.wav")
            
            self.recorder.save_recording(audio_file)
            self.notes[self.current_note].setdefault("attachments", [])
            self.notes[self.current_note]["attachments"].append({
                "path": audio_file,
                "name": f"audio_{timestamp}.wav",
                "type": "audio"
            })
            
            self._save_data()
            self._update_attachments()
            messagebox.showinfo("Успех", "Аудиозапись сохранена")
        else:
            # Начало записи
            self.recorder.start_recording()
            messagebox.showinfo(
                "Запись", 
                "Запись начата. Нажмите кнопку записи еще раз для остановки."
            )

    def set_reminder(self):
        """Установка напоминания"""
        if not self.current_note:
            messagebox.showwarning("Предупреждение", "Выберите заметку")
            return
        
        # Диалог установки даты/времени
        date_str = simpledialog.askstring(
            "Напоминание", 
            "Введите дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):"
        )
        
        if not date_str:
            return
        
        try:
            reminder_dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            if reminder_dt < datetime.now():
                messagebox.showerror("Ошибка", "Дата должна быть в будущем")
                return
            
            # Диалог установки повторения
            recurring = simpledialog.askstring(
                "Повторение", 
                "Повторение (none/daily/weekly):", 
                initialvalue="none"
            )
            
            if recurring not in ["none", "daily", "weekly"]:
                messagebox.showerror("Ошибка", "Недопустимый тип повторения")
                return
            
            # Сохраняем напоминание
            self.notes[self.current_note]["reminder"] = reminder_dt.isoformat()
            self.notes[self.current_note]["reminder_recurring"] = recurring
            self._save_data()
            
            messagebox.showinfo("Успех", "Напоминание установлено")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты")

    def _schedule_reminder_check(self):
        """Проверка напоминаний по расписанию"""
        if not self.reminder_check_active:
            return
        
        now = datetime.now()
        for note_id, note_data in self.notes.items():
            reminder_str = note_data.get("reminder")
            if not reminder_str:
                continue
            
            try:
                reminder_dt = datetime.fromisoformat(reminder_str)
                if now >= reminder_dt:
                    self._notify(note_data)
                    recurring = note_data.get("reminder_recurring", "none")
                    
                    if recurring == "none":
                        note_data["reminder"] = None
                    elif recurring == "daily":
                        note_data["reminder"] = (reminder_dt + timedelta(days=1)).isoformat()
                    elif recurring == "weekly":
                        note_data["reminder"] = (reminder_dt + timedelta(weeks=1)).isoformat()
                    
                    self._save_data()
            except Exception as e:
                logger.error(f"Ошибка обработки напоминания: {e}")
        
        self.root.after(60000, self._schedule_reminder_check)

    def _notify(self, note_data: Dict[str, Any]):
        """Уведомление о напоминании"""
        title = note_data.get("title", "Без названия")
        messagebox.showinfo("Напоминание", f"Напоминание: {title}")
        
        if winsound_available and os.path.exists(self.notification_sound):
            try:
                winsound.PlaySound(self.notification_sound, winsound.SND_FILENAME)
            except Exception as e:
                logger.error(f"Ошибка воспроизведения звука: {e}")

    def toggle_bold(self):
        try:
            if self.text_area.tag_ranges("sel"):
                start = self.text_area.index("sel.first")
                end = self.text_area.index("sel.last")
                selected_text = self.text_area.get(start, end)
                
                # Удаляем выделенный текст и вставляем с разметкой
                self.text_area.delete(start, end)
                self.text_area.insert(start, f"**{selected_text}**")
        except tk.TclError:
            pass

    def toggle_italic(self):
        try:
            if self.text_area.tag_ranges("sel"):
                start = self.text_area.index("sel.first")
                end = self.text_area.index("sel.last")
                selected_text = self.text_area.get(start, end)
                
                # Удаляем выделенный текст и вставляем с разметкой
                self.text_area.delete(start, end)
                self.text_area.insert(start, f"_{selected_text}_")
        except tk.TclError:
            pass


    def toggle_underline(self):
        try:
            if self.text_area.tag_ranges("sel"):
                start = self.text_area.index("sel.first")
                end = self.text_area.index("sel.last")
                selected_text = self.text_area.get(start, end)
                
                # Удаляем выделенный текст и вставляем с разметкой
                self.text_area.delete(start, end)
                self.text_area.insert(start, f"__{selected_text}__")
        except tk.TclError:
            pass

    def _update_button_states(self, event=None):
        try:
            # Проверяем, есть ли выделение
            if self.text_area.tag_ranges("sel"):
                # Получаем выделенный текст
                start = self.text_area.index("sel.first")
                end = self.text_area.index("sel.last")
                selected_text = self.text_area.get(start, end)
                
                # Проверяем наличие Markdown-разметки
                is_bold = selected_text.startswith("**") and selected_text.endswith("**")
                is_italic = selected_text.startswith("_") and selected_text.endswith("_")
                is_underline = selected_text.startswith("__") and selected_text.endswith("__")
                
                # Обновляем состояние кнопок
                self.bold_btn.configure(style="ActiveTool.TButton" if is_bold else "Tool.TButton")
                self.italic_btn.configure(style="ActiveTool.TButton" if is_italic else "Tool.TButton")
                self.underline_btn.configure(style="ActiveTool.TButton" if is_underline else "Tool.TButton")
            else:
                # Сбрасываем состояние кнопок
                self.bold_btn.configure(style="Tool.TButton")
                self.italic_btn.configure(style="Tool.TButton")
                self.underline_btn.configure(style="Tool.TButton")
                
        except tk.TclError:
            pass

    def insert_list(self, list_type: str):
        """Вставка списка (маркированного или нумерованного)"""
        try:
            # Получаем текущую позицию курсора
            cursor_pos = self.text_area.index(tk.INSERT)
            
            # Определяем начало текущей строки
            line_start = self.text_area.index(f"{cursor_pos} linestart")
            
            # Если курсор не в начале строки, добавляем новую строку
            if cursor_pos != line_start:
                self.text_area.insert(cursor_pos, "\n")
                # Обновляем позицию курсора после вставки новой строки
                cursor_pos = self.text_area.index(tk.INSERT)
            
            # Определяем символ для списка
            if list_type == "bullet":
                list_char = "• "
            else:  # numbered
                # Определяем номер следующего пункта
                prev_line_index = self.text_area.index(f"{cursor_pos} -1 line")
                prev_line = self.text_area.get(
                    f"{prev_line_index} linestart", 
                    f"{prev_line_index} lineend"
                ).strip()
                
                if prev_line and prev_line[0].isdigit() and '.' in prev_line:
                    try:
                        num = int(prev_line.split('.')[0]) + 1
                        list_char = f"{num}. "
                    except:
                        list_char = "1. "
                else:
                    list_char = "1. "
            
            # Вставляем символ списка в начале новой строки
            self.text_area.insert(cursor_pos, list_char)
            
        except tk.TclError:
            # Если нет выделения, просто вставляем новую строку с символом списка
            current_pos = self.text_area.index(tk.INSERT)
            self.text_area.insert(current_pos, "\n")
            if list_type == "bullet":
                self.text_area.insert(current_pos, "• ")
            else:
                self.text_area.insert(current_pos, "1. ")

    def change_text_color(self):
        """Изменение цвета текста"""
        color = colorchooser.askcolor(title="Выберите цвет текста")[1]
        if color:
            # Создаем уникальный тег для цвета
            color_tag = f"color_{color.replace('#', '')}"
            
            # Настраиваем тег, если он еще не существует
            if color_tag not in self.text_area.tag_names():
                self.text_area.tag_configure(color_tag, foreground=color)
            
            try:
                # Применяем тег к выделенному тексту
                self.text_area.tag_add(color_tag, "sel.first", "sel.last")
            except tk.TclError:
                # Если нет выделения, применяем к следующему вводимому тексту
                self.text_area.tag_add(color_tag, tk.INSERT)

    def undo_action(self):
        """Отмена последнего действия"""
        try:
            self.text_area.edit_undo()
        except tk.TclError:
            pass

    def redo_action(self):
        """Повтор последнего действия"""
        try:
            self.text_area.edit_redo()
        except tk.TclError:
            pass

    def insert_image(self):
        """Вставка изображения в заметку"""
        if not self.current_note:
            messagebox.showwarning("Предупреждение", "Выберите заметку")
            return
        
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")]
        )
        
        if not file_path:
            logger.info("Вставка изображения отменена пользователем")
            return
        
        try:
            # Копируем изображение во вложения
            note_dir = self._ensure_note_attachments_dir(self.current_note)
            filename = os.path.basename(file_path)
            dest_path = os.path.join(note_dir, filename)
            if os.path.exists(dest_path):
                if not messagebox.askyesno("Подтверждение", f"Файл '{filename}' уже существует. Заменить?"):
                    logger.info(f"Замена файла {filename} отклонена пользователем")
                    return
            shutil.copy(file_path, dest_path)
            logger.info(f"Файл изображения скопирован в {dest_path}")
            
            # Создаем миниатюру
            img = Image.open(dest_path)
            img.thumbnail((100, 100))
            logger.info(f"Размер миниатюры: {img.size}")
            photo = ImageTk.PhotoImage(img)
            
            # Вставляем миниатюру и разметку
            index = self.text_area.index(tk.INSERT)
            self.text_area.insert(index, "\n")
            index = self.text_area.index(tk.INSERT)
            self.text_area.image_create(index, image=photo)
            # Скрываем разметку как тег
            self.text_area.insert(index, "\n![image](" + dest_path + ")\n", ("hidden_image",))
            
            # Сохраняем ссылку на изображение
            if not hasattr(self, 'images'):
                self.images = []
            self.images.append(photo)
            
            # Сохраняем позицию и путь
            image_info = {"index": index, "path": dest_path}
            self.notes[self.current_note].setdefault("image_positions", [])
            self.notes[self.current_note]["image_positions"].append(image_info)
            logger.debug(f"Сохранена позиция изображения: {image_info}")
            
            # Обновляем содержимое заметки
            content = self.text_area.get("1.0", "end-1c")
            self.notes[self.current_note]["content"] = content
            
            # Сохраняем информацию о вложении
            self.notes[self.current_note].setdefault("attachments", [])
            self.notes[self.current_note]["attachments"].append({
                "path": dest_path,
                "name": filename,
                "type": "image"
            })
            
            self._save_data()
            self._update_attachments()
            logger.info(f"Изображение {filename} успешно добавлено к заметке {self.current_note}")
            
        except Exception as e:
            logger.error(f"Ошибка вставки изображения: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось вставить изображение: {str(e)}")

    def _ensure_note_attachments_dir(self, note_id: str) -> str:
        """Создание папки для вложений заметки"""
        note_dir = os.path.join(self.attachments_base_dir, f"note_{note_id}")
        os.makedirs(note_dir, exist_ok=True)
        return note_dir

    def _setup_image_bindings(self):
        # Привязываем двойной клик к текстовому полю
        self.text_area.bind("<Double-Button-1>", self._on_image_double_click)

    def _on_image_double_click(self, event):
        # Получаем позицию клика
        index = self.text_area.index(f"@{event.x},{event.y}")

        # Проверяем, есть ли изображение в этой или соседних позициях
        try:
            # Проверяем теги и изображения в окне клика
            tags = self.text_area.tag_names(index)
            if "hidden_image" in tags or self.text_area.image_cget(index, "image"):
                if self.current_note and "image_positions" in self.notes[self.current_note]:
                    min_distance = float('inf')
                    closest_path = None
                    
                    for pos_info in self.notes[self.current_note]["image_positions"]:
                        pos_index = pos_info["index"]
                        distance = abs(self.text_area.compare(index, ">=", pos_index) and
                                    self.text_area.compare(index, "<=", f"{pos_index} + 1 lines"))
                        if distance < min_distance:
                            min_distance = distance
                            closest_path = pos_info["path"]
                    
                    if closest_path and os.path.exists(closest_path):
                        self._open_image_in_new_window(closest_path)
                        return
                    elif closest_path:
                        messagebox.showerror("Ошибка", f"Файл изображения не найден: {closest_path}")
                        logger.error(f"Файл не найден: {closest_path}")
                    else:
                        logger.warning(f"Ближайший путь изображения не найден для позиции {index}")
            else:
                # Проверяем соседние позиции
                for offset in [-1, 0, 1]:
                    check_index = f"{index} + {offset} chars"
                    try:
                        if self.text_area.image_cget(check_index, "image"):
                            if self.current_note and "image_positions" in self.notes[self.current_note]:
                                for pos_info in self.notes[self.current_note]["image_positions"]:
                                    if self.text_area.compare(check_index, ">=", pos_info["index"]) and \
                                    self.text_area.compare(check_index, "<=", f"{pos_info['index']} + 1 lines"):
                                        path = pos_info["path"]
                                        if os.path.exists(path):
                                            self._open_image_in_new_window(path)
                                            return
                                        else:
                                            messagebox.showerror("Ошибка", f"Файл изображения не найден: {path}")
                                            logger.error(f"Файл не найден: {path}")
                                            return
                    except tk.TclError:
                        continue
                logger.warning(f"Разметка или путь изображения не найдены для позиции {index}")
        except tk.TclError:
            pass

    def _open_image_in_new_window(self, file_path):
        # Проверяем существование файла
        if not os.path.exists(file_path):
            messagebox.showerror("Ошибка", f"Файл изображения не найден: {file_path}")
            logger.error(f"Файл не найден: {file_path}")
            return

        # Создаем новое окно
        new_window = tk.Toplevel(self.root)
        new_window.title("Просмотр изображения")

        try:
            # Загружаем изображение
            img = Image.open(file_path)
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(new_window, image=photo)
            label.pack()

            # Сохраняем ссылку на изображение для нового окна
            new_window.image = photo
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {str(e)}")
            logger.error(f"Ошибка загрузки изображения: {e}", exc_info=True)
            new_window.destroy()

    def insert_link(self):
        """Вставка веб-ссылки в заметку"""
        try:
            url = simpledialog.askstring("Вставка ссылки", "Введите URL:")
            if not url:
                return
            
            text = simpledialog.askstring(
                "Вставка ссылки", 
                "Введите текст ссылки:", 
                initialvalue=url
            )
            
            if not text:
                return
            
            # Вставляем ссылку в текст
            self.text_area.insert(tk.INSERT, text, ("link",))
            
        except Exception as e:
            logger.error(f"Ошибка вставки ссылки: {e}")
            messagebox.showerror("Ошибка", f"Не удалось вставить ссылку: {str(e)}")

    def _on_link_click(self, event):
        """Обработка клика по ссылке"""
        # Получаем позицию клика
        index = self.text_area.index(f"@{event.x},{event.y}")
        
        # Получаем теги в этой позиции
        tags = self.text_area.tag_names(index)
        
        # Проверяем, есть ли тег "link" в месте клика
        if "link" in tags:
            link_range = self.text_area.tag_prevrange("link", index)
            if link_range:
                start_idx = link_range[0]
                end_idx = link_range[1]
                url = self.text_area.get(start_idx, end_idx)
                
                webbrowser.open(url)

    def _apply_markdown_formatting(self):
        """Применяет форматирование на основе Markdown-разметки, удаляя символы форматирования"""
        if not self.current_note:
            return

        # Удаляем все существующие теги форматирования
        self.text_area.tag_remove("bold", "1.0", "end")
        self.text_area.tag_remove("italic", "1.0", "end")
        self.text_area.tag_remove("underline", "1.0", "end")

        # Получаем весь текст
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для жирного текста: **текст**
        bold_pattern = r"\*\*(.*?)\*\*"
        for match in reversed(list(re.finditer(bold_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 2} chars"
            content_end = f"1.0 + {match.end() - 2} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("bold", content_start, content_end)
            # Удаляем символы ** перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем текст после удаления
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для курсива: _текст_
        italic_pattern = r"_(.*?)_"
        for match in reversed(list(re.finditer(italic_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 1} chars"
            content_end = f"1.0 + {match.end() - 1} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("italic", content_start, content_end)
            # Удаляем символы _ перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем текст после удаления
        full_text = self.text_area.get("1.0", "end-1c")

        # Применяем форматирование для подчеркнутого текста: __текст__
        underline_pattern = r"__(.*?)__"
        for match in reversed(list(re.finditer(underline_pattern, full_text))):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            content_start = f"1.0 + {match.start() + 2} chars"
            content_end = f"1.0 + {match.end() - 2} chars"

            # Применяем тег форматирования только к содержимому
            self.text_area.tag_add("underline", content_start, content_end)
            # Удаляем символы __ перед и после текста
            self.text_area.delete(content_end, end_idx)
            self.text_area.delete(start_idx, content_start)

        # Обновляем содержимое заметки после форматирования
        content = self.text_area.get("1.0", "end-1c")
        self.notes[self.current_note]["content"] = content

    def show_text_context_menu(self, event):
        """Контекстное меню для текстового поля"""
        context_menu = tk.Menu(self.root, tearoff=0)
        
        # Основные команды
        context_menu.add_command(
            label="Вырезать", 
            command=lambda: self.text_area.event_generate("<<Cut>>")
        )
        context_menu.add_command(
            label="Копировать",
            command=lambda: self.text_area.event_generate("<<Copy>>"),
        )
        context_menu.add_command(
            label="Вставить", 
            command=lambda: self.text_area.event_generate("<<Paste>>")
        )
        
        context_menu.add_separator()
        
        # Форматирование
        context_menu.add_command(label="Жирный", command=self.toggle_bold)
        context_menu.add_command(label="Курсив", command=self.toggle_italic)
        context_menu.add_command(label="Подчеркнутый", command=self.toggle_underline)
        
        context_menu.tk_popup(event.x_root, event.y_root)

    def show_context_menu(self, event):
        """Контекстное меню для списка заметок"""
        context_menu = tk.Menu(self.root, tearoff=0)
        
        # Основные команды
        context_menu.add_command(label="Новая заметка", command=self.create_note)
        context_menu.add_command(label="Удалить", command=self.delete_selected_note)
        context_menu.add_command(label="Экспорт", command=self.export_note)
        
        context_menu.add_separator()
        
        # Шаблоны
        submenu = tk.Menu(context_menu, tearoff=0)
        for template_name in self.templates:
            submenu.add_command(
                label=template_name.capitalize(),
                command=lambda t=template_name: self.create_note(t),
            )
        
        context_menu.add_cascade(label="Создать из шаблона", menu=submenu)
        context_menu.tk_popup(event.x_root, event.y_root)

    def open_settings(self):
        """Открытие окна настроек"""
        SettingsWindow(self.root, self)

    def show_help(self):
        """Отображение справки"""
        help_text = (
            "Горячие клавиши:\n"
            "Ctrl+N - Новая заметка\n"
            "Ctrl+S - Сохранить\n"
            "Ctrl+F - Поиск\n"
            "Ctrl+O - Прикрепить файл\n"
            "Ctrl+R - Запись аудио\n"
            "Delete - Удалить заметку\n"
            "Ctrl+B - Жирный текст\n"
            "Ctrl+I - Курсив\n"
            "Ctrl+U - Подчеркнутый текст\n"
            "Esc - Закрыть заметку\n"
            "F1 - Справка"
        )
        messagebox.showinfo("Справка", help_text)

    def _select_all_text(self, event):
        """Выделение всего текста"""
        widget = event.widget
        if isinstance(widget, tk.Text):
            widget.tag_add(tk.SEL, "1.0", tk.END)
            return "break"
        elif isinstance(widget, tk.Entry):
            widget.select_range(0, tk.END)
            return "break"

    def _handle_text_change(self, field: str):
        """Обработка изменений текста для автосохранения"""
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        
        self.autosave_timer = self.root.after(
            self.autosave_interval, 
            self.save_current_note
        )
        
        # Обновление информации о состоянии
        self.info_label.config(text="Изменения не сохранены...")

    def _setup_autosave(self):
        """Настройка системы автосохранения"""
        self.autosave_timer = None

    def _on_closing(self):
        """Обработка закрытия приложения"""
        self.reminder_check_active = False
        
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        
        self.save_current_note()
        self._save_data()
        self.root.destroy()

    def run(self):
        """Запуск главного цикла приложения"""
        self.root.mainloop()

if __name__ == "__main__":
    app = NotesApp()
    app.run()