# Kiểm toán đường đi tạo số liệu CAP (BPIC2018 + 4 Quy định)

Ngày 2026-11-09. Phạm vi: mọi module **thực sự chạy** khi tạo số liệu TN5–TN8 cho CAP (vòng lặp sinh, Tầng 1–3,
các kiểm B/C/D/E, engine DECLARE, điều kiện dữ liệu, ngữ cảnh đồ thị, gold, chấm điểm, TN7, báo cáo).
Code BPIC2017 đang tắt không nằm trong phạm vi (chỉ ghi chú ở mục THẤP).

**Nguyên tắc:** đợt kiểm toán chỉ viết test và báo cáo; mỗi lỗi có một test `@unittest.expectedFailure` mang mã
phát hiện (đã xác nhận thất bại đúng vì lỗi mô tả). **Cùng ngày, theo duyệt của người dùng ("sửa tất cả"), mọi
phát hiện đã được sửa** — các test chuyển thành test hồi quy thường.

## 0. Trạng thái sau khi sửa (2026-11-09)

| Mã | Đã sửa thế nào | Kiểm chứng |
|---|---|---|
| F-CACHE | `chat_json` ném `LLMCallError`, **không ghi cache**; `run_cap_generation` ghi khoản đó là ERROR, chạy lại sẽ thử lại; `score_cap` **từ chối chấm** khi còn ERROR (trừ `--allow-errors`) | `test_audit_findings`, `test_cap_scripts` |
| F-JUDGE | Thiếu / sai `verdict` → `JudgeOutputError` (khoản ERROR), không bao giờ EQUIVALENT | `test_audit_findings` |
| F-PREC | Quy ước **(a) chuẩn Declare4Py**: điều kiện của Precedence / Alternate / Chain / **Not Precedence** chỉ trên **B** — engine, kiểm rỗng, câu dịch ngược, phiếu nhãn (`ngày(B)`), prompt CAP, hướng dẫn gán nhãn §3.3 | Kiểm thử chéo 2 000 hồ sơ thật: **0 chênh lệch** (trước 963) |
| F-WORDS | Entity Matcher nhận số viết bằng chữ (one…ninety, "twenty-one") + đơn vị tuần | `test_audit_findings`; chạy thật R809:Art72(3) "three months" → ràng buộc qua |
| F-UNITS | Đơn vị mới `w` (tuần), `mo` (tháng lịch, cộng tháng theo giờ Đức), `wd` (ngày làm việc T2–T6, **không trừ ngày lễ**) trong AST, engine (`src/symbolic/time_windows.py`), phiếu nhãn ("tháng", "tuần", "ngày làm việc"), chấm điểm (EQ cần cùng đơn vị lịch), prompt CAP, hướng dẫn §3.4 | Kiểm thử chéo w / mo / wd so với tham chiếu pandas (DateOffset, bdate_range) trên dữ liệu thật: 0 chênh lệch |
| F-KEY | Chỉ nhận biến key đã biết (GROQ/OPENAI/GEMINI/API_KEY) hoặc dòng trơn `gsk_…`/`sk-…` | `test_audit_findings` |
| Lint / code chết | 0 cảnh báo ruff (F, E9, B, PLE); bỏ biến `R05…R19` không dùng; `zip(strict=True)` | `ruff check` |

**Ảnh hưởng tới số liệu BPIC2017 cũ** (khi mở lại bộ đó và chạy lại; cache/kết quả cũ không tự đổi):
- F-PREC: R17 không đổi; R18 đổi phán quyết ở **1 / 31 509** hồ sơ (vi phạm 1 → 0). Không có rule Not Precedence.
- F-WORDS: Entity Matcher nhận thêm 9 chỗ trong Directive ("one month", "three months", "one year"…) → dễ chấp
  nhận hơn một chút ở Điều 2(2), 2(3), 6(5), 13(1), 16(2). Ánh xạ cũ "one month" → 30 ngày được GIỮ.
- F-CACHE / F-JUDGE: script BPIC2017 cũ (`run_real_llm_experiment.py`) sẽ dừng với lỗi khi API lỗi, thay vì âm
  thầm tính sai.
- Prompt BPIC2017 vẫn giống từng byte (test snapshot đạt); BPIC2017 bật: 337 test đạt.

## 1. Đã làm gì

| Bước | Cách làm | Test |
|---|---|---|
| 1. Kiểm thử chéo engine | Bộ kiểm DECLARE tham chiếu viết lại từ đầu theo ngữ nghĩa Declare4Py, không dùng code engine; so trạng thái từng hồ sơ trên **2 000 hồ sơ BPIC2018 thật** (seed 7): 17 mẫu × 9 loại điều kiện (chuỗi, Boolean, số, ngày lịch theo năm hồ sơ, khoảng ngày sang năm sau, thuộc tính event, kết hợp `and`) + cửa sổ thời gian | `tests/test_engine_differential_bpic2018.py` |
| 2. Test tính chất | Với **mọi** thuộc tính hồ sơ của Γ, **mọi** giá trị trong miền, các ngưỡng số, mọi phép so sánh: giá trị → AST → dòng .decl → engine → đánh giá trên bản ghi hồ sơ THẬT phải bằng phép so sánh Python có kiểu; đường phiếu nhãn và đường LLM phải ra cùng dòng .decl | `tests/test_condition_properties_bpic2018.py` |
| 3. Quét giả định cứng | Tìm tên/ý BPIC2017 viết cứng trên đường đi CAP; đo Entity Matcher trên toàn văn 4 Quy định | `tests/test_audit_findings.py` |
| 4. Nâng độ phủ | `RealLLMClient` (client OpenAI giả, không mạng, không đọc .env thật), script chấm điểm / TN7 / báo cáo / sinh | `tests/test_audit_findings.py`, `tests/test_cap_scripts.py` |

**Kiểm tra độ nhạy của test bước 2:** thay tạm (trong bộ nhớ) hàm so sánh bằng bản cũ có lỗi năm → test báo lỗi
ngay ở `case:year` **và** `case:program-id` (lỗi cũ ảnh hưởng cả thuộc tính này).
**Kiểm tra từng expectedFailure:** chạy thẳng thân test, xác nhận nó thất bại đúng vì lỗi đã mô tả (không phải vì
test viết sai).

## 2. Những gì ĐÚNG (đã kiểm chứng)

- Engine **khớp hoàn toàn** bộ kiểm tham chiếu trên 2 000 hồ sơ thật: mọi mẫu unary, họ Response, Not, Choice,
  với mọi loại điều kiện, có/không cửa sổ thời gian — trừ một chênh lệch duy nhất (F-PREC).
- Điều kiện dữ liệu đúng với **mọi** thuộc tính hồ sơ, giá trị và phép so sánh trên dữ liệu thật (sau khi sửa lỗi năm).
- Độ phủ trên đường đi CAP: `real_llm_client` 42% → **84%**; engine 97%; `data_conditions` 94%; module CAP 93–100%;
  script chấm điểm / TN7 / báo cáo trước 0% → có test cho các hàm chính.

## 3. Phát hiện (xếp theo mức nghiêm trọng)

### NGHIÊM TRỌNG — có thể làm sai số liệu một cách im lặng

**F-CACHE — Lỗi API bị ghi vĩnh viễn vào cache** (`real_llm_client.py`, `chat_json`)
Hết 6 lần thử (mất mạng, **hết hạn mức ngày của Groq**) → trả `"{}"` **và lưu vào cache**.
- Chạy lại không bao giờ gọi API nữa cho lời gọi đó.
- `"{}"` đi vào Tầng 1 như "LLM trả JSON sai" → tốn vòng tự sửa → khoản thành **FAILED** (lỗi của hệ thống)
  thay vì **ERROR** (lỗi hạ tầng). Với 212 khoản × 8 cấu hình trên tài khoản Groq miễn phí, việc chạm hạn mức
  ngày là rất có thể → hàng loạt khoản bị tính sai, không có cảnh báo.
- Sửa đề xuất: ném lỗi, không ghi cache (run_cap_generation đã ghi ERROR và chạy lại sẽ thử lại).

**F-JUDGE — Giám khảo lỗi thì mặc định cho qua** (`verbalizer_roundtrip.py`, `check_roundtrip_fidelity`)
`res.get("verdict", "EQUIVALENT")`: phản hồi không có `verdict` (VD `"{}"` do F-CACHE) → ràng buộc **qua Tầng 3**.
Kết hợp với F-CACHE: một lần API lỗi biến thành "ràng buộc được giám khảo chấp nhận", và lưu mãi trong cache.
- Sửa đề xuất: thiếu/sai `verdict` → coi là lỗi giám khảo (phản hồi lại, hoặc ERROR), không bao giờ là EQUIVALENT.

### CAO — sai lệch có hệ thống trên một nhóm khoản

**F-PREC — Điều kiện của Precedence áp lên sự kiện nào: 5 thành phần hiểu khác nhau**
Với `Precedence(A → B)` kèm điều kiện mức event (ngày, `success`):

| Thành phần | Điều kiện áp lên |
|---|---|
| Chuẩn Declare4Py | B (sự kiện kích hoạt) |
| Engine (`_check_single_trace`) | **cả A và B** |
| Bộ dịch ngược cho giám khảo (`verbalize_declare_ast`) | A ("'A' when date … must have occurred BEFORE it") |
| Phiếu nhãn (`cap_notation`) | chỉ chấp nhận `ngày(A)` |
| Kiểm rỗng B (`log_grounding`) | B |

Đo trên 2 000 hồ sơ thật: `Precedence(begin editing → calculate)` với **khoảng ngày** (1/12 → 30/6 năm sau)
cho kết quả khác chuẩn ở **963/2 000 hồ sơ**; `Alternate Precedence` 1/2 000. Điều kiện mức hồ sơ (năm, cờ,
diện tích) **không** bị ảnh hưởng (A và B cùng hồ sơ). Đây là dạng luật hay gặp trong CAP ("chi trả trong khoảng
ngày …, sau khi …"). Đã biết từ trước (để chờ quyết định); kiểm toán cho thấy nó lan sang cả code CAP.
- **Cần bạn chọn một quy ước, rồi sửa mọi thành phần theo đó:**
  - **(a) Theo chuẩn Declare4Py: điều kiện trên B.** Đúng với tài liệu DECLARE; phải sửa engine, bộ dịch ngược,
    phiếu nhãn (cho `ngày(B)`), mô tả trong prompt.
  - **(b) Điều kiện trên A** (đúng tên trường AST `activation_attr` gắn với `activation_activity`). Ít sửa hơn
    (engine, log_grounding) nhưng lệch chuẩn; phải ghi rõ trong bài.
  - Cả hai đều có thể đổi số liệu BPIC2017 cũ nếu có rule Precedence + điều kiện mức event (cần chạy lại TN4).

**F-WORDS — Entity Matcher không đọc số viết bằng chữ** (`extract_clause_numeric_entities`)
Toàn văn 4 Quy định: 62 chỗ ("two working days", "six months", "eight weeks", "three years") không được nhận;
mọi số viết bằng chữ số đều được nhận. Trong phiếu: **13 khoản** có ngay trong khoản, **37 khoản** có trong khoản
được dẫn chiếu (ảnh hưởng cấu hình Y). Hệ quả: ràng buộc đúng `time_max = 2` cho "two working days" bị báo
"con số không có trong luật" (THRESHOLD_MISMATCH, hoặc **BASELESS** nếu khoản không có con số nào khác — vòng lặp
kết thúc với kết luận sai). Cảnh báo số liệu của gold (`cap_gold`) cũng báo oan.
- Sửa đề xuất: nhận số bằng chữ tiếng Anh (one…twenty, thirty, sixty, ninety…) + đơn vị weeks.

### TRUNG BÌNH

**F-UNITS — Thời hạn theo tháng / tuần / ngày làm việc không biểu diễn được** (thiết kế)
AST chỉ có đơn vị s/m/h/d; quy tắc mục 7 cấm đổi tháng → ngày; engine tính theo ngày lịch. Khoản có thời hạn
"six months", "eight weeks", "two working days" vì vậy **không có gold biểu diễn đúng** (phiếu nhãn báo LỖI với
"tháng") và hệ thống không thể đúng. Không làm sai số liệu nhưng cần **ghi rõ** trong bài như giới hạn, hoặc bổ
sung đơn vị tháng theo lịch và tuần cho engine + AST + phiếu nhãn.

**F-KEY — Có thể gửi nhầm bí mật làm API key** (`_resolve_api_key`, bảo mật)
Khi không có GROQ/OPENAI/GEMINI key, hàm lấy **giá trị đầu tiên có dạng X=Y** trong `.env` (VD `NEO4J_PASSWORD`)
và gửi nó làm API key tới máy chủ LLM bên ngoài. Hiện không xảy ra vì `.env` của bạn có GROQ_API_KEY.
- Sửa đề xuất: chỉ chấp nhận các tên biến key đã biết; không đoán.

### THẤP

- **Lint (ruff):** 30 cảnh báo, không có lỗi chạy: 10 `zip()` không `strict`, 8 import thừa, 8 biến thừa,
  2 biến vòng lặp không dùng, 1 f-string thừa, 1 warning thiếu stacklevel.
- **Code chết BPIC2017:** `benchmark_builder.py:753-761` gán cứng `R05…R19` rồi không dùng (bộ BPIC2017 đang tắt).
- **Chữ còn sót của BPIC2017 trên đường đi CAP, vô hại:** mô tả trường AST nhắc "Directive 2008/48/EC" (không vào
  prompt); `verbalize_declare_ast` mặc định `case_noun="credit case"` (CAP truyền "application case"); mẹo
  `A_Validated` trong Γ (chỉ chạy khi có `A_Validating`); hàm `extract_concrete_trace_snapshots` dùng cột BPIC2017
  (CAP không gọi).

### ĐÃ SỬA trong đợt trước (ghi lại để đủ hồ sơ)

| Mã | Lỗi | Trạng thái |
|---|---|---|
| F-YEAR | `case:year == 2016` / `case:program-id == 215` (chuỗi số trong log, số trong .decl) luôn sai | Đã sửa (`data_conditions._equal`), hồi quy BPIC2017 0 khác; test tính chất giữ lại |
| F-VAC | Docstring nói vòng lặp có kiểm rỗng nhưng không có; kiểm rỗng cũ chỉ ngưỡng số; nhánh viết cứng Directive | Đã sửa (kiểm B, C, D, E) |

## 4. Đề xuất thứ tự sửa (đã thực hiện toàn bộ — xem mục 0)

1. **F-CACHE + F-JUDGE** — sửa trước khi chạy bất kỳ thực nghiệm chính thức nào (ít dòng, rủi ro thấp).
2. **F-PREC** — bạn chọn quy ước (a) hoặc (b); mình sửa đồng bộ 5 thành phần + chạy lại kiểm thử chéo.
3. **F-WORDS** — mở rộng Entity Matcher; chạy lại test BPIC2017 (bật) để chắc không đổi kết quả cũ.
4. **F-KEY** — nhỏ.
5. **F-UNITS** — quyết: ghi là giới hạn trong bài, hay bổ sung đơn vị tháng/tuần.
6. Lint / code chết — tuỳ ý.

## 5. Giới hạn của kiểm toán này

- Bộ kiểm tham chiếu và engine có thể **cùng sai** nếu cùng hiểu sai ngữ nghĩa một mẫu; mình đối chiếu với
  định nghĩa Declare4Py, nhưng không chạy được Declare4Py gốc trong môi trường này.
- Mẫu 2 000/43 809 hồ sơ; các trường hợp hiếm (VD hồ sơ cực dài) có thể không có trong mẫu.
- Prompt và hành vi LLM không kiểm được bằng test tự động — chỉ kiểm được phần ký hiệu bao quanh LLM.

## 6. Đợt 2 — các phần còn lại (2026-11-09) — ĐÃ SỬA TOÀN BỘ (xem 6.1)

Test: `tests/test_audit_round2.py` (9 expectedFailure, đã xác nhận từng cái thất bại đúng vì lỗi mô tả).

**Đã kiểm, ĐÚNG:**
- Engine vs **pm4py** (thư viện bên thứ ba, độc lập với engine và với bộ tham chiếu ở bước 1) trên 2 000 hồ sơ
  BPIC2018: 17 mẫu × 3 cặp activity → khớp 50/51. Ca lệch duy nhất (Init, 4 hồ sơ) do pm4py dùng thứ tự dòng
  trong file còn engine xếp theo thời gian — engine đúng.
- Dẫn chiếu ra văn bản ngoài bộ, "that Regulation", dẫn chiếu đơn lẻ: mẫu 40 cạnh ngẫu nhiên đúng (trừ F-REFMIS).

| Mã | Mức | Phát hiện | Số liệu |
|---|---|---|---|
| **F-REFLIST** | **Cao** | Danh sách / khoảng dẫn chiếu chỉ lấy phần tử ĐẦU ("Articles 53, 55 and 56" → chỉ 53; "Articles 43 to 46" → chỉ 43) | 137 cụm, **385 đích bị mất**; **50 khoản trong phiếu** có ngữ cảnh Y thiếu (91 đích) → Graph-RAG bị đánh giá thấp hơn thực |
| **F-SHEET** | **Cao** | Bộ đọc phiếu sai IM LẶNG: gõ tiếng Việt dạng tổ hợp (NFD) → dòng bị bỏ; dùng `\|` thay `·` → dòng bị bỏ; "Có (ngày lấy từ …)" ở câu (3) → Tier 4 thành Không; hai dòng cùng khoản → dòng sau đè | Khoản bị bỏ hiện thành "Chưa điền", không có lỗi nào được báo |
| **F-PARA** | Trung bình (thiết kế) | Dẫn chiếu trong cùng Điều ("paragraph 1 of this Article") không thành cạnh của đồ thị | 390 chỗ; **53 khoản trong phiếu** (36 Đợt 1, 17 Đợt 2) |
| **F-DOMVAL** | Trung bình | Kiểm C (miền giá trị) chặn oan cách viết tương đương: `2016.0` cho năm, `"true"` cho Boolean | Chặn ràng buộc đúng ở Tầng 2 |
| **F-DAYS** | Thấp–TB | Thời hạn "n ngày" tính n×24 giờ; Quy định (EEC, Euratom) **1182/71** tính theo **ngày lịch** (không tính ngày sự kiện, hết hạn cuối ngày cuối). 3/170 activity chỉ ghi ngày (00:00 giờ Đức: các sự kiện "mail") | 2 luật thử: 0 hồ sơ đổi phán quyết — chỉ lệch khi rơi đúng ngày cuối hạn; `mo` cũng so cả giờ |
| **F-ANNEX** | Thấp (giới hạn) | Phụ lục (Annex) không được tách, không có trong đồ thị | 78 khoản nhắc Phụ lục; 14 trong phiếu |
| **F-REFMIS** | Thấp | Cụm chen ("except paragraph 7(e)") làm các điều trong danh sách bị gán nhầm thành nội bộ | 3 dẫn chiếu, 1 khoản (R809:Art22(1), có trong phiếu) |
| F-PROMPT | Thấp | Danh sách khoá JSON của prompt CAP chưa nhắc `obligation_analysis` / `no_constraint` (quy tắc 6 và few-shot có) | LLM vẫn làm đúng ở các lần chạy thử |

**Lưu ý khi sửa F-REFLIST / F-PARA:** sửa đồ thị phải GIỮ NGUYÊN phiếu gán nhãn đang dùng
(`data/review/cap_item_candidates.json`, cách chọn Đợt 1 dựa trên dẫn chiếu chéo) — chỉ dựng lại cạnh đồ thị và
ngữ cảnh Y, không sinh lại phiếu.

### 6.1. Trạng thái sau khi sửa đợt 2 (người dùng duyệt "sửa tất cả các lỗi", kể cả F-ANNEX)

| Mã | Đã sửa thế nào | Kiểm chứng |
|---|---|---|
| F-REFLIST | Module mới `src/preprocessing/eu_references.py`: đọc từng phần tử danh sách, mở rộng khoảng điều ("43 to 46") và khoảng khoản ("(1) to (4)"), bỏ qua điểm "(a)", "(b)(i)"; chặn số đi kèm đơn vị ("Article 7 and 30 days") | Dẫn chiếu 1 207 → **2 096**; phần tử danh sách bị mất 385 → **0**; đọc tay 30 cạnh mới ngẫu nhiên: 30/30 đúng |
| F-REFMIS | Cụm chen "except …" không cắt danh sách; cả danh sách thuộc văn bản ghi ở cuối | R809:Art22(1) → R1307:Art20/24/30/39 |
| F-PARA | "paragraph N (of this Article)" → khoản cùng Điều; "of that Article" → Điều vừa nhắc | 53 khoản phiếu có thêm cạnh |
| F-ANNEX | `split_annexes` tách 15 Phụ lục (R1306 I–III, R1307 I–XI, R809 Annex) → `data/processed/cap_annexes.json`; node `Annex` trong đồ thị; "Annex X (to Regulation …)" / "the Annex" → cạnh | 15 khoản phiếu dùng được Phụ lục trong ngữ cảnh Y (trước 0) |
| F-SHEET | NFC; bỏ dấu câu cuối; "Không chắc chắn"; Tier 4 theo chữ mở đầu ("Có (…)"); dòng sai định dạng / trùng khoản → báo lỗi từng dòng; đọc file bằng `utf-8-sig` (BOM của Notepad từng làm mất dòng đầu) | `test_audit_round2` |
| F-DOMVAL | `normalize_value` theo kiểu Γ ('true' → True, 2016.0 → '2016'), dùng ở kiểm C VÀ ghi vào AST — chuỗi 'true' trước đây còn khiến engine không bao giờ khớp | `test_audit_round2` |
| F-DAYS | `Declare4Py(..., calendar_periods=True)` cho CAP (sinh, TN7): ngày / tuần / tháng theo ngày lịch giờ Đức, hết hạn cuối ngày cuối, cuối tuần → thứ Hai (Quy định 1182/71 Điều 3; ngày lễ: không có dữ liệu); tháng thiếu ngày → cuối tháng. BPIC2017 giữ n×24 giờ | `test_audit_round2` (gồm 31/1 + 1 tháng = 29/2/2016, ranh giới nửa đêm giờ Đức) |
| F-PROMPT | Danh sách khoá JSON của prompt CAP nhắc obligation_analysis / no_constraint | — |

**Dữ liệu đã dựng lại:** `cap_chunks.json` (966 khoản — mã và văn bản **giống hệt** bản cũ, chỉ dẫn chiếu đổi),
`cap_annexes.json` (mới), `cap_legal_graph.json` (Article 557, Paragraph 868, Annex 28; REFERS_TO 2 419).
**Phiếu gán nhãn KHÔNG đổi** (`cap_item_candidates.json`, `CAP_ITEM_CANDIDATES.md`: hash SHA-256 khớp trước/sau).

**Ngữ cảnh Y trên 212 khoản phiếu:** có dẫn chiếu 181 → 191; trung bình đích dùng 1,8 → 2,5; dùng Phụ lục 0 → 15.
Còn 6 khoản bỏ 17 đích vì ngân sách 12 000 ký tự (giữ ngân sách vì giới hạn token; ghi ở `skipped_refs`).
