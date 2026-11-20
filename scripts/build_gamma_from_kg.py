"""
Bước 0 của MDE trên KG: ghi môi trường kiểu Γ dựng từ tầng Tiến trình của KG, và so với Γ cũ (BPIC2017).

Chạy:  python scripts/build_gamma_from_kg.py [--check]   (--check: chỉ kiểm Γ trên đĩa khớp KG, không ghi)
Đọc:   data/processed/process_graph.json (TN3), data/processed/bpic2018_process_graph.json (C3),
       data/processed/process_schema.json (Γ cũ, chỉ để so sánh — không bị ghi đè)
Ghi:   data/processed/gamma_bpic2017.json, data/processed/gamma_bpic2018.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.datasets import DISABLED_REASON, bpic2017_enabled  # noqa: E402
from src.mde.schema_from_kg import MetamodelViolation, gamma_from_kg  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
DATASETS = {
    "BPIC2017": (PROCESSED / "process_graph.json", PROCESSED / "gamma_bpic2017.json"),
    "BPIC2018": (PROCESSED / "bpic2018_process_graph.json", PROCESSED / "gamma_bpic2018.json"),
}
OLD_SCHEMA = PROCESSED / "process_schema.json"


def _attributes(schema: Mapping[str, Any]) -> Dict[str, str]:
    return {k: v["type"] for k, v in {**schema["case_attributes"], **schema["event_attributes"]}.items()}


def compare(old: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    old_acts, new_acts = set(old["valid_activities"]), set(new["valid_activities"])
    old_attrs, new_attrs = _attributes(old), _attributes(new)
    type_diff = {k: (old_attrs[k], new_attrs[k]) for k in old_attrs.keys() & new_attrs.keys()
                 if old_attrs[k] != new_attrs[k]}
    lines = [
        f"  activity: cũ {len(old_acts)}, KG {len(new_acts)}, chung {len(old_acts & new_acts)}",
        f"  activity chỉ có ở Γ cũ: {sorted(old_acts - new_acts) or '—'}",
        f"  activity chỉ có ở Γ từ KG: {sorted(new_acts - old_acts) or '—'}",
        f"  thuộc tính chỉ có ở Γ cũ (KG coi là cột kỹ thuật): {sorted(old_attrs.keys() - new_attrs.keys()) or '—'}",
        f"  thuộc tính chỉ có ở Γ từ KG: {sorted(new_attrs.keys() - old_attrs.keys()) or '—'}",
        f"  thuộc tính khác kiểu: {type_diff or '—'}",
    ]
    return "\n".join(lines)


def check_current(dataset: str, graph_path: Path, out_path: Path) -> bool:
    """--check: Γ trên đĩa có đúng là phép chiếu (đã kiểm metamodel) của KG hiện tại không. Không ghi gì."""
    gamma = gamma_from_kg(json.loads(graph_path.read_text(encoding="utf-8")), dataset=dataset)
    on_disk = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
    ok = on_disk == gamma
    sys.stdout.write(f"{dataset}: {out_path.relative_to(PROJECT_ROOT)} "
                     + ("KHỚP phép chiếu của KG\n" if ok else "LỆCH KG (Γ cũ / KG đã dựng lại) — chạy lại không có "
                                                          "--check để ghi Γ mới, rồi chạy lại các cấu hình\n"))
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--check", action="store_true", help="chỉ kiểm Γ trên đĩa khớp KG (exit 1 nếu lệch), không ghi")
    args = p.parse_args()
    all_ok = True
    for dataset, (graph_path, out_path) in DATASETS.items():
        if dataset == "BPIC2017" and not bpic2017_enabled():
            sys.stdout.write(f"{dataset}: bỏ qua — {DISABLED_REASON}\n")
            continue
        if not graph_path.exists():
            sys.stdout.write(f"{dataset}: bỏ qua, chưa có {graph_path.relative_to(PROJECT_ROOT)}\n")
            continue
        try:
            if args.check:
                all_ok &= check_current(dataset, graph_path, out_path)
                continue
            gamma = gamma_from_kg(json.loads(graph_path.read_text(encoding="utf-8")), dataset=dataset)
        except MetamodelViolation as exc:
            sys.stdout.write(f"{dataset}: KHÔNG dựng Γ — {exc}\n")
            all_ok = False
            continue
        out_path.write_text(json.dumps(gamma, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.stdout.write(
            f"{dataset}: ghi {out_path.relative_to(PROJECT_ROOT)} — {len(gamma['valid_activities'])} activity, "
            f"{len(gamma['case_attributes'])} thuộc tính hồ sơ, {len(gamma['event_attributes'])} thuộc tính event, "
            f"{len(gamma['activities_by_origin'])} nhóm origin\n")
        if dataset == "BPIC2017" and OLD_SCHEMA.exists():
            sys.stdout.write("  So với Γ cũ (process_schema.json):\n"
                             + compare(json.loads(OLD_SCHEMA.read_text(encoding="utf-8")), gamma) + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
