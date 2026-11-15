"""L1 unit — the result-shaping logic (no real indra model needed)."""

from app.ocr import _box, _line_to_dict


class _Line:
    def __init__(self, text: str, box, conf) -> None:
        self.text = text
        self.box = box
        self.conf = conf


def test_line_to_dict_normalises_box_to_floats() -> None:
    d = _line_to_dict(_Line("CLAIM 12345", (1, 2, 3, 4), 0.97))
    assert d["text"] == "CLAIM 12345"
    assert d["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert d["confidence"] == 0.97


def test_line_to_dict_handles_missing_box() -> None:
    class _NoBox:
        text = "x"

    d = _line_to_dict(_NoBox())
    assert d["bbox"] is None
    assert d["text"] == "x"


def test_box_returns_none_for_unboxed() -> None:
    class _X:
        pass

    assert _box(_X()) is None
