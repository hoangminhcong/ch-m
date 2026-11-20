"""
Công tắc bộ dữ liệu.

Bộ chính hiện tại: BPIC2018 + 4 Quy định CAP. Bộ BPIC2017 + Directive 2008/48/EC được TẠM VÔ HIỆU
(2026-11-09, theo yêu cầu của chủ dự án): không xoá / không di chuyển file nào, chỉ
  - script riêng của BPIC2017 từ chối chạy (require_bpic2017, thoát mã 2);
  - test riêng của BPIC2017 được bỏ qua (skip_unless_bpic2017 / setUpModule);
  - script dùng chung (build_gamma_from_kg, check_setup) bỏ qua phần BPIC2017.
Mở lại:  PowerShell  $env:NSAI_ENABLE_BPIC2017 = "1"   (chỉ trong cửa sổ đó)
"""

import os
import sys
import unittest

ENV_FLAG = "NSAI_ENABLE_BPIC2017"
DISABLED_REASON = (
    f"Bộ BPIC2017 + Directive 2008/48/EC đang tạm vô hiệu (bộ chính: BPIC2018 + CAP). "
    f"Mở lại: đặt biến môi trường {ENV_FLAG}=1, VD PowerShell: $env:{ENV_FLAG} = \"1\""
)


def bpic2017_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip() == "1"


def require_bpic2017(script: str) -> None:
    """Gọi đầu khối __main__ của script riêng BPIC2017: dừng (mã 2) nếu bộ này đang tắt."""
    if not bpic2017_enabled():
        sys.stderr.write(f"{os.path.basename(script)}: {DISABLED_REASON}\n")
        raise SystemExit(2)


skip_unless_bpic2017 = unittest.skipUnless(bpic2017_enabled(), DISABLED_REASON)


def skip_module_unless_bpic2017() -> None:
    """Dùng trong setUpModule() của file test chỉ dành cho BPIC2017."""
    if not bpic2017_enabled():
        raise unittest.SkipTest(DISABLED_REASON)
