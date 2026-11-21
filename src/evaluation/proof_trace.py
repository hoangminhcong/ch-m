"""
Proof trace — truy vết từng ràng buộc hệ thống đưa ra về nguồn (học từ "proof roadmap", Dang et al., ISDS 2026):

  khoản luật (nguyên văn từ KG) → ngữ cảnh đồ thị đã dùng / bị bỏ → phân tích nghĩa vụ của LLM (dẫn chứng có
  thật trong văn bản không?) → từng vòng: trạng thái kiểm Tầng 1/2/3, B, D → dòng .decl cuối → bằng chứng trên log
  (số hồ sơ kích hoạt, vi phạm hàng loạt) → phát hiện của kiểm tập ràng buộc.

Chỉ đọc đầu ra của hệ thống + đồ thị; KHÔNG đọc gold (đây là giải thích của hệ thống, không phải chấm điểm).
"""

import html
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..mde.constraint_ast import DeclareConstraintAST
from ..neural.graph_context import LegalGraphIndex

RULE = "RULE"
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")
MIN_FRAGMENT = 12  # đoạn dẫn chứng ngắn hơn (VD 'and') không đủ để kết luận có / không


_DASHES = re.compile("[‐‑‒–—−­]")  # gạch nối không ngắt / en / em / mềm → '-'


def _norm(text: str) -> str:
    text = _DASHES.sub("-", text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'"))
    return re.sub(r"\s+", " ", text).strip().lower()


NEAR_VERBATIM = 0.8  # tỉ lệ trigram từ của đoạn dẫn chứng có trong văn bản — rút gọn / đổi vài từ vẫn ≥ ngưỡng


def _trigrams(text: str) -> List[tuple]:
    words = re.findall(r"[\w%€]+", text)
    return [tuple(words[i:i + 3]) for i in range(len(words) - 2)]


def evidence_check(evidence: Optional[str], sources: Sequence[str]) -> Dict[str, Any]:
    """Dẫn chứng LLM trích (có thể nối bằng '...') có trong khoản luật / ngữ cảnh không. Ba mức:
      verbatim  mọi đoạn (≥ MIN_FRAGMENT ký tự) có NGUYÊN VĂN
      near      không nguyên văn, nhưng mỗi đoạn có ≥ NEAR_VERBATIM trigram từ trong văn bản (LLM rút gọn câu)
      unsupported  có đoạn dưới ngưỡng — dẫn chứng có thể bị bịa / diễn giải xa văn bản
    coverage = tỉ lệ trigram thấp nhất trong các đoạn."""
    fragments = [f for f in (_norm(x) for x in _ELLIPSIS.split(evidence or "")) if len(f) >= MIN_FRAGMENT]
    haystack = _norm(" ".join(sources))
    source_grams = set(_trigrams(haystack))
    missing = [f for f in fragments if f not in haystack]

    def coverage(f: str) -> float:
        grams = _trigrams(f)
        return sum(g in source_grams for g in grams) / len(grams) if grams else 1.0

    cov = min((coverage(f) for f in fragments), default=0.0)
    level = ("none" if not fragments else "verbatim" if not missing
             else "near" if cov >= NEAR_VERBATIM else "unsupported")
    return {"fragments": len(fragments), "found": len(fragments) - len(missing), "missing": missing,
            "verbatim": level == "verbatim", "level": level, "coverage": round(cov, 3)}


def prompt_extras(nid: str, pred: Mapping[str, Any], graph: Mapping[str, Any]) -> List[str]:
    """Phần ngữ cảnh NGOÀI khoản + khoản dẫn chiếu mà prompt thật sự chứa (cấu hình Z: định nghĩa thuật ngữ, ghi chú
    phạm vi quốc gia — graph_context_chunk_v2). Rà soát 2026-11-20 (lỗi 6): trước đây dẫn chứng trích từ định nghĩa
    bị coi là 'unsupported' (S4 oan). Dựng lại đúng văn bản đã đưa LLM (cùng hàm, cùng đồ thị v2)."""
    from ..kg.legal_enrichment import definitions_context  # nhập tại chỗ: tránh vòng evaluation ↔ kg

    out = []
    if pred.get("definitions"):
        out.append(definitions_context(nid, graph))
    if pred.get("scope_note"):
        out.append((graph.get("scope_notes") or {}).get(nid, ""))
    return [x for x in out if x]


def trace_record(nid: str, pred: Mapping[str, Any], index: LegalGraphIndex,
                 set_findings: Sequence[Mapping[str, Any]] = (), extras: Sequence[str] = ()) -> Dict[str, Any]:
    """Một proof trace (dạng dữ liệu) cho khoản nid. extras = phần ngữ cảnh khác trong prompt (prompt_extras)."""
    clause_text = index.text_of(nid) if nid in index.nodes else ""
    refs = [{"target": r, "text": index.text_of(r) if r in index.nodes else ""} for r in pred.get("context_refs", [])]
    analysis = pred.get("obligation_analysis") or {}
    ast = pred.get("ast")
    decl = DeclareConstraintAST.model_validate(dict(ast)).to_declare4py_line().strip() if ast else None
    mass = (pred.get("process_checks") or {}).get("mass_violation") or {}
    return {
        "clause": nid, "outcome": pred.get("outcome"), "clause_text": clause_text,
        "years": (index.nodes.get(nid, {}).get("props") or {}).get("years"),
        "context_refs": refs, "skipped_refs": list(pred.get("skipped_refs", [])),
        "definitions": list(pred.get("definitions", [])),
        "obligation": analysis,
        "evidence": evidence_check(analysis.get("evidence"), [clause_text] + [r["text"] for r in refs] + list(extras)),
        "prompt_extras": len(extras),
        "rounds": [{"round": t.get("round"), "status": t.get("status"), "error": t.get("error")}
                   for t in pred.get("trajectory", [])],
        "decl": decl, "roundtrip": pred.get("roundtrip_msg"),
        "grounding": pred.get("grounding") or {},
        "mass_violation": {k: mass.get(k) for k in ("activated", "violated", "ratio", "mass_violation", "examples")
                           if k in mass},
        "set_findings": [dict(f) for f in set_findings if nid in (f.get("a"), f.get("b"))],
    }


def build_traces(predictions_doc: Mapping[str, Any], graph: Mapping[str, Any],
                 set_findings: Sequence[Mapping[str, Any]] = ()) -> List[Dict[str, Any]]:
    index = LegalGraphIndex(graph)
    return [trace_record(nid, p, index, set_findings, prompt_extras(nid, p, graph))
            for nid, p in sorted(predictions_doc.get("predictions", {}).items()) if p.get("outcome") == RULE]


def summarize(traces: Sequence[Mapping[str, Any]], set_findings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    kinds: Dict[str, int] = {}
    for f in set_findings:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    checked = [t for t in traces if t["evidence"]["fragments"]]
    level = lambda name: sum(t["evidence"]["level"] == name for t in checked)  # noqa: E731
    return {"rules": len(traces), "evidence_checked": len(checked), "evidence_verbatim": level("verbatim"),
            "evidence_near": level("near"), "evidence_unsupported": level("unsupported"), "set_kinds": kinds}


# -------------------------------------------------------------------------------------- HTML

_CSS = """body{font:14px/1.5 system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#1f2328}
h1{font-size:1.4em}h2{font-size:1.05em;margin:0}h3{font-size:.95em;margin:.8em 0 .2em}section{border:1px solid #d0d7de;
border-radius:6px;padding:1em;margin:1em 0}pre,code{font:12px ui-monospace,monospace;background:#f6f8fa;padding:2px 4px;
border-radius:4px}pre{padding:.6em;white-space:pre-wrap}.muted{color:#59636e}.ok{color:#1a7f37}.bad{color:#cf222e}
.warn{color:#9a6700}table{border-collapse:collapse}td,th{border:1px solid #d0d7de;padding:2px 8px;text-align:left}"""


def _e(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _evidence_html(ev: Mapping[str, Any]) -> str:
    if not ev["fragments"]:
        return "<p class='muted'>không có dẫn chứng đủ dài để kiểm</p>"
    if ev["level"] == "verbatim":
        return f"<p class='ok'>dẫn chứng có nguyên văn trong khoản / ngữ cảnh ({ev['found']}/{ev['fragments']} đoạn)</p>"
    cls, label = (("warn", "gần nguyên văn (LLM rút gọn)") if ev["level"] == "near"
                  else ("bad", "KHÔNG có căn cứ trong văn bản"))
    return (f"<p class='{cls}'>dẫn chứng {label} — {ev['found']}/{ev['fragments']} đoạn nguyên văn, độ phủ trigram "
            f"thấp nhất {ev['coverage']:.0%}; đoạn không nguyên văn:</p>"
            + "".join(f"<pre>{_e(m)}</pre>" for m in ev["missing"]))


def _log_html(g: Mapping[str, Any], m: Mapping[str, Any]) -> str:
    out = ""
    if g:
        out += (f"<p>Hồ sơ có sự kiện kích hoạt: {_e(g.get('witness_cases'))} / {_e(g.get('num_cases'))}"
                + (" — <span class='warn'>RỖNG</span>" if g.get("vacuous") else "") + "</p>")
    if m:
        out += (f"<p>Vi phạm: {_e(m.get('violated'))} / {_e(m.get('activated'))} hồ sơ kích hoạt ({_e(m.get('ratio'))})"
                + (" — <span class='bad'>vi phạm hàng loạt</span>" if m.get("mass_violation") else "")
                + f"; VD hồ sơ: {_e(', '.join(map(str, (m.get('examples') or [])[:5])))}</p>")
    return out or "<p class='muted'>không có</p>"


def _section(t: Mapping[str, Any]) -> str:
    refs = "".join(f"<details><summary><code>{_e(r['target'])}</code></summary><pre>{_e(r['text'][:3000])}</pre>"
                   "</details>" for r in t["context_refs"]) or "<p class='muted'>không dùng khoản dẫn chiếu</p>"
    if t["skipped_refs"]:
        refs += f"<p class='muted'>bỏ (ngoài phạm vi / không có văn bản): {_e(', '.join(t['skipped_refs']))}</p>"
    if t["definitions"]:
        refs += f"<p>Định nghĩa đưa vào: {_e(', '.join(t['definitions']))}</p>"
    rounds = "".join(f"<tr><td>{_e(r['round'])}</td><td>{_e(r['status'])}</td><td>{_e((r['error'] or '')[:300])}"
                     "</td></tr>" for r in t["rounds"])
    sets = "".join(f"<p class='{'bad' if 'CONFLICT' in f['kind'] else 'muted'}'>{_e(f['kind'])}: <code>{_e(f['a'])}"
                   f"</code> ↔ <code>{_e(f['b'])}</code> — {_e(f['note'])}</p>"
                   for f in t["set_findings"]) or "<p class='muted'>không có</p>"
    ob = t["obligation"]
    years = f"<p class='muted'>năm hiệu lực: {_e(t['years'])}</p>" if t["years"] else ""
    return (f"<section id='{_e(t['clause'])}'><h2>{_e(t['clause'])} → <code>{_e(t['decl'])}</code></h2>"
            f"<h3>1. Khoản luật (từ KG)</h3><pre>{_e(t['clause_text'])}</pre>{years}"
            f"<h3>2. Ngữ cảnh đồ thị</h3>{refs}"
            f"<h3>3. Phân tích nghĩa vụ (LLM, kiểm D)</h3><p>Chủ thể: <code>{_e(ob.get('duty_bearer'))}</code> · "
            f"quan sát được trên log: <code>{_e(ob.get('observable_in_log'))}</code></p>"
            f"<pre>{_e(ob.get('evidence'))}</pre>{_evidence_html(t['evidence'])}"
            f"<h3>4. Các vòng sinh – kiểm</h3><table><tr><th>vòng</th><th>trạng thái</th><th>phản hồi</th></tr>{rounds}"
            f"</table><p class='muted'>{_e(t['roundtrip'])}</p>"
            f"<h3>5. Bằng chứng trên log</h3>{_log_html(t['grounding'], t['mass_violation'])}"
            f"<h3>6. Kiểm tập ràng buộc</h3>{sets}</section>")


def render_html(traces: Sequence[Mapping[str, Any]], title: str, summary: Mapping[str, Any]) -> str:
    toc = "".join(f"<li><a href='#{_e(t['clause'])}'>{_e(t['clause'])}</a> <code>{_e(t['decl'])}</code></li>"
                  for t in traces)
    head = (f"<p>{summary['rules']} ràng buộc · dẫn chứng của LLM ({summary['evidence_checked']} có thể kiểm): "
            f"nguyên văn {summary['evidence_verbatim']}, gần nguyên văn {summary['evidence_near']}, "
            f"không có căn cứ {summary['evidence_unsupported']} · kiểm tập ràng buộc: "
            f"{_e(summary['set_kinds'] or 'không phát hiện')}</p>"
            "<p class='muted'>Giải thích của hệ thống (không đọc gold). Nguyên văn khoản và khoản dẫn chiếu lấy từ đồ "
            "thị luật; kiểm tập ràng buộc là kiểm có giới hạn (vết ≤ 5 sự kiện).</p>")
    return (f"<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'><title>{_e(title)}</title>"
            f"<style>{_CSS}</style></head><body><h1>{_e(title)}</h1>{head}<ol>{toc}</ol>"
            + "".join(_section(t) for t in traces) + "</body></html>")
