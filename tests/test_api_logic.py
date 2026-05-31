"""Unit tests for the module-level API helper functions.

These tests do not require a display or a real ParaTranz account — they use
unittest.mock to exercise the logic in isolation.
"""

from unittest.mock import MagicMock

from para_bulkupdate import (
    _api_error,
    _parse_files_list,
    bulk_update_strings,
    get_string_id_dict,
)


# ---------------------------------------------------------------------------
# _api_error
# ---------------------------------------------------------------------------


def test_api_error_none():
    assert _api_error(None) == "API 返回為 None"


def test_api_error_dict_with_message():
    assert _api_error({"message": "Unauthorized"}) == "Unauthorized"


def test_api_error_ok_dict():
    assert _api_error({"total": 5, "results": []}) is None


def test_api_error_list():
    assert _api_error([{"id": 1}]) is None


# ---------------------------------------------------------------------------
# _parse_files_list
# ---------------------------------------------------------------------------


def test_parse_files_list_from_list():
    resp = [{"id": 1, "name": "a.json"}, {"id": 2, "name": "b.json"}]
    result = _parse_files_list(resp)
    assert result == [
        {"id": 1, "name": "a.json"},
        {"id": 2, "name": "b.json"},
    ]


def test_parse_files_list_from_dict_results():
    resp = {"results": [{"id": 3, "name": "c.json"}]}
    result = _parse_files_list(resp)
    assert result == [{"id": 3, "name": "c.json"}]


def test_parse_files_list_skips_missing_id():
    resp = [{"name": "no_id.json"}, {"id": 5, "name": "has_id.json"}]
    result = _parse_files_list(resp)
    assert len(result) == 1
    assert result[0]["id"] == 5


def test_parse_files_list_fallback_name():
    resp = [{"id": 99}]
    result = _parse_files_list(resp)
    assert result[0]["name"] == "99"


def test_parse_files_list_invalid():
    assert _parse_files_list(None) == []
    assert _parse_files_list("not a list") == []


# ---------------------------------------------------------------------------
# get_string_id_dict  (returns {key: {id, translation, stage}})
# ---------------------------------------------------------------------------


def _make_para(file_info, pages):
    para = MagicMock()
    para.files.get_file.return_value = file_info
    para.strings.get_strings.side_effect = pages
    return para


def _noop_log(msg, level="info"):
    pass


def _entry(id, translation="", stage=0):
    """Shorthand for the expected dict shape."""
    return {"id": id, "translation": translation, "stage": stage}


def test_get_string_id_dict_basic():
    page1 = {
        "total": 2,
        "results": [
            {"id": 10, "key": "greeting", "translation": "Hello", "stage": 1},
            {"id": 11, "key": "farewell", "translation": "", "stage": 0},
        ],
    }
    para = _make_para({"total": 2}, [page1])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert result == {
        "greeting": _entry(10, "Hello", 1),
        "farewell": _entry(11, "", 0),
    }


def test_get_string_id_dict_file_none():
    para = _make_para(None, [])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert result is None


def test_get_string_id_dict_file_api_error():
    para = _make_para({"message": "Not found"}, [])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert result is None


def test_get_string_id_dict_missing_total_key():
    para = _make_para({"id": 1}, [])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert result is None


def test_get_string_id_dict_pagination():
    """Two full pages followed by a partial page terminates correctly."""
    page_size = 300
    page1 = {
        "total": 650,
        "results": [{"id": i, "key": f"k{i}", "stage": 0} for i in range(page_size)],
    }
    page2 = {
        "total": 650,
        "results": [
            {"id": i, "key": f"k{i}", "stage": 0}
            for i in range(page_size, page_size * 2)
        ],
    }
    page3 = {
        "total": 650,
        "results": [
            {"id": i, "key": f"k{i}", "stage": 0}
            for i in range(page_size * 2, page_size * 2 + 50)
        ],
    }
    para = _make_para({"total": 650}, [page1, page2, page3])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert len(result) == 650
    assert para.strings.get_strings.call_count == 3


def test_get_string_id_dict_untranslated_uses_page_total():
    """In untranslated mode the page-level total (not file total) drives paging."""
    file_total = 1000  # file has 1000 strings total
    untranslated_total = 2  # but only 2 are untranslated
    page1 = {
        "total": untranslated_total,
        "results": [
            {"id": 1, "key": "a", "stage": 0},
            {"id": 2, "key": "b", "stage": 0},
        ],
    }
    para = _make_para({"total": file_total}, [page1])
    result = get_string_id_dict(para, 1, 1, stage=0, log_fn=_noop_log)
    assert para.strings.get_strings.call_count == 1
    assert result == {"a": _entry(1, "", 0), "b": _entry(2, "", 0)}


def test_get_string_id_dict_progress_reported():
    page1 = {"total": 1, "results": [{"id": 1, "key": "x", "stage": 1}]}
    para = _make_para({"total": 1}, [page1])
    calls = []
    get_string_id_dict(
        para, 1, 1, None, _noop_log, progress_fn=lambda c, t: calls.append((c, t))
    )
    assert len(calls) >= 2  # at least one mid-progress + final


def test_get_string_id_dict_skips_bad_entries():
    page1 = {
        "total": 3,
        "results": [
            {"id": 1, "key": "good", "stage": 1},
            {"id": 2},  # missing key
            {"key": "no_id"},  # missing id
        ],
    }
    para = _make_para({"total": 3}, [page1])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert list(result.keys()) == ["good"]
    assert result["good"]["id"] == 1


def test_get_string_id_dict_none_translation_normalised():
    """API may return null for untranslated strings; should become empty string."""
    page1 = {
        "total": 1,
        "results": [{"id": 1, "key": "k", "translation": None, "stage": 0}],
    }
    para = _make_para({"total": 1}, [page1])
    result = get_string_id_dict(para, 1, 1, None, _noop_log)
    assert result["k"]["translation"] == ""


# ---------------------------------------------------------------------------
# bulk_update_strings
# ---------------------------------------------------------------------------


def _ids(*entries):
    """Build a strings_id_key_dict from (key, id, translation, stage) tuples."""
    return {
        key: {"id": sid, "translation": tr, "stage": st}
        for key, sid, tr, st in entries
    }


def test_bulk_update_strings_all_success():
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("key1", 1, "", 0), ("key2", 2, "", 0))
    updated, skipped, errors = bulk_update_strings(
        para, 1, ids, {"key1": "v1", "key2": "v2"}, _noop_log
    )
    assert updated == 2
    assert skipped == 0
    assert errors == 0


def test_bulk_update_strings_sets_stage_1_for_untranslated():
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "", 0))
    bulk_update_strings(para, 1, ids, {"k": "new"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 1


def test_bulk_update_strings_sets_stage_1_for_translated():
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "old", 1))
    bulk_update_strings(para, 1, ids, {"k": "new"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 1


def test_bulk_update_strings_preserves_reviewed_stage_when_unchanged():
    """stage=3, text unchanged → keep stage=3."""
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "same text", 3))
    bulk_update_strings(para, 1, ids, {"k": "same text"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 3


def test_bulk_update_strings_preserves_double_reviewed_stage_when_unchanged():
    """stage=5, text unchanged → keep stage=5."""
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "same", 5))
    bulk_update_strings(para, 1, ids, {"k": "same"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 5


def test_bulk_update_strings_downgrades_reviewed_when_text_changed():
    """stage=3, text changed → set stage=1."""
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "old text", 3))
    bulk_update_strings(para, 1, ids, {"k": "new text"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 1


def test_bulk_update_strings_downgrades_double_reviewed_when_text_changed():
    """stage=5, text changed → set stage=1."""
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k", 1, "old", 5))
    bulk_update_strings(para, 1, ids, {"k": "new"}, _noop_log)
    kwargs = para.strings.update_string.call_args[1]
    assert kwargs["stage"] == 1


def test_bulk_update_strings_skips_missing_keys():
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("key1", 1, "", 0))
    updated, skipped, errors = bulk_update_strings(
        para, 1, ids, {"key1": "v1", "missing": "v2"}, _noop_log
    )
    assert updated == 1
    assert skipped == 1
    assert errors == 0


def test_bulk_update_strings_api_error_response():
    para = MagicMock()
    para.strings.update_string.return_value = {"message": "Rate limited"}
    ids = _ids(("key1", 1, "", 0))
    updated, skipped, errors = bulk_update_strings(
        para, 1, ids, {"key1": "v1"}, _noop_log
    )
    assert updated == 0
    assert errors == 1


def test_bulk_update_strings_exception():
    para = MagicMock()
    para.strings.update_string.side_effect = RuntimeError("network error")
    ids = _ids(("key1", 1, "", 0))
    updated, skipped, errors = bulk_update_strings(
        para, 1, ids, {"key1": "v1"}, _noop_log
    )
    assert updated == 0
    assert errors == 1


def test_bulk_update_strings_progress_reported():
    para = MagicMock()
    para.strings.update_string.return_value = {"id": 1}
    ids = _ids(("k1", 1, "", 0), ("k2", 2, "", 0))
    calls = []
    bulk_update_strings(
        para,
        1,
        ids,
        {"k1": "v1", "k2": "v2"},
        _noop_log,
        progress_fn=lambda c, t: calls.append((c, t)),
    )
    assert calls[-1] == (2, 2)


def test_bulk_update_strings_empty_translated():
    para = MagicMock()
    ids = _ids(("key1", 1, "", 0))
    updated, skipped, errors = bulk_update_strings(para, 1, ids, {}, _noop_log)
    assert updated == 0
    assert skipped == 0
    assert errors == 0
    para.strings.update_string.assert_not_called()
