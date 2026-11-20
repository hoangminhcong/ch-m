"""
TN4 – Đối chiếu engine DECLARE tự viết của NSAI (src/symbolic/declare4py_verifier.py) với thư viện chuẩn.

Chuẩn đối chiếu:
- pm4py.conformance_declare (pm4py 2.7) cho 13/17 template — chỉ phần luồng điều khiển (không điều kiện
  dữ liệu, không thời hạn). `Not Responded Existence(A,B)` = "A xuất hiện thì B không xuất hiện" (= noncoexistence).
- Định nghĩa tường minh cho 4 template:
  `Choice`, `Exclusive Choice` (pm4py không hỗ trợ);
  `Not Response(A,B)`, `Not Precedence(A,B)` = LTLf G(A -> ¬F B) "không A nào được theo sau bởi B".
  Không dùng 'nonsuccession' của pm4py vì nó lệch LTLf (TN4 phát hiện: coi B|A|B là thoả).

Engine được gọi với consider_vacuity=True: hồ sơ không kích hoạt → "Vacuously Satisfied" (= thoả).
Lỗi gắn nhãn khi consider_vacuity=False được đo riêng bằng `vacuity_mislabels`.
"""

import itertools
import os
import tempfile
import warnings
from typing import Any, Callable, Dict, List, Sequence, Tuple, Union

import pandas as pd

from src.symbolic.declare4py_verifier import Declare4Py

CASE, ACT, TIME = "case:concept:name", "concept:name", "time:timestamp"
MAX_EXAMPLES = 5
SATISFIED_STATES = frozenset({"Satisfied", "Vacuously Satisfied"})
_T0 = pd.Timestamp("2020-01-01", tz="UTC")

Explicit = Callable[[Sequence[str], str, str], bool]


def _choice(seq: Sequence[str], a: str, b: str) -> bool:
    return a in seq or b in seq


def _exclusive_choice(seq: Sequence[str], a: str, b: str) -> bool:
    return (a in seq) != (b in seq)


def _not_succession(seq: Sequence[str], a: str, b: str) -> bool:
    """LTLf G(a -> ¬F b): không có a nào được theo sau (về sau) bởi b."""
    return not any(x == a and b in seq[i + 1:] for i, x in enumerate(seq))


# template engine -> ("pm4py", khoá pm4py, số activity) | ("explicit", hàm, 2)
REFERENCE: Dict[str, Tuple[str, Union[str, Explicit], int]] = {
    "Existence": ("pm4py", "existence", 1),
    "Absence": ("pm4py", "absence", 1),
    "Init": ("pm4py", "init", 1),
    "Exactly1": ("pm4py", "exactly_one", 1),
    "Responded Existence": ("pm4py", "responded_existence", 2),
    "Response": ("pm4py", "response", 2),
    "Precedence": ("pm4py", "precedence", 2),
    "Alternate Response": ("pm4py", "altresponse", 2),
    "Alternate Precedence": ("pm4py", "altprecedence", 2),
    "Chain Response": ("pm4py", "chainresponse", 2),
    "Chain Precedence": ("pm4py", "chainprecedence", 2),
    "Not Co-Existence": ("pm4py", "noncoexistence", 2),
    "Not Responded Existence": ("pm4py", "noncoexistence", 2),
    # pm4py 2.7 'nonsuccession' chỉ báo vi phạm khi MỌI b đứng sau MỌI a (VD coi B|A|B là thoả) —
    # lệch LTLf, nên dùng định nghĩa tường minh (xem TN4).
    "Not Response": ("explicit", _not_succession, 2),
    "Not Precedence": ("explicit", _not_succession, 2),
    "Choice": ("explicit", _choice, 2),
    "Exclusive Choice": ("explicit", _exclusive_choice, 2),
}


# ------------------------------------------------------------------------------- logs


def log_from_sequences(sequences: Sequence[Sequence[str]]) -> pd.DataFrame:
    """Mỗi chuỗi activity thành một hồ sơ; mã hồ sơ = các activity nối bằng '|'; mỗi event cách nhau 1 giờ."""
    rows = [
        {CASE: "|".join(seq), ACT: act, TIME: _T0 + pd.Timedelta(hours=i)}
        for seq in sequences for i, act in enumerate(seq)
    ]
    return pd.DataFrame(rows, columns=[CASE, ACT, TIME])


def exhaustive_log(alphabet: Sequence[str], max_len: int) -> pd.DataFrame:
    """Mọi chuỗi độ dài 1..max_len trên bảng chữ cho trước (kiểm thử vét cạn phạm vi nhỏ)."""
    sequences = [p for n in range(1, max_len + 1) for p in itertools.product(alphabet, repeat=n)]
    return log_from_sequences(sequences)


def _sequences(df: pd.DataFrame) -> Dict[str, List[str]]:
    ordered = df.sort_values([CASE, TIME], kind="mergesort")
    return {str(c): g[ACT].tolist() for c, g in ordered.groupby(CASE, sort=False)}


# ------------------------------------------------------------------------- verdicts


def _engine_results(df: pd.DataFrame, template: str, acts: Sequence[str], vacuity: bool) -> Dict[str, Any]:
    engine = Declare4Py(df)
    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as f:
        f.write(f"{template}[{', '.join(acts)}] | | |\n")
        path = f.name
    try:
        engine.parse_decl_model(path)
        results = engine.conformance_checking(consider_vacuity=vacuity)
    finally:
        os.unlink(path)
    return {case_id: next(iter(res.values())) for (_, case_id), res in results.items()}


def engine_verdicts(df: pd.DataFrame, template: str, acts: Sequence[str]) -> Dict[str, bool]:
    """Kết luận của engine NSAI (True = thoả), chế độ consider_vacuity=True."""
    return {c: r.state in SATISFIED_STATES for c, r in _engine_results(df, template, acts, True).items()}


def reference_verdicts(df: pd.DataFrame, template: str, acts: Sequence[str]) -> Dict[str, bool]:
    """Kết luận theo chuẩn (True = thoả)."""
    kind, ref, arity = REFERENCE[template]
    if kind == "explicit":
        return {c: ref(seq, acts[0], acts[1]) for c, seq in _sequences(df).items()}
    import pm4py

    target = tuple(acts[:arity]) if arity == 2 else acts[0]
    model = {ref: {target: {"support": 1.0, "confidence": 1.0}}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        diag = pm4py.conformance_declare(
            df, model, activity_key=ACT, timestamp_key=TIME, case_id_key=CASE,
            return_diagnostics_dataframe=True,
        )
    return {str(c): int(n) == 0 for c, n in zip(diag["case_id"], diag["no_dev_total"], strict=True)}


def compare_template(df: pd.DataFrame, template: str, acts: Sequence[str]) -> Dict[str, Any]:
    """So kết luận từng hồ sơ giữa engine và chuẩn; kèm tối đa MAX_EXAMPLES ví dụ lệch."""
    mine, ref = engine_verdicts(df, template, acts), reference_verdicts(df, template, acts)
    differing = [c for c in ref if mine.get(c) != ref[c]]
    return {
        "template": template,
        "activities": list(acts),
        "n_traces": len(ref),
        "n_agree": len(ref) - len(differing),
        "n_disagree": len(differing),
        "examples": [
            {"trace": c, "engine": "thoả" if mine.get(c) else "vi phạm", "reference": "thoả" if ref[c] else "vi phạm"}
            for c in differing[:MAX_EXAMPLES]
        ],
    }


def vacuity_mislabels(df: pd.DataFrame, template: str, acts: Sequence[str]) -> int:
    """Số hồ sơ không kích hoạt nhưng bị gắn 'Violated' khi gọi engine với consider_vacuity=False (mặc định)."""
    results = _engine_results(df, template, acts, False)
    return sum(1 for r in results.values() if r.num_activations == 0 and r.state == "Violated")
