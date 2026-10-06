from __future__ import annotations

from enum import Enum


class AudioQuality(str, Enum):
    LOSSLESS = "lossless"
    HQ = "hq"
    SD = "sd"
    LQ = "lq"
