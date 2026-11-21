"""
T3 (kiểm thử 2026-11-20) — phát lại cache LLM bằng code HIỆN TẠI và so với kết quả đã ghi.

Cùng câu trả lời LLM (cache) mà ra outcome / AST / trạng thái từng vòng khác → code đã đổi HÀNH VI so với lúc sinh
file (cố ý — VD sửa lỗi — hoặc không). Dùng để: (1) chứng minh một lần sửa code không đổi kết quả đã báo cáo;
(2) liệt kê đúng các khoản một lần sửa cố ý làm thay đổi.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence


def run_command(python: str, script: str, cfg: str, doc: Mapping[str, Any], out_dir: str,
                only: Optional[Sequence[str]] = None) -> List[str]:
    """Lệnh run_cap_generation chỉ phát lại cache (không gọi API) với đúng model / nhà cung cấp / bộ dữ liệu /
    giám khảo của file gốc."""
    cmd = [python, script, "--config", cfg, "--provider", doc["provider"], "--model", doc["model"],
           "--dataset", doc.get("dataset", "cap"), "--out-dir", out_dir, "--cache-only", "--force"]
    if doc.get("judge_provider"):
        cmd += ["--judge-provider", doc["judge_provider"], "--judge-model", doc["judge_model"]]
    if only:
        cmd += ["--only", *only]
    return cmd


def compare_predictions(original: Mapping[str, Mapping[str, Any]],
                        replayed: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """So từng khoản. Khoản ERROR trong file gốc (chưa có câu trả lời trong cache) không so được → 'skipped'."""
    same, skipped, diffs = 0, [], []
    for nid, a in sorted(original.items()):
        if a.get("outcome") == "ERROR":
            skipped.append(nid)
            continue
        b = replayed.get(nid)
        if b is None or b.get("outcome") == "ERROR":
            diffs.append({"clause": nid, "kind": "replay_error",
                          "replayed": None if b is None else str(b.get("error", ""))[:200]})
            continue
        sa = [t.get("status") for t in a.get("trajectory") or []]
        sb = [t.get("status") for t in b.get("trajectory") or []]
        if a["outcome"] != b["outcome"] or a.get("ast") != b.get("ast") or sa != sb:
            diffs.append({"clause": nid, "kind": "changed", "original": {"outcome": a["outcome"], "statuses": sa},
                          "replayed": {"outcome": b["outcome"], "statuses": sb},
                          "ast_changed": a.get("ast") != b.get("ast")})
        else:
            same += 1
    return {"compared": same + len(diffs), "identical": same, "skipped_error": skipped, "differences": diffs}
