from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QMessageBox
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor, QDesktopServices
import os
import sys
import uuid
import shutil
import sounddevice as sd
from scipy.io.wavfile import write
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QSize, QDateTime, QPoint, QRect
from PySide6.QtGui import (
    QIcon,
    QColor,
    QPalette,
    QTextCursor,
    QAction,
    QKeySequence,
    QPixmap,
    QImage,
    QPainter,
    QPen,
    QTransform,
    QPolygonF,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextEdit,
    QVBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QFileDialog,
    QMessageBox,
    QLabel,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QDockWidget,
    QDialog,
    QColorDialog,
    QInputDialog,
    QLineEdit,
)


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
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        anchor = cursor.charFormat().anchorHref()
        if anchor and anchor.startswith("file://"):
            path = anchor[7:]
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                return
        super().mouseDoubleClickEvent(event)

class ImageEditor(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Editor")
        self.image_path = image_path
        self.image = QPixmap(image_path)
        self.temp_image = self.image.copy()
        self.drawing = False
        self.last_point = QPoint()
        self.pen_color = QColor("red")
        self.pen_width = 3

        self.label = QLabel()
        self.label.setPixmap(self.temp_image)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.resize(self.temp_image.width(), self.temp_image.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.last_point = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.drawing:
            painter = QPainter(self.temp_image)
            pen = QPen(self.pen_color, self.pen_width)
            painter.setPen(pen)
            painter.drawLine(
                self.last_point, event.position().toPoint())
            self.last_point = event.position().toPoint()
            self.label.setPixmap(self.temp_image)

    def accept(self):
        self.temp_image.save(self.image_path)
        super().accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key.Key_S and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.lightGray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if getattr(self, "show_grid", False):
            painter = QPainter(self.label.pixmap())
            pen = QPen(QColor(200, 200, 200), 1, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            step = 20
            for x in range(0, self.temp_image.width(), step):
                painter.drawLine(x, 0, x, self.temp_image.height())
            for y in range(0, self.temp_image.height(), step):
                painter.drawLine(0, y, self.temp_image.width(), y)
            self.label.setPixmap(self.temp_image)
            painter.end()

    @staticmethod
    def open_image_action(parent=None):
        file_path, _ = QFileDialog.getOpenFileName(
            parent, "Выбрать изображение", "", "Images (*.png *.jpg *.bmp)"
        )
        if file_path:
            editor = ImageEditor(file_path, parent)
            editor.exec()

    def resizeEvent(self, event):
        if not self.temp_image.isNull():
            scaled = self.temp_image.scaled(
                self.label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.label.setPixmap(scaled)
        super().resizeEvent(event)

    def clear_canvas(self):
        self.temp_image = QPixmap(self.image.size())
        self.temp_image.fill(Qt.GlobalColor.white)
        self.label.setPixmap(self.temp_image)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import (
            QMenu,
            QColorDialog,
            QInputDialog,
            QFileDialog,
        )

        menu = QMenu(self)
        color_action = menu.addAction("Change Pen Color")
        width_action = menu.addAction("Change Pen Width")
        clear_action = menu.addAction("Clear Canvas")
        save_as_action = menu.addAction("Save As...")
        open_image_action = menu.addAction("Open Another Image")
        flip_horizontal_action = menu.addAction("Flip Horizontally")
        flip_vertical_action = menu.addAction("Flip Vertically")
        rotate_left_action = menu.addAction("Rotate Left")
        rotate_right_action = menu.addAction("Rotate Right")

        action = menu.exec(event.globalPosition().toPoint())

        if action == color_action:
            color = QColorDialog.getColor()
            if color.isValid():
                self.pen_color = color

        elif action == width_action:
            width, ok = QInputDialog.getInt(
                self, "Pen Width", "Enter pen width:", self.pen_width, 1, 20
            )
            if ok:
                self.pen_width = width

        elif action == clear_action:
            self.clear_canvas()

        elif action == save_as_action:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Image As",
                self.image_path,
                "Images (*.png *.jpg *.bmp)",
            )
            if file_path:
                self.temp_image.save(file_path)

        elif action == open_image_action:
            new_path, _ = QFileDialog.getOpenFileName(
                self, "Open Image", "", "Images (*.png *.jpg *.bmp)"
            )
            if new_path:
                self.image_path = new_path
                self.image = QPixmap(new_path)
                self.temp_image = self.image.copy()
                self.label.setPixmap(self.temp_image.scaled(
                    self.label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))


        elif action == flip_horizontal_action:
            self.temp_image = self.temp_image.transformed(
                QTransform().scale(-1, 1)
            )
            self.label.setPixmap(self.temp_image)

        elif action == flip_vertical_action:
            self.temp_image = self.temp_image.transformed(
                QTransform().scale(1, -1)
            )
            self.label.setPixmap(self.temp_image)

        elif action == rotate_left_action:
            transform = QTransform().rotate(-90)
            self.temp_image = self.temp_image.transformed(transform)
            self.label.setPixmap(self.temp_image)

        elif action == rotate_right_action:
            transform = QTransform().rotate(90)
            self.temp_image = self.temp_image.transformed(transform)
            self.label.setPixmap(self.temp_image)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.pen_width = min(self.pen_width + 1, 50)
        else:
            self.pen_width = max(self.pen_width - 1, 1)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()  # точка на экране
            label_pos = self.label.mapFrom(self, pos)  # переводим в координаты QLabel

            if not self.temp_image or self.temp_image.isNull():
                return

            pixmap = self.temp_image.copy()
            painter = QPainter(pixmap)
            pen = QPen(Qt.GlobalColor.red, 4)
            painter.setPen(pen)

            # Преобразуем координаты точки к масштабированному изображению
            scaled_label_size = self.label.size()
            original_image_size = self.temp_image.size()

            x_ratio = original_image_size.width() / scaled_label_size.width()
            y_ratio = original_image_size.height() / scaled_label_size.height()

            image_x = int(label_pos.x() * x_ratio)
            image_y = int(label_pos.y() * y_ratio)

            # Нарисовать кружок в точке
            painter.drawEllipse(QPoint(image_x, image_y), 10, 10)
            painter.end()

            self.temp_image = pixmap
            self.label.setPixmap(pixmap.scaled(
                self.label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            ))

        super().mouseDoubleClickEvent(event)


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.contextMenuEvent(event)


    def mouseDoubleClickTextBox(self):
        from PySide6.QtWidgets import (
            QDialog,
            QTextEdit,
            QDialogButtonBox,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Insert Multiline Text")

        text_edit = QTextEdit()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout = QVBoxLayout()
        layout.addWidget(text_edit)
        layout.addWidget(buttons)
        dialog.setLayout(layout)

        if dialog.exec():
            multiline_text = text_edit.toPlainText()
            painter = QPainter(self.temp_image)
            painter.setPen(QPen(self.pen_color, self.pen_width))
            painter.drawText(50, 50, multiline_text)
            self.label.setPixmap(self.temp_image)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_T:
            self.mouseDoubleClickTextBox()
        elif event.key() == Qt.Key.Key_C:
            self.clear_canvas()
        elif event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.pen_width = min(self.pen_width + 1, 50)
        elif event.key() == Qt.Key.Key_Minus:
            self.pen_width = max(self.pen_width - 1, 1)
        elif event.key() == Qt.Key.Key_F:
            from PySide6.QtWidgets import QColorDialog

            color = QColorDialog.getColor()
            if color.isValid():
                self.pen_color = color

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            image_path = url.toLocalFile()
            if os.path.exists(image_path):
                self.image_path = image_path
                self.image = QPixmap(image_path)
                self.temp_image = self.image.copy()
                self.label.setPixmap(self.temp_image)
                break

    def save_snapshot(self):
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Snapshot", "snapshot.png", "Images (*.png *.jpg *.bmp)"
        )
        if file_path:
            self.temp_image.save(file_path)

    def export_to_pdf(self):
        from PySide6.QtGui import QPainter, QPdfWriter
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", "drawing.pdf", "PDF Files (*.pdf)"
        )
        if file_path:
            pdf_writer = QPdfWriter(file_path)
            pdf_writer.setPageSizeMM(self.temp_image.size())
            painter = QPainter(pdf_writer)
            painter.drawPixmap(0, 0, self.temp_image)
            painter.end()

    def copy_to_clipboard(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setPixmap(self.temp_image)

    def paste_from_clipboard(self):
        from PySide6.QtWidgets import QApplication

        clipboard_image = QApplication.clipboard().image()
        if not clipboard_image.isNull():
            self.temp_image = QPixmap.fromImage(clipboard_image)
            self.label.setPixmap(self.temp_image)

    def resize_canvas(self, width: int, height: int):
        new_image = QPixmap(width, height)
        new_image.fill(Qt.GlobalColor.white)
        painter = QPainter(new_image)
        painter.drawPixmap(0, 0, self.temp_image)
        painter.end()
        self.temp_image = new_image
        self.label.setPixmap(self.temp_image)

    def ask_resize_canvas(self):
        from PySide6.QtWidgets import QInputDialog

        w, ok1 = QInputDialog.getInt(
            self, "Resize Canvas", "Width:", self.temp_image.width(), 100, 5000
        )
        h, ok2 = QInputDialog.getInt(
            self,
            "Resize Canvas",
            "Height:",
            self.temp_image.height(),
            100,
            5000,
        )
        if ok1 and ok2:
            self.resize_canvas(w, h)

    def toggle_grid_overlay(self):
        self.show_grid = not getattr(self, "show_grid", False)
        self.update()

    def blur_image(self):
        from PySide6.QtGui import QImage, QPainterPath

        image = self.temp_image.toImage().convertToFormat(
            QImage.Format.Format_ARGB32
        )
        blurred = QPixmap(self.temp_image.size())
        blurred.fill(Qt.GlobalColor.transparent)

        painter = QPainter(blurred)
        painter.setOpacity(0.5)
        for i in range(5):
            painter.drawImage(0, 0, image)
        painter.end()

        self.temp_image = blurred
        self.label.setPixmap(self.temp_image)

    def invert_colors(self):
        image = self.temp_image.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                inverted = QColor(
                    255 - pixel.red(), 255 - pixel.green(), 255 - pixel.blue()
                )
                image.setPixelColor(x, y, inverted)
        self.temp_image = QPixmap.fromImage(image)
        self.label.setPixmap(self.temp_image)

    def convert_to_grayscale(self):
        image = self.temp_image.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                gray = int(
                    0.3 * pixel.red()
                    + 0.59 * pixel.green()
                    + 0.11 * pixel.blue()
                )
                image.setPixelColor(x, y, QColor(gray, gray, gray))
        self.temp_image = QPixmap.fromImage(image)
        self.label.setPixmap(self.temp_image)

    def apply_sepia_filter(self):
        image = self.temp_image.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                tr = int(
                    0.393 * pixel.red()
                    + 0.769 * pixel.green()
                    + 0.189 * pixel.blue()
                )
                tg = int(
                    0.349 * pixel.red()
                    + 0.686 * pixel.green()
                    + 0.168 * pixel.blue()
                )
                tb = int(
                    0.272 * pixel.red()
                    + 0.534 * pixel.green()
                    + 0.131 * pixel.blue()
                )
                image.setPixelColor(
                    x, y, QColor(min(tr, 255), min(
                        tg, 255), min(tb, 255))
                )
        self.temp_image = QPixmap.fromImage(image)
        self.label.setPixmap(self.temp_image)

    def adjust_brightness(self, factor):
        image = self.temp_image.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                r = min(max(int(pixel.red() * factor), 0), 255)
                g = min(max(int(pixel.green() * factor), 0), 255)
                b = min(max(int(pixel.blue() * factor), 0), 255)
                image.setPixelColor(x, y, QColor(r, g, b))
        self.temp_image = QPixmap.fromImage(image)
        self.label.setPixmap(self.temp_image)

    def adjust_contrast(self, factor):
        image = self.temp_image.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                r = min(
                    max(int((pixel.red() - 128) * factor + 128), 0), 255)
                g = min(
                    max(int((pixel.green() - 128) * factor + 128), 0), 255)
                b = min(
                    max(int((pixel.blue() - 128) * factor + 128), 0), 255)
                image.setPixelColor(x, y, QColor(r, g, b))
        self.temp_image = QPixmap.fromImage(image)
        self.label.setPixmap(self.temp_image)

    def sharpen_image(self):
        from PySide6.QtGui import QImage

        kernel = [[0, -1, 0], [-1, 5, -1], [0, -1, 0]]
        image = self.temp_image.toImage()
        width = image.width()
        height = image.height()
        new_image = QImage(image)

        for y in range(1, height - 1):
            for x in range(1, width - 1):
                r = g = b = 0
                for ky in range(-1, 2):
                    for kx in range(-1, 2):
                        pixel = image.pixelColor(x + kx, y + ky)
                        weight = kernel[ky + 1][kx + 1]
                        r += pixel.red() * weight
                        g += pixel.green() * weight
                        b += pixel.blue() * weight
                new_color = QColor(
                    min(max(r, 0), 255),
                    min(max(g, 0), 255),
                    min(max(b, 0), 255),
                )
                new_image.setPixelColor(x, y, new_color)

        self.temp_image = QPixmap.fromImage(new_image)
        self.label.setPixmap(self.temp_image)

    def emboss_image(self):
        from PySide6.QtGui import QImage

        kernel = [[-2, -1, 0], [-1, 1, 1], [0, 1, 2]]
        image = self.temp_image.toImage()
        width = image.width()
        height = image.height()
        new_image = QImage(image)

        for y in range(1, height - 1):
            for x in range(1, width - 1):
                r = g = b = 0
                for ky in range(-1, 2):
                    for kx in range(-1, 2):
                        pixel = image.pixelColor(x + kx, y + ky)
                        weight = kernel[ky + 1][kx + 1]
                        r += pixel.red() * weight
                        g += pixel.green() * weight
                        b += pixel.blue() * weight
                gray = int((r + g + b) / 3)
                new_color = QColor(
                    min(max(gray + 128, 0), 255),
                    min(max(gray + 128, 0), 255),
                    min(max(gray + 128, 0), 255),
                )
                new_image.setPixelColor(x, y, new_color)

        self.temp_image = QPixmap.fromImage(new_image)
        self.label.setPixmap(self.temp_image)

    def apply_custom_kernel(self, kernel):
        from PySide6.QtGui import QImage

        image = self.temp_image.toImage()
        width = image.width()
        height = image.height()
        new_image = QImage(image)

        for y in range(1, height - 1):
            for x in range(1, width - 1):
                r = g = b = 0
                for ky in range(-1, 2):
                    for kx in range(-1, 2):
                        pixel = image.pixelColor(x + kx, y + ky)
                        weight = kernel[ky + 1][kx + 1]
                        r += pixel.red() * weight
                        g += pixel.green() * weight
                        b += pixel.blue() * weight
                new_color = QColor(
                    min(max(r, 0), 255),
                    min(max(g, 0), 255),
                    min(max(b, 0), 255),
                )
                new_image.setPixelColor(x, y, new_color)

        self.temp_image = QPixmap.fromImage(new_image)
        self.label.setPixmap(self.temp_image)

    def apply_edge_detection(self):
        edge_kernel = [[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]]
        self.apply_custom_kernel(edge_kernel)

    def apply_box_blur(self):
        blur_kernel = [
            [1 / 9, 1 / 9, 1 / 9],
            [1 / 9, 1 / 9, 1 / 9],
            [1 / 9, 1 / 9, 1 / 9],
        ]
        self.apply_custom_kernel(blur_kernel)

    def apply_gaussian_blur(self):
        gaussian_kernel = [
            [1 / 16, 2 / 16, 1 / 16],
            [2 / 16, 4 / 16, 2 / 16],
            [1 / 16, 2 / 16, 1 / 16],
        ]
        self.apply_custom_kernel(gaussian_kernel)

    def reset_image(self):
        self.temp_image = self.image.copy()
        self.label.setPixmap(self.temp_image)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_dark_mode(self):
        dark_style = """
        QWidget {
            background-color: #2e2e2e;
            color: #f0f0f0;
        }
        QPushButton, QToolButton, QMenu, QLineEdit, QTextEdit, QListWidget {
            background-color: #3c3c3c;
            border: 1px solid #5a5a5a;
            color: #f0f0f0;
        }
        """
        if not hasattr(self, "_dark_mode") or not self._dark_mode:
            self.setStyleSheet(dark_style)
            self._dark_mode = True
        else:
            self.setStyleSheet("")
            self._dark_mode = False

    def print_image(self):
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog

        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            painter = QPainter(printer)
            rect = painter.viewport()
            size = self.temp_image.size()
            size.scale(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
            painter.setViewport(rect.x(), rect.y(),
                                size.width(), size.height())
            painter.setWindow(self.temp_image.rect())
            painter.drawPixmap(0, 0, self.temp_image)
            painter.end()

    def draw_rectangle(self, top_left: QPoint, bottom_right: QPoint):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        rect = QRect(top_left, bottom_right)
        painter.drawRect(rect)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_ellipse(self, top_left: QPoint, bottom_right: QPoint):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        rect = QRect(top_left, bottom_right)
        painter.drawEllipse(rect)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_line(self, start: QPoint, end: QPoint):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_arrow(self, start: QPoint, end: QPoint):
        import math

        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawLine(start, end)

        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_size = 10

        p1 = QPoint(
            end.x() - arrow_size * math.cos(angle - math.pi / 6),
            end.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        p2 = QPoint(
            end.x() - arrow_size * math.cos(angle + math.pi / 6),
            end.y() - arrow_size * math.sin(angle + math.pi / 6),
        )
        painter.drawLine(end, p1)
        painter.drawLine(end, p2)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_triangle(self, p1: QPoint, p2: QPoint, p3: QPoint):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawPolygon(p1, p2, p3)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_text_box(self, top_left: QPoint, bottom_right: QPoint, text: str):
        rect = QRect(top_left, bottom_right)
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_filled_rectangle(
        self, top_left: QPoint, bottom_right: QPoint, fill_color: QColor
    ):
        rect = QRect(top_left, bottom_right)
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.setBrush(fill_color)
        painter.drawRect(rect)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_filled_ellipse(
        self, top_left: QPoint, bottom_right: QPoint, fill_color: QColor
    ):
        rect = QRect(top_left, bottom_right)
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.setBrush(fill_color)
        painter.drawEllipse(rect)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_polygon(self, points: list):
        if not points:
            return
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        polygon = QPolygonF(points)
        painter.drawPolygon(polygon)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_filled_polygon(self, points: list, fill_color: QColor):
        if not points:
            return
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.setBrush(fill_color)
        polygon = QPolygonF(points)
        painter.drawPolygon(polygon)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_cross(self, center: QPoint, size: int):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawLine(
            center.x() - size, center.y(), center.x() + size, center.y()
        )
        painter.drawLine(
            center.x(), center.y() - size, center.x(), center.y() + size
        )
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_star(self, center: QPoint, radius: int):
        import math

        points = []
        for i in range(10):
            angle = i * math.pi / 5
            r = radius if i % 2 == 0 else radius / 2
            x = center.x() + r * math.cos(angle)
            y = center.y() + r * math.sin(angle)
            points.append(QPoint(x, y))
        self.draw_polygon(points)

    def draw_heart(self, center: QPoint, size: int):
        path = QPainterPath()
        path.moveTo(center)
        path.cubicTo(
            center.x() - size,
            center.y() - size,
            center.x() - size * 1.5,
            center.y() + size / 3,
            center.x(),
            center.y() + size,
        )
        path.cubicTo(
            center.x() + size * 1.5,
            center.y() + size / 3,
            center.x() + size,
            center.y() - size,
            center.x(),
            center.y(),
        )

        painter = QPainter(self.temp_image)
        painter.setPen(QPen(self.pen_color, self.pen_width))
        painter.setBrush(Qt.BrushStyle.SolidPattern)
        painter.drawPath(path)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_checkmark(self, start: QPoint, mid: QPoint, end: QPoint):
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawLine(start, mid)
        painter.drawLine(mid, end)
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_plus(self, center: QPoint, size: int):
        half = size // 2
        painter = QPainter(self.temp_image)
        pen = QPen(self.pen_color, self.pen_width)
        painter.setPen(pen)
        painter.drawLine(
            center.x() - half, center.y(), center.x() + half, center.y()
        )
        painter.drawLine(
            center.x(), center.y() - half, center.x(), center.y() + half
        )
        painter.end()
        self.label.setPixmap(self.temp_image)

    def draw_pentagon(self, center: QPoint, radius: int):
        import math

        points = []
        for i in range(5):
            angle = 2 * math.pi * i / 5 - math.pi / 2
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            points.append(QPoint(x, y))
        self.draw_polygon(points)

    def draw_diamond(self, center: QPoint, size: int):
        points = [
            QPoint(center.x(), center.y() - size),
            QPoint(center.x() + size, center.y()),
            QPoint(center.x(), center.y() + size),
            QPoint(center.x() - size, center.y()),
        ]
        self.draw_polygon(points)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Выход",
            "Вы хотите сохранить изменения перед выходом?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Save:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить изображение",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)",
            )
            if file_path:
                self.temp_image.save(file_path)
                event.accept()
            else:
                event.ignore()
        elif reply == QMessageBox.StandardButton.Discard:
            event.accept()
        else:
            event.ignore()