import sys
import numpy as np
import io
import asyncio
import aiohttp
import os
import shutil
import re 
import json 
import subprocess
import html

from eidos_lite_core import EidosLiteCore as EidosCore 
from lite_llm_module import ( 
    generate_modification_suggestion_async,
    modify_code_async
)
EIDOS_LOADED = True
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QTimer, QPoint, QUrl, QDate, QSize, QRect
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QFrame, QSplitter, QTextEdit, QPlainTextEdit,
    QCheckBox, QDialog, QFormLayout, QDialogButtonBox,
    QFileDialog, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QInputDialog, QMenu, QHeaderView, QDockWidget, QMainWindow, QMenuBar
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QKeySequence,
    QTextCursor, QPaintEvent, QPainter
)

QT_MULTIMEDIA_LOADED = False
WEB_ENGINE_LOADED = False

from collections import deque

SETTINGS_FILE = "eidos_settings.json"
THEME_LIGHT = """
    QWidget { background-color: #F8F8F8; color: #1E1E1E; font-family: "Noto Sans KR"; font-size: 10pt; }
    QFrame { background-color: #FFFFFF; border-radius: 6px; padding: 5px; margin: 4px; border: 1px solid #DEDEDE; }
    QLabel#Title { color: #800000; font-weight: bold; font-size: 14pt; border: none; }
    QLabel#SubTitle { color: #333333; border-bottom: 2px solid #800000; padding-bottom: 5px; margin-bottom: 5px; font-weight: bold; }
    QTextEdit, QPlainTextEdit, QLineEdit, QTreeWidget, QListWidget { border: 1px solid #CCCCCC; border-radius: 4px; padding: 6px; background-color: #FFFFFF; color: #1E1E1E; }
    QTextEdit#ChatLog { background-color: #FFFFFF; border: none; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QTreeWidget:focus { border: 1px solid #800000; }
    QPushButton { background-color: #800000; color: #FFFFFF; border-radius: 3px; padding: 6px 10px; border: none; }
    QPushButton:hover { background-color: #A00000; }
"""
THEME_DARK_MONOCHROME = """
    QWidget { background-color: #252526; color: #D4D4D4; font-family: "Noto Sans KR"; font-size: 10pt; }
    QFrame { background-color: #1E1E1E; border-radius: 6px; padding: 5px; margin: 4px; border: 1px solid #3A3A3A; }
    QLabel#Title { color: #E0E0E0; font-weight: bold; font-size: 14pt; border: none; }
    QLabel#SubTitle { color: #CCCCCC; border-bottom: 2px solid #999999; padding-bottom: 5px; margin-bottom: 5px; font-weight: bold; }
    QTextEdit, QPlainTextEdit, QLineEdit, QTreeWidget, QListWidget { border: 1px solid #4A4A4A; border-radius: 4px; padding: 6px; background-color: #2D2D2D; color: #D4D4D4; }
    QTextEdit#ChatLog { background-color: #1E1E1E; border: none; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QTreeWidget:focus { border: 1px solid #E0E0E0; }
    QPushButton { background-color: #007ACC; color: #FFFFFF; border-radius: 3px; padding: 6px 10px; border: none; }
    QPushButton:hover { background-color: #0056b3; }
"""
def load_theme_setting() -> str:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("theme", "Light")
    except Exception: pass
    return "Light"

def save_theme_setting(theme_name: str):
    settings = {"theme": theme_name}
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
    except Exception as e: print(f"❌ [Theme] 설정 저장 실패: {e}")

class LineNumberArea(QWidget):
    """ (Lite) 코드 에디터용 줄 번호 위젯 (기존과 동일) """
    def __init__(self, editor: QPlainTextEdit): # [Fix] QTextEdit -> QPlainTextEdit
        super().__init__(editor)
        self.editor = editor
        self.update_palette()

    def sizeHint(self):
        return QSize(self.calculate_width(), 0)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.background_color)
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
        bottom = top + self.editor.blockBoundingRect(block).height()
        painter.setFont(self.editor.font())
        painter.setPen(self.text_color)
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(0, top, self.width() - 5, self.editor.fontMetrics().height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1

    def calculate_width(self) -> int:
        digits = len(str(max(1, self.editor.document().blockCount())))
        space = 10 + self.editor.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_palette(self):
        """ 테마 변경 시 색상 업데이트 """
        palette = self.palette()
        self.text_color = palette.color(QPalette.ColorRole.Text)
        self.background_color = palette.color(QPalette.ColorRole.AlternateBase)
        self.update() # 즉시 다시 그리기

class SettingsDialog(QDialog):
    """ (Lite) 설정 다이얼로그 (AGI/Pro 모드 제거, 테마 설정만 유지) """
    def __init__(self, parent=None, initial_theme: str = "Light"):
        super().__init__(parent)
        self.setWindowTitle("⚙️ EIDOS-Lite 설정")
        self.setMinimumWidth(350)
        self.layout = QFormLayout(self)
        
        self.theme_combo = QComboBox(self)
        self.theme_combo.addItems(["Light", "Dark (Monochrome)"])
        if "Dark" in initial_theme: self.theme_combo.setCurrentText("Dark (Monochrome)")
        else: self.theme_combo.setCurrentText("Light")
        self.layout.addRow("GUI 테마:", self.theme_combo)

        self.account_button = QPushButton("🔑 API 키 관리 (config.py)")
        self.account_button.clicked.connect(lambda: QMessageBox.information(self, "API 키", "config.py 파일을 직접 수정하여 Gemini API 키를 입력하세요."))
        self.layout.addRow("계정:", self.account_button)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.button_box.accepted.connect(self.accept)
        self.layout.addRow(self.button_box)

    def get_selected_theme(self) -> str:
        return "Dark" if "Dark" in self.theme_combo.currentText() else "Light"

class EidosWorker(QThread):
    """ (Lite) GUI와 Lite Core를 연결하는 워커 (단순화됨) """
    
    # (natural_text, reasoning_log, exec_task_state)
    response_ready = Signal(str, str, object)
    
    error_occurred = Signal(str)
    
    code_modification_ready = Signal(dict)
    suggestion_ready = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.eidos_core: Optional[EidosCore] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.stop_event: Optional[asyncio.Event] = None
        
    async def request_modification_suggestion_async(self, current_code: str, chat_history: List[str]):
        """ (Lite) 코드 추천 요청을 Core로 전달 (기존과 동일) """
        if not self.eidos_core: return
        try:
            suggestion_text = await self.eidos_core.request_modification_suggestion_async(current_code, chat_history)
            self.suggestion_ready.emit(suggestion_text)
        except Exception as e:
            self.error_occurred.emit(f"[Suggestion] 오류: {e}")

    async def request_code_modification_async(self, current_code: str, user_request: str, new_file_name: Optional[str], current_file_path: Optional[str]):
        """ (Lite) 코드 수정 요청을 Core로 전달 (기존과 동일) """
        if not self.eidos_core: return
        try:
            response_dict = await self.eidos_core.request_code_modification_async(
                current_code, user_request, new_file_name, current_file_path
            )
            self.code_modification_ready.emit(response_dict)
        except Exception as e:
            self.error_occurred.emit(f"[Code Modify] 오류: {e}")

    async def async_main(self):
        """ (Lite) 메인 루프 (자율성 Heartbeat 제거) """
        try:
            async with aiohttp.ClientSession() as session:
                self.session = session
                if EIDOS_LOADED:
                    try:
                        self.eidos_core = EidosCore()
                        print("✅ EIDOS-Lite Stub Core 로드 완료.")
                    except Exception as e:
                        self.error_occurred.emit(f"Lite Core 초기화 실패: {e}")
                        return
                else:
                    self.error_occurred.emit("EIDOS Lite Core 모듈 로드 실패.")
                    return
                
                self.stop_event = asyncio.Event()
                print("[Worker-Lite] 대기 모드 시작. (자율성 없음)")
                await self.stop_event.wait() # 중지 신호가 올 때까지 영원히 대기

        except Exception as e:
            self.error_occurred.emit(f"[async_main] 오류: {e}")

    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.async_main())
        except Exception as e:
            self.error_occurred.emit(f"워커 스레드 오류: {e}")
        finally:
            if self.loop and not self.loop.is_closed(): self.loop.close()
            print("[Worker-Lite] 이벤트 루프 종료됨.")

    async def _process_async(self, text: str, chat_history: Optional[list] = None, project_dir: Optional[str] = None):
        """ (Lite) Core의 process_input 호출 (단순화됨) """
        if not EIDOS_LOADED or not self.eidos_core:
            self.error_occurred.emit("EIDOS Lite Core가 로드되지 않았습니다.")
            return

        try:
            (
                _, policy_state, _, _, _, _,
                exec_task_state, _, 
                reasoning_log, natural_text, _, _
            ) = await self.eidos_core.process_input(
                 text,
                 None, # image_input (무시)
                 chat_history,
                 project_dir=project_dir
             )
            
            print(f"  [Worker-Lite] Core 응답 수신. Policy: {policy_state}")

            self.response_ready.emit(natural_text, reasoning_log, exec_task_state)
            
        except Exception as e:
            import traceback
            error_msg = f"❌ [Worker-Lite] Core.process_input 처리 중 오류: {e}\n{traceback.format_exc()}"
            print(error_msg)
            self.error_occurred.emit(f"[EIDOS-Lite Core 오류]: {e}")

    def submit_task(self, coro):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
            
    def stop_loop(self):
        if self.loop and self.stop_event:
            self.loop.call_soon_threadsafe(self.stop_event.set)
            
class MainHubWindow(QMainWindow):
    """ (Lite) EIDOS-Lite Studio (Task Manager가 제거된 버전) """
    def __init__(self, eidos_worker, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EIDOS AGI Studio (Lite)")
        self.setGeometry(100, 100, 1200, 800)
        
        self.eidos_worker = eidos_worker
        self.code_editor_instance: Optional[CodeEditorWindow] = None
        self.doc_editor_instance: Optional[DocumentEditorWindow] = None
        self.project_root = os.path.abspath("eidos_files")
        self.current_theme = load_theme_setting()
        
        self.chat_window = ChatWindow(self, worker=self.eidos_worker)
        self.setCentralWidget(self.chat_window)

        self._setup_dock_widgets()
        self._setup_menu_bar()

    def apply_theme(self, theme_name: str):
        """ (Lite) 테마 적용 (기존과 동일) """
        qss = THEME_LIGHT if theme_name == "Light" else THEME_DARK_MONOCHROME
        app = QApplication.instance()
        if app: app.setStyleSheet(qss)
        self.current_theme = theme_name
        save_theme_setting(theme_name)
        
        if self.code_editor_instance: self.code_editor_instance.update_theme_palette()
        if self.doc_editor_instance: self.doc_editor_instance.update_theme_palette()

    @Slot()
    def _open_settings(self):
        """ (Lite) 단순화된 설정 다이얼로그 호출 """
        dialog = SettingsDialog(self, initial_theme=self.current_theme)
        if dialog.exec():
            new_theme = dialog.get_selected_theme()
            if new_theme != self.current_theme:
                self.apply_theme(new_theme)
                self.chat_window.append_message(f"<b>[시스템]</b> GUI 테마가 **{new_theme}** 모드로 변경되었습니다.", "system")

    def _setup_dock_widgets(self):
        """ (Lite) 파일 탐색기 도크 (기존과 동일) """
        self.file_dock = QDockWidget("📁 EIDOS 파일 탐색기", self)
        self.file_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.file_tree = QTreeWidget(self)
        self.file_tree.setHeaderLabels(["파일 및 폴더"])
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._file_tree_context_menu)
        self.file_tree.itemDoubleClicked.connect(self._open_file_in_editor)
        self.file_dock.setWidget(self.file_tree)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.file_dock)
        self._refresh_file_tree()

    @Slot(QTreeWidgetItem, int)
    def _open_file_in_editor(self, item: QTreeWidgetItem, column: int):
        """ (Lite) 코드/문서 에디터 열기 (비디오 에디터 제거) """
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path or os.path.isdir(file_path): return

        editor_type = "DOCUMENT"
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.py', '.js', '.html', '.css', '.bat', '.sh', '.pyw', '.json', '.md', '.txt']:
             editor_type = "CODE" # [Lite] 코드/문서 에디터 통합 (CodeEditor가 더 기능이 많음)
        
        project_dir_for_editor = os.path.dirname(file_path)

        try:
            if editor_type == "CODE":
                if self.code_editor_instance is None or not self.code_editor_instance.isVisible():
                    self.code_editor_instance = CodeEditorWindow(
                        project_dir=project_dir_for_editor, eidos_worker=self.eidos_worker
                    )
                else:
                    self.code_editor_instance.project_root = project_dir_for_editor
                self.code_editor_instance._open_file_in_editor(file_path=file_path)
                self.code_editor_instance.show()
                self.code_editor_instance.activateWindow()
            else: # DOCUMENT (CodeEditor로 통합)
                if self.doc_editor_instance is None or not self.doc_editor_instance.isVisible():
                    self.doc_editor_instance = DocumentEditorWindow(
                        project_dir=project_dir_for_editor, eidos_worker=self.eidos_worker
                    )
                else:
                    self.doc_editor_instance.project_root = project_dir_for_editor
                self.doc_editor_instance._open_file_in_editor(file_path=file_path)
                self.doc_editor_instance.show()
                self.doc_editor_instance.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "에디터 열기 오류", f"에디터 열기 실패: {e}")

    def _refresh_file_tree(self):
        self.file_tree.clear()
        if not os.path.exists(self.project_root): os.makedirs(self.project_root)
        self._populate_tree(self.project_root, self.file_tree.invisibleRootItem())
    def _populate_tree(self, folder_path: str, parent_item: QTreeWidgetItem):
        for name in os.listdir(folder_path):
            if name.startswith('.'): continue
            path = os.path.join(folder_path, name)
            item = QTreeWidgetItem([name]); item.setData(0, Qt.ItemDataRole.UserRole, path)
            if os.path.isdir(path): self._populate_tree(path, item)
            parent_item.addChild(item)
    def _file_tree_context_menu(self, pos: QPoint):
        item = self.file_tree.itemAt(pos); menu = QMenu(self)
        if item is None:
            menu.addAction("📄 새 파일 (루트)").triggered.connect(lambda: self._create_new_item(self.file_tree.invisibleRootItem(), is_file=True, is_root=True))
            menu.addAction("📁 새 폴더 (루트)").triggered.connect(lambda: self._create_new_item(self.file_tree.invisibleRootItem(), is_file=False, is_root=True))
        if item:
            item_path = item.data(0, Qt.ItemDataRole.UserRole); is_dir = os.path.isdir(item_path)
            if is_dir:
                menu.addAction("📄 새 파일").triggered.connect(lambda: self._create_new_item(item, is_file=True))
                menu.addAction("📁 새 폴더").triggered.connect(lambda: self._create_new_item(item, is_file=False))
            menu.addAction("🗑️ 삭제").triggered.connect(lambda: self._delete_item(item))
            menu.addAction("✏️ 이름 바꾸기").triggered.connect(lambda: self._rename_item(item))
        menu.addSeparator(); menu.addAction("🔄 새로고침").triggered.connect(self._refresh_file_tree)
        menu.exec(self.file_tree.mapToGlobal(pos))
    def _create_new_item(self, parent_item: QTreeWidgetItem, is_file: bool, is_root: bool = False):
        parent_path = self.project_root if is_root else parent_item.data(0, Qt.ItemDataRole.UserRole)
        item_type = "파일" if is_file else "폴더"; name, ok = QInputDialog.getText(self, f"새 {item_type} 생성", f"이름:")
        if ok and name:
            try:
                new_path = os.path.join(parent_path, name)
                if is_file: with open(new_path, 'w') as f: pass
                else: os.makedirs(new_path)
                self._refresh_file_tree()
            except Exception as e: QMessageBox.critical(self, "생성 오류", f"생성 실패: {e}")
    def _delete_item(self, item: QTreeWidgetItem):
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "삭제 확인", f"'{os.path.basename(file_path)}'을(를) 삭제하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(file_path): shutil.rmtree(file_path)
                else: os.remove(file_path)
                self._refresh_file_tree()
            except Exception as e: QMessageBox.critical(self, "삭제 오류", f"삭제 실패: {e}")
    def _rename_item(self, item: QTreeWidgetItem): QMessageBox.information(self, "안내", "이름 바꾸기는 아직 지원되지 않습니다.")

    def _setup_menu_bar(self):
        """ (Lite) 메뉴 바 (단순화) """
        menu_bar = QMenuBar(self); self.setMenuBar(menu_bar)
        file_menu = menu_bar.addMenu("파일(&F)")
        file_menu.addAction("새 프로젝트..."); file_menu.addAction("종료", self.close)
        settings_menu = menu_bar.addMenu("설정(&S)")
        settings_action = QAction("⚙️ GUI 테마 설정", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)
        view_menu = menu_bar.addMenu("보기(&V)")
        view_menu.addAction(self.file_dock.toggleViewAction())

    def closeEvent(self, event):
        self.chat_window.closeEvent(event)
        super().closeEvent(event)

class CodeEditorWindow(QWidget):
    """ (Lite) 코드 에디터 (QA 패널 제거) """
    def __init__(self, parent=None, project_dir: str = "eidos_files/default_project", eidos_worker: Optional['EidosWorker'] = None, chat_history_deque: Optional[deque] = None):
        super().__init__(parent)
        self.setWindowTitle(f"EIDOS Code Editor (Lite) - {project_dir}")
        self.setGeometry(200, 200, 900, 600) # 크기 소폭 축소
        
        self.project_root = os.path.abspath(project_dir)
        self.current_file_path: Optional[str] = None
        self.eidos_worker = eidos_worker
        self.code_before_ai_modification: Optional[str] = None
        self.chat_history_deque = chat_history_deque if chat_history_deque else deque(maxlen=30)
        self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(30000); self.autosave_timer.timeout.connect(self._autosave_file); self.autosave_timer.start()

        main_splitter = QSplitter(Qt.Horizontal)
        
        self.file_tree = QTreeWidget(self); self.file_tree.setHeaderLabels(["File Name"])
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._file_tree_context_menu)
        self.file_tree.itemDoubleClicked.connect(self._open_file_in_editor)
        
        editor_console_splitter = QSplitter(Qt.Vertical)

        self.code_editor = QPlainTextEdit(self)
        self.code_editor.setFont(QFont("Consolas", 10))
        self.line_number_area = LineNumberArea(self.code_editor)
        
        editor_widget = QWidget(); editor_layout = QHBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0); editor_layout.setSpacing(0)
        editor_layout.addWidget(self.line_number_area); editor_layout.addWidget(self.code_editor)

        self.debug_console = QTextEdit(self); self.debug_console.setReadOnly(True)
        self.debug_console.setFont(QFont("Consolas", 9)); self.debug_console.setMinimumHeight(100)
        
        editor_console_splitter.addWidget(editor_widget)
        editor_console_splitter.addWidget(self.debug_console)
        editor_console_splitter.setSizes([400, 150])
      

        main_splitter.addWidget(self.file_tree)
        main_splitter.addWidget(editor_console_splitter)
        main_splitter.setSizes([250, 650]) 
        
        layout = QVBoxLayout(self); layout.addWidget(main_splitter)
        
        self.search_bar = QFrame(self); search_layout = QHBoxLayout(self.search_bar)
        self.search_input = QLineEdit(self); self.find_next_button = QPushButton("⬇️ 다음")
        self.find_prev_button = QPushButton("⬆️ 이전"); self.close_search_button = QPushButton("❌")
        search_layout.addWidget(QLabel("찾기:")); search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.find_next_button); search_layout.addWidget(self.find_prev_button)
        search_layout.addWidget(self.close_search_button); self.search_bar.setVisible(False)
        layout.addWidget(self.search_bar)
        
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("💾 저장"); self.save_button.clicked.connect(self._save_file)
        self.run_button = QPushButton("▶️ 미리보기 (실행)"); self.run_button.clicked.connect(self._run_code_preview)
        self.refresh_button = QPushButton("🔄 새로고침"); self.refresh_button.clicked.connect(self._refresh_file_tree)
        self.undo_ai_button = QPushButton("↩️ AI 수정 되돌리기"); self.undo_ai_button.clicked.connect(self._undo_ai_modification)
        self.undo_ai_button.setEnabled(False)
        self.eidos_edit_button = QPushButton("🤖 EIDOS로 기능 추가"); self.eidos_edit_button.clicked.connect(self._eidos_modify_code)
        
        button_layout.addWidget(self.save_button); button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.refresh_button); button_layout.addStretch()
        button_layout.addWidget(self.undo_ai_button); button_layout.addWidget(self.eidos_edit_button)
        layout.addLayout(button_layout)

        self._refresh_file_tree()
        
        self.code_editor.document().blockCountChanged.connect(self._update_line_number_area_width)
        self.code_editor.updateRequest.connect(self._safe_update_line_number_area)
        self._update_line_number_area_width()

        find_action = QAction("Find", self); find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self._show_search_bar); self.addAction(find_action)
        self.find_next_button.clicked.connect(self._find_next); self.find_prev_button.clicked.connect(self._find_prev)
        self.search_input.returnPressed.connect(self._find_next); self.close_search_button.clicked.connect(self._hide_search_bar)

        if self.eidos_worker:
            self.eidos_worker.code_modification_ready.connect(self._on_code_modified)
            self.eidos_worker.error_occurred.connect(self._on_eidos_error)
        else:
            self.debug_console.append("❌ [Critical] EidosWorker가 연결되지 않았습니다.")

    def update_theme_palette(self):
        """ (Lite) 테마 변경 시 줄 번호 영역 색상 업데이트 """
        self.line_number_area.update_palette()

    @Slot(dict)
    def _on_code_modified(self, response_dict: dict):
        try:
            filepath_key = response_dict.get("filepath", "CURRENT")
            new_code = response_dict.get("code", "[EIDOS 응답 오류]")
            if filepath_key == "CURRENT":
                self.code_editor.setPlainText(new_code)
                self.debug_console.append("✅ [EIDOS] 코드가 수정되었습니다.")
            else:
                new_file_path = os.path.join(self.project_root, filepath_key)
                self._save_file_content(new_file_path, new_code)
                self._refresh_file_tree()
                self.debug_console.append(f"✅ [EIDOS] 새 파일 '{filepath_key}'이(가) 생성/저장되었습니다.")
            if self.code_before_ai_modification is not None:
                self.undo_ai_button.setEnabled(True)
        except Exception as e:
            self.debug_console.append(f"❌ [EIDOS] 응답 처리 중 오류: {e}")
            self.undo_ai_button.setEnabled(False)
            self.code_before_ai_modification = None
    @Slot(str)
    def _on_eidos_error(self, error_msg: str):
        if "[Code Modify]" in error_msg or "[Suggestion]" in error_msg:
            self.debug_console.append(f"❌ {error_msg}")

    @Slot()
    def _eidos_modify_code(self):
        if not self.eidos_worker or not self.current_file_path:
            self.debug_console.append("❌ EIDOS Worker 또는 파일이 없습니다.")
            return
        current_code = self.code_editor.toPlainText()
        self.code_before_ai_modification = current_code
        self.undo_ai_button.setEnabled(False) 
        dialog = ModificationDialog(os.path.basename(self.current_file_path), self)
        self.eidos_worker.suggestion_ready.connect(dialog.set_suggestion)
        self.eidos_worker.submit_task(
            self.eidos_worker.request_modification_suggestion_async(current_code, list(self.chat_history_deque))
        )
        if dialog.exec():
            try: self.eidos_worker.suggestion_ready.disconnect(dialog.set_suggestion)
            except RuntimeError: pass
            user_request, new_file_name = dialog.get_values()
            if user_request:
                self.debug_console.append(f"🤖 [EIDOS] 코드 수정 요청: '{user_request}'")
                self.eidos_worker.submit_task(
                    self.eidos_worker.request_code_modification_async(
                        current_code, user_request, new_file_name, self.current_file_path
                    )
                )
            else: self.debug_console.append("ℹ️ 코드 수정이 취소되었습니다.")
        else:
            try: self.eidos_worker.suggestion_ready.disconnect(dialog.set_suggestion)
            except RuntimeError: pass
            self.debug_console.append("ℹ️ 코드 수정이 취소되었습니다.")

    @Slot()
    def _run_code_preview(self):
        if not self.current_file_path: return
        self._save_file() # 저장 필수
        self.debug_console.clear()
        self.debug_console.append(f">>> python {os.path.basename(self.current_file_path)} 실행...")
        try:
            is_gui_app = False
            if self.current_file_path.endswith('.pyw'): is_gui_app = True
            else:
                code_content = self.code_editor.toPlainText()
                if "tk.Tk()" in code_content or "root.mainloop()" in code_content or "QApplication" in code_content:
                    is_gui_app = True
            if is_gui_app:
                self.debug_console.append("✅ GUI 앱 감지. 새 창으로 실행합니다.")
                subprocess.Popen(['python', self.current_file_path], cwd=os.path.dirname(self.current_file_path))
                return
            result = subprocess.run(
                ['python', self.current_file_path],
                cwd=os.path.dirname(self.current_file_path),
                capture_output=True, text=True, timeout=10, encoding='utf-8'
            )
            if result.stdout: self.debug_console.append(f"--- [STDOUT] ---\n{result.stdout.strip()}")
            if result.stderr:
                error_output = result.stderr.strip()
                self.debug_console.append(f"--- [STDERR] ---\n{error_output}")
                self.debug_console.append("\n❌ 실행 실패: AI 자동 디버거를 호출합니다...")
                self._trigger_auto_debugger(error_output) 
            if result.returncode == 0: self.debug_console.append("\n✅ 코드 실행 성공.")
        except Exception as e:
            error_output = f"알 수 없는 실행 오류: {e}"
            self.debug_console.append(f"\n❌ {error_output}")
            self._trigger_auto_debugger(error_output)
    @Slot(str)
    def _trigger_auto_debugger(self, error_message: str):
        if not self.eidos_worker or not self.current_file_path: return
        self.debug_console.append(f"🤖 [AI Auto-Debugger] 오류 감지. EIDOS에 자동 수정을 요청합니다...")
        auto_request = f"[자동 디버깅 요청] 다음 오류를 해결해 주세요:\n{error_message}"
        self.eidos_worker.submit_task(
            self.eidos_worker.request_code_modification_async(
                self.code_editor.toPlainText(), auto_request, None, self.current_file_path
            )
        )

    def _save_file_content(self, absolute_path: str, content: str):
        try:
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            with open(absolute_path, 'w', encoding='utf-8') as f: f.write(content)
        except Exception as e:
            self.debug_console.append(f"❌ 파일 저장 실패: {e}")
    def _autosave_file(self):
        if self.current_file_path: self._save_file_content(self.current_file_path, self.code_editor.toPlainText())
    def closeEvent(self, event): self.autosave_timer.stop(); super().closeEvent(event)
    def _refresh_file_tree(self): self.file_tree.clear(); self._populate_tree(self.project_root, self.file_tree.invisibleRootItem())
    def _populate_tree(self, folder_path: str, parent_item: QTreeWidgetItem):
        for name in os.listdir(folder_path):
            if name.startswith('.'): continue
            path = os.path.join(folder_path, name); item = QTreeWidgetItem([name]); item.setData(0, Qt.ItemDataRole.UserRole, path)
            if os.path.isdir(path): self._populate_tree(path, item)
            parent_item.addChild(item)
    def _open_file_in_editor(self, item: Optional[QTreeWidgetItem] = None, column: int = 0, file_path: Optional[str] = None):
        if item: file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path or os.path.isdir(file_path): return
        try:
            with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
            self.code_editor.setPlainText(content)
            self.setWindowTitle(f"EIDOS Code Editor (Lite) - {os.path.basename(file_path)}")
            self.current_file_path = file_path
        except Exception as e: QMessageBox.critical(self, "파일 열기 오류", f"파일을 열 수 없습니다: {e}")
    def _save_file(self):
        if not self.current_file_path: QMessageBox.warning(self, "저장 오류", "파일이 선택되지 않았습니다."); return
        self._save_file_content(self.current_file_path, self.code_editor.toPlainText())
    def _file_tree_context_menu(self, pos: QPoint):
        item = self.file_tree.itemAt(pos); menu = QMenu(self)
        if item:
            is_dir = os.path.isdir(item.data(0, Qt.ItemDataRole.UserRole))
            if is_dir:
                menu.addAction("📄 새 파일").triggered.connect(lambda: self._create_new_item(item, is_file=True))
                menu.addAction("📁 새 폴더").triggered.connect(lambda: self._create_new_item(item, is_file=False))
            menu.addAction("🗑️ 삭제").triggered.connect(lambda: self._delete_item(item))
        menu.addSeparator(); menu.addAction("🔄 새로고침").triggered.connect(self._refresh_file_tree)
        menu.exec(self.file_tree.mapToGlobal(pos))
    def _create_new_item(self, parent_item: QTreeWidgetItem, is_file: bool):
        parent_path = parent_item.data(0, Qt.ItemDataRole.UserRole); item_type = "파일" if is_file else "폴더"
        name, ok = QInputDialog.getText(self, f"새 {item_type} 생성", "이름:");
        if ok and name:
            try:
                new_path = os.path.join(parent_path, name)
                if is_file: with open(new_path, 'w') as f: pass
                else: os.makedirs(new_path)
                self._refresh_file_tree()
            except Exception as e: QMessageBox.critical(self, "생성 오류", f"생성 실패: {e}")
    def
