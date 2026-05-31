import json
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from paratranz_py import ParaTranz

SETTINGS_FILE = Path.home() / "para_bulkupdate" / "settings.json"

APP_QSS = """
QMainWindow, QWidget {
    background-color: #f5f5f5;
    color: #2c2c2c;
}
QLineEdit, QComboBox {
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 4px 8px;
    background: #ffffff;
    min-height: 24px;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #4a9eff;
}
QLineEdit:disabled, QComboBox:disabled {
    background: #eeeeee;
    color: #888888;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QGroupBox {
    border: 1px solid #cccccc;
    border-radius: 6px;
    margin-top: 10px;
    padding: 6px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 5px 14px;
    background: #f0f0f0;
    color: #2c2c2c;
    min-height: 26px;
}
QPushButton:hover {
    background: #e4e4e4;
    border-color: #b0b0b0;
}
QPushButton:pressed {
    background: #d8d8d8;
}
QPushButton:disabled {
    color: #aaaaaa;
    border-color: #e0e0e0;
    background: #f5f5f5;
}
QPushButton#primary {
    background: #4a9eff;
    color: #ffffff;
    border: 1px solid #3a8eef;
    font-weight: bold;
}
QPushButton#primary:hover {
    background: #3a8eef;
}
QPushButton#primary:pressed {
    background: #2a7edf;
}
QPushButton#primary:disabled {
    background: #a8ccf0;
    border-color: #a8ccf0;
    color: #f0f0f0;
}
QTextEdit {
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    background: #ffffff;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 4px;
}
QProgressBar {
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    background: #eeeeee;
    height: 16px;
    text-align: center;
    font-size: 11px;
    color: #2c2c2c;
}
QProgressBar::chunk {
    background: #4a9eff;
    border-radius: 3px;
}
QStatusBar {
    background: #e8e8e8;
    border-top: 1px solid #cccccc;
    color: #555555;
    font-size: 12px;
}
"""


# ---------------------------------------------------------------------------
# Module-level API helpers (pure logic, testable without Qt)
# ---------------------------------------------------------------------------


def _api_error(resp) -> str | None:
    """Return an error string if resp signals a failure, else None."""
    if resp is None:
        return "API 返回為 None"
    if isinstance(resp, dict) and "message" in resp:
        return resp["message"]
    return None


def _parse_files_list(resp) -> list[dict]:
    """Normalise get_files() response to a list of {id, name} dicts."""
    if isinstance(resp, list):
        return [
            {"id": f["id"], "name": f.get("name", str(f["id"]))}
            for f in resp
            if "id" in f
        ]
    if isinstance(resp, dict):
        items = resp.get("results", resp.get("data", []))
        return [
            {"id": f["id"], "name": f.get("name", str(f["id"]))}
            for f in items
            if "id" in f
        ]
    return []


def get_string_id_dict(
    para: ParaTranz,
    project_id: int,
    file_id: int,
    stage,
    log_fn,
    progress_fn=None,
) -> dict | None:
    """
    Return {key: {'id': int, 'translation': str, 'stage': int}} for strings
    in the given file.

    Stores the current translation and stage so bulk_update_strings can decide
    whether to preserve the review status when the text is unchanged.
    Uses the first-page `total` to drive pagination, so untranslated-only
    mode no longer over-counts pages.
    """
    return_data: dict = {}
    try:
        file_info = para.files.get_file(project_id=project_id, file_id=file_id)
        err = _api_error(file_info)
        if err:
            log_fn(f"無法獲取檔案訊息: {err}", "error")
            return None
        if "total" not in file_info:
            log_fn(f"檔案訊息格式不正確: {file_info}", "error")
            return None

        stage_text = "未翻譯" if stage == 0 else "所有"
        log_fn(
            f"檔案共有 {file_info['total']} 個詞條，將獲取{stage_text}詞條",
            "info",
        )

        page_size = 300
        page = 1
        total_pages = 1

        while True:
            log_fn(f"正在處理第 {page}/{total_pages} 頁...", "info")
            if progress_fn:
                progress_fn(page - 1, total_pages)

            data = para.strings.get_strings(
                project_id=project_id,
                file_id=file_id,
                stage=stage,
                page_size=page_size,
                page=page,
            )
            err = _api_error(data)
            if err:
                log_fn(f"無法獲取第 {page} 頁詞條: {err}", "warning")
                break
            if "results" not in data:
                log_fn(f"第 {page} 頁詞條格式不正確: {data}", "warning")
                break

            if page == 1 and "total" in data:
                total_items = data["total"]
                total_pages = max(1, (total_items + page_size - 1) // page_size)

            results = data["results"]
            if not results:
                break

            for s in results:
                if "id" in s and "key" in s:
                    return_data[s["key"]] = {
                        "id": s["id"],
                        "translation": s.get("translation") or "",
                        "stage": s.get("stage", 0),
                    }

            if len(results) < page_size:
                break
            page += 1

        if progress_fn:
            progress_fn(total_pages, total_pages)

        return return_data
    except Exception as e:
        log_fn(f"獲取詞條時出錯: {str(e)}", "error")
        return None


_REVIEWED_STAGES = frozenset({3, 5})


def bulk_update_strings(
    para: ParaTranz,
    project_id: int,
    strings_id_key_dict: dict,
    translated_strings: dict,
    log_fn,
    progress_fn=None,
) -> tuple[int, int, int]:
    """
    Update strings in bulk.  Returns (updated, skipped, errors).

    Stage logic:
    - If the string is already reviewed (stage 3 or 5) AND the new translation
      text is identical to the current one, the existing stage is preserved so
      reviewers don't need to re-check unchanged entries.
    - In every other case the string is set to stage 1 (已翻譯) so that
      reviewers know the text was touched.
    """
    updated = skipped = errors = 0
    total = len(translated_strings)

    for idx, (key, value) in enumerate(translated_strings.items()):
        if progress_fn:
            progress_fn(idx, total)

        if key not in strings_id_key_dict:
            log_fn(f"詞條鍵值未找到: {key}", "warning")
            skipped += 1
            continue

        entry = strings_id_key_dict[key]
        string_id = entry["id"]
        current_translation = entry["translation"]
        current_stage = entry["stage"]

        # Preserve review status only when the text has not changed
        if current_stage in _REVIEWED_STAGES and value == current_translation:
            new_stage = current_stage
            log_fn(
                f"跳過審核詞條（譯文未變動）- 鍵值: {key} "
                f"(stage {current_stage})",
                "info",
            )
        else:
            new_stage = 1
            log_fn(
                f"更新詞條 - 鍵值: {key} ({string_id})\n譯文: {value}", "info"
            )

        try:
            response = para.strings.update_string(
                project_id=project_id,
                string_id=string_id,
                translate_text=value,
                stage=new_stage,
            )
            err = _api_error(response)
            if err:
                log_fn(f"更新詞條 {key} 失敗: {err}", "error")
                errors += 1
            else:
                updated += 1
        except Exception as e:
            log_fn(f"更新詞條 {key} 時出錯: {str(e)}", "error")
            errors += 1

    if progress_fn:
        progress_fn(total, total)

    return updated, skipped, errors


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------


class FetchFilesWorker(QThread):
    """Fetches the project file list without needing a specific file_id."""

    finished = pyqtSignal(list)

    def __init__(self, auth_token: str, project_id: int):
        super().__init__()
        self.auth_token = auth_token
        self.project_id = project_id

    def run(self):
        try:
            para = ParaTranz(api_token=self.auth_token)
            resp = para.files.get_files(project_id=self.project_id)
            files = _parse_files_list(resp)
        except Exception:
            files = []
        self.finished.emit(files)


class TestConnectionWorker(QThread):
    log = pyqtSignal(str, str)  # message, level
    finished = pyqtSignal(bool, str, list)  # success, message, files

    def __init__(
        self,
        auth_token: str,
        project_id: int,
        file_id: int,
        stage,
    ):
        super().__init__()
        self.auth_token = auth_token
        self.project_id = project_id
        self.file_id = file_id
        self.stage = stage

    def run(self):
        try:
            para = ParaTranz(api_token=self.auth_token)

            file_info = para.files.get_file(
                project_id=self.project_id, file_id=self.file_id
            )
            err = _api_error(file_info)
            if err:
                self.finished.emit(False, f"無法獲取檔案訊息: {err}", [])
                return
            if "total" not in file_info:
                self.finished.emit(False, f"返回格式不正確: {file_info}", [])
                return

            self.log.emit(
                f"連接成功！檔案中共有 {file_info['total']} 個詞條", "success"
            )

            files: list[dict] = []
            try:
                resp = para.files.get_files(project_id=self.project_id)
                files = _parse_files_list(resp)
            except Exception:
                pass

            stage_text = "未翻譯" if self.stage == 0 else "所有"
            self.log.emit(f"正在測試獲取{stage_text}詞條...", "info")
            data = para.strings.get_strings(
                project_id=self.project_id,
                file_id=self.file_id,
                stage=self.stage,
                page_size=10,
                page=1,
            )
            err = _api_error(data)
            if err:
                self.finished.emit(False, f"獲取詞條失敗: {err}", files)
                return

            results = data.get("results", [])
            mode_text = "未翻譯詞條" if self.stage == 0 else "所有詞條"
            if self.stage == 0 and not results:
                self.log.emit("注意：未找到未翻譯詞條，可能所有詞條都已翻譯", "warning")
                self.finished.emit(True, "連接成功，但未找到未翻譯的詞條", files)
            else:
                self.log.emit(
                    f"成功獲取{mode_text}，第一頁 {len(results)} 個", "success"
                )
                self.finished.emit(True, f"成功連接並獲取{mode_text}！", files)

        except Exception as e:
            self.finished.emit(False, f"連接時發生錯誤: {str(e)}", [])


class UpdateWorker(QThread):
    update_log = pyqtSignal(str, str)  # message, level
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        auth_token: str,
        project_id: int,
        file_id: int,
        translated_file_path: str,
        stage=None,
    ):
        super().__init__()
        self.auth_token = auth_token
        self.project_id = project_id
        self.file_id = file_id
        self.translated_file_path = Path(translated_file_path)
        self.stage = stage

    def run(self):
        try:
            para = ParaTranz(api_token=self.auth_token)

            try:
                string_translated_dict = json.loads(
                    self.translated_file_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                self.finished.emit(False, f"無法載入翻譯檔案: {str(e)}")
                return

            stage_desc = "未翻譯的" if self.stage == 0 else "所有"
            self.update_log.emit(f"正在獲取{stage_desc}詞條 ID 字典...", "info")

            def log_fn(msg: str, level: str = "info") -> None:
                self.update_log.emit(msg, level)

            def progress_fn(current: int, total: int) -> None:
                self.progress.emit(current, total)

            strings_id_key_dict = get_string_id_dict(
                para,
                self.project_id,
                self.file_id,
                self.stage,
                log_fn,
                progress_fn,
            )
            if not strings_id_key_dict:
                self.finished.emit(
                    False,
                    "無法獲取詞條 ID 字典，請檢查專案 ID 和檔案 ID 是否正確",
                )
                return

            self.update_log.emit(f"找到 {len(strings_id_key_dict)} 個詞條", "info")
            self.update_log.emit("開始批量更新詞條...", "info")

            updated, skipped, errors = bulk_update_strings(
                para,
                self.project_id,
                strings_id_key_dict,
                string_translated_dict,
                log_fn,
                progress_fn,
            )

            summary = f"已更新 {updated} 個詞條，跳過 {skipped} 個，失敗 {errors} 個"
            level = "success" if errors == 0 else "warning"
            self.update_log.emit(summary, level)

            if errors > 0 and updated > 0 and errors > updated / 2:
                self.update_log.emit("錯誤率過高，可能存在嚴重問題", "error")
                self.finished.emit(False, f"更新完成但錯誤率過高。{summary}")
            else:
                self.finished.emit(True, f"更新成功完成！{summary}")

        except Exception as e:
            self.finished.emit(False, f"執行過程中發生錯誤: {str(e)}")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class BulkUpdateGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker: UpdateWorker | None = None
        self._test_worker: TestConnectionWorker | None = None
        self._fetch_worker: FetchFilesWorker | None = None
        self._init_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("ParaTranz 批量更新工具")
        self.setMinimumSize(760, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 6)

        # Log text must be created before _build_log_header references it
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)

        root.addLayout(self._build_form())

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        root.addLayout(self._build_log_header())
        root.addWidget(self._log_text)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._set_status("就緒")

    def _build_form(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # --- Token ---
        row = QHBoxLayout()
        lbl = QLabel("認證 Token:")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("輸入您的 ParaTranz API Token")
        row.addWidget(self._token_input)
        self._token_eye = QPushButton("顯示")
        self._token_eye.setFixedWidth(52)
        self._token_eye.setCheckable(True)
        self._token_eye.toggled.connect(self._toggle_token_visibility)
        row.addWidget(self._token_eye)
        layout.addLayout(row)

        # --- Project ID ---
        row = QHBoxLayout()
        lbl = QLabel("專案 ID:")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        self._project_input = QLineEdit()
        self._project_input.setValidator(QIntValidator(0, 9_999_999))
        self._project_input.setPlaceholderText("例如: 12345")
        row.addWidget(self._project_input)
        layout.addLayout(row)

        # --- File ID (combo with fetch) ---
        row = QHBoxLayout()
        lbl = QLabel("檔案 ID:")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        self._file_combo = QComboBox()
        self._file_combo.setEditable(True)
        self._file_combo.lineEdit().setPlaceholderText(
            "輸入 ID 或關鍵字搜尋，或點擊「載入清單」"
        )
        # Allow substring search so the user can type any part of the filename
        completer = self._file_combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        row.addWidget(self._file_combo)
        self._load_files_btn = QPushButton("載入清單")
        self._load_files_btn.clicked.connect(self._load_files)
        row.addWidget(self._load_files_btn)
        layout.addLayout(row)

        # --- Translation file ---
        row = QHBoxLayout()
        lbl = QLabel("翻譯檔案:")
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        self._trans_input = QLineEdit()
        self._trans_input.setPlaceholderText("選擇 JSON 格式翻譯檔案")
        row.addWidget(self._trans_input)
        browse_btn = QPushButton("瀏覽...")
        browse_btn.clicked.connect(self._browse_file)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        # --- Update mode ---
        mode_group = QGroupBox("更新模式")
        mode_layout = QHBoxLayout(mode_group)
        self._all_radio = QRadioButton("更新全部詞條")
        self._untranslated_radio = QRadioButton("僅更新未翻譯詞條")
        self._all_radio.setChecked(True)
        mode_layout.addWidget(self._all_radio)
        mode_layout.addWidget(self._untranslated_radio)
        layout.addWidget(mode_group)

        # --- Action buttons ---
        row = QHBoxLayout()
        self._test_btn = QPushButton("測試連線")
        self._test_btn.clicked.connect(self._test_connection)
        row.addWidget(self._test_btn)

        self._save_btn = QPushButton("儲存設定")
        self._save_btn.clicked.connect(self._save_settings)
        row.addWidget(self._save_btn)

        self._run_btn = QPushButton("開始更新")
        self._run_btn.setObjectName("primary")
        self._run_btn.setDefault(True)
        self._run_btn.clicked.connect(self._start_update)
        row.addWidget(self._run_btn)

        layout.addLayout(row)
        return layout

    def _build_log_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("執行日誌:"))
        row.addStretch()

        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self._log_text.clear)
        row.addWidget(clear_btn)

        copy_btn = QPushButton("複製")
        copy_btn.clicked.connect(self._copy_log)
        row.addWidget(copy_btn)

        save_btn = QPushButton("另存…")
        save_btn.clicked.connect(self._save_log)
        row.addWidget(save_btn)

        return row

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _toggle_token_visibility(self, checked: bool):
        self._token_eye.setText("隱藏" if checked else "顯示")
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._token_input.setEchoMode(mode)

    def _set_status(self, msg: str):
        self._status_bar.showMessage(msg)

    def append_log(self, message: str, level: str = "info"):
        colours = {
            "error": "#cc3333",
            "success": "#229944",
            "warning": "#bb6600",
        }
        colour = colours.get(level, "#2c2c2c")
        escaped = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        self._log_text.append(f'<span style="color:{colour}">{escaped}</span>')
        sb = self._log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_log(self):
        QApplication.clipboard().setText(self._log_text.toPlainText())

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "儲存日誌", "log.txt", "文字檔案 (*.txt)"
        )
        if path:
            Path(path).write_text(self._log_text.toPlainText(), encoding="utf-8")

    def _get_file_id(self) -> str:
        data = self._file_combo.currentData()
        if data is not None:
            return str(data)
        return self._file_combo.currentText().strip()

    def _get_stage(self):
        return 0 if self._untranslated_radio.isChecked() else None

    def _validate(self, check_file: bool = True) -> bool:
        if not self._token_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入認證 Token")
            return False
        if not self._project_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入專案 ID")
            return False
        if not self._get_file_id():
            QMessageBox.warning(self, "錯誤", "請輸入或選擇檔案 ID")
            return False
        if check_file and not self._trans_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請選擇翻譯檔案")
            return False
        try:
            int(self._project_input.text())
            int(self._get_file_id())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "專案 ID 和檔案 ID 必須為數字")
            return False
        return True

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇翻譯檔案", "", "JSON 檔案 (*.json)"
        )
        if path:
            self._trans_input.setText(path)

    def _set_busy(self, busy: bool):
        for btn in (
            self._test_btn,
            self._run_btn,
            self._save_btn,
            self._load_files_btn,
        ):
            btn.setEnabled(not busy)
        self._progress.setVisible(busy)
        if not busy:
            self._progress.setValue(0)

    def _populate_file_combo(self, files: list[dict]):
        current_id = self._get_file_id()
        self._file_combo.clear()
        for f in files:
            self._file_combo.addItem(f"{f['name']} ({f['id']})", userData=f["id"])
        if current_id.isdigit():
            idx = self._file_combo.findData(int(current_id))
            if idx >= 0:
                self._file_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _load_files(self):
        if not self._token_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入認證 Token")
            return
        if not self._project_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入專案 ID")
            return
        try:
            project_id = int(self._project_input.text())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "專案 ID 必須為數字")
            return

        self._load_files_btn.setEnabled(False)
        self._load_files_btn.setText("載入中...")
        self._set_status("正在載入檔案清單...")

        self._fetch_worker = FetchFilesWorker(self._token_input.text(), project_id)
        self._fetch_worker.finished.connect(self._on_files_fetched)
        self._fetch_worker.start()

    def _on_files_fetched(self, files: list):
        self._load_files_btn.setEnabled(True)
        self._load_files_btn.setText("載入清單")
        if files:
            self._populate_file_combo(files)
            self._set_status(f"已載入 {len(files)} 個檔案")
            self.append_log(f"已載入 {len(files)} 個檔案", "success")
        else:
            self._set_status("無法載入檔案清單")
            QMessageBox.warning(
                self,
                "載入失敗",
                "無法載入檔案清單，請確認 Token 和專案 ID 是否正確",
            )

    def _test_connection(self):
        if not self._validate(check_file=False):
            return

        stage = self._get_stage()
        mode_text = "未翻譯詞條" if stage == 0 else "所有詞條"
        self._set_busy(True)
        self._test_btn.setText("測試中...")
        self._log_text.clear()
        self._set_status("正在測試連線...")
        self.append_log(f"正在測試 ParaTranz API 連接 (模式: {mode_text})...", "info")

        self._test_worker = TestConnectionWorker(
            self._token_input.text(),
            int(self._project_input.text()),
            int(self._get_file_id()),
            stage,
        )
        self._test_worker.log.connect(self.append_log)
        self._test_worker.finished.connect(self._test_finished)
        self._test_worker.start()

    def _test_finished(self, success: bool, message: str, files: list):
        self._set_busy(False)
        self._test_btn.setText("測試連線")

        if files:
            self._populate_file_combo(files)

        if success:
            self._set_status(f"連線測試成功：{message}")
            QMessageBox.information(self, "連接測試成功", message)
        else:
            self._set_status(f"連線測試失敗：{message}")
            QMessageBox.critical(self, "連接測試失敗", message)

    def _start_update(self):
        if not self._validate():
            return

        stage = self._get_stage()
        mode_text = "未翻譯詞條" if stage == 0 else "所有詞條"
        reply = QMessageBox.question(
            self,
            "確認更新",
            f"確定要更新{mode_text}嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        file_id_data = self._file_combo.currentData()
        file_id = file_id_data if file_id_data is not None else int(self._get_file_id())

        self._set_busy(True)
        self._run_btn.setText("更新中...")
        self._log_text.clear()
        self._set_status(f"正在批量更新{mode_text}...")
        self.append_log(f"開始批量更新{mode_text}...", "info")

        self._worker = UpdateWorker(
            self._token_input.text(),
            int(self._project_input.text()),
            file_id,
            self._trans_input.text(),
            stage=stage,
        )
        self._worker.update_log.connect(self.append_log)
        self._worker.progress.connect(self._update_progress)
        self._worker.finished.connect(self._update_finished)
        self._worker.start()

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
            self._progress.setFormat(f"{current}/{total}")

    def _update_finished(self, success: bool, message: str):
        self._set_busy(False)
        self._run_btn.setText("開始更新")

        if success:
            self._set_status(f"完成：{message}")
            self.append_log(message, "success")
            QMessageBox.information(self, "完成", message)
        else:
            self._set_status(f"失敗：{message}")
            self.append_log(f"錯誤: {message}", "error")
            QMessageBox.critical(self, "錯誤", message)

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self):
        try:
            if not SETTINGS_FILE.exists():
                return
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

            if "auth_token" in settings:
                self._token_input.setText(settings["auth_token"])
            if "project_id" in settings:
                self._project_input.setText(str(settings["project_id"]))
            if "file_id" in settings:
                self._file_combo.setCurrentText(str(settings["file_id"]))
            if "translate_file_path" in settings:
                self._trans_input.setText(settings["translate_file_path"])
            if settings.get("update_mode") == "untranslated":
                self._untranslated_radio.setChecked(True)
            else:
                self._all_radio.setChecked(True)

            x = settings.get("window_x", 100)
            y = settings.get("window_y", 100)
            w = settings.get("window_width", 760)
            h = settings.get("window_height", 560)
            self.setGeometry(x, y, w, h)

            self.append_log("已載入設定檔案", "info")
        except Exception as e:
            self.append_log(f"載入設定檔案時出錯: {str(e)}", "error")

    def _save_settings(self):
        geo = self.geometry()
        file_id_data = self._file_combo.currentData()
        file_id_str = (
            str(file_id_data) if file_id_data is not None else self._get_file_id()
        )

        settings = {
            "auth_token": self._token_input.text(),
            "project_id": self._project_input.text(),
            "file_id": file_id_str,
            "translate_file_path": self._trans_input.text(),
            "update_mode": (
                "untranslated" if self._untranslated_radio.isChecked() else "all"
            ),
            "window_x": geo.x(),
            "window_y": geo.y(),
            "window_width": geo.width(),
            "window_height": geo.height(),
        }
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(settings, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            self.append_log(f"設定已儲存至 {SETTINGS_FILE}", "success")
            QMessageBox.information(
                self,
                "儲存成功",
                f"設定已成功儲存至\n{SETTINGS_FILE}"
                "\n\n⚠️ 注意：此儲存包含你的 API Token，請妥善保管！",
            )
        except Exception as e:
            self.append_log(f"儲存設定時出現錯誤: {str(e)}", "error")
            QMessageBox.critical(self, "儲存失敗", f"儲存設定時出錯: {str(e)}")

    def _save_window_geometry(self):
        try:
            if SETTINGS_FILE.exists():
                settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            else:
                settings = {}
            geo = self.geometry()
            settings.update(
                {
                    "window_x": geo.x(),
                    "window_y": geo.y(),
                    "window_width": geo.width(),
                    "window_height": geo.height(),
                }
            )
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(settings, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
        except Exception:
            pass

    def closeEvent(self, event):
        for worker in (self._worker, self._test_worker, self._fetch_worker):
            if worker and worker.isRunning():
                worker.quit()
                worker.wait(2000)
        self._save_window_geometry()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    window = BulkUpdateGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
