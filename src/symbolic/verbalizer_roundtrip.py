"""
Bước 3.1: Kiểm chứng Ràng buộc Không cần Đáp án chuẩn (Deterministic Verbalization, Generic Entity Matcher & Roundtrip Check)
Tham khảo:
- Bài OCL2026 (OVAS): Mục 3.4.6 & Mục 5.3 (Reference-free verification scenarios)
- Bài IJCAI 2025 (Declarative PM) & Roundtrip Check (arXiv:2604.25031):
  1. Dịch ngược tất định AST DECLARE sang câu ngôn ngữ tự nhiên chuẩn hóa (verbalization).
  2. Thuật toán Đối chiếu thực thể định lượng tổng quát (Generic Entity Matcher): Dùng Regex quét toàn bộ các con số
     và đơn vị trong điều khoản luật gốc; nếu AI chọn con số không xuất hiện trong văn bản luật, trả về phản hồi
     theo phong cách Trình biên dịch (Compiler Diagnostic) mà không mớm đáp án.
  3. Trọng tài LLM độc lập (Independent Roundtrip Judge): Đối chiếu câu dịch ngược với văn bản luật thô.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .domain_profiles import BPIC2017_PROFILE, DomainProfile, build_judge_prompt

TIME_UNIT_NAMES = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "calendar days",
    "w": "weeks",
    "mo": "calendar months",
    "wd": "working days",
}
JUDGE_VERDICTS = ("EQUIVALENT", "REVERSED_ORDER", "THRESHOLD_MISMATCH", "BASELESS")


class JudgeOutputError(RuntimeError):
    """Giám khảo (LLM) trả phản hồi không có verdict hợp lệ — lỗi của bước kiểm, không phải ràng buộc đạt/không đạt."""

# Các từ chỉ số lượng phổ biến trong văn bản pháp lý tiếng Anh của EU Directive
WORD_NUMBER_MAP: List[Tuple[str, float, str]] = [
    (r"\bone\s+month\b", 30.0, "days"),
    (r"\bone\s+year\b", 12.0, "months"),
    (r"\btwelve\s+months\b", 12.0, "months"),
    (r"\bfourteen\s+calendar\s+days\b", 14.0, "days"),
    (r"\bfourteen\s+days\b", 14.0, "days"),
]


_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_NUM_WORD = rf"(?:(?:{'|'.join(_TENS)})(?:[-\s](?:{'|'.join(list(_ONES)[:9])}))?|{'|'.join(_ONES)})"
# v1.2 (rà soát lõi C1): 'calendar' / 'working' trước mọi đơn vị thời gian ('three calendar months')
_WORD_NUM_UNIT = re.compile(
    rf"\b({_NUM_WORD})\s+((?:calendar\s+|working\s+)?(?:days?|weeks?|months?|years?))\b", re.IGNORECASE)


# Tập Đức (v2): số viết bằng chữ + đơn vị tiếng Đức ('drei Tage', '14 aufeinanderfolgende Tage', 'einem Monat').
# Danh từ tiếng Đức viết hoa → so khớp đơn vị phân biệt hoa thường (không đụng văn bản tiếng Anh).
_DE_ONES = {"ein": 1, "eins": 1, "eine": 1, "einem": 1, "einen": 1, "einer": 1, "eines": 1, "zwei": 2, "drei": 3,
            "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
            "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18,
            "neunzehn": 19}
_DE_TENS = {"zwanzig": 20, "dreißig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60, "siebzig": 70,
            "achtzig": 80, "neunzig": 90}
_DE_UNIT_DIGITS = ("ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun")
_DE_WORD = (rf"(?i:(?:{'|'.join(_DE_UNIT_DIGITS)})und(?:{'|'.join(_DE_TENS)})|"
            rf"{'|'.join(sorted([*_DE_TENS, *_DE_ONES], key=len, reverse=True))})")
_DE_UNITS = (("Kalendertag", "days"), ("Arbeitstag", "days"), ("Tag", "days"), ("Woche", "weeks"),
             ("Monat", "months"), ("Jahr", "years"), ("Hektar", "ha"), ("Prozent", "%"), ("Euro", "EUR"),
             ("EUR", "EUR"), ("€", "EUR"))
# Tính từ xen giữa số và đơn vị ('14 aufeinanderfolgende Tage'), trừ mạo từ ('3 der Tage' không phải 3 ngày) — C1
_DE_NUM_UNIT = re.compile(
    # '1,000' (đúng 3 chữ số sau dấu phẩy) mơ hồ → để bước chung đọc là hàng nghìn kiểu Anh; '0,3' / '1,50' vẫn là
    # thập phân kiểu Đức
    rf"(?<![\w.,])(\d{{1,3}}(?:\.\d{{3}})+|\d+(?:,(?!\d{{3}}(?!\d))\d+)?|{_DE_WORD})"
    r"(?:\s+(?!(?:der|die|das|des|den|dem|ein|eine|einer|eines)\b)[a-zäöüß]+(?:e|en|er|es))?\s+"
    r"(Kalendertag(?:e|en)?|Arbeitstag(?:e|en)?|Tag(?:e|en|es)?|Woche(?:n)?|Monat(?:e|en|s)?|Jahr(?:e|en|es)?"
    r"|Hektar|Prozent|Euro|EUR|€)(?!\w)")


def _de_number(raw: str) -> Optional[float]:
    low = raw.lower()
    if low in _DE_ONES:
        return float(_DE_ONES[low])
    if low in _DE_TENS:
        return float(_DE_TENS[low])
    m = re.fullmatch(rf"({'|'.join(_DE_UNIT_DIGITS)})und({'|'.join(_DE_TENS)})", low)
    if m:
        return float(_DE_ONES[m.group(1)] + _DE_TENS[m.group(2)])
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        return float(raw.replace(".", ""))
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _word_to_number(text: str) -> Optional[float]:
    parts = re.split(r"[-\s]+", text.lower())
    total = 0
    for p in parts:
        if p in _TENS:
            total += _TENS[p]
        elif p in _ONES:
            total += _ONES[p]
        else:
            return None
    return float(total)


def extract_clause_numeric_entities(clause_text: str) -> List[Tuple[float, str]]:
    """
    Bước 1 của Generic Entity Matcher:
    Dùng Regex quét toàn bộ các con số và đơn vị định lượng trong văn bản điều khoản luật
    (ví dụ: [(14.0, 'days'), (200.0, 'EUR'), (75000.0, 'EUR'), (1.0, '%')]).
    Không gõ cứng theo bất kỳ mã điều khoản (article_id) nào.
    """
    if not clause_text:
        return []

    found: List[Tuple[float, str]] = []
    seen: set = set()

    # 1. Quét dạng "EUR 200", "EUR 75 000", "EUR 10,000", "EUR 1 500"
    eur_prefix_pattern = re.compile(
        r"\b(EUR|euro|euros)\s*(\d{1,3}(?:[\s,]\d{3})+|\d+(?:[.,]\d+)?)\b",
        re.IGNORECASE,
    )
    for match in eur_prefix_pattern.finditer(clause_text):
        raw_num = match.group(2).replace(" ", "").replace(",", ".")
        # Nếu có nhiều dấu chấm do phân tách hàng nghìn (vd 75.000), xử lý chuẩn
        if raw_num.count(".") == 1 and len(raw_num.split(".")[1]) == 3:
            raw_num = raw_num.replace(".", "")
        try:
            val = float(raw_num)
            key = (val, "EUR")
            if key not in seen:
                seen.add(key)
                found.append(key)
        except ValueError:
            pass

    # 2. Quét dạng "<số> <đơn vị>" như "14 calendar days", "30 calendar days", "1 %", "0,5 %", "12 months"
    num_unit_pattern = re.compile(
        # v1.2 (rà soát lõi C1): '1,000' hàng nghìn kiểu Anh; ')' sau số ('ten (10) days'); '-' ('30-day');
        # số ít + 'calendar' / 'working' cho mọi đơn vị thời gian; 'per cent' / 'percent'.
        r"\b(\d{1,3}(?:[  ]\d{3})+|\d{1,3}(?:,\d{3})+|\d+(?:[.,]\d+)?)\)?\s*-?\s*"
        # (?!\w) thay cho \b: '\b' sau '%' không bao giờ khớp ('%' và khoảng trắng đều không phải ký tự chữ) nên
        # '5 %' từng bị bỏ sót (sửa 2026-11-18, v1.1 — docs/V2_DANG_KY_TRUOC.md). Với đơn vị là chữ: như '\b'.
        r"((?:calendar\s+|working\s+)?(?:days?|weeks?|months?|years?)|hectares?|ha|EUR|euro|euros|%"
        r"|per\s*cent|percent)(?!\w)",
        re.IGNORECASE,
    )
    _cite = re.compile(r"(?:Articles?|points?|paragraphs?|No\.?)\s*$", re.IGNORECASE)
    # Đoạn số + đơn vị tiếng Đức ('1.250 Euro' = 1250) do bước 2c đọc; bước chung bỏ qua đúng các đoạn đó, nên văn bản
    # tiếng Anh đọc như v1 ('0.100 ha' = 0,1 — rà soát 2026-11-18, MEDIUM-1).
    de_spans = [m.span() for m in _DE_NUM_UNIT.finditer(clause_text)]
    for match in num_unit_pattern.finditer(clause_text):
        if any(match.start() < e and s < match.end() for s, e in de_spans):
            continue
        raw_num = match.group(1)
        if re.search(r"[  ]", raw_num) and _cite.search(clause_text[:match.start()]):
            raw_num = re.split(r"[  ]", raw_num)[-1]  # 'Article 12 150 hectares' = 150 ha, không phải 12 150
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw_num):
            raw_num = raw_num.replace(",", "")  # '1,000 EUR' = 1000 (trước đây 1,0)
        raw_num = re.sub(r"[  ]", "", raw_num).replace(",", ".")
        unit_raw = match.group(2).lower()
        if "cent" in unit_raw:
            unit = "%"
        elif "day" in unit_raw:
            unit = "days"
        elif "week" in unit_raw:
            unit = "weeks"
        elif "month" in unit_raw:
            unit = "months"
        elif "year" in unit_raw:
            unit = "years"
        elif "eur" in unit_raw:
            unit = "EUR"
        elif unit_raw.startswith("h"):
            unit = "ha"
        else:
            unit = unit_raw
        try:
            val = float(raw_num)
            key = (val, unit)
            if key not in seen:
                seen.add(key)
                found.append(key)
        except ValueError:
            pass

    # 2b. F-WORDS (kiểm toán 2026-11-09): số viết bằng chữ + đơn vị thời gian ("two working days", "six months",
    #     "eight weeks") — trước đây bị bỏ sót (62 chỗ trong 4 Quy định CAP). Giữ đúng đơn vị, không quy đổi.
    for match in _WORD_NUM_UNIT.finditer(clause_text):
        val = _word_to_number(match.group(1))
        unit_raw = match.group(2).lower()
        unit = next(u for k, u in (("day", "days"), ("week", "weeks"), ("month", "months"), ("year", "years"))
                    if k in unit_raw)
        key = (val, unit)
        if val is not None and key not in seen:
            seen.add(key)
            found.append(key)

    # 2c. Tập Đức (v2): '<số | số chữ> [tính từ] <đơn vị tiếng Đức>'
    for match in _DE_NUM_UNIT.finditer(clause_text):
        val = _de_number(match.group(1))
        unit = next(u for k, u in _DE_UNITS if match.group(2).startswith(k))
        key = (val, unit)
        if val is not None and key not in seen:
            seen.add(key)
            found.append(key)

    # 3. Quét các cụm từ chỉ số lượng chuẩn trong văn bản pháp lý ("one month" -> 30 days, "one year" -> 12 months)
    for pattern_str, mapped_val, mapped_unit in WORD_NUMBER_MAP:
        if re.search(pattern_str, clause_text, flags=re.IGNORECASE):
            key = (mapped_val, mapped_unit)
            if key not in seen:
                seen.add(key)
                found.append(key)

    return found


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
_MONTH_RE = "|".join(MONTHS)  # phân biệt hoa thường: tránh động từ 'may'
_DAY_MONTH = re.compile(rf"(?<![0-9])([0-9]{{1,2}})(?:st|nd|rd|th)?[ ]+({_MONTH_RE})(?![a-z])")
_MONTH_DAY = re.compile(rf"(?<![A-Za-z])({_MONTH_RE})[ ]+([0-9]{{1,2}})(?:st|nd|rd|th)?(?![0-9])")
_DATE_VAL = re.compile(r"^(year(?:[+-]\d+)?|\d{4})-(\d{2})-(\d{2})$")
DE_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
             "November", "Dezember"]
_DE_DAY_MONTH = re.compile(rf"(?<![0-9])([0-9]{{1,2}})\.\s*({'|'.join(DE_MONTHS)})(?![a-zäöü])")


def extract_clause_dates(clause_text: str) -> Set[Tuple[int, int]]:
    """Các mốc ngày lịch (tháng, ngày) trong điều khoản: '15 May', 'May 15', '1st December' (bộ CAP)."""
    found: Set[Tuple[int, int]] = set()
    for m in _DAY_MONTH.finditer(clause_text or ""):
        found.add((MONTHS.index(m.group(2)) + 1, int(m.group(1))))
    for m in _MONTH_DAY.finditer(clause_text or ""):
        found.add((MONTHS.index(m.group(1)) + 1, int(m.group(2))))
    for m in _DE_DAY_MONTH.finditer(clause_text or ""):  # tập Đức: '15. Mai'
        found.add((DE_MONTHS.index(m.group(2)) + 1, int(m.group(1))))
    return {(mo, d) for mo, d in found if 1 <= d <= 31}


def _format_dates(dates: Set[Tuple[int, int]]) -> str:
    return ", ".join(f"{d} {MONTHS[mo - 1]}" for mo, d in sorted(dates))


def _all_conditions(ast_dict: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
    """(nhãn, thuộc tính, giá trị) của điều kiện chính và mọi extra_conditions."""
    conds = [("activation_val", ast_dict.get("activation_attr"), ast_dict.get("activation_val"))]
    for i, c in enumerate(ast_dict.get("extra_conditions") or []):
        conds.append((f"extra_conditions[{i}].val", c.get("attr"), c.get("val")))
    return conds


def _verify_dates_and_extras(
    ast_dict: Dict[str, Any], clause_text: str, allowed_numbers: set, formatted_entities: str, has_entities: bool
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Mở rộng cho bộ CAP: giá trị 'date' và giá trị số trong extra_conditions phải có trong văn bản luật."""
    dates = extract_clause_dates(clause_text)
    for label, attr, val in _all_conditions(ast_dict):
        if attr == "date":
            m = _DATE_VAL.match(str(val))
            if not m:
                continue  # Tầng 1 đã chặn dạng ngày sai
            key = (int(m.group(2)), int(m.group(3)))
            fixed_year = None if m.group(1).startswith("year") else m.group(1)
            if not dates:
                return (False, "BASELESS",
                        f"[Diagnostic Mismatch]: Ngày {label}={val} bạn chọn không xuất hiện trong văn bản luật "
                        f"của điều khoản này (Không có mốc ngày lịch nào được quy định trong điều khoản này).")
            if key not in dates or (fixed_year and fixed_year not in clause_text):
                return (False, "THRESHOLD_MISMATCH",
                        f"[Diagnostic Mismatch]: Ngày {label}={val} bạn chọn không xuất hiện trong văn bản luật "
                        f"của điều khoản này. Các mốc ngày được luật đề cập gồm: {_format_dates(dates)}. "
                        f"Hãy đọc lại văn bản và tự hiệu chỉnh.")
        elif label != "activation_val" and isinstance(val, (int, float)) and not isinstance(val, bool)                 and float(val) != 0.0 and float(val) not in allowed_numbers:
            verdict = "THRESHOLD_MISMATCH" if has_entities else "BASELESS"
            return (False, verdict,
                    f"[Diagnostic Mismatch]: Con số {label}={val} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này. Các mốc định lượng được luật đề cập gồm: {formatted_entities}. "
                    f"Hãy đọc lại văn bản và tự hiệu chỉnh.")
    return True, None, None


_YEAR_VALUE = re.compile(r"^(?:19|20)\d{2}$")
_YEAR_IN_TEXT = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _verify_year_values(ast_dict: Dict[str, Any], clause_text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Kiểm E: giá trị điều kiện dạng NĂM (chuỗi '2017', VD case:year) phải có trong văn bản luật — cùng quy tắc
    với con số và ngày. Chặn trường hợp LLM 'sửa' ràng buộc rỗng bằng cách đổi sang một năm có trong log.
    """
    years = sorted(set(_YEAR_IN_TEXT.findall(clause_text)))
    for label, _attr, val in _all_conditions(ast_dict):
        if isinstance(val, str) and _YEAR_VALUE.match(val.strip()) and val.strip() not in years:
            verdict = "THRESHOLD_MISMATCH" if years else "BASELESS"
            stated = f"Các năm được luật đề cập gồm: {', '.join(years)}." if years else \
                "Không có năm nào được quy định trong điều khoản này."
            return (False, verdict,
                    f"[Diagnostic Mismatch]: Năm {label}={val} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này. {stated} Hãy đọc lại văn bản và tự hiệu chỉnh.")
    return True, None, None


# Đơn vị thời hạn của AST → tên đơn vị của Entity Matcher (giờ / phút / giây: luật CAP không dùng → không kiểm đơn vị)
_AST_TIME_UNITS = {"d": "days", "wd": "days", "w": "weeks", "mo": "months"}
_TIME_UNIT_NAMES = {"days", "weeks", "months", "years"}


def verify_generic_numeric_entities(
    ast_dict: Dict[str, Any],
    retrieved_chunk: Dict[str, Any],
    check_year_values: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Bước 2 & 3 của Generic Entity Matcher:
    So sánh con số mà AI nộp lên (`time_max` hoặc `activation_val`) với danh sách các mốc định lượng
    được trích xuất tự động bằng Regex từ văn bản điều khoản `retrieved_chunk['text']`.
    Nếu lệch hoặc không xuất hiện, trả về thông báo theo phong cách Trình biên dịch (Compiler Diagnostic)
    không mớm đáp án:
      (False, verdict, diagnostic_message)
    Nếu hợp lệ (hoặc không dùng ngưỡng số), trả về:
      (True, None, None)
    check_year_values=True (kiểm E, bộ CAP): thêm kiểm giá trị dạng năm; mặc định tắt (BPIC2017 giữ nguyên).
    """
    clause_text = str(retrieved_chunk.get("text", ""))
    if check_year_values:
        ok_year = _verify_year_values(ast_dict, clause_text)
        if not ok_year[0]:
            return ok_year
    entities = extract_clause_numeric_entities(clause_text)
    allowed_numbers = {val for val, _ in entities}
    formatted_entities = (
        ", ".join(f"[{int(v) if v.is_integer() else v}, '{u}']" for v, u in entities)
        if entities
        else "Không có mốc số học nào được quy định trong điều khoản này"
    )

    # 1. Kiểm tra time_max nếu AI đặt giới hạn thời gian
    t_max = ast_dict.get("time_max")
    if isinstance(t_max, (int, float)) and t_max > 0:
        if not entities:
            return (
                False,
                "BASELESS",
                (
                    f"[Diagnostic Mismatch]: Con số time_max={t_max} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này ({formatted_entities}). Đây là suy luận thiếu căn cứ định lượng từ văn bản gốc."
                ),
            )
        if float(t_max) not in allowed_numbers:
            return (
                False,
                "THRESHOLD_MISMATCH",
                (
                    f"[Diagnostic Mismatch]: Con số time_max={t_max} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này. Các mốc định lượng được luật đề cập gồm: {formatted_entities}. "
                    f"Hãy đọc lại văn bản và tự hiệu chỉnh."
                ),
            )

    # 1b. v1.2 (rà soát lõi C5, C6): con số của thời hạn phải đi với ĐƠN VỊ thời gian khớp trong luật ('14 days'
    #     không cho time_max=14 tháng; '5 %' không cho thời hạn 5 ngày), và time_min (> 0) cũng phải có căn cứ.
    unit_name = _AST_TIME_UNITS.get(ast_dict.get("time_unit") or "d")
    time_ents = {(v, u) for v, u in entities if u in _TIME_UNIT_NAMES}
    for label, value in (("time_max", t_max), ("time_min", ast_dict.get("time_min"))):
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0) or unit_name is None:
            continue
        if (float(value), unit_name) not in time_ents:
            return (
                False,
                "THRESHOLD_MISMATCH",
                (
                    f"[Diagnostic Mismatch]: {label}={value} {unit_name} không khớp thời hạn nào trong văn bản luật "
                    f"của điều khoản này (số và đơn vị). Các mốc định lượng được luật đề cập gồm: {formatted_entities}. "
                    f"Hãy đọc lại văn bản và tự hiệu chỉnh."
                ),
            )

    # 2. Kiểm tra activation_val nếu AI đặt ngưỡng số học (khác 0 — vì 0 thường dùng để kiểm tra tồn tại > 0)
    act_val = ast_dict.get("activation_val")
    if isinstance(act_val, (int, float)) and not isinstance(act_val, bool) and float(act_val) != 0.0:
        if not entities:
            return (
                False,
                "BASELESS",
                (
                    f"[Diagnostic Mismatch]: Con số activation_val={act_val} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này ({formatted_entities}). Văn bản gốc không quy định ngưỡng số học này."
                ),
            )
        if float(act_val) not in allowed_numbers:
            return (
                False,
                "THRESHOLD_MISMATCH",
                (
                    f"[Diagnostic Mismatch]: Con số activation_val={act_val} bạn chọn không xuất hiện trong văn bản luật "
                    f"của điều khoản này. Các mốc định lượng được luật đề cập gồm: {formatted_entities}. "
                    f"Hãy đọc lại văn bản và tự hiệu chỉnh."
                ),
            )

    # 3. Bộ CAP: điều kiện 'date' và extra_conditions (BPIC2017 không dùng — nhánh này không chạy)
    return _verify_dates_and_extras(ast_dict, clause_text, allowed_numbers, formatted_entities, bool(entities))


def verbalize_declare_ast(ast_dict: Dict[str, Any], case_noun: str = "credit case") -> str:
    """
    1. Hàm dịch ngược tất định (Deterministic Verbalizer) theo mẫu của Declare4Py & IJCAI 2025.
    Chuyển cây cú pháp DeclareConstraintAST thành câu tiếng Anh chuẩn hóa để kiểm tra Roundtrip.
    """
    tpl = ast_dict["template_name"]
    act_a = ast_dict["activation_activity"]
    act_b = ast_dict.get("target_activity")
    cond = (
        f" when {ast_dict['activation_attr']} {ast_dict['activation_op']} {ast_dict['activation_val']}"
        if ast_dict.get("activation_attr")
        else ""
    )
    for extra in ast_dict.get("extra_conditions") or []:  # điều kiện nối 'and' (bộ CAP)
        cond += f" and {extra['attr']} {extra['op']} {extra['val']}"
    unit_label = TIME_UNIT_NAMES.get(
        str(ast_dict.get("time_unit") or "d"),
        str(ast_dict.get("time_unit") or "d"),
    )
    lo = ast_dict.get("time_min")
    # v1.2 (rà soát lõi C6): time_min > 0 được engine áp dụng → phải hiện trong bản diễn đạt cho giám khảo
    time_str = (
        (f" between {lo} and {ast_dict['time_max']} {unit_label}" if lo else f" within {ast_dict['time_max']} {unit_label}")
        if ast_dict.get("time_max") is not None
        else ""
    )

    mapping = {
        "Existence": f"Activity '{act_a}'{cond} must occur at least once in the {case_noun}.",
        "Absence": f"Activity '{act_a}'{cond} must never occur in the {case_noun}.",
        "Init": f"Every {case_noun} must start with activity '{act_a}'{cond}.",
        "Exactly1": f"Activity '{act_a}'{cond} must occur exactly once in the {case_noun}.",
        "Choice": f"Either activity '{act_a}' or activity '{act_b}'{cond} must occur in the {case_noun}.",
        "Exclusive Choice": f"Either activity '{act_a}' or activity '{act_b}'{cond} must occur, but not both.",
        "Responded Existence": f"If activity '{act_a}'{cond} occurs in the {case_noun}, then '{act_b}' must also occur (before or after){time_str}.",
        # F-PREC (2026-11-09): họ Precedence — điều kiện thuộc sự kiện KÍCH HOẠT B (chuẩn Declare4Py)
        "Precedence": f"Whenever '{act_b}'{cond} occurs, '{act_a}' must have occurred BEFORE it{time_str}.",
        "Alternate Precedence": f"Each time '{act_b}'{cond} occurs, '{act_a}' must have occurred BEFORE it without another '{act_b}' in between{time_str}.",
        "Chain Precedence": f"Immediately before '{act_b}'{cond} occurs, '{act_a}' must occur{time_str}.",
        "Response": f"Whenever '{act_a}'{cond} occurs, '{act_b}' must eventually occur AFTER it{time_str}.",
        "Alternate Response": f"Each time '{act_a}'{cond} occurs, '{act_b}' must occur AFTER it before '{act_a}' recurs{time_str}.",
        "Chain Response": f"Immediately after '{act_a}'{cond} occurs, '{act_b}' must occur{time_str}.",
        "Not Responded Existence": f"If '{act_a}'{cond} occurs, '{act_b}' must never occur in the {case_noun}.",
        "Not Response": f"Whenever '{act_a}'{cond} occurs, '{act_b}' must NOT occur after it{time_str}.",
        "Not Precedence": f"Whenever '{act_b}'{cond} occurs, '{act_a}' must NOT have occurred before it{time_str}.",
        "Not Co-Existence": f"Activities '{act_a}'{cond} and '{act_b}' cannot both occur in the same {case_noun}.",
    }
    return mapping.get(tpl, f"{tpl}[{act_a}, {act_b}]{cond}{time_str}")


def check_roundtrip_fidelity(
    ast_dict: Dict[str, Any],
    retrieved_chunk: Dict[str, Any],
    llm_client: Any,
    profile: DomainProfile = BPIC2017_PROFILE,
    check_year_values: bool = False,
    judge_notes: str = "",
) -> Tuple[bool, str]:
    """
    2. Kiểm tra Roundtrip (Kết hợp Generic Entity Matcher + Trọng tài LLM độc lập đối chiếu với điều khoản gốc).
    Trọng tài chỉ thấy: văn bản luật + ràng buộc ứng viên. Không nhận mô tả gold của rule, và prompt
    không chứa ví dụ trích từ bộ đề (xem tests/test_no_gold_in_prompts.py).
    check_year_values: bật kiểm E (năm) trong Entity Matcher — bộ CAP; mặc định tắt.
    """
    verbalized_rule = verbalize_declare_ast(ast_dict, case_noun=profile.case_noun)

    # Bước A: Chạy Generic Entity Matcher (kiểm tra tính có căn cứ của các con số bằng Regex)
    ok_num, num_verdict, num_diag = verify_generic_numeric_entities(ast_dict, retrieved_chunk,
                                                                    check_year_values=check_year_values)
    if not ok_num and num_verdict and num_diag:
        return (
            False,
            f"[Layer 3 Semantic {num_verdict}]: {num_diag} (Back-translation: {verbalized_rule})",
        )

    # Ẩn extra_conditions rỗng: prompt BPIC2017 giữ nguyên như trước khi AST có trường này.
    shown_ast = {k: v for k, v in ast_dict.items() if not (k == "extra_conditions" and not v)}
    # judge_notes (v2) chỉ vào prompt giám khảo, KHÔNG vào văn bản mà Entity Matcher đối chiếu ở Bước A.
    prompt = build_judge_prompt(
        profile, retrieved_chunk, json.dumps(shown_ast, ensure_ascii=False), verbalized_rule, judge_notes
    )
    if hasattr(llm_client, "chat_json"):
        res = llm_client.chat_json(
            prompt,
            temperature=0.0,
            ast_dict=ast_dict,
            retrieved_chunk=retrieved_chunk,
        )
        if isinstance(res, str):
            res = json.loads(res)
    else:
        raw = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        res = json.loads(raw)

    # F-JUDGE (kiểm toán 2026-11-09): trước đây thiếu 'verdict' → mặc định EQUIVALENT (ràng buộc QUA Tầng 3).
    verdict = res.get("verdict") if isinstance(res, dict) else None
    if verdict not in JUDGE_VERDICTS:
        raise JudgeOutputError(f"Giám khảo trả phản hồi không hợp lệ (verdict={verdict!r}): {str(res)[:200]}")
    if verdict == "EQUIVALENT":
        return True, "Roundtrip check passed."

    return (
        False,
        f"[Layer 3 Semantic {verdict}]: {res.get('diagnostic_feedback', '')} "
        f"(Back-translation: {verbalized_rule})",
    )
