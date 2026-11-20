"""
Gold ứng viên cho bộ CAP từ phiếu gán nhãn `CAP_ITEM_CANDIDATES_<tên>.txt` (khối "Mẫu trả lời").

Mỗi khoản thành một mục, phân loại theo nhãn — KHÔNG tự sửa nhãn (quyết định gold thuộc người duyệt):
  positive   Quan sát được = Có, có ≥ 1 ràng buộc chuyển được sang AST → đáp án đúng là (một trong) các AST
  trap       Quan sát được = Không → đáp án đúng là BASELESS (hệ thống không được sinh ràng buộc)
  uncertain  Quan sát được = Không chắc → không chấm cho tới khi người duyệt quyết
  invalid    Có nhưng thiếu ràng buộc, hoặc ràng buộc không chuyển được (lỗi ghi rõ) → phải sửa phiếu
Tier 4 = câu (3) "Cần điều tham chiếu" là Có / Một phần.
Cờ cảnh báo (không loại tự động): con số / ngày trong ràng buộc không có trong khoản luật (và khoản được
dẫn chiếu, nếu Tier 4) — quy tắc mục 7.
"""

import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..symbolic.verbalizer_roundtrip import verify_generic_numeric_entities
from .cap_notation import NotationError, notation_to_ast

FIELD = r"\*{0,2}\s*%s\s*:\s*\*{0,2}"
# Mã khoản: CAP 'R809:Art22(1)'; tập Đức (v2) 'DE-InVeKoSV:§7(3)@2016' (@năm khi văn bản khác nhau giữa các năm)
NODE_ID = r"(R\d+:Art[\w()]+|DE-\w+:§[0-9a-z()]+(?:@[0-9-]+)?)"
_LINE = re.compile(
    r"^\s*" + NODE_ID + r"\s*:\s*" + FIELD % "Quan sát được" + r"(.*?)\s*·\s*"
    + FIELD % "Ràng buộc mới" + r"(.*?)\s*·\s*" + FIELD % "Cần điều tham chiếu" + r"(.*?)\s*·\s*"
    + FIELD % "Độ chắc chắn" + r"(.*?)\s*·\s*" + FIELD % "Lý do" + r"(.*)$",
    re.MULTILINE,
)
_ID_START = re.compile(r"^\s*" + NODE_ID + r"\s*:")
EMPTY = {"", "—", "-", "–", "___"}
OBSERVABLE = {"có": "yes", "không": "no", "không chắc": "unsure", "không chắc chắn": "unsure"}
TIER4_PREFIXES = ("có", "một phần")
KINDS = ("positive", "trap", "uncertain", "invalid", "unlabeled")


def _clean(value: str) -> str:
    return value.strip().strip("*").strip()


def _answer(value: str) -> str:
    """Câu trả lời ngắn đã chuẩn hoá: chữ thường, bỏ dấu câu cuối ('Có.' → 'có')."""
    return value.strip().rstrip(".,;:!").strip().lower()


def needs_reference(answer: str) -> bool:
    """Câu (3) 'Cần điều tham chiếu' = Có / Một phần — kể cả khi có ghi thêm giải thích ('Có (ngày … lấy từ …)')."""
    a = _answer(answer)
    return any(a == p or a.startswith(p + " ") or a.startswith(p + "(") for p in TIER4_PREFIXES)


def parse_label_sheet(text: str) -> Dict[str, Dict[str, Any]]:
    """
    Đọc mọi dòng 'R…:Art…: **Quan sát được:** … · … · **Lý do:** …'. Dòng còn '___' coi như chưa điền.
    F-SHEET (kiểm toán đợt 2): chuẩn hoá Unicode NFC (bộ gõ tổ hợp); dòng có mã khoản nhưng sai định dạng, hoặc
    một khoản xuất hiện hai lần → ValueError liệt kê từng dòng (trước đây bị bỏ qua / bị đè IM LẶNG).
    """
    out: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    for no, line in enumerate(unicodedata.normalize("NFC", text).splitlines(), start=1):
        start = _ID_START.match(line)
        if not start:
            continue
        m = _LINE.match(line)
        if not m:
            problems.append(f"dòng {no} ({start.group(1)}): sai định dạng 'Mẫu trả lời' (thiếu trường hoặc dấu ·)")
            continue
        if m.group(1) in out:
            problems.append(f"dòng {no} ({m.group(1)}): khoản đã có ở dòng trước")
            continue
        obs, raw, ref, conf, reason = (_clean(m.group(i)) for i in range(2, 7))
        constraints = [] if raw in EMPTY else [c.strip() for c in raw.split(";") if c.strip() not in EMPTY]
        out[m.group(1)] = {"observable": OBSERVABLE.get(_answer(obs), "blank" if obs in EMPTY else obs),
                           "constraints": constraints, "needs_ref": ref, "confidence": conf, "reason": reason}
    if problems:
        raise ValueError("Phiếu nhãn có dòng không đọc được:\n" + "\n".join(problems))
    return out


def _context_text(chunk: Mapping[str, Any], tier4: bool) -> str:
    texts = [chunk.get("text", "")]
    if tier4:
        texts += [r.get("text", "") for r in chunk.get("referenced", []) if r.get("found")]
    return "\n".join(texts)


CASE_SCOPED_EXISTENCE = ("Existence", "Exactly1", "Init")


def case_condition_flags(ast: Mapping[str, Any]) -> List[str]:
    """
    Existence(A) | case:X == v nghĩa là MỌI hồ sơ phải có một A thoả X — hồ sơ không thuộc diện X cũng bị tính vi
    phạm. Ý 'hồ sơ thuộc diện X thì phải có A' viết là Responded Existence(<bước mọi hồ sơ đều có> → A) | case:X == v.
    """
    if ast.get("template_name") not in CASE_SCOPED_EXISTENCE or not ast.get("activation_attr"):
        return []
    attrs = [ast["activation_attr"]] + [c["attr"] for c in ast.get("extra_conditions") or []]
    case_attrs = [a for a in attrs if str(a).startswith("case:")]
    if not case_attrs:  # chỉ điều kiện ngày / thuộc tính event: không thuộc lỗi này
        return []
    return [f"ĐIỀU KIỆN HỒ SƠ TRÊN {ast['template_name']}: mọi hồ sơ không thoả {', '.join(case_attrs)} đều bị tính vi "
            f"phạm. Nếu ý là 'hồ sơ thuộc diện đó thì phải có A', viết Responded Existence(Payment application / "
            f"Application / mail income → A) | <điều kiện> (hướng dẫn mục 5.2)"]


def number_flags(ast: Mapping[str, Any], context_text: str) -> List[str]:
    """Cảnh báo mục 7: con số / ngày không có trong văn bản (dùng chính Generic Entity Matcher)."""
    ok, verdict, diag = verify_generic_numeric_entities(dict(ast), {"text": context_text}, check_year_values=True)
    return [] if ok else [f"{verdict}: {diag}"]


def _positive(node_id: str, label: Mapping[str, Any], chunk: Mapping[str, Any],
              gamma: Mapping[str, Any], tier4: bool) -> Dict[str, Any]:
    gold, errors, warnings = [], [], []
    for notation in label["constraints"]:
        try:
            ast = notation_to_ast(notation, gamma, node_id)
        except NotationError as exc:
            errors.append(f"'{notation}': {exc}")
            continue
        warnings += [f"'{notation}': {w}" for w in number_flags(ast, _context_text(chunk, tier4)) + case_condition_flags(ast)]
        if ast not in gold:
            gold.append(ast)
    if not label["constraints"]:
        errors.append("Quan sát được = Có nhưng không ghi ràng buộc")
    kind = "invalid" if errors else "positive"
    return {"kind": kind, "gold": gold, "errors": errors, "warnings": warnings}


def classify_clause(node_id: str, label: Optional[Mapping[str, Any]], chunk: Mapping[str, Any],
                    gamma: Mapping[str, Any]) -> Dict[str, Any]:
    """Khoản phiếu → mục gold. Khoản có 'years' (tập Đức) mang năm vào gold (rà soát 2026-11-18 E-H5) để bước
    phán quyết từng hồ sơ giới hạn đúng năm mà không phụ thuộc file phiếu."""
    out = _classify(node_id, label, chunk, gamma)
    if label is not None and label["observable"] == "yes" and str(label.get("needs_ref", "")).strip() in EMPTY:
        out["warnings"] = [*out["warnings"], "Câu (3) Cần điều tham chiếu chưa điền → coi là Không (không Tier 4)"]
    if label is not None and label["observable"] in ("no", "unsure") and label.get("constraints"):
        out["warnings"] = [*out["warnings"], "Có ghi ràng buộc nhưng Quan sát được = Không / Không chắc → ràng "
                                             "buộc bị bỏ qua"]
    return {**out, "years": list(chunk["years"])} if chunk.get("years") else out


def _classify(node_id: str, label: Optional[Mapping[str, Any]], chunk: Mapping[str, Any],
              gamma: Mapping[str, Any]) -> Dict[str, Any]:
    base = {"node_id": node_id, "round": chunk.get("round"), "label": dict(label) if label else None}
    if label is None or label["observable"] == "blank":
        return {**base, "kind": "unlabeled", "tier4": False, "gold": [], "errors": [], "warnings": []}
    tier4 = label["observable"] == "yes" and needs_reference(label["needs_ref"])
    if label["observable"] == "yes":
        return {**base, "tier4": tier4, **_positive(node_id, label, chunk, gamma, tier4)}
    kind = {"no": "trap", "unsure": "uncertain"}.get(label["observable"], "invalid")
    errors = [] if kind != "invalid" else [f"Quan sát được = '{label['observable']}' (cần Có / Không / Không chắc)"]
    return {**base, "kind": kind, "tier4": False, "gold": [], "errors": errors, "warnings": []}


def build_gold_candidates(labels: Mapping[str, Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]],
                          gamma: Mapping[str, Any]) -> Dict[str, Any]:
    """Mọi khoản của phiếu (theo thứ tự phiếu) → mục gold ứng viên. Nhãn cho khoản lạ → lỗi."""
    known = {c["node_id"] for c in candidates}
    unknown = sorted(set(labels) - known)
    if unknown:
        raise KeyError(f"Nhãn cho khoản không có trong phiếu: {unknown}")
    clauses = {c["node_id"]: classify_clause(c["node_id"], labels.get(c["node_id"]), c, gamma) for c in candidates}
    summary = Counter(c["kind"] for c in clauses.values())
    summary["tier4"] = sum(c["tier4"] for c in clauses.values() if c["kind"] == "positive")
    summary["with_warnings"] = sum(bool(c["warnings"]) for c in clauses.values())
    return {"status": "candidate", "clauses": clauses, "summary": {k: summary.get(k, 0) for k in
                                                                   (*KINDS, "tier4", "with_warnings")}}


def approval_blockers(gold: Mapping[str, Any]) -> List[str]:
    """Lý do chưa duyệt được: khoản invalid (phải sửa phiếu) và khoản CHƯA gán nhãn (rà soát 2026-11-18 E-H4: trước
    đây được duyệt rồi im lặng bị loại khỏi phép chấm). Cảnh báo số liệu chỉ hiển thị, không chặn."""
    out = [f"{nid}: {'; '.join(c['errors'])}" for nid, c in gold["clauses"].items() if c["kind"] == "invalid"]
    return out + [f"{nid}: chưa gán nhãn" for nid, c in gold["clauses"].items() if c["kind"] == "unlabeled"]


def scored_clauses(gold: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Khoản được chấm điểm: positive và trap (uncertain / unlabeled / invalid không chấm)."""
    return {nid: c for nid, c in gold["clauses"].items() if c["kind"] in ("positive", "trap")}
