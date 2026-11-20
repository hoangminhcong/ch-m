"""
Kiểm B — kiểm rỗng trên log (log-grounded vacuity) TRONG vòng lặp sinh (real_llm_client.py).

Ràng buộc mà sự kiện kích hoạt (thoả điều kiện dữ liệu) không xuất hiện ở hồ sơ nào thì không nói gì về log:
Response/Precedence thoả rỗng ở mọi hồ sơ, Existence vi phạm ở mọi hồ sơ. VD R1306:Art70(2) sinh
'Precedence[…] | A.case:year == 2018' trong khi log chỉ có 2015–2017.

Chỉ là PHẢN HỒI, không loại: một ràng buộc đúng vẫn có thể rỗng (luật nói về sự việc chưa xảy ra trong log).
Vòng lặp báo một lần cho mỗi ràng buộc; LLM giữ nguyên → chấp nhận, gắn cờ `vacuous` trong kết quả.
Không dùng gold: chỉ log + ràng buộc ứng viên. Lời phản hồi không gợi ý giá trị thay thế.
"""

from typing import Any, Dict, Mapping, Optional, Sequence

from ..mde.constraint_ast import DeclareConstraintAST


class LogGroundingChecker:
    """Đếm số hồ sơ có sự kiện kích hoạt thoả điều kiện, trên một engine Declare4Py đã nạp log."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._cache: Dict[str, int] = {}

    @property
    def num_cases(self) -> int:
        return self.engine.num_cases

    def cases_in(self, years: Optional[Sequence[int]] = None) -> int:
        """Số hồ sơ của các năm (tập Đức); None = mọi hồ sơ."""
        return self.num_cases if years is None else self.engine.cases_in(years)

    def witness_cases(self, ast: Mapping[str, Any], years: Optional[Sequence[int]] = None) -> int:
        line = DeclareConstraintAST.model_validate(dict(ast)).to_declare4py_line().strip()
        key = line if years is None else f"{line}@{sorted(years)}"
        if key not in self._cache:
            parsed = self.engine.parse_decl_lines([line])
            if not parsed:
                raise ValueError(f"Engine không phân tích được dòng .decl: {line}")
            self._cache[key] = (self.engine.count_witness_cases(parsed[0]) if years is None
                                else self.engine.count_witness_cases(parsed[0], years=years))
        return self._cache[key]


def describe_activation(ast: Mapping[str, Any]) -> str:
    """Phía kích hoạt + điều kiện, viết cho LLM (tiếng Anh, như các phản hồi khác của vòng lặp)."""
    precedence = str(ast.get("template_name", "")).endswith("Precedence")
    act = ast.get("target_activity") if precedence and ast.get("target_activity") else ast.get("activation_activity")
    conds = []
    if ast.get("activation_attr"):
        conds.append(f"{ast['activation_attr']} {ast.get('activation_op')} {ast.get('activation_val')!r}")
    conds += [f"{c['attr']} {c['op']} {c['val']!r}" for c in ast.get("extra_conditions") or []]
    return f"'{act}'" + (f" with {' and '.join(conds)}" if conds else "")


def vacuity_feedback(ast: Mapping[str, Any], num_cases: int, allow_no_constraint: bool) -> str:
    unary_existence = ast.get("template_name") in ("Existence", "Exactly1", "Init")
    effect = ("it would be violated by every case" if unary_existence
              else "it can never be activated and is vacuously satisfied by every case")
    escape = ("If the clause imposes no obligation that is observable in the processing of individual cases, "
              "return no_constraint with your obligation_analysis instead."
              if allow_no_constraint else "Return the constraint that the clause actually supports.")
    return (
        f"[Log-grounded Vacuity]: In the event log ({num_cases} cases) no case contains the activation event "
        f"{describe_activation(ast)}, so {effect}. Re-read the clause. Do not introduce activities, values or "
        f"dates that the clause does not state. {escape}"
    )


def grounding_record(witness: Optional[int], num_cases: Optional[int]) -> Dict[str, Any]:
    return {"witness_cases": witness, "num_cases": num_cases, "vacuous": witness == 0 if witness is not None else None}
