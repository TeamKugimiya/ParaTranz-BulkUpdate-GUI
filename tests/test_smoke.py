"""Smoke tests: verify the module loads and key objects can be constructed."""


def test_module_attributes():
    import para_bulkupdate

    for attr in (
        "APP_QSS",
        "SETTINGS_FILE",
        "BulkUpdateGUI",
        "UpdateWorker",
        "TestConnectionWorker",
        "FetchFilesWorker",
        "get_string_id_dict",
        "bulk_update_strings",
        "_api_error",
        "_parse_files_list",
        "main",
    ):
        assert hasattr(para_bulkupdate, attr), f"Missing: {attr}"


def test_gui_window_title(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w.windowTitle() == "ParaTranz 批量更新工具"
    w.close()


def test_gui_minimum_size(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w.minimumWidth() == 760
    assert w.minimumHeight() == 560
    w.close()


def test_gui_has_status_bar(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w.statusBar() is not None
    w.close()


def test_gui_log_is_readonly(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w._log_text.isReadOnly()
    w.close()


def test_gui_run_btn_is_default(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w._run_btn.isDefault()
    w.close()


def test_gui_token_echo_mode_is_password(qapp):
    from PyQt6.QtWidgets import QLineEdit

    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w._token_input.echoMode() == QLineEdit.EchoMode.Password
    w.close()


def test_gui_file_combo_is_editable(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    assert w._file_combo.isEditable()
    w.close()


def test_append_log_colour_levels(qapp):
    from para_bulkupdate import BulkUpdateGUI

    w = BulkUpdateGUI()
    w._log_text.clear()
    w.append_log("error msg", "error")
    w.append_log("success msg", "success")
    w.append_log("warning msg", "warning")
    w.append_log("plain msg", "info")
    html = w._log_text.toHtml()
    assert "#cc3333" in html
    assert "#229944" in html
    assert "#bb6600" in html
    w.close()


def test_update_worker_instantiation():
    from para_bulkupdate import UpdateWorker

    worker = UpdateWorker("token", 1, 2, "/tmp/file.json", stage=None)
    assert worker.project_id == 1
    assert worker.file_id == 2
    assert worker.stage is None


def test_fetch_files_worker_instantiation():
    from para_bulkupdate import FetchFilesWorker

    worker = FetchFilesWorker("token", 42)
    assert worker.project_id == 42
