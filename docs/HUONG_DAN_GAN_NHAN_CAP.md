# Hướng dẫn gán nhãn — 4 Quy định CAP và log BPIC2018

Tài liệu này dùng cho phiếu **`CAP_ITEM_CANDIDATES.md`** và là **tài liệu duy nhất** cần đọc (cùng bảng
`CAP_VOCABULARY.md`). Với mỗi khoản luật trong phiếu, người gán trả lời ba câu hỏi ở mục 3.

---

## 1. Bối cảnh

- **Luật:** 4 Quy định EU về **Chính sách Nông nghiệp Chung (CAP)** — chi trả trực tiếp cho nông dân:

  | Mã | Văn bản | Nội dung chính |
  |---|---|---|
  | **R1306** | Regulation (EU) No 1306/2013 | Tài chính, cơ quan chi trả, hệ thống quản lý và kiểm soát (IACS), thời hạn chi trả |
  | **R1307** | Regulation (EU) No 1307/2013 | Các chương trình chi trả trực tiếp (basic payment, greening, young farmer, small farmer, …) |
  | **R640** | Delegated Regulation (EU) No 640/2014 | IACS, điều kiện từ chối / thu hồi, **phạt hành chính** |
  | **R809** | Implementing Regulation (EU) No 809/2014 | Nộp đơn, thay đổi đơn, **kiểm tra** (hành chính, tại chỗ), mẫu kiểm tra |

  Mã khoản có tiền tố văn bản: `R809:Art13(1)` = Quy định 809/2014, Điều 13, khoản 1.
  Các văn bản **dẫn chiếu lẫn nhau rất nhiều** (VD R809 nói "thời hạn theo Article 78 của 1306/2013").

- **Log:** BPIC2018 — hồ sơ xin chi trả trực tiếp của nông dân tại một bang của Đức, 2015–2017,
  ~43 800 hồ sơ (mỗi hồ sơ = một nông dân × một năm), ~2,5 triệu sự kiện. Log ghi việc **cơ quan chi trả**
  xử lý giấy tờ: nhận đơn, sửa, kiểm tra, tính và chi tiền, khiếu nại.

- **Mục đích:** biết khoản luật nào đặt ra nghĩa vụ **kiểm tra được trên log**, viết nghĩa vụ đó thành ràng buộc
  DECLARE, và đánh dấu khoản nào phải đọc thêm khoản được dẫn chiếu mới viết đúng.

## 2. Nhận gì, nộp gì

| | |
|---|---|
| **Nhận** | `CAP_ITEM_CANDIDATES.md` (phiếu), `CAP_VOCABULARY.md` (bảng tên activity và thuộc tính), file này |
| **Nộp** | File `CAP_ITEM_CANDIDATES_<tên>.txt` chứa khối "Mẫu trả lời" ở đầu phiếu, đã điền đủ mọi dòng |

Phiếu có **hai đợt** (bảng ở đầu phiếu). Đợt 2 là mẫu ngẫu nhiên: phần lớn sẽ là "Không" — điều đó bình thường và
**cũng là kết quả cần đo**, đừng bỏ qua.

**Không có khoản nào bị lọc trước.** Phiếu có cả khoản định nghĩa, phạm vi, quyền của Ủy ban, khoản không có
*shall/must*. Người gán quyết định khoản đó có kiểm tra được trên log không.

## 3. Ba câu hỏi cho mỗi khoản

### (1) Quan sát được — khoản này có nghĩa vụ mà log cho phép kiểm tra không?

| Trả lời | Khi nào |
|---|---|
| **Có** | Có nghĩa vụ (ai đó *phải* / *không được* làm gì), các sự việc mà nghĩa vụ nói tới đều có activity / thuộc tính tương ứng trong log (mục 5, theo quy tắc proxy mục 6), **và** về nguyên tắc một hồ sơ có thể vi phạm nó |
| **Không** | Không có nghĩa vụ (định nghĩa, phạm vi áp dụng, "may" = chỉ cho phép), **hoặc** log thiếu sự kiện tương ứng, **hoặc** nghĩa vụ không nằm ở mức từng hồ sơ |
| **Không chắc** | Phân vân — vẫn ghi lý do |

Gợi ý theo loại khoản:

| Tình huống | Gợi ý |
|---|---|
| Nghĩa vụ đặt lên **cơ quan chi trả / Nhà nước thành viên** về việc **xử lý hồ sơ** (kiểm tra, chi trả, thông báo, thu hồi) | Log ghi việc của cơ quan chi trả, nên **có thể** quan sát được — xét xem có activity / thuộc tính tương ứng không |
| Nghĩa vụ của Nhà nước thành viên về việc **làm luật, báo cáo Ủy ban, lập hoặc duy trì hệ thống / cơ sở dữ liệu** | Thường **Không** (không có sự kiện trong log) |
| Nghĩa vụ của **nông dân** (nộp đơn, khai báo) | Quan sát được nếu log có sự kiện tương ứng (VD activity nhận đơn) |
| Khoản trao **quyền cho Ủy ban** ban hành văn bản, khoản định nghĩa, khoản phạm vi | Thường **Không**; nhưng một định nghĩa có thể cần cho câu (3) của khoản khác |
| Điều kiện về chương trình / diện tích / người trẻ … | Xét thuộc tính `case:` ở mục 5.2 |
| Log chỉ có một phần sự việc (VD có kết quả phạt nhưng không có cách tính) | Chỉ viết ràng buộc cho phần kiểm được, ghi phần còn thiếu ở Lý do |

Log **không** có: nội dung giấy tờ, lý do quyết định, ngày gửi bưu điện / ngày ghi trên đơn (chỉ có thời điểm hệ
thống ghi nhận sự kiện), các bước sau năm 2017.

### (2) Ràng buộc mới — chỉ khi (1) là "Có"

Viết nghĩa vụ thành ràng buộc DECLARE theo mục 4–5. Một khoản có thể cho **nhiều** ràng buộc, cách nhau bằng `;`.
Nếu ràng buộc trùng với một khoản khác, cứ ghi. Không áp dụng thì ghi `—`.

### (3) Cần điều tham chiếu — chỉ khi (1) là "Có" và khoản có dẫn chiếu

Muốn viết **đúng** ràng buộc ở (2), có cần đọc khoản được dẫn chiếu không?

| Trả lời | Nghĩa |
|---|---|
| **Có** | Chỉ đọc khoản này thì **không thể** viết đúng: thiếu mốc bắt đầu, điều kiện, đối tượng, hoặc con số / ngày nằm ở khoản kia |
| **Một phần** | Viết được phần chính, nhưng một chi tiết (ngoại lệ, điều kiện phụ, con số) chỉ có ở khoản kia |
| **Không** | Khoản được dẫn chiếu không làm thay đổi ràng buộc |
| **—** | Khoản không có dẫn chiếu, hoặc (1) không phải "Có" |

Trả lời **khắt khe**: chỉ chọn **Có / Một phần** khi chỉ ra được *chi tiết cụ thể* lấy từ khoản kia (ngày, con số,
điều kiện, đối tượng, mốc tính) và ghi chi tiết đó ở cột Lý do.

Cách đọc khoản được dẫn chiếu trong phiếu:
- Bấm dòng *"Khoản được dẫn chiếu: …"* để mở nguyên văn. Dẫn chiếu cả Điều thì phiếu ghép **mọi khoản** của Điều
  đó (có thể dài — chỉ cần đọc phần liên quan).
- *"Dẫn chiếu ra ngoài bộ 4 văn bản"* (VD 1305/2013, Treaty): phiếu không kèm nguyên văn. Nếu cho rằng cần văn bản
  đó mới viết đúng, ghi ở Lý do; được phép tra EUR-Lex.

> Ví dụ (luật thư viện giả định, không thuộc phiếu). Khoản A: *"Người mượn phải trả sách trong 21 ngày kể từ ngày
> nhận thẻ theo Điều 5."* Điều 5: *"Thẻ được giao khi thư viện kích hoạt tài khoản."* Log có `Kích hoạt tài khoản`,
> `Mượn sách`, `Trả sách`. → Quan sát được: **Có** · Ràng buộc: `Response(Kích hoạt tài khoản → Trả sách) ≤ 21 ngày`
> · Cần điều tham chiếu: **Có** — *mốc "ngày nhận thẻ" chỉ xác định được qua Điều 5 (= Kích hoạt tài khoản)*.

## 4. Các mẫu ràng buộc DECLARE

A, B là tên activity trong log (chép đúng từ `CAP_VOCABULARY.md`).

| Mẫu | Đọc là | Ví dụ đời thường |
|---|---|---|
| `Existence(A)` | Mỗi hồ sơ phải có A | Hồ sơ nào cũng phải có bước "nhận đơn" |
| `Absence(A)` | Không hồ sơ nào được có A | — |
| `Existence(A) với X op v` | **MỌI** hồ sơ phải có một lần A mà X thoả điều kiện — hồ sơ nào không có A như vậy đều vi phạm (xem 5.2 trước khi dùng với thuộc tính `case:`) | — |
| `Response(A → B)` | Nếu có A thì **sau đó** phải có B | Đã nhận đơn thì sau đó phải trả lời |
| `Response(A → B) ≤ n ngày` | Như trên, và B phải xảy ra trong vòng n ngày sau A | Trả lời trong 14 ngày |
| `Precedence(A → B)` | Nếu có B thì **trước đó** phải có A | Muốn chi tiền thì trước đó phải kiểm tra |
| `Chain Response(A → B)` / `Chain Precedence(A → B)` | B phải xảy ra **ngay sau** A / A phải **ngay trước** B | — |
| `Responded Existence(A → B)` | Nếu có A thì hồ sơ cũng phải có B (trước hay sau đều được) | — |
| `Not Response(A → B)` | Sau A không được có B | — |
| `Not Co-Existence(A → B)` | A và B không được cùng xuất hiện trong một hồ sơ | Hồ sơ bị từ chối thì không được chi tiền |

Cách ghi (các dòng chỉ minh hoạ **cách viết**, không phải đáp án):

```
Precedence(Duyệt hồ sơ → Chi tiền)
Response(Nhận đơn → Trả lời) ≤ 30 ngày
Responded Existence(Nhận đơn → Kiểm tra) | case:area > 10
Response(A → B) | case:young farmer == True and case:area >= 1
```
Điều kiện ghi sau `với` hoặc `|`; nhiều điều kiện nối bằng `and`. Nhiều ràng buộc trong một khoản: cách nhau `;`.

## 5. Từ vựng log

### 5.1. Tên activity

Mỗi activity có dạng **`loại giấy tờ / tiến trình con / hành động`**, VD
`Payment application / Application / mail income`. Có **170** activity — xem đủ ở `CAP_VOCABULARY.md`
(kèm số hồ sơ có activity đó). Cùng một hành động ở loại giấy tờ khác là **activity khác**:
`… / begin payment` của `Payment application / Application` khác `Payment application / Objection`.

Loại giấy tờ có trong log: `Payment application`, `Entitlement application`, `Parcel document`,
`Geo parcel document`, `Control summary`, `Department control parcels`, `Inspection`, `Reference alignment`.

**Loại giấy tờ thay đổi theo năm** (đếm trên log — số hồ sơ có loại giấy tờ đó / tổng hồ sơ của năm):

| Loại giấy tờ | 2015 | 2016 | 2017 |
|---|---|---|---|
| `Parcel document` (kê khai thửa đất, kiểu cũ) | 14 750 / 14 750 | 0 | 0 |
| `Geo parcel document` (kê khai thửa đất, kiểu mới) | 0 | 14 552 / 14 552 | 14 507 / 14 507 |
| `Entitlement application` (đơn xin quyền hưởng) | 14 748 | 307 | 205 |
| `Department control parcels` | 14 748 | 14 549 | 0 |
| `Payment application`, `Control summary`, `Reference alignment` | gần như mọi hồ sơ | gần như mọi hồ sơ | gần như mọi hồ sơ |
| `Inspection` (kiểm tra tại chỗ) | ~7 % | ~7 % | ~7 % |

Khi **cùng một bước** được ghi bằng activity khác nhau theo năm, viết **nhóm** `{A1 | A2}` (đúng tên trong bảng từ vựng,
ngăn bằng `|`) — ràng buộc thoả khi có **một trong** các activity của nhóm. VD:
`Precedence({Parcel document / Main / finish editing | Geo parcel document / Declared / finish editing} → Payment application / Application / begin payment)`
(chỉ minh hoạ cú pháp, không phải đáp án). Viết một activity chỉ có ở 2016–2017 sẽ báo vi phạm mọi hồ sơ 2015.

Nhà cung cấp dữ liệu **không công bố định nghĩa đầy đủ** từng hành động. Hiểu theo nghĩa tiếng Anh thông thường;
không chắc thì ghi Độ chắc chắn: Thấp và nói rõ cách hiểu ở cột Lý do (quy tắc proxy, mục 6).

### 5.2. Thuộc tính hồ sơ (`case:…`)

Log có **nhiều thuộc tính mức hồ sơ**: năm (`case:year`), diện tích (`case:area`), số thửa, các cờ chương trình
(`case:young farmer`, `case:small farmer`, `case:greening`, …), cờ chọn kiểm tra (`case:selected_random`,
`case:selected_risk`, `case:selected_manually`), số tiền xin / chi / phạt theo năm (`case:amount_applied0…3`,
`case:payment_actual0…3`, `case:penalty_amount0…3`), và các cờ phạt `case:penalty_*` (mã phạt — ý nghĩa từng mã
**không được công bố**; không đoán ý nghĩa mã).

Ràng buộc được phép dùng thuộc tính hồ sơ làm **điều kiện** — chọn mẫu theo ĐÚNG ý muốn nói:

| Ý của luật | Viết | KHÔNG viết |
|---|---|---|
| Hồ sơ thuộc diện X: nếu có A thì sau đó phải có B | `Response(A → B) \| case:young farmer == True` | |
| Hồ sơ thuộc diện X **phải có** A | `Responded Existence(Payment application / Application / mail income → A) \| case:young farmer == True` | `Existence(A) \| case:young farmer == True` |
| Hồ sơ thuộc diện X **không được có** A | `Absence(A) \| case:rejected == True` | |

**Vì sao không viết `Existence(A) | case:X`:** `Existence` có điều kiện nghĩa là **MỌI hồ sơ** phải có một A thoả điều
kiện — nên mọi hồ sơ **không** thuộc diện X đều bị tính vi phạm (VD chỉ ~2 % hồ sơ được chọn kiểm tra ngẫu nhiên →
98 % hồ sơ "vi phạm"). `Payment application / Application / mail income` có ở gần như mọi hồ sơ (43 808 / 43 809)
nên dùng làm điểm khởi đầu của `Responded Existence`: điều kiện chỉ áp lên hồ sơ thuộc diện X.

### 5.3. Mốc ngày trong năm

Luật CAP hay nói **ngày lịch cố định** ("trước 15 tháng X", "từ ngày 1 tháng X đến 30 tháng Y năm sau").
Ghi theo dạng sau (ngày/tháng; "năm" = năm của hồ sơ `case:year`, "năm+1" = năm sau):

```
Absence(A) với ngày(A) > 15/05/năm                      không được có A SAU ngày 15/5 (hạn chót)
Absence(A) với ngày(A) < 01/12/năm ; Absence(A) với ngày(A) > 30/06/năm+1    A chỉ được xảy ra trong khoảng
Existence(A) với ngày(A) <= 15/05/năm                   MỌI hồ sơ phải có A và có trước 15/5
```

Chọn mẫu theo ý luật (giống 5.2):
- **Hạn chót / khoảng thời gian** ("phải nộp trước…", "chi trả trong khoảng…"): vi phạm là **A xảy ra muộn / ngoài
  khoảng** → dùng `Absence(A) với ngày(A) > …` (và `< …` cho đầu khoảng). Hồ sơ không có A thì không vi phạm.
- Chỉ dùng `Existence(A) với ngày(A) …` khi luật bắt **mọi hồ sơ** phải có A trước mốc đó. Lưu ý: nhiều loại
  giấy tờ chỉ có ở một số năm (5.1) — `Existence` sẽ báo vi phạm mọi hồ sơ năm không có giấy tờ đó.

Ví dụ (luật thư viện giả định, **không** thuộc phiếu): *"Đơn gia hạn thẻ năm phải nộp trước ngày 31 tháng 1."*
→ `Absence(Gia hạn thẻ) với ngày(Gia hạn thẻ) > 31/01/năm`.

Ngày phải nằm trong chính khoản đó **hoặc** trong khoản được dẫn chiếu (khi đó câu (3) phải là **Có** /
**Một phần**, ghi rõ ngày lấy từ đâu).

**Ngày / điều kiện gắn với activity nào:** điều kiện thuộc activity **kích hoạt** ràng buộc —
- `Existence(A)`, `Response(A → B)`, `Not Response(A → B)`…: activity **A** → `… với ngày(A) …`
- `Precedence(A → B)` (và Alternate / Chain / Not Precedence): activity **B** (việc xảy ra sau, cần A đi trước)
  → `Precedence(A → B) với ngày(B) trong [01/12/năm, 30/06/năm+1]`
  = "mỗi lần B xảy ra trong khoảng ngày đó thì trước đó phải có A". Ghi `ngày(A)` cho Precedence sẽ bị báo lỗi.

### 5.4. Thời hạn — giữ đúng đơn vị của luật

Không quy đổi đơn vị: ghi đúng như luật nói.

```
Response(A → B) ≤ 15 ngày            ("15 days" / "15 calendar days")
Response(A → B) ≤ 2 ngày làm việc    ("two working days" — Thứ Hai–Thứ Sáu)
Response(A → B) ≤ 8 tuần             ("eight weeks")
Response(A → B) ≤ 6 tháng            ("six months" — tháng theo lịch, KHÔNG đổi thành 180 ngày)
```

## 6. Quy tắc "proxy" (dùng một activity thay cho sự việc trong luật)

Log hiếm khi có đúng tên sự việc trong luật, nên **được phép dùng proxy**, nhưng phải thoả:

- ✅ **Chấp nhận** khi activity *trực tiếp thể hiện* sự việc mà luật nói tới.
- ❌ **Không chấp nhận** khi activity chỉ là *bước nội bộ nằm gần đó* về thời gian, hoặc chỉ là thứ tự kỹ thuật
  của hệ thống mà luật không hề nói tới.
- ❌ **Không chấp nhận** khi tên activity chỉ **trùng chữ** với luật mà không cùng sự việc.
- ❌ **Không chấp nhận** khi phải *đoán* thêm điều luật không nói (VD đoán lý do quyết định khi log không ghi).

Khi dùng proxy, ghi rõ ở cột Lý do: *"proxy: <activity> ≈ <sự việc trong luật>"*.

## 7. Quy tắc con số, ngày và thời hạn

- Con số phải **xuất hiện trong chính khoản luật** (hoặc khoản được dẫn chiếu — khi đó ghi rõ ở Lý do và câu (3)
  là Có / Một phần). Con số lấy từ thống kê dữ liệu, kinh nghiệm hay "cho hợp lý" → **không hợp lệ**.
- Số viết bằng chữ trong luật ("two", "six") vẫn là con số có trong luật.
- Giữ **đúng đơn vị** (mục 5.4): "một tháng" không phải 30 hay 90 ngày.
- Kiểm tra **mốc tính**: luật nói "30 ngày kể từ X" thì ràng buộc phải bắt đầu từ X, không từ bước khác.
- Kiểm tra **con số ấy thuộc về việc gì**: cùng một con số có thể là hạn của *nông dân* chứ không phải của *cơ quan
  chi trả*, hoặc là ngưỡng của một chương trình khác.

## 8. Trường hợp khó thường gặp

| Tình huống | Cách xử lý |
|---|---|
| Khoản luật dài, nhiều điểm (a), (b), (c)… | Xét từng điểm; ghi ở Lý do điểm nào cho ra ràng buộc |
| Khoản chỉ nói "theo thủ tục ở Điều X" mà không có nghĩa vụ riêng | Xét Điều X qua câu (3); nếu bản thân khoản không đặt nghĩa vụ → Quan sát được: Không |
| Không chắc ý nghĩa một activity | Dựa vào `CAP_VOCABULARY.md`; vẫn không chắc thì chọn, Độ chắc chắn: Thấp |
| Nghĩa vụ đúng nhưng log chỉ có ngày (không có giờ) | Vẫn viết; thời hạn được tính theo ngày lịch |

## 9. Nộp bài

Chép khối "Mẫu trả lời" ở đầu phiếu vào file `.txt`, điền **mọi** dòng (không áp dụng thì ghi `—`), đặt tên
`CAP_ITEM_CANDIDATES_<tên>.txt`. Mỗi khoản **đúng một dòng**, giữ nguyên mã khoản, nhãn in đậm và dấu `·`.
Phân vân thì vẫn chọn, ghi Độ chắc chắn: Thấp.

## 10. Gán nhãn có AI hỗ trợ

Phiếu được gán bằng **nhiều AI độc lập**, sau đó **người** kiểm mọi chỗ các AI trả lời khác nhau.

### 10.1. Chọn AI

- Dùng **ít nhất 2 AI, của các công ty khác nhau** (VD một mô hình của Anthropic, một của Google, một của
  OpenAI). Hai AI cùng họ dễ sai giống nhau, làm "đồng thuận" mất ý nghĩa.
- **Không dùng mô hình mà hệ thống đang được đánh giá dùng** (`openai/gpt-oss-120b` trên Groq) hay mô hình cùng
  họ của nó: gold do chính mô hình đó viết sẽ chấm hệ thống cao hơn thực tế.
- Ghi lại **tên mô hình, phiên bản, ngày chạy** của từng AI (cần cho bài báo).

### 10.2. Mỗi AI nhận gì — và KHÔNG được nhận gì

| Gửi cho AI | KHÔNG gửi cho AI |
|---|---|
| File này (`HUONG_DAN_GAN_NHAN_CAP.md`) | Câu trả lời của AI khác |
| `CAP_VOCABULARY.md` | Bất cứ file nào trong `results/`, `data/review/cap_gold_*`, `docs/CAP_GOLD_REVIEW.md` |
| Một đợt khoản của `CAP_ITEM_CANDIDATES.md` (xem 10.3) | Kết quả, nhận xét hay ý kiến của người kiểm về các khoản |

Mỗi AI làm trong **cuộc trò chuyện mới**, không dùng bộ nhớ / dự án có chứa tài liệu khác của đề tài.

### 10.3. Chia đợt

Phiếu dài (~1,2 MB, vì Đợt 1 kèm nguyên văn các khoản được dẫn chiếu) — không AI nào nhận hết một lần. Các đợt đã
chia sẵn ở **`docs/cap_batches/`**: `dot_01.md` … `dot_23.md` (mỗi đợt tối đa 15 khoản và ~60 KB; danh sách ở
`DANH_SACH_DOT.md`). Chia lại: `python scripts/split_cap_sheet.py`. **Mọi AI nhận đúng cùng các đợt, cùng câu
lệnh**; mỗi file đợt có sẵn "Mẫu trả lời" của chính các khoản trong đợt.

### 10.4. Câu lệnh mẫu (dán nguyên văn, kèm các file ở 10.2)

**Prompt chính** — giống hệt cho mọi đợt và mọi AI:

```
Bạn là người gán nhãn cho một nghiên cứu khoa học về kiểm tra tuân thủ pháp luật trên nhật ký quy trình.

Tôi đính kèm 3 file:
- HUONG_DAN_GAN_NHAN_CAP.md: hướng dẫn gán nhãn (đọc kỹ toàn bộ trước khi làm, nhất là mục 3–7)
- CAP_VOCABULARY.md: bảng tên activity và thuộc tính của log (chỉ được dùng đúng các tên trong bảng này)
- dot_XX.md: một đợt các khoản luật cần gán nhãn

Nhiệm vụ: gán nhãn TẤT CẢ các khoản trong file đợt, theo đúng hướng dẫn.

Yêu cầu bắt buộc:
1. Trả lời MỖI khoản bằng ĐÚNG MỘT dòng theo "Mẫu trả lời" ở đầu file đợt: giữ nguyên mã khoản, các nhãn in đậm
   và dấu · ngăn cách; thay mọi chỗ ___ bằng câu trả lời:
   <mã khoản>: **Quan sát được:** … · **Ràng buộc mới:** … · **Cần điều tham chiếu:** … · **Độ chắc chắn:** … · **Lý do:** …
2. Quan sát được: chỉ ghi Có, Không hoặc Không chắc.
   Cần điều tham chiếu: chỉ ghi Có, Một phần, Không hoặc —.
   Độ chắc chắn: chỉ ghi Cao, TB hoặc Thấp.
3. Ràng buộc mới viết đúng cú pháp ở mục 4–5 của hướng dẫn; tên activity và thuộc tính PHẢI chép đúng từng chữ
   từ bảng từ vựng. Nhiều ràng buộc thì ngăn cách bằng dấu ;. Nếu Quan sát được không phải Có thì ghi —.
4. Mọi con số, ngày, thời hạn phải có trong khoản luật hoặc khoản được dẫn chiếu; giữ đúng đơn vị của luật
   (ngày / ngày làm việc / tuần / tháng), không quy đổi.
5. Với Precedence(A → B), điều kiện ngày ghi cho B. Với các mẫu khác, điều kiện ghi cho A.
6. Lý do: ngắn gọn (1–2 câu), nêu căn cứ trong khoản luật; nếu dùng proxy thì ghi "proxy: <activity> ≈ <sự việc>";
   nếu Cần điều tham chiếu là Có / Một phần thì ghi rõ chi tiết lấy từ khoản nào.
7. Phân vân vẫn phải chọn, ghi Độ chắc chắn: Thấp. Không bỏ trống khoản nào.
8. Chọn mẫu theo mục 5.1–5.3 của hướng dẫn: hạn chót / khoảng thời gian → Absence(A) với ngày(A) > mốc;
   "hồ sơ thuộc diện X phải có A" → Responded Existence(Payment application / Application / mail income → A) | X,
   KHÔNG viết Existence(A) | case:…; cùng một bước được ghi bằng activity khác nhau theo năm (VD Parcel document
   năm 2015, Geo parcel document năm 2016–2017) → nhóm {A1 | A2}.

Định dạng đầu ra: CHỈ các dòng trả lời, mỗi khoản một dòng, theo đúng thứ tự trong file đợt, đặt trong một
khối code. Không viết lời mở đầu, giải thích hay tóm tắt nào khác.
```

**Prompt sửa lỗi** — chỉ khi AI trả sai định dạng / thiếu khoản / thêm lời giải thích (cùng cuộc trò chuyện).
Chỉ dùng để sửa **định dạng**, không bao giờ nhắc AI đổi ý kiến:

```
Câu trả lời chưa đúng định dạng. Hãy trả lại TOÀN BỘ các dòng, mỗi khoản của file đợt đúng một dòng theo
"Mẫu trả lời", đủ tất cả các khoản, đặt trong một khối code, không thêm bất kỳ chữ nào khác.
Giữ nguyên nội dung các câu trả lời đã đưa, chỉ sửa định dạng.
```

Lưu câu trả lời của mỗi AI vào **một file riêng**: `CAP_ITEM_CANDIDATES_<tên-AI>.txt` (nối các đợt theo thứ tự).
Kiểm nhanh mỗi đợt: đủ số dòng, không có dòng thừa (lời dẫn, tóm tắt) — dòng sai định dạng sẽ bị báo lỗi ở bước sau.

### 10.5. Đối chiếu và người kiểm

1. Chạy `python scripts/compare_cap_labels.py --labels CAP_ITEM_CANDIDATES_<AI-1>.txt CAP_ITEM_CANDIDATES_<AI-2>.txt …`
   (dòng sai định dạng → sửa định dạng, KHÔNG đổi ý của AI, rồi chạy lại). Script so từng khoản: Quan sát được,
   Ràng buộc mới (so **theo nghĩa**, sau khi chuyển thành AST — viết khác nhau mà cùng nghĩa vẫn là giống), Cần điều
   tham chiếu. Kết quả ở `data/review/ai_compare/`:
   - `DOI_CHIEU.md` — tỉ lệ đồng thuận, kappa, và từng khoản bất đồng (nguyên văn luật + câu trả lời của mỗi AI);
   - `CAP_ITEM_CANDIDATES_final_draft.txt` — nháp nhãn cuối: khoản đồng thuận điền sẵn, khoản bất đồng để `___`,
     dòng `# CẦN NGƯỜI QUYẾT` / `# KIỂM NGẪU NHIÊN` đánh dấu khoản cần người xem.
2. **Khoản các AI khác nhau → người quyết** (đọc khoản luật, chọn hoặc viết lại đáp án), điền vào file nháp.
3. **Khoản các AI giống nhau → vẫn kiểm ngẫu nhiên**: script đã chọn sẵn ít nhất **20 khoản** (hoặc 10%, lấy số lớn
   hơn, seed cố định). Lý do: nhiều AI có thể **cùng sai**; ghi lại số khoản phải sửa trong mẫu — tỉ lệ này phải
   báo cáo.
4. Lưu file nháp đã điền thành `CAP_ITEM_CANDIDATES_final.txt` rồi chạy `build_cap_gold.py --labels …` → duyệt →
   `--approve`.

### 10.6. Phải ghi trong bài báo

- Gold được tạo bằng **AI hỗ trợ + người kiểm**: tên / phiên bản các AI, ngày chạy, câu lệnh (10.4).
- Tỉ lệ đồng thuận giữa các AI (trước khi người kiểm), số khoản người phải quyết, số khoản người đã sửa.
- Tỉ lệ sai trong mẫu ngẫu nhiên các khoản AI đồng thuận (10.5 bước 3).
- Các AI làm gold khác họ với mô hình của hệ thống được đánh giá.
