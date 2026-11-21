"""
Bước 0 – Kiểm tra môi trường thực nghiệm. Chạy lại sau mỗi bước cài đặt.

Chạy:  python scripts/check_setup.py
Không in ra mật khẩu / API key, chỉ báo có hay không.
"""

import importlib
import os
import sys
from pathlib import Path
from typing import Callable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
REQUIRED_PACKAGES = ["pandas", "pyarrow", "pydantic", "pm4py", "rank_bm25", "fitz", "neo4j", "dotenv", "openai"]
# Bộ chính: BPIC2018 + 4 Quy định CAP (Phần C của runbook)
CAP_DATA_FILES = [
    "data/interim/bpic2018_events.parquet",
    "data/interim/bpic2018_cases.parquet",
    "data/processed/cap_chunks.json",
    "data/processed/cap_legal_graph.json",
    "data/processed/bpic2018_process_graph.json",
    "data/processed/gamma_bpic2018.json",
]
# 2026-11-21: dữ liệu BPIC2017 đã chuyển ra kho lưu → chỉ kiểm dữ liệu của bộ chính
DATA_FILES = CAP_DATA_FILES


def check_python() -> Tuple[bool, str]:
    ok = sys.version_info >= (3, 11)
    return ok, f"Python {sys.version.split()[0]} ({sys.executable})"


def check_packages() -> Tuple[bool, str]:
    missing = []
    for name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return not missing, "đủ thư viện" if not missing else f"thiếu: {', '.join(missing)}"


def check_data() -> Tuple[bool, str]:
    missing = [p for p in DATA_FILES if not (PROJECT_ROOT / p).exists()]
    return not missing, "đủ dữ liệu" if not missing else f"thiếu: {', '.join(missing)}"


def check_env_file() -> Tuple[bool, str]:
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        return False, "chưa có .env (copy từ .env.example)"
    from dotenv import load_dotenv

    load_dotenv(env)
    keys = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
    status = ", ".join(f"{k}={'có' if os.getenv(k) else 'TRỐNG'}" for k in keys)
    return all(os.getenv(k) for k in keys), status


def check_neo4j() -> Tuple[bool, str]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.kg.neo4j_store import Neo4jKGStore

    try:
        store = Neo4jKGStore.from_env()
    except Exception as exc:  # báo lỗi kết nối cho người dùng, không dừng các kiểm tra khác
        return False, f"không kết nối được: {type(exc).__name__}: {str(exc)[:120]}"
    with store.driver.session() as session:
        count = session.run("MATCH (n:KG) RETURN count(n) AS c").single()["c"]
    store.close()
    return True, f"kết nối OK, đang có {count} node KG"


def _check_provider(name: str, base_url: str, model: str) -> Tuple[bool, str]:
    """Một nhà cung cấp: có key không, key có liệt kê được model chính không (lấy danh sách model — không sinh token,
    không tốn quota). Không dùng models.retrieve(): tên model có '/' bị mã hoá '%2F' và Groq trả 404."""
    from openai import OpenAI

    from src.evaluation.real_llm_client import key_vars_for

    var = next((v for v in key_vars_for(base_url) if os.getenv(v)), None)
    if var is None:
        return False, f"{name}: chưa có key ({' / '.join(key_vars_for(base_url))})"
    try:
        available = {m.id for m in OpenAI(api_key=os.getenv(var), base_url=base_url).models.list()}
    except Exception as exc:  # báo lỗi xác thực / mạng cho người dùng, không dừng các nhà cung cấp khác
        return False, f"{name}: key {var} không dùng được ({type(exc).__name__})"
    if model not in available:
        return False, f"{name}: key {var} hợp lệ nhưng không có model '{model}'"
    return True, f"{name}: key {var} hợp lệ, model '{model}' khả dụng"


def check_llm() -> Tuple[bool, str]:
    """Mọi nhà cung cấp của run_cap_generation (Cerebras, Groq); OK khi ÍT NHẤT một nhà cung cấp dùng được model
    chính. 2026-11-21: trước đây chỉ kiểm Groq — báo LỖI dù Cerebras (nhà cung cấp chính) dùng được."""
    from scripts.run_cap_generation import PROVIDERS

    results = [_check_provider(name, url, model) for name, (url, model) in sorted(PROVIDERS.items())]
    return any(ok for ok, _ in results), " | ".join(detail for _, detail in results)


CHECKS: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
    ("Python >= 3.11", check_python),
    ("Thư viện", check_packages),
    ("Dữ liệu đã xử lý", check_data),
    ("File .env", check_env_file),
    ("Neo4j", check_neo4j),
    ("LLM (gpt-oss-120b)", check_llm),
]


def main() -> int:
    all_ok = True
    for name, check in CHECKS:
        ok, detail = check()
        all_ok = all_ok and ok
        sys.stdout.write(f"[{'OK ' if ok else 'LỖI'}] {name:<18} {detail}\n")
    sys.stdout.write("\nTất cả đã sẵn sàng.\n" if all_ok else "\nCòn mục LỖI, xem docs/HUONG_DAN_THUC_NGHIEM.md.\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
