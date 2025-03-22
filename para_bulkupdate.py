import os
import json
import sys
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QMessageBox,
    QRadioButton,
    QGroupBox,
)
from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger
from paratranz_py import ParaTranz


class UpdateWorker(QThread):
    update_log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self, auth_token, project_id, file_id, translated_file_path, stage=None
    ):
        super().__init__()
        self.auth_token = auth_token
        self.project_id = project_id
        self.file_id = file_id
        self.translated_file_path = translated_file_path
        self.stage = stage

    def run(self):
        try:
            # 初始化 ParaTranz
            para = ParaTranz(api_token=self.auth_token)

            # 加載翻譯檔案
            try:
                with open(self.translated_file_path, "r", encoding="utf-8") as f:
                    string_translated_dict = json.load(f)
            except Exception as e:
                self.finished.emit(False, f"無法加載翻譯檔案: {str(e)}")
                return

            # 獲取詞條 ID 字典
            try:
                stage_description = "未翻譯的" if self.stage == 0 else "所有"
                self.update_log.emit(f"正在獲取{stage_description}詞條 ID 字典...")
                strings_id_key_dict = self.get_string_id_dict(
                    para, self.project_id, self.file_id, self.stage
                )
                if strings_id_key_dict is None or len(strings_id_key_dict) == 0:
                    self.finished.emit(
                        False, "無法獲取詞條 ID 字典，請檢查專案 ID 和檔案 ID 是否正確"
                    )
                    return

                self.update_log.emit(f"找到 {len(strings_id_key_dict)} 個詞條")
            except Exception as e:
                self.finished.emit(False, f"獲取詞條 ID 時出錯: {str(e)}")
                return

            # 批量更新詞條
            try:
                self.update_log.emit("開始批量更新詞條...")
                result = self.bulk_update_string(
                    para, self.project_id, strings_id_key_dict, string_translated_dict
                )
                if result:
                    self.update_log.emit("詞條更新完成！")
                    self.finished.emit(True, "更新成功完成！")
                else:
                    self.finished.emit(False, "更新詞條過程中發生錯誤")
                    return
            except Exception as e:
                self.finished.emit(False, f"更新詞條時出錯: {str(e)}")
                return

        except Exception as e:
            self.finished.emit(False, f"執行過程中發生錯誤: {str(e)}")

    def get_string_id_dict(self, para, project_id, file_id, stage=None):
        """
        透過 ParaTranz API 獲取特定檔案的詞條資訊
        並將其轉換成 key 與 id 的字典

        stage: None 代表全部詞條，0 代表僅未翻譯的詞條
        """
        return_data = {}
        try:
            # 檢查是否能獲取檔案信息
            file_info = para.files.get_file(project_id=project_id, file_id=file_id)

            # 檢查回傳值是否為 None 或缺少必要字段
            if file_info is None:
                self.update_log.emit("無法獲取檔案信息，API 返回為 None")
                return None

            if "total" not in file_info:
                self.update_log.emit(f"檔案信息格式不正確: {file_info}")
                return None

            file_string_count = file_info["total"]
            stage_text = "未翻譯" if stage == 0 else "所有"
            self.update_log.emit(
                f"檔案中共有 {file_string_count} 個詞條，將獲取{stage_text}詞條"
            )

            # 使用檔案詞條數量計算分頁
            page_size = 300
            page_count = file_string_count // page_size + 1

            # 依照分頁循環
            for i in range(page_count):
                page = i + 1
                self.update_log.emit(f"正在處理第 {page}/{page_count} 頁...")
                data = para.strings.get_strings(
                    project_id=project_id,
                    file_id=file_id,
                    stage=stage,
                    page_size=page_size,
                    page=page,
                )

                # 檢查回傳值是否為 None 或缺少必要字段
                if data is None:
                    self.update_log.emit(f"無法獲取第 {page} 頁詞條，API 返回為 None")
                    continue

                if "results" not in data:
                    self.update_log.emit(f"第 {page} 頁詞條格式不正確: {data}")
                    continue

                for string_data in data["results"]:
                    if "id" not in string_data or "key" not in string_data:
                        continue
                    string_id = string_data["id"]
                    string_key = string_data["key"]
                    return_data[string_key] = string_id

            return return_data
        except Exception as e:
            self.update_log.emit(f"獲取詞條時出錯: {str(e)}")
            return None

    def bulk_update_string(
        self, para, project_id, strings_id_key_dict, translated_strings
    ):
        """
        透過 ParaTranz API 批量更新詞條資訊
        """
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for string_key in translated_strings:
            if string_key in strings_id_key_dict:
                string_id = strings_id_key_dict[string_key]
                string_value = translated_strings[string_key]
                log_message = (
                    f"更新詞條 - 鍵值: {string_key} ({string_id})\n譯文: {string_value}"
                )
                self.update_log.emit(log_message)

                try:
                    response = para.strings.update_string(
                        project_id=project_id,
                        string_id=string_id,
                        translate_text=string_value,
                        stage=1,
                    )

                    # 檢查更新結果
                    if response is None:
                        self.update_log.emit(
                            f"更新詞條 {string_key} 失敗: API 返回為 None"
                        )
                        error_count += 1
                    # 如果返回的是字典，可以檢查其中是否包含錯誤信息
                    elif isinstance(response, dict) and "message" in response:
                        self.update_log.emit(
                            f"更新詞條 {string_key} 失敗: {response['message']}"
                        )
                        error_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    self.update_log.emit(f"更新詞條 {string_key} 時出錯: {str(e)}")
                    error_count += 1
            else:
                self.update_log.emit(f"詞條鍵值未找到: {string_key}")
                skipped_count += 1

        self.update_log.emit(
            f"已更新 {updated_count} 個詞條，跳過 {skipped_count} 個詞條，失敗 {error_count} 個詞條"
        )

        # 如果有嚴重錯誤，可能需要返回 False
        if error_count > (updated_count / 2) and updated_count > 0:
            self.update_log.emit("錯誤率過高，可能存在嚴重問題")
            return False

        return True


class BulkUpdateGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # 設置主視窗
        self.setWindowTitle("ParaTranz 批量更新工具")
        self.setGeometry(100, 100, 700, 500)

        # 主佈局
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # 創建表單佈局
        form_layout = QVBoxLayout()

        # AUTH TOKEN
        token_layout = QHBoxLayout()
        token_label = QLabel("認證 Token:")
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)  # 密碼模式
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_input)
        form_layout.addLayout(token_layout)

        # 專案 ID
        project_layout = QHBoxLayout()
        project_label = QLabel("專案 ID:")
        self.project_input = QLineEdit()
        project_layout.addWidget(project_label)
        project_layout.addWidget(self.project_input)
        form_layout.addLayout(project_layout)

        # 檔案 ID
        file_layout = QHBoxLayout()
        file_label = QLabel("檔案 ID:")
        self.file_input = QLineEdit()
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_input)
        form_layout.addLayout(file_layout)

        # 翻譯檔案路徑
        translate_file_layout = QHBoxLayout()
        translate_file_label = QLabel("翻譯檔案:")
        self.translate_file_input = QLineEdit()
        self.translate_file_button = QPushButton("瀏覽...")
        self.translate_file_button.clicked.connect(self.browse_file)
        translate_file_layout.addWidget(translate_file_label)
        translate_file_layout.addWidget(self.translate_file_input)
        translate_file_layout.addWidget(self.translate_file_button)
        form_layout.addLayout(translate_file_layout)

        # 添加更新模式選擇
        update_mode_group = QGroupBox("更新模式")
        update_mode_layout = QHBoxLayout()

        self.update_all_radio = QRadioButton("更新全部詞條")
        self.update_untranslated_radio = QRadioButton("僅更新未翻譯詞條")
        self.update_all_radio.setChecked(True)  # 默認選擇更新全部

        update_mode_layout.addWidget(self.update_all_radio)
        update_mode_layout.addWidget(self.update_untranslated_radio)
        update_mode_group.setLayout(update_mode_layout)
        form_layout.addWidget(update_mode_group)

        # 添加測試連接按鈕
        self.test_button = QPushButton("測試連接")
        self.test_button.clicked.connect(self.test_connection)
        form_layout.addWidget(self.test_button)

        # 添加執行按鈕
        self.run_button = QPushButton("開始更新")
        self.run_button.clicked.connect(self.start_update)
        form_layout.addWidget(self.run_button)

        # 添加日誌文本框
        log_label = QLabel("執行日誌:")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # 將所有元素添加到主佈局
        main_layout.addLayout(form_layout)
        main_layout.addWidget(log_label)
        main_layout.addWidget(self.log_text)

        # 設置日誌
        logger.remove()  # 移除預設的日誌處理器
        logger.add(lambda msg: self.append_log(msg), level="INFO")

        # 加載環境變數（如果有）
        if os.getenv("AUTH_TOKEN"):
            self.token_input.setText(os.getenv("AUTH_TOKEN"))
        if os.getenv("PROJECT_ID"):
            self.project_input.setText(os.getenv("PROJECT_ID"))
        if os.getenv("FILE_ID"):
            self.file_input.setText(os.getenv("FILE_ID"))
        if os.getenv("TRANSLATED_FILE_PATH"):
            self.translate_file_input.setText(os.getenv("TRANSLATED_FILE_PATH"))

        self.worker = None

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "選擇翻譯檔案", "", "JSON 檔案 (*.json)"
        )
        if file_path:
            self.translate_file_input.setText(file_path)

    def append_log(self, message):
        self.log_text.append(message)
        # 滾動到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def validate_inputs(self, check_file=True):
        if not self.token_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入認證 Token")
            return False
        if not self.project_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入專案 ID")
            return False
        if not self.file_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請輸入檔案 ID")
            return False
        if check_file and not self.translate_file_input.text().strip():
            QMessageBox.warning(self, "錯誤", "請選擇翻譯檔案")
            return False

        # 檢查專案 ID 和檔案 ID 是否為數字
        try:
            int(self.project_input.text())
            int(self.file_input.text())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "專案 ID 和檔案 ID 必須為數字")
            return False

        return True

    def get_selected_stage(self):
        """獲取選擇的更新模式對應的 stage 值"""
        return 0 if self.update_untranslated_radio.isChecked() else None

    def test_connection(self):
        """測試 ParaTranz API 連接，並根據選擇的模式測試詞條獲取"""
        if not self.validate_inputs(check_file=False):
            return

        # 獲取選擇的更新模式
        stage = self.get_selected_stage()
        mode_text = "僅未翻譯詞條" if stage == 0 else "所有詞條"

        self.test_button.setEnabled(False)
        self.test_button.setText("測試中...")
        self.log_text.clear()
        self.append_log(f"正在測試 ParaTranz API 連接 (模式: {mode_text})...")

        try:
            # 創建 ParaTranz 實例
            para = ParaTranz(api_token=self.token_input.text())

            # 嘗試獲取專案信息
            project_id = int(self.project_input.text())
            file_id = int(self.file_input.text())

            # 測試獲取檔案信息
            file_info = para.files.get_file(project_id=project_id, file_id=file_id)

            if file_info is None:
                self.append_log("無法獲取檔案信息，API 返回為 None")
                QMessageBox.critical(
                    self,
                    "連接測試失敗",
                    "無法獲取檔案信息，請檢查 Token、專案 ID 和檔案 ID 是否正確",
                )
                return
            elif isinstance(file_info, dict) and "message" in file_info:
                self.append_log(f"獲取檔案信息失敗: {file_info['message']}")
                QMessageBox.critical(
                    self, "連接測試失敗", f"API 返回錯誤: {file_info['message']}"
                )
                return
            elif isinstance(file_info, dict) and "total" in file_info:
                self.append_log(f"連接成功！檔案中共有 {file_info['total']} 個詞條")
            else:
                self.append_log(f"獲取檔案信息，但返回格式不正確: {file_info}")
                QMessageBox.warning(
                    self, "連接測試結果異常", "連接到 API 成功，但返回格式不符合預期"
                )
                return

            # 測試按指定模式獲取詞條
            self.append_log(f"正在測試獲取{mode_text}...")

            # 僅獲取第一頁詞條進行測試
            data = para.strings.get_strings(
                project_id=project_id,
                file_id=file_id,
                stage=stage,
                page_size=100,
                page=1,
            )

            if data is None:
                self.append_log("無法獲取詞條數據，API 返回為 None")
                QMessageBox.critical(self, "測試獲取詞條失敗", "無法獲取詞條數據")
                return
            elif isinstance(data, dict) and "message" in data:
                self.append_log(f"獲取詞條失敗: {data['message']}")
                QMessageBox.critical(
                    self, "測試獲取詞條失敗", f"API 返回錯誤: {data['message']}"
                )
                return
            elif isinstance(data, dict) and "results" in data:
                result_count = len(data["results"])
                self.append_log(f"成功獲取詞條！第一頁共 {result_count} 個詞條。")

                if stage == 0 and result_count == 0:
                    self.append_log("注意：未找到未翻譯的詞條，可能所有詞條都已翻譯")
                    QMessageBox.information(
                        self,
                        "連接測試成功",
                        "成功連接到 ParaTranz API，但未找到未翻譯的詞條，可能所有詞條都已翻譯",
                    )
                else:
                    QMessageBox.information(
                        self,
                        "連接測試成功",
                        f"成功連接到 ParaTranz API，能夠獲取{mode_text}！",
                    )
            else:
                self.append_log(f"獲取詞條數據，但返回格式不正確: {data}")
                QMessageBox.warning(
                    self, "測試獲取詞條異常", "獲取詞條成功，但返回格式不符合預期"
                )
                return

        except Exception as e:
            self.append_log(f"測試連接時出錯: {str(e)}")
            QMessageBox.critical(
                self, "連接測試失敗", f"連接 ParaTranz API 時發生錯誤: {str(e)}"
            )
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("測試連接")

    def start_update(self):
        if not self.validate_inputs():
            return

        # 獲取選擇的更新模式
        stage = self.get_selected_stage()
        mode_text = "僅未翻譯詞條" if stage == 0 else "所有詞條"

        # 顯示確認對話框
        reply = QMessageBox.question(
            self,
            "確認更新",
            f"確定要更新{mode_text}嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # 禁用按鈕，防止重複點擊
        self.run_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.run_button.setText("更新中...")

        # 清空日誌
        self.log_text.clear()
        self.append_log(f"開始批量更新{mode_text}...")

        # 創建並啟動線程
        self.worker = UpdateWorker(
            self.token_input.text(),
            int(self.project_input.text()),
            int(self.file_input.text()),
            self.translate_file_input.text(),
            stage=stage,
        )
        self.worker.update_log.connect(self.append_log)
        self.worker.finished.connect(self.update_finished)
        self.worker.start()

    def update_finished(self, success, message):
        # 啟用按鈕
        self.run_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.run_button.setText("開始更新")

        # 顯示完成消息
        if success:
            self.append_log(message)
            QMessageBox.information(self, "完成", message)
        else:
            self.append_log(f"錯誤: {message}")
            QMessageBox.critical(self, "錯誤", message)


def main():
    app = QApplication(sys.argv)
    window = BulkUpdateGUI()
    window.show()
    sys.exit(app.exec())  # 在 PyQt6 中，exec_ 方法已改名為 exec


if __name__ == "__main__":
    main()
