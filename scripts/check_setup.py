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
REQUIRED_PACKAGES = ["pandas", "pyarrow", "pydantic", "pm4py", "rank_bm25", "fitz", "neo4j", "dotenv", "openai"]
DEFAULT_LLM_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
BPIC2017_DATA_FILES = [
    "data/interim/bpic2017_events.parquet",
    "data/processed/directive_chunks.json",
    "data/processed/process_schema.json",
    "data/processed/benchmark_rules_30.json",
]
# Bộ chính: BPIC2018 + 4 Quy định CAP (Phần C của runbook)
CAP_DATA_FILES = [
    "data/interim/bpic2018_events.parquet",
    "data/interim/bpic2018_cases.parquet",
    "data/processed/cap_chunks.json",
    "data/processed/cap_legal_graph.json",
    "data/processed/bpic2018_process_graph.json",
    "data/processed/gamma_bpic2018.json",
]
sys.path.insert(0, str(PROJECT_ROOT))
from src.datasets import bpic2017_enabled  # noqa: E402

# BPIC2017 đang tạm vô hiệu (src/datasets.py): chỉ kiểm file của nó khi NSAI_ENABLE_BPIC2017=1
DATA_FILES = CAP_DATA_FILES + (BPIC2017_DATA_FILES if bpic2017_enabled() else [])


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
    keys = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "GROQ_API_KEY"]
    status = ", ".join(f"{k}={'có' if os.getenv(k) else 'TRỐNG'}" for k in keys)
    return all(os.getenv(k) for k in keys[:3]), status


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


def check_llm() -> Tuple[bool, str]:
    """
    Xác thực API key bằng cách lấy danh sách model (không sinh token, không tốn quota).
    Không dùng models.retrieve(): tên model chứa '/' bị mã hoá thành '%2F' trong URL và Groq trả 404.
    """
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return False, "chưa có GROQ_API_KEY trong .env"
    from openai import OpenAI

    model = os.getenv("LLM_MODEL_NAME", DEFAULT_LLM_MODEL)
    client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL))
    try:
        available = {m.id for m in client.models.list()}
    except Exception as exc:  # báo lỗi xác thực/mạng cho người dùng
        return False, f"key không dùng được: {type(exc).__name__}: {str(exc)[:120]}"
    if model not in available:
        similar = sorted(m for m in available if "gpt-oss" in m or "llama" in m)[:5]
        return False, f"key hợp lệ nhưng không có model '{model}'. Gợi ý: {similar}"
    return True, f"key hợp lệ, model '{model}' khả dụng"


CHECKS: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
    ("Python >= 3.11", check_python),
    ("Thư viện", check_packages),
    ("Dữ liệu đã xử lý", check_data),
    ("File .env", check_env_file),
    ("Neo4j", check_neo4j),
    ("LLM (Groq)", check_llm),
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
