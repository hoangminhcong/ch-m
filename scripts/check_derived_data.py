"""
T1 (kiểm thử 2026-11-20) — dữ liệu phái sinh trên đĩa có đúng là kết quả dựng lại từ nguồn không.

Dựng lại TRONG BỘ NHỚ (không ghi gì vào data/) rồi so với file trên đĩa:
  cap_legal_graph.json       ← cap_chunks.json + cap_annexes.json          (build_cap_graphs.py)
  cap_legal_graph_v2.json    ← cap_chunks.json + cap_legal_graph.json      (build_cap_legal_v2.py)
  de_legal_graph.json        ← de_chunks.json + cap_legal_graph.json       (build_de_legal_graph.py)
  bpic2018_process_graph.json, bpic2018_process_profile.json ← log BPIC2018 (nạp log ~1 phút; --no-log để bỏ)
Khác → file trên đĩa đã cũ (nguồn đổi mà chưa dựng lại) hoặc phép dựng không tất định → exit 1.
(Γ và tầng Cầu nối có phép kiểm riêng: build_gamma_from_kg.py --check, build_mapping_graph.py --check.)

Chạy:  python scripts/check_derived_data.py [--no-log]
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PROCESSED = PROJECT_ROOT / "data" / "processed"
INTERIM = PROJECT_ROOT / "data" / "interim"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _legal_cap() -> Any:
    from src.kg.regulation_graph_builder import build_regulation_graph_file
    with tempfile.TemporaryDirectory() as d:  # hàm dựng ghi ra file → ghi vào thư mục tạm
        build_regulation_graph_file(PROCESSED / "cap_chunks.json", Path(d) / "g.json", PROCESSED / "cap_annexes.json")
        return _load(Path(d) / "g.json")


def _legal_v2() -> Any:
    from scripts.build_cap_legal_v2 import build
    return build(_load(PROCESSED / "cap_chunks.json"), _load(PROCESSED / "cap_legal_graph.json"))


def _legal_de() -> Any:
    from src.kg.de_legal_graph import build_de_legal_graph
    return build_de_legal_graph(_load(PROCESSED / "de_chunks.json"), _load(PROCESSED / "cap_legal_graph.json"))


LEGAL_CHECKS: List[Tuple[str, Callable[[], Any], List[str]]] = [
    ("cap_legal_graph.json", _legal_cap, ["cap_chunks.json", "cap_annexes.json"]),
    ("cap_legal_graph_v2.json", _legal_v2, ["cap_chunks.json", "cap_legal_graph.json"]),
    ("de_legal_graph.json", _legal_de, ["de_chunks.json", "cap_legal_graph.json"]),
]


def compare(name: str, rebuilt: Any, on_disk: Any) -> Dict[str, Any]:
    """Kết quả so một file: same + các khóa cấp đầu khác nhau (để biết phần nào cũ)."""
    same = _canon(rebuilt) == _canon(on_disk)
    keys: List[str] = []
    if not same and isinstance(rebuilt, dict) and isinstance(on_disk, dict):
        keys = sorted(k for k in set(rebuilt) | set(on_disk) if _canon(rebuilt.get(k)) != _canon(on_disk.get(k)))
    return {"file": name, "same": same, "differing_keys": keys}


def _skipped(name: str, why: str) -> Dict[str, Any]:
    return {"file": name, "same": None, "differing_keys": [], "skipped": why}


def check_legal() -> List[Dict[str, Any]]:
    out = []
    for name, build, sources in LEGAL_CHECKS:
        if not (PROCESSED / name).exists() or not all((PROCESSED / s).exists() for s in sources):
            out.append(_skipped(name, "thiếu file nguồn / đích"))
            continue
        out.append(compare(name, build(), _load(PROCESSED / name)))
    return out


def check_log_derived() -> List[Dict[str, Any]]:
    if not (INTERIM / "bpic2018_events.parquet").exists():
        return [_skipped("bpic2018_process_*.json", "chưa có log")]
    import pandas as pd

    from src.kg.process_graph_builder import build_process_graph, with_composite_activity
    from src.kg.process_profile import build_process_profile
    events = with_composite_activity(pd.read_parquet(INTERIM / "bpic2018_events.parquet"))
    cases = pd.read_parquet(INTERIM / "bpic2018_cases.parquet")
    graph = json.loads(_canon(build_process_graph(events, cases=cases).to_dict()))
    profile = json.loads(_canon(build_process_profile(events, cases)))
    return [compare("bpic2018_process_graph.json", graph, _load(PROCESSED / "bpic2018_process_graph.json")),
            compare("bpic2018_process_profile.json", profile, _load(PROCESSED / "bpic2018_process_profile.json"))]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1])
    p.add_argument("--no-log", action="store_true", help="bỏ đồ thị / hồ sơ Tiến trình (không nạp log)")
    args = p.parse_args()
    rows = check_legal() + ([] if args.no_log else check_log_derived())
    for r in rows:
        status = ("bỏ qua (" + r["skipped"] + ")" if r.get("skipped") else "KHỚP" if r["same"]
                  else f"KHÁC — khóa: {r['differing_keys']}")
        sys.stdout.write(f"  {r['file']:<32} {status}\n")
    stale = [r["file"] for r in rows if r["same"] is False]
    if stale:
        sys.stdout.write(f"\nDữ liệu phái sinh KHÔNG khớp nguồn: {stale}. Dựng lại bằng script tương ứng (xem đầu file "
                         "này) rồi chạy lại các cấu hình bị ảnh hưởng.\n")
        return 1
    sys.stdout.write("Dữ liệu phái sinh khớp nguồn.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
