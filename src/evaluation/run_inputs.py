"""
Dấu dữ liệu đầu vào của một lần sinh luật (A2): SHA-256 của mọi file dữ liệu mà cấu hình đọc.

Vì sao: sự cố v1.2 (2026-11-19) — dữ liệu khoản / đồ thị được sửa giữa hai lần chạy, file kết quả không ghi lại
mình được sinh từ dữ liệu nào, nên kết quả hai phiên bản dữ liệu nằm lẫn trong một file mà không công cụ nào báo.

  meta["inputs"]            {tên: sha256} của lần chạy ghi file gần nhất
  meta["inputs_id"]         mã ngắn của cả bộ (12 ký tự hex)
  prediction["inputs_id"]   mã của bộ dữ liệu đã sinh RA khoản đó (khoản sinh trước khi có cơ chế này: không có)

Chỉ dấu DỮ LIỆU (file); prompt / code không nằm trong dấu.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

MISSING = "missing"
CHUNK_BYTES = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK_BYTES), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(paths: Mapping[str, Path]) -> Dict[str, str]:
    """{tên: sha256}; file không tồn tại → 'missing' (vẫn ghi để thấy cấu hình chạy thiếu đầu vào)."""
    return {name: sha256_file(Path(p)) if Path(p).exists() else MISSING for name, p in sorted(paths.items())}


def inputs_id(fp: Mapping[str, str]) -> str:
    return hashlib.sha256(json.dumps(dict(sorted(fp.items()))).encode("utf-8")).hexdigest()[:12]


def changed_inputs(old: Mapping[str, str], new: Mapping[str, str]) -> List[str]:
    """Tên các đầu vào chung của hai dấu mà nội dung khác nhau."""
    return sorted(k for k in old.keys() & new.keys() if old[k] != new[k])


def code_version(root: Path) -> Dict[str, Any]:
    """Phiên bản CODE của lần chạy (2026-11-20): SHA-256 của mọi file .py trong src/ và scripts/ (đường dẫn + nội
    dung, thứ tự cố định) — không cần git; kèm mã commit git nếu thư mục là kho git. Chỉ GHI LẠI, không chặn chạy tiếp
    (sửa lỗi code giữa các lần chạy là bình thường), nhưng cho phép truy kết quả về đúng phiên bản code."""
    import subprocess

    files = sorted(p for d in ("src", "scripts") for p in (root / d).rglob("*.py") if "__pycache__" not in p.parts)
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    out: Dict[str, Any] = {"sha256": h.hexdigest()[:16], "files": len(files)}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "scripts"], cwd=root,
                               capture_output=True, text=True, timeout=10)
        if commit.returncode == 0:
            out.update(git_commit=commit.stdout.strip(), git_dirty=bool(dirty.stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        pass  # không có git: dấu sha256 vẫn đủ để so phiên bản code
    return out


def input_conflicts(docs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Rà các file dự đoán (cấu hình → nội dung predictions_<cfg>.json).
      within    cấu hình → số khoản sinh từ bộ dữ liệu KHÁC bộ ghi ở meta (file lẫn hai phiên bản dữ liệu)
      across    tên đầu vào → {cấu hình: sha256} khi hai cấu hình đọc cùng đầu vào nhưng nội dung khác
      unstamped cấu hình → số khoản chưa có dấu (sinh trước khi có cơ chế này — không kết luận được)"""
    within: Dict[str, int] = {}
    unstamped: Dict[str, int] = {}
    seen: Dict[str, Dict[str, str]] = {}
    for cfg, doc in docs.items():
        file_id = doc.get("inputs_id")
        ids = [p.get("inputs_id") for p in doc.get("predictions", {}).values()]
        if any(i is None for i in ids):
            unstamped[cfg] = sum(1 for i in ids if i is None)
        n_other = sum(1 for i in ids if i is not None and i != file_id)
        if n_other:
            within[cfg] = n_other
        for name, digest in (doc.get("inputs") or {}).items():
            seen.setdefault(name, {})[cfg] = digest
    across = {name: by_cfg for name, by_cfg in seen.items() if len(set(by_cfg.values())) > 1}
    return {"within": within, "across": across, "unstamped": unstamped}
