import base64
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.utils.image_validator import validate_base64_image, validate_image_bytes


def _png_bytes() -> bytes:
    out = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(out, format="PNG")
    return out.getvalue()


def test_validate_image_bytes_rebuilds_image_and_reports_real_mime():
    rebuilt, mime = validate_image_bytes(_png_bytes())

    assert mime == "image/png"
    assert rebuilt.startswith(b"\x89PNG\r\n\x1a\n")

    parsed = Image.open(BytesIO(rebuilt))
    assert parsed.format == "PNG"
    assert parsed.size == (1, 1)


def test_validate_image_bytes_rejects_non_image_payload():
    with pytest.raises(ValueError, match="头像文件头校验失败"):
        validate_image_bytes(b"not an image")


def test_validate_base64_image_reuses_strong_binary_validation():
    raw = _png_bytes()
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

    rebuilt_url = validate_base64_image(data_url)

    assert rebuilt_url.startswith("data:image/png;base64,")
    _, payload = rebuilt_url.split(",", 1)
    rebuilt = base64.b64decode(payload, validate=True)
    assert Image.open(BytesIO(rebuilt)).format == "PNG"
