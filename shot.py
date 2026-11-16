import cv2
import numpy as np
from typing import Optional

MAX_WIDTH = 1280
JPEG_QUALITY = 70
MAX_BYTES = 900000


def encode_jpeg(frame: np.ndarray, max_width: int = MAX_WIDTH, quality: int = JPEG_QUALITY) -> Optional[bytes]:
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, max(1, round(h * max_width / w))), interpolation=cv2.INTER_AREA)
    q = quality
    try:
        while q >= 30:
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            if ok and len(buf) <= MAX_BYTES:
                return bytes(buf)
            q -= 15
        return None
    except Exception:
        return None
