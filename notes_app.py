import numpy as np
from image_editor import ImageEditor
import json
import time
import os
import sys
import uuid
import shutil
import sounddevice as sd
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QSize, QDateTime, QPoint, QRect, QThread, Signal
from PySide6.QtGui import (QIcon, QColor, QPalette, QTextCursor, QAction,
                           QKeySequence, QPixmap, QImage, QPainter, QPen,
                           QTransform, QPolygonF, QPainterPath, QImageReader,
                           QFont, QKeySequence, QAction, QDesktopServices, QTextCharFormat,
                           QTextDocument)
from scipy.io.wavfile import write
from PySide6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout, QPushButton,
                            QListWidget, QListWidgetItem, QWidget, QFileDialog, QMessageBox,
                            QLabel, QHBoxLayout, QSplitter, QToolBar, QDockWidget, QDialog,
                            QColorDialog, QInputDialog, QLineEdit, QStyleFactory, QCheckBox,
                            QSpinBox, QDialogButtonBox, QFormLayout, QDateTimeEdit, QComboBox,
                            QScrollArea, QAbstractItemView, QSystemTrayIcon, QFontComboBox, QLayout,
                            QSizePolicy, QMenu)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        return self.itemList[index] if index < len(self.itemList) else None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x, y, lineHeight = rect.x(), rect.y(), 0
        for item in self.itemList:
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()

class CustomTextEdit(QTextEdit):
    def __init__(self, parent=None, paste_image_callback=None):
        super().__init__(parent)
        self.paste_image_callback = paste_image_callback

    def insertFromMimeData(self, source):
        if source.hasImage() and self.paste_image_callback:
            image = source.imageData()
            self.paste_image_callback(image)
        else:
            super().insertFromMimeData(source)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            main_window = self.window()
            if hasattr(main_window, "exit_note"):
                main_window.exit_note()
                return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()

        if char_format.isImageFormat():
            image_format = char_format.toImageFormat()
            image_path = image_format.name()
            if os.path.exists(image_path):
                from image_editor import ImageEditor
                editor = ImageEditor(image_path, self)
                editor.exec()
                return

        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        anchor = cursor.charFormat().anchorHref()
        if anchor:
            if anchor.startswith("file://"):
                path = anchor[7:]
                if os.path.exists(path):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                    return
            elif anchor.startswith("http://") or anchor.startswith("https://"):
                QDesktopServices.openUrl(QUrl(anchor))
                return

        super().mouseDoubleClickEvent(event)

class Note:
    def __init__(self, title, content, tags, favorite, timestamp, reminder, uuid):
        self.title = title
        self.content = content
        self.tags = tags
        self.favorite = favorite
        self.timestamp = timestamp
        self.reminder = reminder
        self.uuid = uuid


    def to_dict(self):
        return {
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "favorite": self.favorite,
            "timestamp": self.timestamp,
            "reminder": self.reminder,
            "uuid": self.uuid
        }

    @staticmethod
    def from_dict(data):
        return Note(
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            favorite=data.get("favorite", False),
            timestamp=data.get("timestamp", ""),
            reminder=data.get("reminder", None),
            uuid=data.get("uuid", str(uuid.uuid4()))
        )



class NotesApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Заметки")
        self.setGeometry(100, 100, 1000, 700)
        self.notes = []
        self.settings = QSettings("NPostnov", "NotesApp")
        self.init_toolbar()
        self.init_ui()
        self.list_widget = self.notes_list

        self.init_theme()
        self.load_settings()
        self.audio_recorder = None
        self.is_recording = False
        self.current_audio_path = ""
        self.audio_thread = None
        self.current_note = None
        self.notes_list.setMaximumWidth(250)
        self.notes_list.itemClicked.connect(self.load_note)
        self.init_all_components()

    def init_ui(self):
        self.notes_list = QListWidget()
        self.notes_list.setMaximumWidth(250)
        self.notes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self.show_notes_list_context_menu)

        self.text_edit = CustomTextEdit(paste_image_callback=self.insert_image_from_clipboard)
        self.text_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self.show_text_edit_context_menu)
        self.text_edit.setAcceptRichText(True)
        self.text_edit.setUndoRedoEnabled(True)
        self.text_edit.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_edit.setStyleSheet("font-size: 14px;")

        self.new_note_button = QPushButton("Новая заметка")
        self.save_note_button = QPushButton("Сохранить заметку")
        self.delete_note_button = QPushButton("Удалить заметку")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.new_note_button)
        button_layout.addWidget(self.save_note_button)
        button_layout.addWidget(self.delete_note_button)

        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.text_edit)
        editor_layout.addLayout(button_layout)

        editor_widget = QWidget()
        editor_widget.setLayout(editor_layout)

        splitter = QSplitter()
        splitter.addWidget(self.notes_list)
        splitter.addWidget(editor_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        central_widget = QWidget()
        self.main_layout = QVBoxLayout()

        self.main_layout.addWidget(self.toolbar_scroll)

        self.main_layout.addWidget(splitter)

        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)

        self.new_note_button.clicked.connect(self.new_note)
        self.save_note_button.clicked.connect(self.save_note)
        self.delete_note_button.clicked.connect(self.delete_note)

        self.notes_list.setDragEnabled(True)
        self.notes_list.setAcceptDrops(True)
        self.notes_list.setDropIndicatorShown(True)
        self.notes_list.setDefaultDropAction(Qt.MoveAction)
        self.notes_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.notes_list.model().rowsMoved.connect(self.handle_note_reorder)


    def show_text_edit_context_menu(self, position):
        menu = QMenu(self)

        copy_action = menu.addAction("Копировать")
        paste_action = menu.addAction("Вставить")
        cut_action = menu.addAction("Вырезать")
        clear_action = menu.addAction("Очистить всё")

        action = menu.exec(self.text_edit.mapToGlobal(position))

        if action == copy_action:
            self.text_edit.copy()
        elif action == paste_action:
            self.text_edit.paste()
        elif action == cut_action:
            self.text_edit.cut()
        elif action == clear_action:
            self.text_edit.clear()

    def show_notes_list_context_menu(self, position):
        menu = QMenu()

        open_action = menu.addAction("Открыть заметку")
        delete_action = menu.addAction("Удалить заметку")
        favorite_action = menu.addAction("Добавить в избранное")

        action = menu.exec(self.notes_list.viewport().mapToGlobal(position))

        item = self.notes_list.itemAt(position)
        if not item:
            return

        note = item.data(Qt.UserRole)

        if action == open_action:
            self.select_note(note)
        elif action == delete_action:
            self.notes = [n for n in self.notes if n.uuid != note.uuid]
            note_dir = os.path.join("Notes", note.uuid)
            if os.path.exists(note_dir):
                shutil.rmtree(note_dir)
            self.save_all_notes_to_disk()
            self.refresh_notes_list()
        elif action == favorite_action:
            note.favorite = not note.favorite
            self.refresh_notes_list()

    def handle_link_click(self, url):
        path = url.toLocalFile()
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


    def insert_audio_link(self, filepath):
        filename = os.path.basename(filepath)
        self.text_edit.insertHtml(f'<a href="file://{filepath}">{filename}</a><br>')
        self.save_note()

    def toggle_bold(self):
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            current_weight = cursor.charFormat().fontWeight()
            fmt.setFontWeight(QFont.Normal if current_weight > QFont.Normal else QFont.Bold)
            cursor.mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)

    def toggle_italic(self):
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontItalic(not cursor.charFormat().fontItalic())
            cursor.mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)

    def toggle_underline(self):
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
            cursor.mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)

    def exit_note(self):
        self.text_edit.clear()
        self.text_edit.clearFocus()
        self.current_note = None
        self.notes_list.clearSelection()
        self.refresh_notes_list()


    def toggle_audio_recording(self):
        if self.audio_thread and self.audio_thread.isRunning():
            self.audio_thread.stop()
            self.audio_thread = None
            self.audio_button.setText("🎙 Записать аудио")
        else:
            filename = str(uuid.uuid4()) + ".wav"
            folder_path = os.path.join("Notes", "Audio")
            os.makedirs(folder_path, exist_ok=True)
            full_path = os.path.join(folder_path, filename)

            class AudioRecorderThread(QThread):
                recording_finished = Signal(str)

                def __init__(self, file_path):
                    super().__init__()
                    self.file_path = file_path
                    self._running = True
                    self.audio_data = []

                def callback(self, indata, frames, time, status):
                    if self._running:
                        self.audio_data.append(indata.copy())

                def run(self):
                    try:
                        with sd.InputStream(samplerate=44100, channels=1, dtype='int16', callback=self.callback):
                            while self._running:
                                sd.sleep(100)
                        audio_array = np.concatenate(self.audio_data, axis=0)
                        write(self.file_path, 44100, audio_array)
                        self.recording_finished.emit(self.file_path)
                    except Exception as e:
                        print("Ошибка записи:", e)

                def stop(self):
                    self._running = False

            self.audio_thread = AudioRecorderThread(full_path)
            self.audio_thread.recording_finished.connect(
                self.insert_audio_link)
            self.audio_thread.start()
            self.audio_button.setText("⏹ Остановить запись")

    def init_toolbar(self):
        full_toolbar_widget = QWidget()
        full_layout = QVBoxLayout(full_toolbar_widget)
        full_layout.setContentsMargins(0, 0, 0, 0)
        full_layout.setSpacing(5)

        top_toolbar_widget = QWidget()
        flow_layout = FlowLayout(top_toolbar_widget)

        def add_tool_button(icon_path, tooltip, callback):
            button = QPushButton()
            button.setText(tooltip.split()[0])
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            button.setFixedSize(32, 32)
            flow_layout.addWidget(button)

        toggle_fav_button = QPushButton("⭐")
        toggle_fav_button.setToolTip("Добавить/удалить из избранного")
        toggle_fav_button.clicked.connect(self.toggle_favorite)
        flow_layout.addWidget(toggle_fav_button)

        add_tool_button("", "🏷 Тег", self.add_tag_to_note)
        add_tool_button("", "➕ Новая", self.create_new_note)
        add_tool_button("", "💾 Сохранить", self.save_note)
        add_tool_button("", "🗑 Удалить", self.delete_note)
        self.audio_button = QPushButton("🎤")
        self.audio_button.setToolTip("Записать аудио")
        self.audio_button.setFixedSize(32, 32)
        self.audio_button.clicked.connect(self.toggle_audio_recording)
        flow_layout.addWidget(self.audio_button)
        add_tool_button("", "🖼 Картинка", self.attach_file_to_note)
        add_tool_button("", "📊 Таблица", self.insert_table)
        add_tool_button("", "🔗 Ссылка", self.insert_link)
        add_tool_button("", "🔤 Цвет", self.change_text_color)
        add_tool_button("", "🎨 Фон", self.change_background_color)
        add_tool_button("", "⚙ Настройки", self.show_settings_window)
        add_tool_button("", "❓ Справка", self.show_help_window)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["По заголовку", "По дате", "Избранные"])
        self.sort_combo.setToolTip("Сортировка")
        self.sort_combo.currentIndexChanged.connect(self.apply_sorting)
        flow_layout.addWidget(self.sort_combo)

        self.sort_order_combo = QComboBox()
        self.sort_order_combo.addItems(["↑", "↓"])
        self.sort_order_combo.setToolTip("Порядок сортировки")
        self.sort_order_combo.currentIndexChanged.connect(self.apply_sorting)
        flow_layout.addWidget(self.sort_order_combo)

        self.search_mode_combo = QComboBox()
        self.search_mode_combo.addItems(["Заголовок", "Содержимое"])
        flow_layout.addWidget(self.search_mode_combo)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Поиск...")
        flow_layout.addWidget(self.search_bar)

        search_button = QPushButton("🔍")
        search_button.clicked.connect(self.trigger_search)
        flow_layout.addWidget(search_button)

        add_tool_button("", "𝐁", self.toggle_bold)
        add_tool_button("", "𝐼", self.toggle_italic)
        add_tool_button("", "U̲", self.toggle_underline)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("Times New Roman"))
        self.font_combo.currentFontChanged.connect(self.change_font)
        flow_layout.addWidget(self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 48)
        self.font_size_spin.setValue(14)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        flow_layout.addWidget(self.font_size_spin)

        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("Фильтр по тегу...")
        self.tag_filter.setFixedWidth(150)
        flow_layout.addWidget(self.tag_filter)

        tag_filter_button = QPushButton("Применить")
        tag_filter_button.clicked.connect(self.apply_tag_filter)
        flow_layout.addWidget(tag_filter_button)

        favorites_button = QPushButton("★ Избранные")
        favorites_button.clicked.connect(self.show_favorites_only)
        flow_layout.addWidget(favorites_button)

        reset_button = QPushButton("Сбросить фильтр")
        reset_button.clicked.connect(self.refresh_notes_list)
        flow_layout.addWidget(reset_button)

        reminder_layout = QHBoxLayout()
        reminder_layout.setContentsMargins(0, 0, 0, 0)
        reminder_layout.setSpacing(10)

        reminder_button = QPushButton("Установить напоминание")
        reminder_button.clicked.connect(self.set_reminder_for_note)

        remove_reminder_button = QPushButton("Удалить напоминание")
        remove_reminder_button.clicked.connect(self.remove_reminder_from_note)

        reminder_layout.addWidget(reminder_button)
        reminder_layout.addWidget(remove_reminder_button)

        reminder_layout.addStretch()

        bottom_toolbar_widget = QWidget()
        bottom_toolbar_widget.setLayout(reminder_layout)

        full_layout.addWidget(top_toolbar_widget)
        full_layout.addWidget(bottom_toolbar_widget)

        self.toolbar_scroll = QScrollArea()
        self.toolbar_scroll.setWidget(full_toolbar_widget)
        self.toolbar_scroll.setWidgetResizable(True)
        self.toolbar_scroll.setMaximumHeight(140)
        self.toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.search_bar.setFocusPolicy(Qt.FocusPolicy.ClickFocus)


    def handle_combined_search(self):
        tag = self.tag_filter.text().strip().lower()
        text = self.search_bar.text().strip().lower()
        mode = self.search_mode_combo.currentText()

        self.notes_list.clear()
        for note in self.notes:
            matches_tag = tag in [t.lower() for t in note.tags] if tag else True
            matches_search = False

            if mode == "Заголовок":
                matches_search = text in note.title.lower()
            elif mode == "Содержимое":
                doc = QTextDocument()
                doc.setHtml(note.content)
                plain_text = doc.toPlainText().lower()
                matches_search = text in plain_text
            elif not text:
                matches_search = True

            if matches_tag and matches_search:
                item = QListWidgetItem(note.title)
                item.setData(Qt.UserRole, note)
                if note.favorite:
                    item.setForeground(QColor("gold"))
                self.notes_list.addItem(item)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        
        copy_action = menu.addAction("Копировать всё")
        clear_action = menu.addAction("Очистить всё")
        
        action = menu.exec(event.globalPos())
        
        if action == copy_action:
            self.selectAll()
            self.copy()
        elif action == clear_action:
            self.clear()


    def change_font(self, font):
        self.text_edit.setCurrentFont(font)

    def change_font_size(self, size):
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)

    def trigger_search(self):
        self.handle_combined_search()

    def init_theme(self):
        theme = self.settings.value("theme", "dark")

        if theme == "dark":
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

    def insert_image_from_clipboard(self, image: QImage):
        if not self.current_note:
            QMessageBox.warning(self, "Нет заметки", "Пожалуйста, выберите или создайте заметку.")
            return

        note_dir = os.path.join("Notes", self.current_note.uuid)
        os.makedirs(note_dir, exist_ok=True)

        filename = f"clipboard_{uuid.uuid4().hex}.png"
        filepath = os.path.join(note_dir, filename)
        try:
            image.save(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изображение: {e}")
            return

        self.text_edit.insertHtml(f'<img src="{filepath}" width="200">')
        self.save_note()



    def new_note(self):
        title, ok = QInputDialog.getText(self, "Новая заметка", "Введите название:")
        if ok and title:
            # Проверка на дубликаты
            for note in self.notes:
                if note.title == title:
                    QMessageBox.warning(self, "Дубликат", f"Заметка с названием '{title}' уже существует.")
                    return

            note_uuid = str(uuid.uuid4())
            note = Note(
                title=title,
                content="",
                tags=[],
                favorite=False,
                timestamp=QDateTime.currentDateTime().toString(Qt.ISODate),
                reminder=None,
                uuid=note_uuid
            )
            self.notes.append(note)
            note_dir = os.path.join("Notes", note.uuid)
            os.makedirs(note_dir, exist_ok=True)

            self.current_note = note
            self.refresh_notes_list()
            self.show_note_with_attachments(note)
            self.text_edit.setFocus()

    def save_note(self):
        if self.current_note:
            self.current_note.content = self.text_edit.toHtml()
            self.save_note_to_file(self.current_note)
            self.refresh_notes_list()
            QMessageBox.information(self, "Сохранено", "Заметка успешно сохранена.")

    def show_notification(self, message):
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray_icon = QSystemTrayIcon(self)
            tray_icon.setIcon(QIcon("icon.png"))
            tray_icon.show()
            tray_icon.showMessage("Заметки", message, QSystemTrayIcon.Information, 3000)
        else:
            QMessageBox.information(self, "Заметки", message)

    def delete_note(self):
        selected_items = self.notes_list.selectedItems()
        if not selected_items:
            return

        reply = QMessageBox.question(
            self, "Удаление", "Удалить выбранную заметку?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            item = selected_items[0]
            note = item.data(Qt.UserRole)

            self.notes = [n for n in self.notes if n.uuid != note.uuid]

            note_dir = os.path.join("Notes", note.uuid)
            if os.path.exists(note_dir):
                try:
                    shutil.rmtree(note_dir)
                except Exception as e:
                    print(f"Ошибка при удалении файлов заметки: {e}")

            if self.current_note and self.current_note.uuid == note.uuid:
                self.current_note = None
                self.text_edit.clear()

            self.refresh_notes_list()
            self.save_all_notes_to_disk()

    def load_note(self, item):
        note = item.data(Qt.ItemDataRole.UserRole)
        self.select_note(note)

    def select_note(self, note):
        self.current_note = note
        self.show_note_with_attachments(note)

    def refresh_notes_list(self):
        self.notes_list.clear()
        for note in self.notes:
            item = QListWidgetItem(note.title)
            item.setData(Qt.UserRole, note)
            if note.favorite:
                item.setForeground(QColor("gold"))
            self.notes_list.addItem(item)
        self.search_bar.clear()
        self.tag_filter.clear()

    def toggle_favorite(self):
        if self.current_note:
            self.current_note.favorite = not self.current_note.favorite
            self.refresh_notes_list()

    def search_notes(self, text):
        self.notes_list.clear()
        for note in self.notes:
            if text.lower() in note.title.lower() or text.lower() in note.content.lower():
                item = QListWidgetItem(note.title)
                item.setData(Qt.ItemDataRole.UserRole, note)
                if note.favorite:
                    item.setForeground(QColor("gold"))
                self.notes_list.addItem(item)

    def show_favorites_only(self):
        self.notes_list.clear()
        for note in self.notes:
            if note.favorite:
                item = QListWidgetItem(note.title)
                item.setData(Qt.UserRole, note)
                item.setForeground(QColor("gold"))
                self.notes_list.addItem(item)

    def sort_notes_by_title(self):
        self.notes.sort(key=lambda note: note.title.lower())
        self.refresh_notes_list()

    def sort_notes_by_date(self):
        self.notes.sort(key=lambda note: note.timestamp, reverse=True)
        self.refresh_notes_list()

    def add_tag_to_note(self):
        if self.current_note:
            tag, ok = QInputDialog.getText(self, "Добавить тег", "Введите тег:")
            if ok and tag:
                if tag not in self.current_note.tags:
                    self.current_note.tags.append(tag)
                    QMessageBox.information(
                        self, "Тег добавлен", f"Тег '{tag}' ' добавлен к заметке."
                    )

    def get_all_tags(self):
        tags = set()
        for note in self.notes:
            tags.update(note.tags)
        return sorted(tags)
    
    def show_all_notes(self):
        self.refresh_notes_list()

    def show_notes_by_tag(self, tag):
        self.notes_list.clear()
        for note in self.notes:
            if tag in note.tags:
                item = QListWidgetItem(note.title)
                item.setData(Qt.ItemDataRole.UserRole, note)
                if note.favorite:
                    item.setForeground(QColor("gold"))
                self.notes_list.addItem(item)

    def apply_tag_filter(self):
        tag = self.tag_filter.text().strip()
        if tag:
            self.show_notes_by_tag(tag)

    def show_help_window(self):
        help_text = (
            "<h2>Справка - Заметки</h2>"
            "<ul>"
            "<li><b>Ctrl+N</b>: Создать новую заметку</li>"
            "<li><b>Ctrl+S</b>: Сохранить текущую заметку</li>"
            "<li><b>Del</b>: Удалить выбранную заметку</li>"
            "<li><b>Toggle Favorite</b>: Добавить/убрать из избранного</li>"
            "<li>Используйте строку поиска для фильтрации заметок по заголовку или содержимому.</li>"
            "<li>Use 'Добавить тег' to assign tags to a note.</li>"
            "<li>Введите название тега, чтобы отфильтровать заметки.</li>"
            "</ul>"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("Справка")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(help_text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    
    def show_settings_window(self):

        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки")
        layout = QFormLayout(dialog)

        theme_combo = QComboBox()
        theme_combo.addItems(["Светлая", "Тёмная"])
        theme_combo.setCurrentText("Тёмная" if self.settings.value("theme", "dark") == "dark" else "Светлая")

        layout.addRow("Тема оформления:", theme_combo)

        autosave_checkbox = QCheckBox()
        autosave_checkbox.setChecked(self.autosave_enabled)
        layout.addRow("Автосохранение:", autosave_checkbox)

        interval_spinbox = QSpinBox()
        interval_spinbox.setRange(1, 18000)
        interval_spinbox.setValue(self.autosave_interval // 1000)
        layout.addRow("Интервал автосохранения (сек):", interval_spinbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        dialog.setLayout(layout)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec():
            self.autosave_enabled = autosave_checkbox.isChecked()
            self.autosave_interval = interval_spinbox.value() * 1000
            self.settings.setValue("autosave_enabled", self.autosave_enabled)
            self.settings.setValue("autosave_interval", self.autosave_interval)
            if self.autosave_enabled:
                self.autosave_timer.start(self.autosave_interval)
            else:
                self.autosave_timer.stop()
            theme = theme_combo.currentText()
            if theme == "Тёмная":
                self.apply_dark_theme()
                self.settings.setValue("theme", "dark")
            else:
                self.apply_light_theme()
                self.settings.setValue("theme", "light")

    def rebuild_toolbar(self):
        if self.toolbar_scroll:
            self.layout().removeWidget(self.toolbar_scroll)
            self.toolbar_scroll.setParent(None)
            self.toolbar_scroll.deleteLater()
            self.toolbar_scroll = None
        self.init_toolbar()
        self.main_layout.insertWidget(0, self.toolbar_scroll)

    def add_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Файл")
        help_menu = menu_bar.addMenu("Справка")
        settings_menu = menu_bar.addMenu("Настройки")

        new_action = QAction("Новая заметка", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_note)
        file_menu.addAction(new_action)

        save_action = QAction("Сохранить заметку", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_note)
        file_menu.addAction(save_action)

        delete_action = QAction("Удалить заметку", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.delete_note)
        file_menu.addAction(delete_action)

        help_action = QAction("Справка:", self)
        help_action.setShortcut("F1")
        help_action.triggered.connect(self.show_help_window)
        help_menu.addAction(help_action)

        settings_action = QAction("Настройки:", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings_window)
        settings_menu.addAction(settings_action)

    def apply_dark_theme(self):
        self.setStyle(QStyleFactory.create("Fusion"))
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(142, 45, 197).lighter())
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.notes_list.setStyleSheet("color: white; background-color: #2b2b2b;")
        self.text_edit.setStyleSheet("font-size: 14px; color: white; background-color: #2b2b2b;")
        QApplication.instance().setPalette(dark_palette)
        self.setStyleSheet("""
                                QToolTip {
                                    background-color: #2a2a2a;
                                    color: white;
                                    border: 1px solid white;
                                    padding: 5px;
                                    font-size: 12px;
                                }
                            """)
        self.rebuild_toolbar()

    def apply_light_theme(self):
        self.setStyle(QStyleFactory.create("Fusion"))
        
        default_palette = QApplication.style().standardPalette()
        QApplication.instance().setPalette(default_palette)
        self.notes_list.setStyleSheet("color: black; background-color: white;")
        self.text_edit.setStyleSheet("font-size: 14px; color: black; background-color: white;")
        self.new_note_button.setStyleSheet("")
        self.save_note_button.setStyleSheet("")
        self.delete_note_button.setStyleSheet("")
        self.audio_button.setStyleSheet("")
        self.menuBar().setStyleSheet("")
        self.setStyleSheet("""
                                QToolTip {
                                    background-color: #ffffff;
                                    color: #000000;
                                    border: 1px solid #999;
                                    padding: 5px;
                                    font-size: 12px;
                                }""")
        self.rebuild_toolbar()

    def ensure_notes_directory(self):
        if not os.path.exists("Notes"):
            os.makedirs("Notes")

    def save_note_to_file(self, note: Note):
        self.ensure_notes_directory()
        note_dir = os.path.join("Notes", note.uuid)
        if not os.path.exists(note_dir):
            os.makedirs(note_dir)
        note_path = os.path.join(note_dir, "note.json")
        data = {
            "title": note.title,
            "content": note.content,
            "tags": note.tags,
            "favorite": note.favorite,
            "timestamp": note.timestamp if isinstance(note.timestamp, str) else note.timestamp.toString(Qt.ISODate),
            "reminder": getattr(note, "reminder", None)
        }
        try:
            with open(note_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить заметку: {e}")

    def load_notes_from_disk(self):
        self.notes.clear()
        notes_dir = os.path.join(os.getcwd(), "Notes")
        if not os.path.exists(notes_dir):
            return

        for note_folder in os.listdir(notes_dir):
            note_dir = os.path.join(notes_dir, note_folder)
            if not os.path.isdir(note_dir):
                continue

            note_file = os.path.join(note_dir, "note.json")
            if not os.path.exists(note_file):
                continue

            try:
                with open(note_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                note = Note.from_dict(data)

                self.notes.append(note)

            except Exception as e:
                print(f"Ошибка при загрузке заметки из {note_file}: {e}")

        self.refresh_notes_list()


    def attach_file_to_note(self):
        if not self.current_note:
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Прикрепить файл")
        if not file_path:
            return

        note_dir = os.path.join("Notes", self.current_note.uuid)
        os.makedirs(note_dir, exist_ok=True)

        file_name = os.path.basename(file_path)
        destination = os.path.join(note_dir, file_name)
        try:
            shutil.copy(file_path, destination)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось скопировать файл: {e}")
            return

        image_formats = QImageReader.supportedImageFormats()
        is_image = any(file_name.lower().endswith(fmt.data().decode()) for fmt in image_formats)

        if is_image:
            self.text_edit.insertHtml(f'<img src="{destination}" width="200">')
        else:
            self.text_edit.insertHtml(f'<a href="file://{destination}">{file_name}</a>')

        self.save_note()
        QMessageBox.information(
            self, "Файл прикреплён", f"Файл '{file_name}' прикреплён к заметке."
        )


    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.current_note:
            return

        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                note_dir = os.path.join("Notes", self.current_note.title)
                if not os.path.exists(note_dir):
                    os.makedirs(note_dir)
                shutil.copy(
                    file_path, os.path.join(
                        note_dir, os.path.basename(file_path))
                )

        QMessageBox.information(
            self, "Перетаскивание файлов", "Files dropped and прикреплён к заметке."
        )

    def list_attachments_for_current_note(self):
        if not self.current_note:
            return

        note_dir = os.path.join("Notes", self.current_note.title)
        if not os.path.exists(note_dir):
            return

        attachments = []
        for file_name in os.listdir(note_dir):
            if file_name != "note.txt":
                attachments.append(file_name)

        attachment_links = "\n".join(
            f'<a href="file://{os.path.abspath(os.path.join(note_dir, f))}">{f}</a>'
            for f in attachments
        )

        if attachment_links:
            self.text_edit.append("\n--- Attachments ---\n" + attachment_links)

    def show_note_with_attachments(self, note):
        if self.current_note:
            note = self.current_note
            self.text_edit.setHtml(note.content)

            note_dir = os.path.join("Notes", note.uuid)
            if not os.path.isdir(note_dir):
                return

            attachments = ""
            ignored_files = {"note.json", ".DS_Store", "Thumbs.db"}

            for file in os.listdir(note_dir):
                if file in ignored_files:
                    continue
                file_path = os.path.join(note_dir, file)

                if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                    continue  
                else:
                    link = f'<a href="file://{file_path}">{file}</a>'
                    attachments += link + "<br>"

            if attachments and "--- Attachments ---" not in note.content:
                note.content += "<br>--- Attachments ---<br>" + attachments
                self.text_edit.setHtml(note.content)

    def set_reminder_for_note(self):
        if not self.current_note:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Установить напоминание")
        layout = QFormLayout(dialog)

        datetime_edit = QDateTimeEdit(QDateTime.currentDateTime())
        datetime_edit.setCalendarPopup(True)
        layout.addRow("Напоминание Date & Time:", datetime_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            dt = datetime_edit.dateTime()
            self.current_note.reminder = dt.toString("yyyy-MM-dd HH:mm")
            QMessageBox.information(
                self, "Напоминание установлено", f"Напоминание установлено на {self.current_note.reminder}"
            )

    def remove_reminder_from_note(self):
        if self.current_note and hasattr(self.current_note, "reminder"):
            del self.current_note.reminder
            QMessageBox.information(
                self, "Напоминание удалено", "Напоминание было удалено."
            )

    def check_upcoming_reminders(self):
        now = QDateTime.currentDateTime()
        for note in self.notes:
            if hasattr(note, "reminder"):
                reminder_dt = QDateTime.fromString(
                    note.reminder, "yyyy-MM-dd HH:mm")
                if now.secsTo(reminder_dt) < 60 and now.secsTo(reminder_dt) > -60:
                    QMessageBox.information(
                        self, "Напоминание", f"Напоминание for note: {note.title}"
                    )

    def setup_reminder_timer(self):

        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_upcoming_reminders)
        self.reminder_timer.start(60000)

    def save_all_notes_to_disk(self):
            self.ensure_notes_directory()
            unique_notes = {}
            for note in self.notes:
                unique_notes[note.uuid] = note
            self.notes = list(unique_notes.values())
            for note in self.notes:
                self.save_note_to_file(note)


    def init_all_components(self):
        self.load_notes_from_disk()
        self.add_menu_bar()
        self.setup_reminder_timer()
        self.setAcceptDrops(True)

        self.autosave_enabled = self.settings.value("autosave_enabled", True, type=bool)
        self.autosave_interval = self.settings.value("autosave_interval", 300000, type=int)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave_current_note)
        if self.autosave_enabled:
            self.autosave_timer.start(self.autosave_interval)

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("lastNoteText", self.text_edit.toHtml())

    def load_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        last_text = self.settings.value("lastNoteText")
        if last_text:
            self.text_edit.setHtml(last_text)

    def change_text_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            cursor = self.text_edit.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            cursor.mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)



    def change_background_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            cursor = self.text_edit.textCursor()
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            cursor.mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)



    def insert_link(self):

        url, ok = QInputDialog.getText(self, "Вставить ссылку", "Введите ссылку:")
        if ok and url:
            label, ok2 = QInputDialog.getText(
                self, "Текст ссылки", "Введите отображаемый текст:")
            if ok2 and label:
                self.text_edit.insertHtml(f'<a href="{url}">{label}</a>')

    def insert_table(self):
        rows, ok1 = QInputDialog.getInt(self, "Вставить таблицу", "Количество строк:", 2, 1, 100)
        cols, ok2 = QInputDialog.getInt(self, "Вставить таблицу", "Количество столбцов:", 2, 1, 100)
        if ok1 and ok2:
            is_dark = self.settings.value("theme", "dark") == "dark"
            border_color = "white" if is_dark else "black"

            html = f"<table border='1' cellspacing='0' cellpadding='3' style='border-collapse:collapse; border: 1px solid {border_color};'>"
            for _ in range(rows):
                html += "<tr>"
                for _ in range(cols):
                    html += f"<td style='min-width:1em; padding:3px; border: 1px solid {border_color};'>&nbsp;</td>"
                html += "</tr>"
            html += "</table>"
            self.text_edit.insertHtml(html)


    def apply_sorting(self):
        index = self.sort_combo.currentIndex()
        if index == 0:
            reverse = self.sort_order_combo.currentIndex() == 1
            if index == 0:
                self.notes.sort(key=lambda note: note.title.lower(), reverse=reverse)
            elif index == 1:
                self.notes.sort(key=lambda note: note.timestamp, reverse=reverse)
            elif index == 2:
                self.show_favorites_only()
                return
            self.refresh_notes_list()
        elif index == 1:
            self.sort_notes_by_date()
        elif index == 2:
            self.show_favorites_only()

    def handle_note_reorder(self):
        new_order = []
        for i in range(self.notes_list.count()):
            item = self.notes_list.item(i)
            note = item.data(Qt.UserRole)
            new_order.append(note)
        self.notes = new_order
        self.save_all_notes_to_disk()

    def insert_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Вставить изображение", "", "Images (*.png *.xpm *.jpg *.bmp *.gif)"
        )
        if file_path:
            image_name = os.path.basename(file_path)
            note_dir = os.path.join("Notes", self.current_note.title)
            if not os.path.exists(note_dir):
                os.makedirs(note_dir)
            saved_path = os.path.join(note_dir, image_name)
            shutil.copy(file_path, saved_path)
            self.text_edit.insertHtml(f'<img src="{saved_path}" width="200">')

    def autosave_current_note(self):
        for note in self.notes:
            if note == self.current_note:
                note.content = self.text_edit.toHtml()
            self.save_note_to_file(note)



    def open_image_editor(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Редактировать изображение", "", "Images (*.png *.jpg *.bmp)"
        )
        if file_path:
            editor = ImageEditor(file_path, self)
            editor.exec()
    def create_new_note(self):
        self.new_note()

    def save_current_note(self):
        self.save_note()

    def delete_current_note(self):
        self.delete_note()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NotesApp()
    window.show()
    sys.exit(app.exec())