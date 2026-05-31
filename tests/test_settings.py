"""Tests for settings persistence (save/load)."""

import json

import pytest

from para_bulkupdate import BulkUpdateGUI


@pytest.fixture
def app(qapp):
    return qapp


@pytest.fixture
def settings_path(tmp_path):
    path = tmp_path / "settings.json"
    return path


@pytest.fixture
def window(app, settings_path, monkeypatch):
    import para_bulkupdate
    from unittest.mock import MagicMock

    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    # Prevent modal QMessageBox from blocking test execution
    monkeypatch.setattr(para_bulkupdate.QMessageBox, "information", MagicMock())
    monkeypatch.setattr(para_bulkupdate.QMessageBox, "critical", MagicMock())
    w = BulkUpdateGUI()
    yield w
    w.close()


def _write_settings(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_settings_populates_token(qapp, settings_path, monkeypatch):
    import para_bulkupdate

    _write_settings(settings_path, {"auth_token": "secret123"})
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    w = BulkUpdateGUI()
    assert w._token_input.text() == "secret123"
    w.close()


def test_load_settings_populates_project_id(qapp, settings_path, monkeypatch):
    import para_bulkupdate

    _write_settings(settings_path, {"project_id": 456})
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    w = BulkUpdateGUI()
    assert w._project_input.text() == "456"
    w.close()


def test_load_settings_populates_file_id(qapp, settings_path, monkeypatch):
    import para_bulkupdate

    _write_settings(settings_path, {"file_id": "789"})
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    w = BulkUpdateGUI()
    assert w._file_combo.currentText() == "789"
    w.close()


def test_load_settings_sets_untranslated_mode(qapp, settings_path, monkeypatch):
    import para_bulkupdate

    _write_settings(settings_path, {"update_mode": "untranslated"})
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    w = BulkUpdateGUI()
    assert w._untranslated_radio.isChecked()
    w.close()


def test_load_settings_sets_all_mode_by_default(qapp, settings_path, monkeypatch):
    import para_bulkupdate

    _write_settings(settings_path, {"update_mode": "all"})
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", settings_path)
    w = BulkUpdateGUI()
    assert w._all_radio.isChecked()
    w.close()


def test_load_settings_missing_file_is_silent(qapp, tmp_path, monkeypatch):
    import para_bulkupdate

    missing = tmp_path / "nonexistent.json"
    monkeypatch.setattr(para_bulkupdate, "SETTINGS_FILE", missing)
    # Should not raise
    w = BulkUpdateGUI()
    w.close()


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_settings_writes_token(window, settings_path):
    window._token_input.setText("my_token")
    window._project_input.setText("0")
    window._save_settings()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["auth_token"] == "my_token"


def test_save_settings_writes_project_id(window, settings_path):
    window._token_input.setText("tok")
    window._project_input.setText("9999")
    window._save_settings()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["project_id"] == "9999"


def test_save_settings_writes_update_mode_untranslated(window, settings_path):
    window._token_input.setText("tok")
    window._project_input.setText("1")
    window._untranslated_radio.setChecked(True)
    window._save_settings()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["update_mode"] == "untranslated"


def test_save_settings_writes_update_mode_all(window, settings_path):
    window._token_input.setText("tok")
    window._project_input.setText("1")
    window._all_radio.setChecked(True)
    window._save_settings()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["update_mode"] == "all"


def test_save_settings_writes_window_geometry(window, settings_path):
    window._token_input.setText("tok")
    window._project_input.setText("1")
    window._save_settings()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "window_x" in saved
    assert "window_width" in saved
