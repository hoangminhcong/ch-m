"""
Ghi JSON nguyên tử (file tạm cùng thư mục + os.replace), thử lại khi file đích bị khoá tạm.

Vì sao: thư mục dự án nằm trong OneDrive. Trình đồng bộ giữ khoá file vài trăm ms → 'Access is denied'. Ghi thẳng
(write_text) vừa có thể làm DỪNG cả đợt chạy (ngoại lệ ngoài vòng try), vừa có thể để lại file kết quả ghi dở nếu
tiến trình bị ngắt giữa chừng. Ghi nguyên tử: file đích luôn là bản cũ đầy đủ hoặc bản mới đầy đủ.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from src.evaluation.real_llm_client import CACHE_REPLACE_RETRIES, CACHE_REPLACE_WAIT_S


def write_json_atomic(path: Path, obj: Any, *, indent: int = 1, retries: int = CACHE_REPLACE_RETRIES,
                      wait_s: float = CACHE_REPLACE_WAIT_S, sleep: Callable[[float], None] = time.sleep) -> bool:
    """True = đã ghi. False = file đích vẫn bị khoá sau `retries` lần (file cũ giữ nguyên, file tạm bị xoá)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            sleep(wait_s * (attempt + 1))
    try:
        tmp.unlink()
    except OSError:
        pass  # file tạm cũng bị khoá: lần ghi sau ghi đè cùng tên
    return False
