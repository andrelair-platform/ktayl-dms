"""Smoke — validates the REAL indra API shape (downloads the model; runs in CI, slow).

This is the ground-truth check that ``app.ocr`` matches the installed ``indra-ocr`` library
(the ``load() → convert()`` contract from ADR-002). A blank image is enough to exercise the full
call path (load + convert + attribute access) without asserting specific recognised text.
"""

import cv2
import numpy as np

from app.ocr import run_ocr


def test_indra_real_api_shape(tmp_path) -> None:
    img = np.full((64, 128, 3), 255, dtype=np.uint8)
    path = str(tmp_path / "blank.png")
    cv2.imwrite(path, img)

    result = run_ocr(path)

    assert "text" in result
    assert "pages" in result
    assert isinstance(result["pages"], list)
    assert isinstance(result["text"], str)
