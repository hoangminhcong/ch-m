# Phiên bản v2 — đăng ký trước (pre-registration)

**Ngày chốt: 2026-11-16.** Viết TRƯỚC khi cài đặt và TRƯỚC mọi lần chạy v2. Mọi thay đổi sau ngày này phải ghi vào
mục "Thay đổi sau đăng ký" kèm ngày và lý do.

## 1. Bối cảnh

Kết quả v1 (`results/cap_cerebras/`, gold `data/review/cap_gold_approved.json`: 3 positive, 207 bẫy, 8 không chắc):

- Y 188/210 đúng; mức chuẩn "luôn BASELESS" 207/210; tỉ lệ cân bằng Y 45,4% so với mức chuẩn 50%.
- 0/3 khoản positive đúng ở mọi cấu hình; X ≈ Y (p = 1,0).
- Ba kiểu hỏng: chọn sai activity (R1307:Art32(1)), thiếu nhóm activity theo năm (R1307:Art33(1)),
  ngoại lệ quốc gia không áp dụng cho log Đức nhưng làm Tầng 3 loại luật (R809:Art22(1)).

**v1 được đóng băng.** Không cấu hình v1 nào (X, Y, Y-no*) đổi hành vi; các cải tiến v2 chỉ bật trong cấu hình mới.

## 2. Quy tắc đánh giá (chốt)

1. Kết luận về v2 **chỉ** được rút ra trên **tập positive mới**, gán nhãn xong và duyệt TRƯỚC khi chạy v2 trên tập đó.
2. 3 khoản positive của gold v1 **không** được dùng để chỉnh prompt, ngưỡng hay code. Chạy v2 trên gold v1 được phép
   nhưng chỉ báo cáo kèm ghi chú "đã nhìn thấy khi thiết kế".
3. Báo cáo luôn có mức chuẩn "luôn BASELESS" và tỉ lệ cân bằng (đã cài: `score_cap.py`, `build_cap_report.py`).
4. Cùng model gpt-oss-120b, temperature 0, cùng nhà cung cấp, cùng số vòng tự sửa như v1.

## 3. Tham số chốt

| Tham số | Giá trị | Lý lẽ (không dựa trên gold) |
|---|---|---|
| Ngưỡng "vi phạm hàng loạt" | **20%** số hồ sơ có kích hoạt bị báo vi phạm | Một cơ quan đang vận hành thật hiếm khi vi phạm một quy định ở hơn 1/5 số hồ sơ |
| Hành động khi vượt ngưỡng | Phản hồi **một lần** cho mỗi ràng buộc, kèm ≤ 2 hồ sơ phản ví dụ; LLM giữ nguyên → chấp nhận, gắn cờ | Như kiểm rỗng B: chỉ phản hồi, không tự loại (luật đúng vẫn có thể bị vi phạm nhiều) |
| Gợi ý nhóm activity theo năm | Phản hồi một lần khi activity dùng chỉ có ở một phần các năm của log và có activity cùng bước ở loại giấy tờ khác phủ các năm còn lại | Tất định, từ log |

## 4. Thành phần v2

| # | Thành phần | Nguồn | Tất định |
|---|---|---|---|
| 1 | Năm hoạt động của activity; gợi ý nhóm `{A \| B}` | log | Có |
| 2 | Kiểm vi phạm hàng loạt + phản ví dụ từ log (gộp mục "thứ tự DIRECTLY_FOLLOWS": engine kiểm thứ tự chính xác hơn DF) | log | Có |
| 3 | Kiểm thuộc tính event nằm trên đúng activity (HAS_ATTRIBUTE) | log | Có |
| 4 | Quan hệ hồ sơ → tài liệu → loại giấy tờ (`docid`) | log | Có |
| 5 | Vai trò: tỉ lệ nhân viên / máy tự động theo activity (`org:resource`) | log | Có |
| 6 | Ontology nhỏ 8 loại giấy tờ (nghĩa, quan hệ, activity do nông dân khởi phát) | Claude soạn, **người duyệt** | Không |
| 7 | DefinedTerm + USES_TERM (định nghĩa thuật ngữ đưa vào ngữ cảnh) | văn bản luật | Có |
| 8 | ScopeCondition: ngoại lệ theo quốc gia; log thuộc Đức | văn bản luật + sự thật về log | Có |
| 9 | MAPS_TO điều luật → loại giấy tờ (qua thuật ngữ trong ontology) | ontology đã duyệt | Có (sau khi duyệt) |
| 10 | Nêu bật loại giấy tờ liên quan trong prompt (không xoá activity khỏi Γ) | MAPS_TO | Có |
| 11 | Hồ sơ activity cho Tầng 3 (loại giấy tờ, năm, tỉ lệ hồ sơ, bước trước/sau, vai trò) | KG | Có |
| 12 | GROUNDED_IN / ON: luật đã kiểm chứng → điều khoản, activity | kết quả chạy | Có |

Ontology (mục 6) chỉ được hệ thống dùng khi có `"status": "approved"` (giống gold).

## 5. Tập positive mới

Nguồn: văn bản thực thi cấp quốc gia của Đức cho các quy định CAP (2015–2017). Claude tìm và kiểm nguồn, dựng phiếu;
gán nhãn theo `docs/HUONG_DAN_GAN_NHAN_CAP.md` mục 10 (nhiều AI khác công ty, không dùng gpt-oss-120b, người kiểm mọi
bất đồng); người dùng duyệt. Có chủ đích nhiều khoản Tier 4 (cần dẫn chiếu).

### 5.1 Quyết định của người dùng (2026-11-18, trước khi dựng phiếu)

| Câu hỏi | Quyết định |
|---|---|
| Văn bản | **InVeKoSV** (InVeKoS-Verordnung, 24/02/2015, BGBl. I S. 166) + **DirektZahlDurchfV** (Direktzahlungen-Durchführungsverordnung, 03/11/2014, BGBl. I S. 1690) |
| Ngôn ngữ | **Giữ nguyên tiếng Đức** (không dịch); Entity Matcher được bổ sung số / ngày viết bằng chữ tiếng Đức |
| Phiên bản | **Theo từng năm nộp đơn của log** (2015, 2016, 2017): mỗi khoản lấy bản có hiệu lực cho năm đó; khoản đổi nội dung giữa các năm → mục riêng theo năm |
| Chọn khoản | Mọi khoản của hai văn bản (không lọc tay), như quy tắc đã áp cho CAP |

Nguồn văn bản: bản hiện hành ở gesetze-im-internet.de (XML) chỉ dùng để định vị; nội dung theo năm dựng lại từ lịch sử
phiên bản (buzer.de, "alle Fassungen seit 2006") và đối chiếu bản công bố trên Bundesgesetzblatt khi có.

## Thay đổi sau đăng ký

- **2026-11-16 (trước mọi lần chạy v2) — mở rộng thành phần 1.** Định nghĩa "cùng bước" (cùng tiến trình con +
  hành động ở loại giấy tờ khác) không nối được loại giấy tờ đổi tên theo năm khi tên bước cũng đổi. Thêm quan hệ
  tất định ở mức loại giấy tờ: hai loại có năm hoạt động **không giao nhau** và **gộp lại phủ đủ các năm của log**
  là "thay thế nhau theo năm" (`doctype_replacements`). Trên log thật chỉ có một cặp: Parcel document (2015) ↔
  Geo parcel document (2016–2017).
  *Công bố:* thông tin này đã có trong bảng loại giấy tờ theo năm của hướng dẫn gán nhãn (2026-11-10), và cặp này
  liên quan tới khoản gold R1307:Art33(1) đã thấy khi phân tích lỗi v1. Quy tắc phát hiện là chung (không nêu tên
  loại giấy tờ nào); vẫn phải đánh giá trên tập positive mới.
- **2026-11-18 — sửa lỗi kỹ thuật có sẵn của v1 → v1.1.** Entity Matcher (Tầng 3, Bước A) không bao giờ nhận số
  phần trăm trong văn bản tiếng Anh ('5 %'): mẫu đặt `\b` ngay sau '%'. Sửa: `(?!\w)` (đơn vị là chữ: không đổi),
  test hồi quy trong tests/test_entity_matcher_de.py. Lỗi tìm thấy khi viết test cho tập Đức, KHÔNG phải từ kết quả.
  Ảnh hưởng đo trước khi chạy lại (phát lại cache): 37/218 khoản có '%', không khoản positive nào; 18 lượt
  khoản–cấu hình đổi đường đi (X 0, Y 3, Y-noVac 2, Y-noDomain 1, Y-noDuty 12, còn lại 0). v1 giữ nguyên ở
  results/cap_cerebras/; v1.1 = results/cap_cerebras_v11/ (chỉ các khoản bị ảnh hưởng được gọi LLM lại). Bài báo
  cáo cả hai. v2 (Z) và tập Đức dùng code đã sửa ngay từ đầu.
- **2026-11-18 (trước mọi lần chạy v2) — thêm phân tích đã định trước.**
  (a) Ablation của Z, mỗi cấu hình tắt đúng một nhóm, so cặp McNemar với Z: Z-noLegal (định nghĩa + phạm vi),
  Z-noProcess (kiểm thuộc tính / năm / vi phạm hàng loạt), Z-noMass (chỉ vi phạm hàng loạt), Z-noNotes (ghi chú
  cho giám khảo), Z-noHint (gợi ý loại giấy tờ).
  (b) Tập Đức: prompt chỉ đổi phần mô tả nguồn văn bản ("German national rules implementing the CAP … written in
  German … log from Germany"), quy tắc / ví dụ / ngữ cảnh giám khảo giữ nguyên (`german_profile`).
  (c) Ontology bản nháp thêm `legal_terms_de` (thuật ngữ tiếng Đức) — cùng quy trình duyệt.
- **2026-11-18/19 — rà soát toàn bộ bằng 3 agent độc lập; đã sửa (trước mọi lần chạy v2):**
  - Đánh giá: Choice / Exclusive Choice / Not Co-Existence đối xứng; `time_min` trong phép so; cùng thời hạn khác
    đơn vị → UNIT_DIFF; kappa không xác định → None; score_cap dừng khi thiếu dự đoán / trộn lần chạy, liệt kê khoản
    không chấm; gold mang `years`, khoản chưa gán nhãn chặn duyệt, cảnh báo nhãn thiếu / mâu thuẫn; conformance dừng
    khi tập Đức thiếu năm hoặc phạm vi năm rỗng; báo cáo hiện mọi cấu hình, không sập khi None; ký hiệu '< N' thời
    hạn bị từ chối. Điểm v1 / v1.1 KHÔNG đổi (kiểm lại: Y 188 / 189, X 187); gold CAP dựng lại khớp hoàn toàn.
  - Tập Đức: khoản ma DirektZahlDurchfV §36 (đánh số lại) bị loại, §35 chỉ còn bản 2017; phụ lục bị cắt; dẫn
    chiếu: số nhiều bổ ngữ, khoảng có chữ cái, 'Gesetz über …'; mọi phiên bản trùng năm được nối; cờ 'có con số'
    theo Entity Matcher. Phiếu: 256 → 255 khoản (chỉ đợt 18 đổi mã).
  - v2: hồ sơ tầng Tiến trình giữ thứ tự log khi trùng thời điểm (bước trước / sau đúng); định nghĩa: dấu phẩy
    sau nháy, cắt định nghĩa cuối ở hết câu, phạm vi Chương / mục đích riêng → trong Article, dẫn nhập theo Article;
    ghi chú phạm vi chỉ cho câu ngoại lệ. Cache LLM ghi nguyên tử + gộp (không đổi kết quả).
  - Các lỗi ảnh hưởng v1: người dùng quyết định "Sửa hết → v1.2" (mục dưới).
- **2026-11-19 — sửa lỗi kỹ thuật có sẵn của v1 → v1.2** (cùng quy trình v1.1: đo bằng phát lại cache trước, sửa
  ở code dùng chung, chỉ gọi LLM lại cho khoản bị ảnh hưởng; v1, v1.1 giữ nguyên; báo cáo cả ba).
  - Lõi: Entity Matcher — 'calendar / working' trước mọi đơn vị thời gian, số nghìn kiểu Anh '1,000' (và tiếng Đức
    '1.000' chỉ ở đoạn tiếng Đức), 'per cent', EUR/€ tiếng Đức, không ghép 'Article 12 150'; kiểm đơn vị thời gian
    (ngày / tuần / tháng) của time_min / time_max phải khớp khoản; ngày làm việc tính từ ngày làm việc trước đó;
    điều kiện dữ liệu không đọc được vẫn bỏ nhưng cảnh báo; tên thuộc tính 'A.' trong điều kiện phụ; khóa
    vacuity / năm / hàng loạt theo dòng .decl; trả lời rỗng của LLM không vào cache.
  - Dữ liệu CAP: bộ tách khoản — dòng xuống hàng bắt đầu bằng năm ('2014.') không còn thành khoản giả (bỏ
    R1307:Art21, R1307:Art25(2015) — không thuộc phiếu / gold), tiêu đề 'CHAPTER 2 / SECTION 3', chú thích
    '( 1 ) …' bị bỏ khỏi khoản: 966 → 964 khoản, 32 khoản đổi nguyên văn. Dẫn chiếu — 'Regulation (EU) 1307/2013'
    (không 'No'), '(Euratom, EC)', 'Regulation 1305/2013', chuỗi 'in conjunction with / as well as / with the
    exception of', 'thereof' (văn bản nhắc gần nhất, kể cả Directive), 'of that Regulation' không tiền ngữ → không
    mặc định cùng văn bản: 9 khoản đổi dẫn chiếu. Ngữ cảnh Y — đích giữ chỗ (ngoài phạm vi / không văn bản) bị bỏ,
    khoản của Điều đã dẫn chiếu không lặp lại.
  - Phiếu CAP cập nhật TẠI CHỖ (không chọn lại: giữ mã, thứ tự, đợt): 52/218 mục đổi nguyên văn khoản hoặc khoản
    được dẫn chiếu. Gold CAP dựng lại khớp hoàn toàn (218 khoản, 0 khác biệt nhãn).
  - v1.2 = results/cap_cerebras_v12/ (sao từ v1.1, phát lại cache để tìm khoản bị ảnh hưởng).
  - Bổ sung cùng ngày (trước khi chạy lại v1.2): chú thích '( 1 ) … p 48).' (thiếu dấu chấm) còn lẫn ở R809:Art5;
    PDF R640 mất gạch nối ở 17 chỗ ngắt từ ('legisla tion') → nối lại khi từ ghép có ở chỗ khác trong cùng văn bản
    (13 khoản R640, 7 trên phiếu). Tập Đức: 'in Verbindung mit' (6 khoản đổi dẫn chiếu; 4 khoản từng trỏ nhầm
    InVeKoSV §6 thay vì §6 Marktorganisationsgesetz) — phiếu Đức dựng lại, dòng trả lời giữ nguyên.
- **2026-11-20 — sửa lỗi sau rà soát kiểm thử (người dùng: "sửa tất cả rồi đưa t1-t3 vào để kiểm tra"); áp dụng
  cho MỌI lần chạy SAU v1.2** (v1.2 hoàn tất bằng code commit `b32a643` — phát lại cache chứng minh code đó cho kết quả
  giống hệt v1.2, 1 526/1 526 khoản). Không rút từ gold; không đổi prompt.
  - Lõi, Tầng 1: `time_max` chỉ được dùng với mẫu có ngữ nghĩa thời hạn trong engine / Cypher / bản diễn đạt
    (Response, Alternate / Chain Response, Responded Existence, Precedence, Alternate / Chain Precedence, Not
    Response, Not Precedence). Existence, Absence, Init, Exactly1, Choice, Exclusive Choice, Not Co-Existence, Not
    Responded Existence bỏ qua cửa sổ thời gian → trước đây là thời hạn "trên giấy" và làm N3 (B6) được thoả mà
    không có thời hạn thật. Hạn chót kiểu mốc ngày dùng điều kiện `date` (như N5 đã ghi).
  - Entity Matcher — đề xuất rồi HOÀN TÁC (người dùng: "hoàn tác lỗi 9"): đổi "khoản không có mốc số / ngày / năm
    nào → BASELESS ngay" thành phản hồi cho LLM. Phát lại cache v1.2 (T3): đúng 4 khoản đổi hành vi — X: R1307:Art24(8),
    R809:Art71(6), R809:Art75; Y: R809:Art50(5) — cả 4 là bẫy hoặc không chấm và hành vi cũ ĐÚNG ở cả 4, không khoản
    positive nào được lợi → giữ hành vi cũ. Sau hoàn tác: phát lại v1.2 bằng code hiện tại 1 526/1 526 giống hệt.
  - Lõi, Tầng 2: activity tự lặp so theo tập thành viên (`{A | B}` với `{B | A}` hay hai nhóm chung một activity).
  - Chấm (phân loại MÔ TẢ, không đổi EQ / tỉ lệ đúng / p): Precedence(A,B) so với Responded Existence(B,A) (không
    phải (A,B)); thời hạn ở mẫu phủ định đổi chiều mạnh / yếu. v1–v1.2: 0 khoản đổi lớp.
  - TN7: khoản nhiều gold chọn gold theo kappa (trước: agreement); in p < 0,0001 thay vì "p = 0".
  - Ghi nhận / cổng: model giám khảo vào cổng "lẫn lần chạy"; dấu code từng khoản; `--force --only` với lần chạy
    khác bị chặn; proof trace của Z đối chiếu cả định nghĩa / ghi chú phạm vi có trong prompt (S4).
  - Kiểm thử thường trực: T1 (dữ liệu phái sinh = dựng lại từ nguồn) trong `run_pipeline pre`, T2 (bất biến đầu ra)
    cuối `run_pipeline post`, T3 (`run_pipeline replay`: phát lại cache bằng code hiện tại) sau mỗi lần sửa code.
- **2026-11-21 — giới hạn độ dài câu trả lời khi gọi API (hạ tầng, không đổi logic).** Cerebras (30k token / phút)
  tính độ dài trả lời MẶC ĐỊNH vào hạn mức: cùng prompt ~9,7k token, không gửi giới hạn → 429 mãi, gửi
  `max_completion_tokens=8000` → 200 (đo bằng scripts/check_api_quota.py). Thêm `--max-tokens` (mặc định không gửi
  = như cũ; ghi `max_completion_tokens` vào meta; câu trả lời bị cắt ở giới hạn = ERROR, không cache). Khoá cache không
  đổi → mọi kết quả cũ phát lại y nguyên. v1.2 Y-noDuty: 2 khoản cuối (R1307:Art41(3), R1307:Art43(9), lỗi ở vòng sửa
  thứ 5 / 4, prompt 55–60k ký tự) chạy bằng `b32a643` + đúng bản vá này (meta của file ghi git_dirty = true vì vậy).

## Bổ sung đăng ký trước (2026-11-19) — **ĐÃ DUYỆT 2026-11-19** (người dùng: "oke duyệt tất cả", gồm B4 tùy chọn; B5 theo phương án (a)), áp dụng trước mọi lần chạy Z và tập Đức

Nguồn: thảo luận sau khi đọc Dang et al., *Legal Reasoning in LLMs Through Ontology-Based Knowledge Graphs*, ISDS 2026;
rà công trình liên quan: `docs/CONG_TRINH_LIEN_QUAN.md`. KHÔNG đổi chỉ số chính (mục 2) — chỉ thêm phân tích phụ.

**B1. Chấm theo thành phần (kiểu IRAC) — phân tích PHỤ, cho mọi cấu hình, CAP và tập Đức.** Mỗi khoản có gold
ràng buộc (positive), chấm 4 mức lồng nhau, mức sau chỉ tính khi mức trước đạt:
  - *Issue*: hệ thống KHÔNG trả BASELESS (nhận ra có nghĩa vụ quan sát được).
  - *Rule*: cùng mẫu DECLARE với gold (mẫu đối xứng so không theo thứ tự — như `cap_scoring`).
  - *Application*: cùng tập activity (nhóm `{A | B}` so theo tập) VÀ cùng tập điều kiện VÀ cùng thời hạn (quy về giây).
  - *Conclusion*: EQ như chỉ số chính.
  Khoản bẫy: chỉ *Issue* (đúng = BASELESS). Báo cáo tỉ lệ từng mức kèm Wilson 95%; không kiểm định giả thuyết mới.
  *Làm rõ khi cài đặt (2026-11-19, trước khi có số B1 nào):* định nghĩa trên làm *Application* trùng *Conclusion*
  (cùng activity + điều kiện + thời hạn = EQ). Cài đặt: *Application* = cùng **activity** (nhóm so theo tập, mẫu đối
  xứng không theo thứ tự); điều kiện và thời hạn thuộc *Conclusion* (= EQ). (`cap_scoring.component_rates`.)
**B2. Kiểm tập ràng buộc và proof trace — mô tả, KHÔNG dùng để chấm.** Với tập luật của mỗi cấu hình: số cặp
CONFLICT / CONFLICT_IF_ACTIVATED / IMPLIES / DUPLICATE (`src/symbolic/constraint_set_checks.py`, kiểm có giới hạn,
vết ≤ 5); tỉ lệ dẫn chứng của LLM nguyên văn / gần nguyên văn / không có căn cứ (`src/evaluation/proof_trace.py`,
ngưỡng gần nguyên văn 0,8 trigram — chốt TRƯỚC khi chạy). Không đổi đầu ra của hệ thống.
  *Cập nhật 2026-11-20:* kiểm tập chuyển từ duyệt vết ≤ 5 sang tích automat (DFA) — chính xác mọi độ dài; DFA khớp
  định nghĩa LTLf trên mọi vết ngắn (35 581 phép so, cả 17 mẫu); trên v1.1, 4 265 cặp luật của 8 cấu hình: 0 khác
  biệt so với cách cũ. Thêm một trường hợp có thời hạn chứng minh chặt được (Response ≤ t1 với Not Response ≤ t2,
  t1 ≤ t2, cùng đơn vị cố định).
  *Sửa 2026-11-20 (đối chiếu với engine):* điều kiện của Choice / Exclusive Choice áp cho cả A và B; họ Alternate
  ngắt ở A / B bất kỳ (không xét điều kiện). v1, v1.1: 0 luật bị ảnh hưởng, mọi phát hiện giữ nguyên; v1.2 có 1 luật
  Alternate có điều kiện — kiểm tập v1.2 chưa chạy, nên dùng bản đã sửa ngay từ đầu.
**B3. Cổng metamodel.** Mọi đồ thị dùng cho một lần chạy phải qua `scripts/check_kg_metamodel.py` (0 vi phạm);
kết quả kiểm ghi kèm lần chạy.
**B4. (TÙY CHỌN — người dùng quyết, tốn API) Câu hỏi phụ Graph-RAG.** Thêm cấu hình *R*: cùng prompt / ngân sách
ký tự như Y nhưng ngữ cảnh = k khoản lấy bằng BM25 trên toàn bộ khoản (k sao cho tổng ký tự ≤ ngân sách của Y).
So cặp McNemar R vs Y và X vs Y CHỈ trên các khoản tập Đức có dẫn chiếu tới 4 Quy định CAP (79 khoản). Kết quả âm
được báo cáo như kết quả âm. Nếu không duyệt B4: bài KHÔNG khẳng định gì về Graph-RAG so với RAG truyền thống.
  *Làm rõ khi cài đặt (2026-11-19, trước mọi lần chạy R):* "ngân sách như Y" = **khớp từng khoản**: R được đúng số ký
  tự ngữ cảnh mà Y thêm cho CHÍNH khoản đó (Y không có ngữ cảnh → R cũng không); cùng giới hạn 3 000 ký tự mỗi khoản.
  Kho truy xuất = mọi node có văn bản của cùng đồ thị luật (BM25Okapi chuẩn, không trọng số miền), bỏ chính khoản và
  các phiên bản năm khác của nó, chỉ lấy node có năm giao với năm của khoản. Đã kiểm: |ngữ cảnh R − Y| ≤ 20 ký tự
  mọi khoản (CAP và Đức); chỉ 51/504 (CAP), 41/383 (Đức) khoản ngữ cảnh trùng nhau. Tập so: 79 khoản Đức có dẫn
  chiếu trong phạm vi tới 4 Quy định CAP (`score_cap.eu_ref_subset`).
**B5. Hiệu lực theo thời gian của văn bản CAP (mối đe dọa tính hợp lệ — báo cáo, không tự sửa gold).** Đối chiếu
bản hợp nhất có hiệu lực ngày 15/5 mỗi năm log (Cellar / EUR-Lex): xem `docs/CAP_HIEU_LUC_THOI_GIAN.md`. Mọi khoản
positive và không chắc chắn có nguyên văn giống hệt ở cả 3 năm; các khoản khác biệt đều là bẫy. Quyết định (a):
giữ nhãn, báo cáo 18 khoản bẫy có sửa đổi là giới hạn (nhãn bẫy không phụ thuộc chi tiết đã sửa); hệ thống tiếp tục
dùng bản gốc cho CAP.
  *Bổ sung 2026-11-20 (A5) — phân tích ĐỘ NHẠY, mô tả, không phải giả thuyết mới:* `score_cap.py` chấm lại CAP sau khi
  bỏ các khoản trong `data/review/cap_temporal_versions.json` (`check_cap_versions.py`, 18 khoản) và in kèm mọi cấu
  hình + mọi cặp McNemar. Chỉ báo cáo "kết luận có đổi hay không"; số chính vẫn là số trên toàn bộ khoản. Thêm sau
  khi đã biết số v1.1 (ghi rõ): trên v1.1 không kết luận nào đổi (Y 171/192; cặp có ý nghĩa vẫn có ý nghĩa, cặp
  không có ý nghĩa vẫn không; Y vẫn thua luôn-BASELESS, 0 / 18).

## Bổ sung đăng ký trước B6–B7 (2026-11-20) — **ĐÃ DUYỆT 2026-11-20** (người dùng: "làm tất đi"), chốt TRƯỚC mọi lần chạy N

**Nguồn và rủi ro chỉnh theo gold — ghi rõ.** Thiết kế dưới đây rút ra SAU khi xem 16 luật sai lọt qua của Y (v1.1)
trên khoản bẫy CAP (phân loại: 9 quy định nội dung, 3 tính toán, 1 tổ chức, 1 chế tài, 1 lưu hồ sơ, 1 thời hạn bị bỏ
mất). Vì vậy: **CAP là tập PHÁT TRIỂN cho N** (số CAP của N chỉ báo cáo kèm nhãn này); **kết quả chính của N lấy trên
tập Đức** (chưa hệ thống nào chạy, gold do người gán). Không chỉnh danh mục / quy tắc / prompt của N sau khi có bất kỳ
số nào của N.

**B6. Cấu hình N = Y + khung chuẩn tắc có danh mục đóng (M2) trước khi viết DECLARE.**
  - Prompt: quy tắc 6 của kiểm D mở rộng — `obligation_analysis` thêm `norm_type` ∈ {action_order, deadline,
    prohibition, content_requirement, calculation, organisational, penalty, definition} (định nghĩa từng loại trong
    prompt), `action` (trích nguyên văn cụm hành động), `deadline` (trích nguyên văn hoặc null). Ví dụ few-shot vẫn là
    miền giả định (thư viện), thêm một ví dụ content_requirement.
  - Quy tắc ký hiệu (code, không do LLM):
    (N1) `norm_type` ngoài danh mục / thiếu `action` → lỗi định dạng, phản hồi (như D).
    (N2) `norm_type` ∉ {action_order, deadline, prohibition} → **kết thúc ngay, outcome BASELESS**
         (trạng thái `DECLINED_NORM_TYPE`), kể cả khi LLM vẫn trả ràng buộc.
    (N3) `deadline` khác null mà AST không có thời hạn (`time_max`) cũng không có điều kiện `date` → phản hồi
         (`FAILED_NORM_DEADLINE`) mỗi vòng.
    (N4) Hỗ trợ từ KG: loại giấy tờ của MỌI activity trong AST phải nằm trong các loại giấy tờ mà khoản được nối tới
         qua MAPS_TO (tầng Cầu nối, ontology đã duyệt 2026-11-20). Không thoả (kể cả khoản không có MAPS_TO nào) →
         phản hồi MỘT lần (`FAILED_KG_SUPPORT`); LLM giữ nguyên → chấp nhận, ghi cờ `kg_support = false`.
    (N1+) *Bổ sung 2026-11-20 (rà soát, người dùng: "sửa tất cả"), TRƯỚC mọi lần chạy N:* `action` và `deadline`
         phải là trích dẫn THẬT của văn bản đưa cho LLM (khoản + khoản dẫn chiếu) — cùng phép kiểm dẫn chứng của
         proof trace (B2): 'unsupported' → phản hồi (`FAILED_NORM_FRAME`); đoạn < 12 ký tự không xét.
    (N4+) *Cùng ngày:* MAPS_TO của N4 (và dòng gợi ý của Z) đọc từ tầng Cầu nối của KG (`*_mapping_graph.json`)
         thay vì tính lại từ ontology — trùng từng chữ trên 218 khoản CAP + 255 khoản Đức (test), prompt không đổi.
    (Giám khảo) *Cùng ngày:* tuỳ chọn `--judge-provider/--judge-model` cho giám khảo Tầng 3 khác model bộ sinh.
         Mặc định (như đăng ký) = cùng model; nếu dùng giám khảo khác thì phải ghi trước khi chạy và báo cáo riêng.
    (N5) *Bổ sung 2026-11-20, TRƯỚC mọi lần chạy N (người dùng: "làm tất cả"):* mẫu DECLARE phải hợp loại chuẩn
         tắc — action_order: mẫu khẳng định (Existence, Init, Exactly1, Choice, Exclusive Choice, Responded Existence,
         họ Response / Precedence); deadline: họ Response / Precedence (có time_max) hoặc Existence / Absence (có điều
         kiện ngày); prohibition: Absence, Not Responded Existence, Not Response, Not Precedence, Not Co-Existence.
         Không hợp → phản hồi mỗi vòng (`FAILED_NORM_TEMPLATE`). Bảng lấy từ ngữ nghĩa mẫu và mục 5.2–5.3 của hướng
         dẫn gán nhãn, không từ gold; prompt N thêm quy tắc 9 nêu đúng bảng này.
  - Thứ tự trong vòng: D (định dạng, N1) → N2 → Tầng 1–2 → nhất quán D → N3 → N5 → N4 → B → Tầng 3. Mọi tham số khác như Y.
  - Ontology chưa duyệt → không chạy N.
  - So sánh (McNemar chính xác, như mục 2): **N vs Y trên tập Đức** (chính); N vs Y trên CAP (phát triển). Báo cáo
    thêm: luật sai lọt qua trên bẫy, đúng trên positive, B1 theo thành phần, phễu kiểm chứng (trạng thái mới N2–N4).
    Kết quả âm (N làm mất luật đúng trên positive tập Đức) được báo cáo như kết quả âm.

**B7. Nhãn REVIEW (M9) — mô tả, KHÔNG đổi đầu ra, KHÔNG đổi điểm.** Sau khi sinh, mỗi luật (outcome RULE) của mọi
cấu hình nhận các tín hiệu cố định (chốt ở đây, không chọn lại theo kết quả):
  (S1) vi phạm hàng loạt trên log: tỉ lệ hồ sơ kích hoạt vi phạm > 0,20 (ngưỡng đã đăng ký cho Z);
  (S2) không có hỗ trợ từ KG (quy tắc N4);
  (S3) dính CONFLICT / CONFLICT_IF_ACTIVATED với luật khác cùng cấu hình (kiểm tập, B2);
  (S4) dẫn chứng `unsupported` (proof trace, B2);
  (S5) rỗng trên log mà vẫn được chấp nhận (`grounding.vacuous = true`).
  Mức nghi ngờ = số tín hiệu (0–5); REVIEW = mức ≥ 1. Báo cáo bảng *giữ lại — rủi ro* (selective prediction): với
  mỗi ngưỡng k = 1..5 (giữ luật có mức < k), số luật giữ lại và, theo gold, số luật sai trên bẫy / đúng (EQ) trên
  positive trong số đó. Không chọn một ngưỡng "tốt nhất" để báo cáo như kết quả chính.
