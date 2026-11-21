# Hướng dẫn Thực nghiệm: NSAI + Graph-RAG cho Kiểm tra Tuân thủ

Tài liệu này hướng dẫn bạn **tự chạy từng thực nghiệm**, xem kết quả trực quan và ghi số liệu.
Mỗi thực nghiệm (TN) gồm 4 phần: **Mục đích → Lệnh chạy → Xem kết quả → Ghi số liệu & hiểu ý nghĩa**.

> Quy ước: mọi lệnh chạy trong **PowerShell**, tại thư mục dự án
> `...\NCKH\neuron_symbolic_MDE-main\neuron_symbolic_MDE-main`.

---

## Bản đồ thực nghiệm

| TN | Nội dung | Module | Trả lời câu hỏi | Trạng thái |
|---|---|---|---|---|
| TN1 | Dựng & xem tầng Pháp lý của KG | M1 | KG tự động giàu hơn RKG nhập tay bao nhiêu? | ✅ Sẵn sàng |
| TN2 | Chuẩn bị bộ đề: chống rò rỉ, rà gold, soạn Tier 4, khoá đề | Đánh giá | Bộ đề có đúng luật và không lộ đáp án không? | 🔄 Bước 1–2 sẵn sàng |
| TN3 | Dựng tầng Tiến trình của KG từ log đầy đủ (tầng "thay UML") | M3 | Log thực sự có những gì để kiểm tra? | ✅ Sẵn sàng |
| TN4 | Đối chiếu engine Declare với thư viện chuẩn | M8 | Engine có đúng ngữ nghĩa 17 template không? | ✅ Sẵn sàng |
| TN5 | Khung chuẩn tắc (cấu hình N) + nối khái niệm luật → loại giấy tờ (tầng Cầu nối, MAPS_TO) | M2, M4 | Chặn được luật sai từ gốc không? | 🔄 Đã dựng; chưa chạy (đánh giá tạm gác, 2026-11-20) |
| TN6 | Sinh ràng buộc: X vs Y (đồ thị) vs R (BM25) — CAP (C6) | M5, M6 | Ngữ cảnh từ graph có tăng tỉ lệ đúng, nhất là Tier 4? | ✅ CAP v1, v1.1; 🔄 v1.2; tập Đức chờ gold |
| TN7 | Kết luận từng hồ sơ: ràng buộc gold vs ràng buộc sinh ra (toàn log) | M8, M9, M11 | Sai lệch khi hình thức hoá ảnh hưởng bao nhiêu hồ sơ? | ✅ CAP v1; v1.1/v1.2 chưa chạy |
| TN8 | Ablation (+ nhãn REVIEW, phễu kiểm chứng, proof trace) | M9, M10, M11 | Thành phần nào đóng góp bao nhiêu? | ✅ CAP v1, v1.1; đánh giá giải thích chưa làm |
| C1–C4 | Bộ thứ hai BPIC2018 + CAP: chuyển log, tách luật, dựng KG, phiếu gán nhãn (Phần C) | M1, M3 | Có câu Tier 4 quan sát được không? | ✅ CAP; tập Đức: AI 1/2 xong, chờ AI 2 + người quyết |

> Kiến trúc tổng quan (tầng KG, 5 giai đoạn, thứ tự kiểm, cấu hình): **`docs/KIEN_TRUC.md`**.

> **Bộ dữ liệu chính: BPIC2018 + 4 Quy định CAP (Phần C).** Bộ BPIC2017 + Directive 2008/48/EC (TN1–TN4 ở Phần B)
> **đã gỡ khỏi dự án (2026-11-21)**: dữ liệu chuyển ra kho lưu `C:\Users\hayab\nsai_archive_bpic2017`, 22 module /
> script riêng của BPIC2017 (`run_phase1a`…`run_phase4`, `run_benchmark_evaluation`, `run_real_llm_experiment`,
> `export_gold_review`, `adjudicate_gold`, `validate_declare_engine`, `experiment_runner`, `benchmark_builder`, …)
> gỡ khỏi code — còn nguyên trong lịch sử git (commit `57757a4`). Phần B dưới đây giữ lại làm lịch sử: các lệnh
> của nó không còn chạy được. Muốn chạy lại BPIC2017: `git checkout 57757a4 -- scripts src tests`, chép kho lưu về đúng
> chỗ, đặt `$env:NSAI_ENABLE_BPIC2017 = "1"`.

> Ghi chú thay đổi kế hoạch: bỏ phép so κ với 5 checker viết tay của bài cũ — cả 5 đều là template DECLARE
> nên so với engine là thừa. Thay vào đó, bài báo có một **bảng đối chiếu** 5 checker ↔ template DECLARE
> (2/5 checker dùng ngưỡng luật không quy định: 8 ngày, 1 ngày).

---

## Phần A — Cài đặt (làm một lần)

### Bước 0. Mở terminal và dùng đúng Python

Môi trường Python đã được tạo sẵn tại `C:\Users\hayab\.venvs\nsai-compliance`
(đặt ngoài OneDrive để OneDrive không phải đồng bộ hàng chục nghìn file thư viện).

```powershell
cd "C:\Users\hayab\OneDrive - Hoc vien Ky thuat mat ma\Desktop\NCKH\neuron_symbolic_MDE-main\neuron_symbolic_MDE-main"
& "C:\Users\hayab\.venvs\nsai-compliance\Scripts\Activate.ps1"
```

Nếu báo lỗi *"running scripts is disabled"*, chạy một lần lệnh sau rồi kích hoạt lại:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Kích hoạt thành công thì đầu dòng lệnh có chữ `(nsai-compliance)`. Từ đây `python` là Python của dự án.

### Bước 1. Tạo file `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```
Để notepad mở đó, bạn sẽ điền mật khẩu Neo4j ở Bước 2 và API key ở Bước 3.
**Không gửi file `.env` cho ai (kể cả dán vào chat).**

### Bước 2. Chạy Neo4j bằng Docker

1. Mở **Docker Desktop** (Start menu → Docker Desktop), chờ đến khi góc dưới trái báo *Engine running*.
2. Tự chọn một mật khẩu **≥ 8 ký tự** (thay `DatMatKhauCuaBan` bên dưới). Chạy:
   ```powershell
   docker run -d --name nsai-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/DatMatKhauCuaBan -e NEO4J_server_memory_heap_max__size=2G -e NEO4J_server_memory_pagecache_size=2G -v nsai_neo4j_data:/data neo4j:5.26
   ```
   - `-p 7474` là giao diện web, `-p 7687` là cổng Python kết nối vào.
   - `-v nsai_neo4j_data:/data` giữ dữ liệu lại khi tắt máy.
   - Bộ nhớ 2G + 2G đủ cho log đầy đủ 1,2 triệu event (TN3).
3. Chờ ~30 giây, mở trình duyệt: **http://localhost:7474** → đăng nhập `neo4j` / mật khẩu vừa đặt.
4. Điền mật khẩu vào `.env`: `NEO4J_PASSWORD=DatMatKhauCuaBan`, lưu file.

Lệnh dùng hằng ngày:
```powershell
docker start nsai-neo4j            # bật lại sau khi khởi động máy
docker stop nsai-neo4j             # tắt khi không dùng (giải phóng RAM)
docker logs nsai-neo4j --tail 20   # xem lỗi nếu không vào được
```

> Vì sao không dùng Neo4j Aura Free (bản cloud miễn phí)? Aura Free giới hạn 200.000 node,
> trong khi log đầy đủ có hơn 1,2 triệu event. Bản Docker chạy trên máy bạn không bị giới hạn.

### Bước 3. Lấy API key Groq (cần từ TN5 trở đi)

1. Vào **https://console.groq.com**, đăng nhập.
2. Menu **API Keys** → **Create API Key** → đặt tên `nsai` → copy key (dạng `gsk_...`, chỉ hiện một lần).
3. Dán vào `.env`: `GROQ_API_KEY=gsk_...`, lưu file.

Gói miễn phí của Groq giới hạn số request/phút. Dự án đã có **cache**: mỗi câu hỏi giống nhau chỉ gọi API
một lần, các lần chạy lại lấy từ cache, nên kết quả **tái lập được** và không tốn thêm quota.

### Bước 4. Kiểm tra tất cả

```powershell
python scripts/check_setup.py
```
Kết quả mong đợi (mọi dòng đều `OK`):
```
[OK ] Python >= 3.11     Python 3.11.9 (...)
[OK ] Thư viện           đủ thư viện
[OK ] Dữ liệu đã xử lý   đủ dữ liệu
[OK ] File .env          NEO4J_URI=có, NEO4J_USERNAME=có, NEO4J_PASSWORD=có
[OK ] Neo4j              kết nối OK, đang có 0 node KG
[OK ] LLM (gpt-oss-120b) cerebras: key CEREBRAS_API_KEY hợp lệ, model 'gpt-oss-120b' khả dụng | groq: …
```
Dòng LLM `OK` khi ÍT NHẤT một nhà cung cấp (Cerebras hoặc Groq) có key dùng được model chính.
Banner của PM4Py và cảnh báo `fitz ... deprecated` in ra trước là bình thường.

Chạy toàn bộ test:
```powershell
python -m unittest discover -s tests
```
Mong đợi: `OK`. (Nếu chưa có `GROQ_API_KEY` sẽ có đúng 1 lỗi `Missing API key` ở một test cũ — bình thường.)

---

## Phần B — Các thực nghiệm

> **Lịch sử (BPIC2017, đã gỡ 2026-11-21).** TN1–TN4 dưới đây là của bộ BPIC2017 + Directive; script của chúng đã gỡ
> khỏi code (còn trong git, commit `57757a4`). Thực nghiệm hiện tại: **Phần C** (lần chạy chính thức: mục C9).

### TN1. Dựng và xem tầng Pháp lý của Knowledge Graph

**Mục đích.** Bài báo cũ nhập tay RKG (21 node, 40 cạnh) và reviewer chê *"không mở rộng được"*.
TN1 cho thấy tầng Pháp lý có thể dựng **tự động, tất định** từ văn bản luật, kèm các quan hệ
mà cách NSAI đang làm không dùng tới: tham chiếu chéo (`REFERS_TO`), định nghĩa (`DEFINES`),
khái niệm được nhắc (`MENTIONS`). (Thực nghiệm NSAI cũ đưa thẳng đúng một khoản luật cho LLM — truy xuất
"oracle" — nên LLM không bao giờ thấy điều khoản được tham chiếu.)

**Chạy.**
```powershell
Measure-Command { python scripts/build_legal_graph.py | Out-Default }
python scripts/load_kg_to_neo4j.py data/processed/legal_graph.json --replace
```
Mong đợi:
```
Nodes: {'Article': 32, 'Paragraph': 71, 'LegalConcept': 14}
Edges: {'HAS_PARAGRAPH': 71, 'REFERS_TO': 157, 'DEFINES': 14, 'MENTIONS': 213}
...
TotalSeconds : ...    <- thời gian dựng đồ thị, ghi vào bảng bên dưới
```

**Xem kết quả trực quan.** Mở http://localhost:7474, dán từng câu vào ô lệnh trên cùng, bấm ▶.

① Tổng quan đồ thị:
```cypher
MATCH (n:KG)
RETURN [l IN labels(n) WHERE l <> 'KG'][0] AS loai_node, count(*) AS so_luong
ORDER BY so_luong DESC
```

② Điều 14 (quyền rút lui) và mọi thứ nó liên kết tới — **chọn tab Graph** để xem hình:
```cypher
MATCH p = (:Article {id:'Art14'})-[:HAS_PARAGRAPH]->(:Paragraph)-[:REFERS_TO|MENTIONS]->()
RETURN p
```
Bạn sẽ thấy `Art14(1)` nối tới `Art10` (thông tin hợp đồng): thời hạn "14 ngày" chỉ hiểu đúng
khi biết thời điểm khách nhận thông tin theo Điều 10.

③ Điều khoản "trung tâm" (được tham chiếu nhiều nhất):
```cypher
MATCH (target:KG)<-[:REFERS_TO]-(src)
RETURN target.id AS dieu_khoan, count(src) AS so_lan_duoc_tham_chieu
ORDER BY so_lan_duoc_tham_chieu DESC LIMIT 10
```

④ Khái niệm pháp lý được nhắc nhiều nhất:
```cypher
MATCH (c:LegalConcept)<-[:MENTIONS]-(p)
RETURN c.term AS khai_niem, count(p) AS so_khoan_nhac_toi
ORDER BY so_khoan_nhac_toi DESC
```

⑤ Ngữ cảnh mà Graph-RAG sẽ đưa cho LLM khi xử lý Điều 14(1):
```cypher
MATCH (p:Paragraph {id:'Art14(1)'})
OPTIONAL MATCH (p)-[:REFERS_TO]->(ref)
OPTIONAL MATCH (ref)-[:HAS_PARAGRAPH]->(refPara)
OPTIONAL MATCH (p)-[:MENTIONS]->(c:LegalConcept)
RETURN p.text AS khoan_goc,
       collect(DISTINCT coalesce(refPara.id, ref.id)) AS khoan_duoc_tham_chieu,
       collect(DISTINCT c.term + ': ' + c.definition) AS dinh_nghia
```

**Ghi số liệu** (dùng cho bài báo):

| Chỉ số | RKG nhập tay (bài cũ) | KG tự động (TN1) |
|---|---|---|
| Số node | 21 | |
| Số cạnh | 40 | |
| Số loại quan hệ | 4 | |
| Thời gian dựng | thủ công | ___ giây |
| Top-3 điều khoản trung tâm (truy vấn ③) | — | |

**Hiểu ý nghĩa.**
- Truy vấn ③ chỉ ra các điều khoản là **điều kiện của điều khoản khác**. Nếu chỉ đưa cho LLM đúng một khoản
  (như NSAI cũ), LLM không thấy chúng. Đây là động cơ thêm ngữ cảnh từ graph (cấu hình Y, TN6) và
  soạn bộ đề Tier 4 để đo riêng tình huống này (TN2).
- Truy vấn ⑤ chính là **gói ngữ cảnh** mà M5 sẽ dựng tự động — bạn đang nhìn thứ LLM sẽ được đọc.
- Tầng này **chưa** có activity của log: nối luật ↔ log là việc của M4 (TN5).

> Chạy xong, gửi mình bảng số liệu (không gửi .env) để cùng phân tích rồi chuyển sang TN2.

---

### TN2. Chuẩn bị bộ đề đánh giá

**Mục đích.** Bộ đề (30 rule + Tier 4) chỉ dùng ở bước đánh giá cuối, nhưng phải **đúng luật**,
**không lộ đáp án** cho hệ thống, và được **khoá trước** khi code các cấu hình X/Y — giống đề thi phải
in xong trước khi vào phòng thi. TN2 gồm 4 bước; hiện làm được bước 1–2.

| Bước | Nội dung | Trạng thái |
|---|---|---|
| 1 | Chống rò rỉ đáp án vào đầu vào | ✅ đã sửa code + có test |
| 2 | Rà gold toàn bộ 30 rule (phiếu sinh tự động) | 🔄 chờ bạn gán nhãn |
| 3 | Soạn câu mới: rà lại toàn bộ Directive + ứng viên Tier 4 (phiếu sinh từ graph) | 🔄 chờ gán nhãn |
| 4 | Chia dev/test cho Tier 4, khoá toàn bộ đề bằng hash | ⏳ |

#### Bước 1 — Kiểm chứng: hệ thống không đọc được đáp án

Trước đây, nếu thiếu văn bản luật của một rule, code **âm thầm lấy mô tả của đáp án làm đầu vào cho LLM**.
Đã sửa: giờ báo lỗi. Bạn tự kiểm chứng:

```powershell
python -m unittest tests.test_benchmark_no_gold_leak -v
```
Mong đợi 3 dòng `... ok`:
- `test_missing_clause_raises_instead_of_using_gold_description` — xoá thử văn bản Điều 14(1) thì phải báo lỗi.
- `test_no_rule_input_equals_its_gold_description` — không rule nào có đầu vào trùng mô tả đáp án.
- `test_every_rule_gets_a_clause` — đủ 30 rule đều có văn bản luật.

Muốn **thấy tận mắt** đầu vào mà LLM nhận cho một rule (VD R15):
```powershell
python -c "import sys, json; sys.stdout.reconfigure(encoding='utf-8'); from src.evaluation.benchmark_builder import build_normative_rule_benchmark as b; c={x['article_id']:x for x in json.load(open('data/processed/directive_chunks.json',encoding='utf-8'))}; r=[x for x in b(c) if x['rule_id']=='R15'][0]; print('DAU VAO LLM:', r['retrieved_chunk']['text'][:300]); print('DAP AN (LLM khong thay):', r['description'])"
```

#### Bước 2 — Rà gold

> **Ghi chú 2026-11-10:** các phiếu BPIC2017 (`GOLD_REVIEW*.md`, `ITEM_CANDIDATES.md`) và hướng dẫn
> `HUONG_DAN_GAN_NHAN.md` đã được xoá khỏi `docs/` (bộ BPIC2017 đã gán nhãn xong và đang tắt; nhãn + gold vẫn còn
> trong `data/review/`). Phiếu sinh lại được bằng các lệnh dưới đây; hướng dẫn gán nhãn hiện dùng là
> `HUONG_DAN_GAN_NHAN_CAP.md` (cho bộ CAP).

Sinh phiếu gán nhãn (nguyên văn luật được chép **tự động** từ dữ liệu, không chép tay):
```powershell
python scripts/export_gold_review.py
```
Mong đợi:
```
Đã ghi docs\GOLD_REVIEW.md (30 rule)
- Đánh giá: ✅ hợp lý: **6**, ⚠ cần xem: **10**, ❌ gold không khớp luật: **14**
```
Mở `docs/GOLD_REVIEW.md` (trong VS Code bấm `Ctrl+Shift+V` để xem dạng đẹp). Mỗi rule có: nguyên văn luật,
gold đang ghi, nhận xét sơ bộ của trợ lý, đề xuất. Điền **Bảng quyết định** ở đầu file
(GIỮ / SỬA / BẪY / LOẠI). Với R20, R21: mở bản chính thức Directive 2008/48/EC trên EUR-Lex,
đối chiếu Phụ lục I Phần II điểm (d) và (g).

> Phiếu được sinh lại mỗi lần chạy script — **điền quyết định xong thì lưu một bản sao**
> (VD `docs/GOLD_REVIEW_quyetdinh.md`) để không bị ghi đè.

Có thể xem dữ liệu log để tự đánh giá, VD R22 nói về "thấu chi" — log có activity nào liên quan không:
```powershell
python -c "import json; s=json.load(open('data/processed/process_schema.json',encoding='utf-8')); print('\n'.join(s['valid_activities']))"
```

**Người gán nhãn thứ hai (độc lập).** Sinh phiếu **không có** nhận xét của trợ lý, để người kia không bị dẫn dắt:
```powershell
python scripts/export_gold_review.py --blind
```
Gửi cho họ đúng 2 file: `docs/GOLD_REVIEW_BLIND.md` và `docs/HUONG_DAN_GAN_NHAN.md`.
**Không** gửi `GOLD_REVIEW.md` hay `data/review/gold_review_notes.json` (chứa ý kiến của trợ lý).
Bản thân bạn cũng nên đọc `HUONG_DAN_GAN_NHAN.md` để hai người dùng chung một tiêu chí.

> Gửi mình Bảng quyết định đã điền (của bạn, và của người thứ hai nếu có) — mình sẽ tính độ đồng thuận
> và liệt kê các rule hai người lệch nhau để cùng thảo luận.

**Kết quả bước 2 (đã làm).** Nhãn của người gán độc lập được lưu nguyên văn ở
`data/review/labels_annotator_B.txt`; áp 3 điều chỉnh đã thống nhất (A1 gộp câu trùng, A2 `O_Sent` gồm cả hai
kênh, A3 câu bẫy xét chính ràng buộc trong gold):
```powershell
python scripts/adjudicate_gold.py
```
Chi tiết từng rule ở `data/review/gold_adjudicated.json` (nhãn gốc giữ ở trường `annotator`, điều chỉnh ở
`adjustments`).

**Cập nhật sau phiếu Phần B** (`data/review/labels_annotator_B_partB.txt`, 61 khoản; script tự đọc). Thêm 3 điều chỉnh:
- **A4 – tự mâu thuẫn:** R12 / Điều 5(6): Phần A "kiểm tra được" (TB), Phần B "không" (Cao) → lấy Phần B, R12 thành câu bẫy.
- **A5 – con số không có trong luật:** bỏ 3 ràng buộc "> 0" ở Điều 5(1) (cùng quy tắc mục 7 người gán đã áp ở R17).
- **A6 – khoản mới:** Điều 8(2) chỉ áp dụng khi tăng hạn mức → `| A.case:ApplicationType == "Limit raise"`.

Mong đợi: `{'positive': 3, 'trap': 18}`, loại bỏ R13, R14, R20, R21; câu thường P01 Điều 5(1), P02 Điều 8(1),
P03 Điều 8(2). Không có mâu thuẫn nào khác: 9 khoản còn lại mà cả hai phần cùng hỏi đều khớp.

#### Bước 3 — Soạn câu mới (rà lại Directive + Tier 4)

Bộ đề chỉ còn 3 câu có ràng buộc đúng, nên cần soạn thêm. Phiếu được sinh từ đồ thị pháp lý (TN1):
mọi khoản có *shall/must* ngoài Điều 1–3, khoản có tham chiếu chéo xếp đầu, kèm nguyên văn khoản được tham chiếu.
```powershell
python scripts/export_item_candidates.py
```
Mong đợi: `61 khoản nghĩa vụ: {'cross': 13, 'intra': 9, 'none': 39}, có con số: 6`.

Gửi cho người gán nhãn: `docs/ITEM_CANDIDATES.md` + `docs/HUONG_DAN_GAN_NHAN.md` (đọc **Phần B**).
Khoản trả lời "Cần điều tham chiếu: Có / Một phần" sẽ thành câu **Tier 4**. Mình sẽ cập nhật bộ đề theo đúng quyết định của bạn (có test), rồi sang bước 3.

---

### TN3. Dựng tầng Tiến trình của Knowledge Graph (tầng "thay UML")

**Mục đích.** Bài OVAS cần một sơ đồ UML do người vẽ để biết "hệ thống có những gì" khi kiểm tra ràng buộc.
Ở đây, thứ đó được **khai phá tự động từ log**: activity nào tồn tại, thuộc tính nào tồn tại, activity nào
thực sự mang thuộc tính nào, bước nào thường nối tiếp bước nào. Tầng này là "mô hình" mà Tầng 2 (MDE)
sẽ kiểm tra ràng buộc dựa vào, và là đích để nối luật ↔ log ở TN5.

Mức **lược đồ**: không nạp từng event (1,2 triệu) — việc kiểm tra tuân thủ chạy thẳng trên log.

**Chạy.**
```powershell
Measure-Command { python scripts/build_process_graph.py | Out-Default }
python scripts/load_kg_to_neo4j.py data/processed/process_graph.json --replace
```
Mong đợi:
```
Log: 1202267 event, 31509 hồ sơ
Nodes: {'Activity': 26, 'Attribute': 10}
Edges: {'DIRECTLY_FOLLOWS': 178, 'HAS_ATTRIBUTE': 7}
```
`--replace` chỉ xoá node `Activity`/`Attribute` cũ — tầng Pháp lý (TN1) giữ nguyên.

**Xem kết quả trực quan** (http://localhost:7474).

① Hai tầng đã có trong cùng một đồ thị:
```cypher
MATCH (n:KG)
RETURN [l IN labels(n) WHERE l <> 'KG'][0] AS loai_node, count(*) AS so_luong
ORDER BY so_luong DESC
```

② **Bản đồ quy trình** (chỉ các chuyển tiếp ≥ 5 000 lần cho dễ nhìn) — chọn tab **Graph**:
```cypher
MATCH p = (:Activity)-[r:DIRECTLY_FOLLOWS]->(:Activity)
WHERE r.count >= 5000
RETURN p
```
Thử hạ ngưỡng xuống 1000 để thấy quy trình "rối" hơn thế nào.

③ Activity nào xuất hiện ở bao nhiêu % hồ sơ:
```cypher
MATCH (a:Activity)
RETURN a.name AS activity, a.origin AS nguon, a.case_count AS so_ho_so, a.case_ratio AS ti_le
ORDER BY ti_le DESC
```

④ **Thuộc tính nào nằm ở activity nào** — đây là thông tin UML cung cấp trong OVAS:
```cypher
MATCH (a:Activity)-[r:HAS_ATTRIBUTE]->(t:Attribute)
RETURN a.name AS activity, t.name AS thuoc_tinh, t.type AS kieu, t.min AS min, t.max AS max,
       r.non_null_ratio AS ti_le_co_gia_tri
```

⑤ Thuộc tính mức hồ sơ và miền giá trị:
```cypher
MATCH (t:Attribute {level:'case'})
RETURN t.name, t.type, t.min, t.max, t.values
```

**Ghi số liệu:**

| Chỉ số | Giá trị |
|---|---|
| Số node Activity / Attribute | |
| Số cạnh DIRECTLY_FOLLOWS / HAS_ATTRIBUTE | |
| Thời gian dựng (giây) | |
| Activity mang toàn bộ thuộc tính của đề nghị vay (truy vấn ④) | |
| Khoảng giá trị `OfferedAmount` (min – max) | |
| Khoảng giá trị `case:RequestedAmount` (min – max) | |

**Hiểu ý nghĩa — đối chiếu với phiếu gold (TN2).** Các con số ở trên là *bằng chứng dữ liệu* khi gán nhãn:
- Nếu `OfferedAmount` luôn nằm trong [5 000; 75 000] thì ràng buộc "OfferedAmount ≥ 200" hay "≤ 75 000"
  **không bao giờ bị vi phạm** — nó không phân biệt được hồ sơ tuân thủ với hồ sơ vi phạm.
- `case:RequestedAmount` có thể > 75 000: đó là những hồ sơ **nằm ngoài phạm vi** Directive (Điều 2(2)(c)) —
  đúng vai trò "bộ lọc phạm vi", không phải "vi phạm".
- Thuộc tính của đề nghị vay chỉ có ở một activity: ràng buộc gắn `CreditScore` vào activity khác sẽ bị
  Tầng 2 bắt lỗi khi Tầng 2 đọc từ KG (bước tiếp theo).
- Truy vấn ⑤ cho thấy giá trị `case:LoanGoal` có trong log — so với bẫy R25 (`Mortgage_RealEstate`).

> Lưu ý cho người gán nhãn thứ hai: các số liệu này là **dữ kiện**, không phải ý kiến — có thể chia sẻ.

---

### TN4. Kiểm định engine DECLARE so với chuẩn

**Mục đích.** Mọi kết luận "tuân thủ / vi phạm" của hệ thống đều do engine DECLARE tự viết của NSAI
(`src/symbolic/declare4py_verifier.py`) đưa ra. Nếu engine hiểu sai một template thì mọi số liệu dựa trên nó
đều sai — dù LLM viết ràng buộc đúng. TN4 kiểm tra engine **trước** khi dùng nó để chấm.

**Cách kiểm tra — vét cạn phạm vi nhỏ.** Sinh **mọi** hồ sơ độ dài 1–4 trên 3 activity {A, B, C}
(120 hồ sơ), chạy cả 17 template trên engine NSAI và trên chuẩn, đếm số hồ sơ hai bên kết luận khác nhau.
Chuẩn = thư viện **pm4py 2.7** cho 13 template; **định nghĩa LTLf viết tường minh** cho 4 template
(Choice, Exclusive Choice — pm4py không có; Not Response, Not Precedence — xem lưu ý bên dưới).

**Chạy.**
```powershell
python scripts/validate_declare_engine.py
python -m unittest tests.test_declare_engine_validation -v
```
**Kết quả lần đầu (engine gốc của NSAI)** — ghi lại để đưa vào bài:
```
Template                  Khớp  Lệch  Gắn sai vacuity*
Choice(A,B)                116     4                 4   C: engine=thoả, chuẩn=vi phạm
Exclusive Choice(A,B)      116     4                 4
Precedence(A,B)            120     0                30   (mọi template 2 activity: 30)
Not Precedence(A,B)         74    46                30   A|A|A|B: engine=thoả, chuẩn=vi phạm
Template lệch chuẩn: ['Choice', 'Exclusive Choice', 'Not Precedence']   (14/17 khớp)
```
**Sau khi sửa engine** (có test `tests/test_declare_engine_semantics.py`), mong đợi khi bạn chạy lại:
```
Template                  Khớp  Lệch  Gắn sai vacuity*
Existence(A)               120     0                 0
...                        (cả 17 dòng: Khớp 120, Lệch 0, Gắn sai 0)
Template lệch chuẩn: không có
```
Kết quả đầy đủ ở `results/tn4_engine_validation.json`.

**Kiểm tra trên log thật** (3 câu thường của bộ đề, engine đã sửa — hỗ trợ nhóm activity `{X | Y}`):

| Ràng buộc | Vi phạm | Thoả | Không kích hoạt |
|---|---|---|---|
| Precedence(O_Sent (mail and online) → O_Accepted) — một kênh | 190 (báo oan) | 17 038 | 14 281 |
| Precedence({O_Sent (mail and online) \| O_Sent (online only)} → O_Accepted) | 0 | 17 228 | 14 281 |
| Precedence(W_Call after offers → O_Accepted) | 0 | 17 228 | 14 281 |
| Precedence(W_Validate application → O_Accepted) | 0 | 17 228 | 14 281 |

(Nạp log đầy đủ vào engine mất ~2 phút; kiểm tra 4 ràng buộc ~2 giây.)

**Ghi số liệu:**

| Chỉ số | Giá trị |
|---|---|
| Số template khớp chuẩn — engine gốc / sau khi sửa | 14 / 17 → ___ / 17 |
| Template lệch ở engine gốc (tên, số hồ sơ lệch) | Choice 4, Exclusive Choice 4, Not Precedence 46 |
| Hồ sơ không kích hoạt bị gắn "Violated" — engine gốc / sau khi sửa | 30 mỗi template → ___ |

**Hiểu ý nghĩa.**
- **Not Precedence bị đảo chiều.** `Not Precedence(A,B)` nghĩa là "B không được có A đứng trước". Engine lại
  kiểm tra "A không được có B đứng trước". Trong khi đó phần dịch ngược của Tầng 3 (`verbalizer_roundtrip.py`)
  mô tả **đúng** nghĩa chuẩn → trọng tài đọc một nghĩa, engine kiểm tra nghĩa ngược lại.
- **Choice / Exclusive Choice.** Hồ sơ không có cả A lẫn B (VD chỉ có C) phải **vi phạm** "phải có A hoặc B",
  nhưng engine coi là "không kích hoạt → thoả". Trong pipeline (`run_layer3_declare4py_verifier`), các hồ sơ này
  bị xếp vào "vacuous" nên **không bao giờ được đếm là vi phạm**.
- **Gắn sai vacuity.** Ở chế độ mặc định (`consider_vacuity=False`), hồ sơ không kích hoạt bị gắn "Violated"
  (chuẩn: thoả). Pipeline hiện tại tránh được vì kiểm tra số lần kích hoạt trước, nhưng code mới nào đọc
  trường `state` (VD TN7) sẽ đếm sai.
- **Lưu ý về chính thư viện chuẩn:** `nonsuccession` của pm4py 2.7 chỉ báo vi phạm khi *mọi* B đứng sau *mọi* A
  (coi `B|A|B` là thoả), lệch định nghĩa LTLf. Vì vậy TN4 dùng định nghĩa tường minh cho Not Response /
  Not Precedence. Bài học: kiểm định cần **hai nguồn độc lập**, không tin tuyệt đối một thư viện.
- **Chưa kiểm:** điều kiện dữ liệu (VD `OfferedAmount > 5000`) và thời hạn (VD ≤ 14 ngày) — pm4py không hỗ trợ.
  Ngoài ra engine **lan truyền** thuộc tính đề nghị vay sang mọi event của hồ sơ (`ffill().bfill()`), nên một event
  có thể "mượn" giá trị của một đề nghị **xảy ra sau nó** — cần xem lại khi có ràng buộc gắn điều kiện dữ liệu.

---

## Phần C — Bộ dữ liệu thứ hai: BPIC2018 + 4 Quy định CAP

Lý do: trên BPIC2017 không có câu Tier 4 nào quan sát được (log dừng ở bước ký hợp đồng). Bộ CAP có
**234 dẫn chiếu chéo giữa các văn bản** — đúng chỗ Graph-RAG cần chứng minh. Bộ BPIC2017 vẫn giữ nguyên.

Dữ liệu gốc để ngoài repo, trong `~/Downloads`: file XES (1,9 GB) và 4 PDF EUR-Lex
`CELEX_32013R1306_EN_TXT.pdf`, `CELEX_32013R1307_EN_TXT.pdf`, `CELEX_32014R0640_EN_TXT.pdf`, `CELEX_32014R0809_EN_TXT.pdf`.

### C1. Chuyển log XES → parquet (một lần, ~5 phút)
```powershell
python scripts/convert_bpic2018.py
```
Mong đợi: `data/interim/bpic2018_events.parquet` và `bpic2018_cases.parquet` (61 cột). Cột hồ sơ không khai báo
trong `<global>` của XES (VD `amount_applied1`) vẫn được giữ.

### C2. Tách 4 Quy định thành khoản + nhận diện dẫn chiếu
```powershell
python scripts/parse_cap_regulations.py
```
Mong đợi: `data/processed/cap_chunks.json`, **966 khoản** (R1306 329 · R1307 308 · R640 110 · R809 219), và
`data/processed/cap_annexes.json`, **15 Phụ lục** (R1306 I–III, R1307 I–XI, R809 Annex).
Dẫn chiếu (sau kiểm toán đợt 2, `src/preprocessing/eu_references.py`): danh sách và khoảng được mở rộng hết
("Articles 43 to 46" → 43, 44, 45, 46), "paragraph N" → khoản cùng Điều, "Annex X" → Phụ lục — tổng **2 096**.

> Chạy lại bước này KHÔNG đổi phiếu gán nhãn (phiếu do `export_cap_candidates.py` sinh, **không chạy lại** khi
> phiếu đang được gán nhãn).

### C3. Dựng KG: tầng Pháp lý + tầng Tiến trình
```powershell
python scripts/build_cap_graphs.py               # cả hai tầng (tầng Tiến trình mất vài phút)
python scripts/build_cap_graphs.py --legal-only  # chỉ tầng Pháp lý (sau khi tách lại luật)
```
Mong đợi:
- Tầng Pháp lý: Article 557, Paragraph 868, **Annex 28** (15 Phụ lục đã tách + 13 Phụ lục được nhắc nhưng ngoài
  bộ / không có); REFERS_TO **2 419** = trong cùng văn bản 1 838 · sang văn bản ngoài bộ 303 ·
  **sang văn bản khác trong bộ 278**.
- Tầng Tiến trình: **170 activity** (tên = `loại giấy tờ / tiến trình con / hành động`), 62 thuộc tính
  (60 mức hồ sơ, 2 mức event), DIRECTLY_FOLLOWS 3 639.

### C3b. Dựng môi trường kiểu Γ (Tầng 2 của MDE) từ tầng Tiến trình của KG
```powershell
python scripts/build_gamma_from_kg.py
```
Đây là chỗ "KG thay vai trò UML" thành code: Γ, thứ Tầng 2 dùng để chặn activity/thuộc tính bịa và sai kiểu,
được lấy thẳng từ KG thay vì từ `process_schema.json` (script riêng cho BPIC2017, **không bị ghi đè**).
Mong đợi:
```
BPIC2017: ghi data\processed\gamma_bpic2017.json — 26 activity, 3 thuộc tính hồ sơ, 8 thuộc tính event, 3 nhóm origin
  activity: cũ 26, KG 26, chung 26
  thuộc tính chỉ có ở Γ cũ (KG coi là cột kỹ thuật): ['Action', 'EventID', 'EventOrigin', 'OfferID',
    'case:concept:name', 'concept:name', 'lifecycle:transition', 'org:resource']
  thuộc tính khác kiểu: —
BPIC2018: ghi data\processed\gamma_bpic2018.json — 170 activity, 60 thuộc tính hồ sơ, 3 thuộc tính event, 8 nhóm origin
```
Kiểm chứng: `python -m unittest tests.test_schema_from_kg -v` (9 test, gồm 3 test so Γ từ KG với Γ cũ trên BPIC2017).

### C3c. Engine DECLARE cho BPIC2018: bảng hồ sơ, điều kiện `and`, ngày lịch theo giờ Đức
Ba mở rộng, làm **đồng bộ** ở metamodel (AST, Tầng 1), Γ (Tầng 2) và engine (Tầng 3):

| Mở rộng | Cú pháp `.decl` | AST / Γ |
|---|---|---|
| Bảng hồ sơ riêng | `Declare4Py(events, cases=cases, timezone="Europe/Berlin")` — thuộc tính `case:` lưu 1 lần / hồ sơ | — |
| Tên có dấu cách, nối `and` | `A.case:young farmer == True and A.case:area > 10` | trường `extra_conditions`; Γ kiểm từng điều kiện |
| Ngày lịch (giờ địa phương) | `A.date <= year-05-15`, `A.date <= year+1-06-30`, `A.date < 2016-01-01` | Tầng 1 kiểm dạng ngày; Γ đòi có `case:year` khi dùng `year` |

`year` = `case:year` của hồ sơ; thiếu năm → điều kiện **không** thoả. Không truyền `cases` / `timezone`
thì engine chạy y như cũ (BPIC2017).

**Kiểm chứng bằng test** (42 test mới; cả bộ 230 test):
```powershell
python -m unittest tests.test_data_conditions tests.test_declare4py_cases tests.test_metamodel_cap_extensions -v
python -m unittest discover -s tests
```
Test biên quan trọng: event lúc 00:30 ngày 16/5 giờ Đức (= 22:30 ngày 15/5 UTC) **vi phạm** hạn 15/5 khi
`timezone="Europe/Berlin"`, nhưng "kịp hạn" nếu tính theo UTC.

**BPIC2017 không đổi:** 12 dạng điều kiện (5 dạng đang có trong bộ đề + 7 dạng khác) chạy trên toàn bộ
1 202 267 event bằng bản cũ và bản mới của engine: **0 event cho kết quả khác**.

**Chạy trên BPIC2018 thật** (máy mình: nạp ~3 phút mỗi múi giờ, tổng ~6 phút):
```powershell
python scripts/check_bpic2018_engine.py
```
> Ràng buộc trong script là **ví dụ để kiểm engine** (hạn 15/5 theo R809 Art13(1), cửa sổ chi trả
> 1/12–30/6 theo R1306 Art75(1), activity là proxy) — **không phải gold**, không đưa vào bảng kết quả.
> Script ghép tên activity bằng `with_composite_activity` (giống Γ và KG). **Mọi lần chạy engine trên
> BPIC2018 đều phải ghép tên như vậy**: parquet chỉ có tên ngắn (`mail income`, 41 tên), không ghép thì
> mọi ràng buộc 0 kích hoạt (lần chạy đầu của mình bị đúng lỗi này, script giờ dừng nếu tên không có trong log).

Kết quả lần chạy trước của mình (để bạn so sánh; số hồ sơ, tổng 43 809):
```
                                                         UTC                 Europe/Berlin
                                                   vi phạm   thoả        vi phạm   thoả
Absence[mail income] | date > year-05-15              4305  39504           4626  39183
Absence[begin payment] | date < year-12-01               0  43809              0  43809
Absence[begin payment] | date > year+1-06-30             1  43808              1  43808
Response[mail income, begin payment] | young farmer      2   3552 (40255 không kích hoạt, cả hai múi giờ)
Absence[mail income] | young farmer and date > 15/5    490  43319            522  43287
```
(`mail income`, `begin payment` = `Payment application / Application / …`.) Chênh 321 hồ sơ ở dòng đầu là do
nhiều event được ghi lúc 00:00 giờ Đức: tính theo UTC thì lùi về ngày hôm trước. Đây là lý do phải tính theo giờ Đức.
Kết quả đầy đủ: `results/bpic2018_engine_check.json`.

### C3d. Prompt cho bộ CAP (hồ sơ miền)
Chữ của prompt sinh ràng buộc và prompt trọng tài Tầng 3.1 nằm trong `src/symbolic/domain_profiles.py`:

| | `BPIC2017_PROFILE` (mặc định) | `CAP_PROFILE` |
|---|---|---|
| Luật | Directive 2008/48/EC | 4 Quy định CAP (1306/2013, 1307/2013, 640/2014, 809/2014) |
| Trường JSON | như cũ | thêm `extra_conditions`, thuộc tính giả `date` (`year-MM-DD`, `year+1-MM-DD`, `YYYY-MM-DD`) |
| Danh sách thuộc tính | chỉ tên | tên + kiểu Γ, VD `case:young farmer (Boolean)` |
| Ví dụ few-shot | 2 ví dụ ngân hàng giả định (như cũ) | 2 ví dụ **thư viện giả định** (hạn 31/1; sinh viên dưới 18 tuổi), không trùng phiếu CAP |
| Trọng tài: BASELESS khi | giao dịch bị loại khỏi phạm vi / con số không có trong luật / trái luật | khoản không có nghĩa vụ quan sát được (định nghĩa, quyền của Ủy ban, báo cáo của Nhà nước) / con số **hoặc ngày** không có trong luật / trái luật |

Gọi: `run_single_rule_with_real_llm(..., profile=CAP_PROFILE)` và Γ = `data/processed/gamma_bpic2018.json`.
Không truyền `profile` thì prompt BPIC2017 **giữ nguyên từng byte** — test so với ảnh chụp prompt trước khi tách
profile (`tests/fixtures/bpic2017_prompts_snapshot.json`).

Generic Entity Matcher (Tầng 3.1, không cần LLM) mở rộng cho CAP: nhận đơn vị `hectare(s)` / `ha`; giá trị
`date` phải có ngày tương ứng trong khoản ("15 May", "May 15", "1st December"); giá trị số trong
`extra_conditions` cũng phải có trong khoản. Không khoản nào của Directive 2008/48/EC có đơn vị `ha` nên BPIC2017
không đổi.

Kiểm chứng:
```powershell
python -m unittest tests.test_domain_profiles tests.test_entity_matcher_cap -v
```
> Lưu ý về cache LLM: `real_llm_cache.json` và `results/real_llm_cache_120b.json` (ngày 21/10) **không trúng**
> với prompt BPIC2017 hiện tại (phát lại offline 30 quy tắc: 0 lượt trúng, kể cả lời gọi sinh đầu tiên — phần
> prompt này không đổi trong đợt sửa CAP). Mình chưa xác định chính xác thay đổi nào sau 21/10 gây ra việc này.
> Lần chạy TN5/TN6 chính thức của bạn sẽ gọi API mới; nên dùng `--cache-file` mới để không lẫn với cache cũ.

### C4. Phiếu gán nhãn Phần B cho CAP
```powershell
python scripts/export_cap_candidates.py
```
Mong đợi:
```
Đợt 1: 158 {'R1306': 8, 'R1307': 25, 'R640': 50, 'R809': 75}
Đợt 2: 60 {'R1306': 24, 'R1307': 21, 'R640': 4, 'R809': 11} (seed=2018)
Dẫn chiếu trong bộ không tìm được nguyên văn: 0
```
(Sinh lại 2026-11-09 sau khi sửa nhận diện dẫn chiếu + thêm Phụ lục, TRƯỚC khi gán nhãn; bản cũ 212 khoản không còn dùng.)
Chia đợt cho AI: `python scripts/split_cap_sheet.py` → `docs/cap_batches/` (23 đợt). Đối chiếu nhãn các AI:
`python scripts/compare_cap_labels.py --labels …` (hướng dẫn gán nhãn mục 10.5).

- **Đợt 1** = mọi khoản có dẫn chiếu sang Quy định khác trong bộ (ứng viên Tier 4).
- **Đợt 2** = mẫu ngẫu nhiên phân tầng theo văn bản từ 808 khoản còn lại, seed cố định (cùng seed → cùng mẫu).
- **Không lọc trước** theo phạm vi hay *shall/must*: người gán nhãn quyết định.

Gán nhãn: `docs/HUONG_DAN_GAN_NHAN_CAP.md` là tài liệu **tự đủ** (không cần hướng dẫn nào khác), kèm
`docs/CAP_VOCABULARY.md` và phiếu `docs/CAP_ITEM_CANDIDATES.md`. Gán bằng nhiều AI rồi người kiểm phần khác nhau:
quy trình ở **mục 10** của hướng dẫn.
Bản máy đọc: `data/review/cap_item_candidates.json` (có trường `round` và nguyên văn khoản được dẫn chiếu).

### C5. Gold CAP từ phiếu nhãn (bạn duyệt)
Khi nhận được `CAP_ITEM_CANDIDATES_<tên>.txt` (có thể chỉ Đợt 1 trước; dòng còn `___` = chưa chấm):
```powershell
python scripts/build_cap_gold.py --labels CAP_ITEM_CANDIDATES_<tên>.txt
```
- Ghi `data/review/cap_gold_candidates.json` và **`docs/CAP_GOLD_REVIEW.md`** — mở file .md, đọc cột *Gold (AST)*:
  đó là cách máy hiểu ký hiệu của người gán. Sai ý → sửa file .txt, chạy lại.
- Phân loại: *Có ràng buộc* (chấm EQ) · *Bẫy* (Quan sát được = Không → đáp án BASELESS) · *Không chắc* (không chấm)
  · *LỖI* (ký hiệu không chuyển được — VD tên activity sai chính tả, "≤ 1 tháng": máy **không đoán**, phải sửa phiếu).
- *Cảnh báo số/ngày*: con số hay ngày trong ràng buộc không có trong khoản luật (và khoản được dẫn chiếu nếu Tier 4) —
  quy tắc mục 7. Máy **không tự bỏ**; bạn quyết.
- Khi hết LỖI: `python scripts/build_cap_gold.py --labels … --approve "<tên bạn>"` → `data/review/cap_gold_approved.json`.

### C6. TN5–TN8 trên CAP: sinh → chấm → phán quyết từng hồ sơ → báo cáo
**Bước sinh không đọc gold** (chạy được trước khi có nhãn; test `test_generation_never_reads_gold` kiểm điều này).
Mỗi khoản ~1 phút (chủ yếu chờ giới hạn tốc độ Groq) → 218 khoản ≈ 3,5–4 giờ / cấu hình. Ngắt giữa chừng thì chạy lại
cùng lệnh: khoản đã xong được bỏ qua.
```powershell
python scripts/run_cap_generation.py --config Y --limit 3        # thử nhanh 3 khoản
python scripts/run_cap_generation.py --config Y                   # cấu hình chính (Graph-RAG)
python scripts/run_cap_generation.py --config X                   # đường cơ sở: chỉ khoản luật (= "tắt graph")
python scripts/run_cap_generation.py --config Y-noL3              # TN8: tắt Tầng 3
python scripts/run_cap_generation.py --config Y-noL12             # TN8: tắt Tầng 1–2 tự sửa
python scripts/run_cap_generation.py --config Y-retry1            # TN8: không tự sửa
python scripts/score_cap.py                                       # TN5, TN6 (McNemar), TN8
python scripts/run_cap_conformance.py                             # TN7, ~3 phút nạp log
python scripts/build_cap_report.py                                # → results/cap/report.html
```
TN8 thêm 3 cấu hình (chạy cùng cách): `--config Y-noVac`, `--config Y-noDomain`, `--config Y-noDuty`.
Mỗi lần chạy cấu hình có kiểm B (mọi cấu hình trừ Y-noVac) nạp log trước ~30 giây (trước 2026-11-20: ~2,5 phút;
đã tối ưu bước lập chỉ mục engine, kết quả giống hệt — so trên toàn log, `tests/test_engine_index_fast_path.py`).

| Cấu hình | Ngữ cảnh đưa LLM | Khác |
|---|---|---|
| X | chỉ khoản luật | — |
| Y | khoản luật + khoản được dẫn chiếu (cạnh REFERS_TO 1 bước trên đồ thị luật; Điều → ghép các khoản) | — |
| Y-noL12 / Y-noL3 / Y-retry1 | như Y | tắt Tầng 1–2 / tắt Tầng 3 / 1 vòng |
| Y-noVac / Y-noDomain / Y-noDuty | như Y | tắt B / tắt C + E / tắt D (prompt CAP cũ) |

**Các kiểm chống ràng buộc rỗng / bịa** (thêm 2026-11-09, sau ca R1306:Art70(2) sinh `case:year == 2018`
trong khi log chỉ có 2015–2017 và nghĩa vụ là của Nhà nước). Thứ tự mỗi vòng, lỗi → phản hồi cho LLM:

| Kiểm | Ở đâu | Bắt gì |
|---|---|---|
| **D** phân tích nghĩa vụ | prompt CAP + `src/symbolic/obligation_gate.py` | LLM điền `duty_bearer` / `observable_in_log` / dẫn chứng trước; được trả `no_constraint` (→ BASELESS). Nói "Nhà nước / Ủy ban" mà vẫn trả ràng buộc → yêu cầu xem lại (1 lần) |
| Tầng 1–2 + **C** | `typing_environment.check_value_domain` | Giá trị không bao giờ có trên log (`== '2018'`; `area > max`). Miền giá trị lấy từ KG |
| **B** kiểm rỗng | `src/symbolic/log_grounding.py` | 0 hồ sơ có sự kiện kích hoạt thoả điều kiện → phản hồi **1 lần**; LLM giữ nguyên → chấp nhận, gắn cờ `grounding.vacuous` (ràng buộc đúng vẫn có thể rỗng) |
| Tầng 3 + **E** | Entity Matcher | Giá trị dạng năm phải có trong văn bản luật (chặn "sửa" 2018 → 2017) |

Phản hồi không bao giờ gợi ý giá trị thay thế. Không kiểm nào đọc gold. BPIC2017 không bị ảnh hưởng
(các kiểm mặc định tắt; prompt BPIC2017 vẫn giống từng byte — test `TestBPIC2017PromptsByteIdentical`).
Báo cáo có bảng "Các kiểm đã can thiệp bao nhiêu lần".

Sửa kèm: engine so `case:year == 2016` (chuỗi trong log, số trong dòng .decl) trước đây **luôn sai** — đã sửa
(`data_conditions._equal`); hồi quy BPIC2017 12 điều kiện × 1,2 triệu event: 0 khác biệt.

Cách chấm (`src/evaluation/cap_scoring.py`):
- Mỗi khoản ra một kết quả: RULE (AST) · BASELESS · FAILED (hết vòng).
- Khoản có ràng buộc: **đúng = EQ** — cùng mẫu, cùng activity, cùng *tập* điều kiện (kể cả ngày, `extra_conditions`),
  cùng thời hạn (quy về giây). Nhiều gold → lấy khớp tốt nhất. Còn lại phân lớp STRENGTHENED / WEAKENED / COND_DIFF /
  REVERSED / MISMATCH / MISSED_AS_BASELESS / FAILED.
- Khoản bẫy: **đúng = BASELESS**.
- Tỉ lệ kèm **khoảng tin cậy Wilson 95%**; X vs Y so cặp bằng **McNemar chính xác** (cùng khoản) — trên mọi khoản và
  riêng Tier 4. Số khoản nhỏ → khoảng tin cậy rộng; báo cáo đúng như vậy, đừng chỉ nêu % điểm.
- TN7: với mỗi khoản có ràng buộc, chạy gold và ràng buộc hệ thống sinh trên **43 809 hồ sơ** (giờ Europe/Berlin) →
  độ khớp, precision / recall của "vi phạm", **Cohen's kappa** (độ khớp cao có thể chỉ vì hầu hết hồ sơ không vi phạm —
  kappa trừ phần đó), và cờ RỖNG (không kích hoạt hồ sơ nào).

Gold chưa duyệt: `score_cap.py` / `run_cap_conformance.py` từ chối; thêm `--allow-candidate` chỉ để thử pipeline —
kết quả và báo cáo gắn nhãn **UNAPPROVED**.

> Lần chạy của bạn ghi vào `results/cap/` (thư mục được tạo ở lần chạy đầu).

**Mức chuẩn và tỉ lệ cân bằng (thêm 2026-11-16).** Gần như mọi khoản là bẫy, nên `score_cap.py` in thêm dòng
`[always-BASELESS]` (kết luận BASELESS cho mọi khoản, không đọc gì) và cột **Cân bằng** = trung bình(tỉ lệ đúng
khoản có ràng buộc, tỉ lệ đúng khoản bẫy); mức chuẩn đạt 50%. Báo cáo HTML có thẻ "Tỉ lệ cân bằng" và cặp
"Y vs luôn BASELESS". Trích số trong bài phải kèm mức chuẩn này.

### C6b. v1.2 — chạy lại các khoản bị ảnh hưởng bởi lỗi kỹ thuật đã sửa (2026-11-19)

Danh sách sửa: `docs/V2_DANG_KY_TRUOC.md` → "v1.2". Dữ liệu (khoản, đồ thị luật, phiếu) đã dựng lại; gold CAP không
đổi. Thư mục `results/cap_cerebras_v12/` = bản sao v1.1 đã **phát lại cache bằng code v1.2**: khoản có prompt
không đổi giữ nguyên kết quả (đã kiểm: 0 khoản ngoài nhóm ERROR đổi kết quả); khoản có prompt đổi (văn bản khoản
hoặc ngữ cảnh dẫn chiếu đổi) bị đánh **ERROR (cache miss)** và cần gọi LLM lại:

| Cấu hình | X | Y | Y-noL12 | Y-noL3 | Y-retry1 | Y-noVac | Y-noDomain | Y-noDuty |
|---|---|---|---|---|---|---|---|---|
| Khoản ERROR (cần chạy lại) | 11 | 54 | 54 | 54 | 54 | 54 | 55 | 58 |

(X: chỉ 11 khoản đổi nguyên văn; Y-*: thêm các khoản có khoản được dẫn chiếu đổi văn bản / dẫn chiếu. Trong nhóm
ERROR của Y có 2 khoản positive.) Lệnh **không có `--force`** chỉ chạy các khoản ERROR:
```powershell
& C:\Users\hayab\.venvs\nsai-compliance\Scripts\Activate.ps1
$env:PYTHONIOENCODING = "utf-8"
foreach ($c in "X","Y","Y-noL12","Y-noL3","Y-retry1","Y-noVac","Y-noDomain","Y-noDuty") {
  python scripts/run_cap_generation.py --config $c --provider cerebras --model gpt-oss-120b --out-dir results/cap_cerebras_v12
}
python scripts/score_cap.py --pred-dir results/cap_cerebras_v12
python scripts/run_cap_conformance.py --pred-dir results/cap_cerebras_v12 --configs X Y Y-noL12 Y-noL3 Y-retry1 Y-noVac Y-noDomain Y-noDuty
python scripts/build_cap_report.py --dir results/cap_cerebras_v12
```
Ngắt giữa chừng → chạy lại cùng lệnh. Còn khoản ERROR sau khi chạy (lỗi mạng / giới hạn) → chạy lại lệnh của cấu hình
đó. Kiểm tra trước khi báo số: `score_cap.py` từ chối nếu còn ERROR (đừng thêm `--allow-errors`).
Gửi lại cho trợ lý: toàn bộ phần in ra của `score_cap.py` (để lập bảng v1 / v1.1 / v1.2 cạnh nhau).

### C6c. Metamodel, kiểm tập ràng buộc, proof trace, hiệu lực theo năm (2026-11-19, không gọi API)

Học từ Dang et al., ISDS 2026 (xem `docs/CONG_TRINH_LIEN_QUAN.md`, đăng ký bổ sung B2–B5 trong
`docs/V2_DANG_KY_TRUOC.md`). Mọi lệnh chạy vài giây đến vài phút, không đọc gold (trừ đếm theo loại ở lệnh 4).
```powershell
python scripts/check_kg_metamodel.py                         # 1. mọi đồ thị tuân thủ metamodel (src/kg/metamodel.py)
python scripts/export_verified_constraints.py --pred-dir results/cap_cerebras_v12 --config Y
                                                             # 2. luật đã kiểm → KG + kiểm TẬP ràng buộc (mâu thuẫn / kéo theo)
python scripts/build_proof_traces.py --pred-dir results/cap_cerebras_v12 --config Y
                                                             # 3. proof_traces_Y.html: khoản → ngữ cảnh → nghĩa vụ → các vòng → log
python scripts/check_cap_versions.py                         # 4. so khoản với bản hợp nhất có hiệu lực 15/5 mỗi năm (cần mạng lần đầu)
python scripts/verification_funnel.py --pred-dir results/cap_cerebras_v12
                                                             # 5. phễu kiểm chứng: mỗi lớp chặn bao nhiêu vòng, luật sai lọt qua
```
5. Trên v1.1 (tham khảo): Y 283 vòng, 68 vòng bị chặn (Tầng 1–2: 34, Tầng 3: 20, B: 7, D: 7); 0 luật cuối chưa qua
   kiểm; **luật sai lọt qua 16/207 khoản bẫy** (Y-noL3: 50/207 — tác dụng của Tầng 3). Bảng ghi ra
   `verification_funnel.md`, dán thẳng vào bài.
Mong đợi:
1. 4 đồ thị TUÂN THỦ; "quan hệ khai báo chưa dùng" có MAPS_TO (chờ duyệt ánh xạ miền) và các quan hệ tầng Ràng buộc
   (chỉ có trong file `verified_constraints_*.json`).
2. Trên v1.1 (để tham khảo): Y có 2 cặp CONFLICT_IF_ACTIVATED (R1306:Art7(6) ↔ R809:Art34(1), R809:Art34(1) ↔
   R809:Art72(1)); Y-noDuty 5 cặp mâu thuẫn khi kích hoạt + 6 kéo theo.
3. Đầu trang: số dẫn chứng của LLM nguyên văn / gần nguyên văn / không có căn cứ (v1.1 Y: 18 / 4 / 0).
4. 18 khoản khác nội dung — đều là bẫy; positive và không chắc chắn giống hệt (`docs/CAP_HIEU_LUC_THOI_GIAN.md`).

Ghi chú tên gọi: file `data/review/bpic2018_ontology.json` là **ánh xạ miền** (tri thức M1: loại giấy tờ, quan hệ cụ
thể của BPIC2018), KHÔNG phải metamodel. Metamodel (M2) là `src/kg/metamodel.py` + schema AST.

### C7. v2 — cấu hình Z (KG giàu hơn)

Đọc trước: `docs/V2_DANG_KY_TRUOC.md` (đăng ký trước: tham số chốt, quy tắc đánh giá). **v1 đóng băng**: X, Y, Y-no*
không đổi (đã kiểm: phát lại Y từ cache bằng code mới → 218/218 khoản giống hệt).

1. Dựng dữ liệu v2 (không gọi API, mỗi lệnh < 1 phút):
   ```powershell
   python scripts/build_process_profile.py   # năm, vai trò, tài liệu, bước trước/sau → bpic2018_process_profile.json
   python scripts/build_cap_legal_v2.py      # định nghĩa + phạm vi quốc gia → cap_legal_graph_v2.json
   ```
2. Duyệt ontology: `docs/ONTOLOGY_BPIC2018_DUYET.md` → đổi `"status": "approved"` trong
   `data/review/bpic2018_ontology.json`.
3. Chạy Z (giống các cấu hình khác):
   ```powershell
   python scripts/run_cap_generation.py --provider cerebras --out-dir results/cap_cerebras --min-interval 13 --config Z
   ```
4. Chấm: `score_cap.py` thêm cặp **"v2 Z vs Y"**. Theo đăng ký trước, kết luận về v2 chỉ rút ra trên **tập positive
   mới**; trên gold hiện tại phải ghi "đã nhìn thấy khi thiết kế".

Z gồm: ngữ cảnh Y + định nghĩa thuật ngữ khoản dùng + ghi chú phạm vi quốc gia; kiểm thuộc tính event sai chỗ, gợi ý
nhóm activity theo năm, vi phạm hàng loạt (> 20% hồ sơ kích hoạt, phản hồi một lần kèm 2 hồ sơ phản ví dụ); ghi chú
activity cho giám khảo Tầng 3; dòng gợi ý loại giấy tờ (khi ontology đã duyệt). Mỗi khoản của Z ghi thêm
`process_checks`, `definitions`, `scope_note`, `doctype_hint`.

### C8. Tập Đức (InVeKoSV + DirektZahlDurchfV) — tập positive mới

Quyết định: `docs/V2_DANG_KY_TRUOC.md` mục 5.1. Dữ liệu đã dựng sẵn; chỉ chạy lại các lệnh 1–2 nếu cần dựng lại.

1. Dựng khoản theo năm + phiếu (không gọi API LLM):
   ```powershell
   python scripts/fetch_de_laws.py --offline   # bỏ --offline để tải thêm trang thiếu từ buzer.de / gesetze-im-internet.de
   python scripts/export_de_candidates.py      # docs/DE_ITEM_CANDIDATES.md + docs/de_batches/ (18 đợt)
   python scripts/build_de_legal_graph.py      # đồ thị Pháp lý cho Y/Z trên tập Đức
   ```
2. Gán nhãn: `docs/DE_GAN_NHAN_BO_SUNG.md` (bổ sung cho HUONG_DAN_GAN_NHAN_CAP.md). Không ghi điều kiện năm.
3. Gold (thư mục RIÊNG — script từ chối nếu thiếu `--out-dir`, để không ghi đè gold CAP):
   ```powershell
   python scripts/build_cap_gold.py --labels <file nhãn>.txt --candidates data/review/de_item_candidates.json --out-dir data/review/de_gold
   python scripts/build_cap_gold.py --labels <file nhãn>.txt --candidates data/review/de_item_candidates.json --out-dir data/review/de_gold --approve "<tên>"
   ```
4. Sinh (mỗi cấu hình như bộ CAP, thư mục kết quả riêng). Trước khi chạy: `python scripts/check_kg_metamodel.py`
   phải báo TUÂN THỦ (đăng ký bổ sung B3). Cấu hình đã đăng ký cho tập Đức: X, Y, Z, các ablation Z, và **R**
   (B4 — RAG truyền thống BM25, ngân sách ký tự khớp Y từng khoản):
   ```powershell
   foreach ($c in "X","Y","R","Z","Z-noLegal","Z-noProcess","Z-noMass","Z-noNotes","Z-noHint") {
     python scripts/run_cap_generation.py --provider cerebras --model gpt-oss-120b --dataset de --out-dir results/de_cerebras --min-interval 13 --config $c
   }
   ```
   (Z-noHint chỉ khác Z khi ánh xạ miền đã duyệt.) `score_cap.py` tự in thêm cặp "B4 R vs Y" và "B4 X vs Y" trên 79
   khoản Đức có dẫn chiếu tới 4 Quy định CAP, và bảng B1 (chấm theo thành phần).
5. Chấm và phán quyết từng hồ sơ (khoản có năm chỉ so trên hồ sơ của các năm đó):
   ```powershell
   python scripts/score_cap.py --gold data/review/de_gold/cap_gold_approved.json --pred-dir results/de_cerebras
   python scripts/run_cap_conformance.py --gold data/review/de_gold/cap_gold_approved.json --pred-dir results/de_cerebras --candidates data/review/de_item_candidates.json --configs X Y Z
   python scripts/build_cap_report.py --dir results/de_cerebras
   ```

Giới hạn theo năm được áp ở: kiểm rỗng B, kiểm vi phạm hàng loạt (Z) và bước phán quyết từng hồ sơ. Entity Matcher
nhận số / ngày tiếng Đức ('15. Mai', 'drei Tage', '0,3 Hektar', '1.250 Euro').

---

### C6d. Chạy theo pipeline có cổng kiểm + dấu dữ liệu (2026-11-20, không gọi API)

Thay cho gõ từng lệnh của C6/C6c. Sinh luật (gọi API) vẫn chạy riêng từng cấu hình như cũ.

```powershell
python scripts/run_pipeline.py pre                       # 1) KG tuân thủ metamodel → Γ trên đĩa đúng là chiếu của KG → in dấu dữ liệu
python scripts/run_cap_generation.py --provider cerebras --out-dir results/cap_cerebras_v13 --config Y   # 2) như cũ, từng cấu hình
python scripts/run_pipeline.py post --pred-dir results/cap_cerebras_v13 --configs Y R   # 3) chấm → phễu → xuất + kiểm tập → proof trace → báo cáo
```
Thêm `--conformance` ở bước 3 để chạy cả TN7 (nạp log). Bước nào lỗi thì pipeline **dừng** và ghi rõ bước đó.

**Tầng Cầu nối (A4, ontology đã duyệt 2026-11-20).** `python scripts/build_mapping_graph.py` dựng
`data/processed/{cap,de}_mapping_graph.json` (DocumentType, OF_DOCTYPE, RELATED_DOCTYPE, MAPS_TO khoản → loại giấy
tờ); `pre` kiểm file này khớp ontology + đồ thị. Nạp vào Neo4j phải CÙNG đồ thị luật + tiến trình:
`python scripts/load_kg_to_neo4j.py data/processed/cap_legal_graph.json data/processed/bpic2018_process_graph.json data/processed/cap_mapping_graph.json --replace`.
Từ nay cấu hình Z dùng ontology (nghĩa loại giấy tờ cho giám khảo + dòng gợi ý MAPS_TO) — Z-noHint mới thật sự khác Z.

**Dấu dữ liệu (A2).** Mỗi file `predictions_*.json` mới ghi `inputs` (SHA-256 của mọi file dữ liệu cấu hình đọc: phiếu
khoản, Γ, đồ thị, log, hồ sơ tiến trình, ontology) và mỗi khoản ghi `inputs_id`. Hệ quả:
- chạy tiếp vào file cũ mà dữ liệu đã đổi → **dừng**, báo file nào đổi. Dùng `--force` (khoản có prompt không đổi lấy
  lại từ cache, không tốn API) hoặc `--out-dir` mới;
- `score_cap.py` **từ chối chấm** khi các khoản / cấu hình sinh từ các phiên bản dữ liệu khác nhau (`--allow-mixed` để bỏ qua);
- file sinh trước 2026-11-20 (v1, v1.1, v1.2 phần đã chạy) chưa có dấu → chỉ được báo "chưa có dấu", không kết luận.

### C6e. Cấu hình N (khung chuẩn tắc, B6) và nhãn REVIEW (B7) — 2026-11-20

**Nhãn REVIEW (không gọi API, không đổi điểm)** — chạy cho bất kỳ thư mục kết quả nào (đã có trong `run_pipeline post`):
```powershell
python scripts/review_flags.py --pred-dir results/cap_cerebras_v12 --configs Y
```
Ghi `review_flags_<cfg>.md / .json`: 5 tín hiệu (S1 vi phạm hàng loạt > 20%, S2 không có hỗ trợ KG qua MAPS_TO,
S3 mâu thuẫn trong tập, S4 dẫn chứng không có căn cứ, S5 rỗng mà vẫn chấp nhận), mức nghi ngờ, bảng giữ lại — rủi ro.
Số thử trên v1.1 (Y): 22/22 luật bị REVIEW (S1 20, S2 14, S3 3) — trên CAP, Y không có luật đúng nào để giữ lại.

**Cấu hình N (gọi API — bạn chạy).** Cần ontology đã duyệt (đã duyệt 2026-11-20). Theo B6: **tập Đức là đánh giá
chính** (cần gold tập Đức đã gán nhãn), CAP chỉ là tập phát triển.
```powershell
# CAP (tập phát triển) — cùng thư mục với Y để so cặp N vs Y
python scripts/run_cap_generation.py --provider cerebras --out-dir results/cap_cerebras_v12 --config N
# tập Đức (đánh giá chính) — cần chạy cả Y trên tập Đức để so cặp
python scripts/run_cap_generation.py --provider cerebras --dataset de --out-dir results/de_cerebras --config Y
python scripts/run_cap_generation.py --provider cerebras --dataset de --out-dir results/de_cerebras --config N
python scripts/run_pipeline.py post --pred-dir results/de_cerebras --gold data/review/de_gold/cap_gold_approved.json --configs Y N
```
`score_cap` in thêm cặp `B6 N vs Y (…)`; phễu kiểm chứng có 4 hàng mới (N1–N4).
Chỉ chạy N trên CAP **sau khi** v1.2 xong (cùng thư mục `results/cap_cerebras_v12`).

### C6f. KG đầy đủ 5 tầng và kiểm luật trên Neo4j (M8) — 2026-11-20, không gọi API

```powershell
python scripts/build_full_kg.py --pred-dir results/cap_cerebras_v12 --config Y      # đã có trong run_pipeline post
python scripts/load_kg_to_neo4j.py results/cap_cerebras_v12/kg_full_Y.json --replace  # xem trên http://localhost:7474
python scripts/verify_cypher_compiler.py --synthetic                                   # Cypher ↔ engine, vét cạn
python scripts/verify_cypher_compiler.py --pred-dir results/cap_cerebras_v12 --config Y --cases 2000
```
`verify_cypher_compiler.py` ghi đè nhãn `:EvCase` / `:Ev` (đồ thị sự kiện), không đụng node KG. Xoá khi không cần:
`MATCH (n) WHERE n:Ev OR n:EvCase CALL (n) { DETACH DELETE n } IN TRANSACTIONS` (trong Neo4j Browser).

### C6g. Kiểm thử thường trực T1–T3 và hoàn tất v1.2 bằng đúng code của nó — 2026-11-20, không gọi API

T1 chạy trong `run_pipeline pre`, T2 ở cuối `run_pipeline post` (bước nào báo vi phạm thì pipeline dừng). T3 chạy
riêng sau mỗi lần sửa code — phát lại cache, KHÔNG gọi API, không ghi vào file dự đoán (chỉ ghi `replay_check.json`):
```powershell
python scripts/run_pipeline.py replay --pred-dir results/cap_cerebras_v12 --configs Y X
```
"N/N khoản giống hệt" = lần sửa không đổi kết quả đã báo cáo; có khoản khác → danh sách để quyết định (đổi cố ý hay lỗi).

**v1.2 còn 48 khoản ERROR ở Y-noDuty.** Các bản sửa 2026-11-20 (Tầng 1 thời hạn, tự lặp theo tập) CÓ THỂ đổi hành
vi sinh: trên 7 cấu hình v1.2 phát lại được thì không khoản nào đổi (1 526/1 526 giống hệt, cả với code hiện tại và
commit `b32a643`), nhưng Y-noDuty từng có một vòng đề xuất `time_max` trên mẫu không thời hạn — 48 khoản còn lại có thể
gặp lại. Để v1.2 chỉ một phiên bản hành vi, hoàn tất bằng commit `b32a643` trong một thư mục làm việc riêng. Log
(`data/interim`) không nằm trong git → nối thư mục log sang (junction, không sao chép 2 GB):
```powershell
$repo = (Get-Location).Path                      # đang ở thư mục dự án
git worktree add ..\nsai_v12 b32a643
New-Item -ItemType Junction -Path ..\nsai_v12\data\interim -Target "$repo\data\interim"
Copy-Item .env ..\nsai_v12\.env
cd ..\nsai_v12
python scripts/run_cap_generation.py --provider cerebras --config Y-noDuty --out-dir "$repo\results\cap_cerebras_v12"
cd $repo
cmd /c rmdir ..\nsai_v12\data\interim            # GỠ JUNCTION TRƯỚC (rmdir chỉ xoá liên kết, không đụng log gốc)
git worktree remove ..\nsai_v12                   # rồi mới gỡ thư mục làm việc phụ
```
**Không** gỡ worktree khi junction còn đó (`--force` hoặc xoá thư mục bằng Explorer có thể đi theo liên kết và xoá
log gốc trong `data\interim`).
Sau đó chạy `run_pipeline post` bằng code hiện tại (chấm / phân tích không đổi kết quả sinh). Mọi lần chạy MỚI (N, R,
Z, tập Đức, v1.3) dùng code hiện tại.

### C9. Lần chạy CHÍNH THỨC bộ CAP (2026-11-21; v1–v1.2 là chạy thử)

Code commit `53c080e` (sau khi gỡ code BPIC2017; dấu `code.sha256` = `199640a02cf180d2`, mọi file kết quả phải ghi đúng dấu này), thư mục
`results\cap_official`, cache trống. Hạn mức Cerebras đo được (mỗi key): 5 request / phút, 150 / giờ, 30 000 token /
phút, 1 000 000 token / ngày; một cấu hình cần ~300–550 request và ~1 triệu token → **mỗi key ~1 cấu hình / ngày,
~2,5–4 giờ**. Hai key chạy song song ở hai cửa sổ (mỗi cấu hình một file cache riêng, an toàn).

Một lần trước khi bắt đầu (và sau mỗi lần sửa code / dữ liệu): `python scripts\run_pipeline.py pre` phải qua hết.

Mỗi ngày, mỗi cửa sổ một cấu hình (cửa sổ 1 dùng `CEREBRAS_API_KEY`, cửa sổ 2 `CEREBRAS_API_KEY_2`):
```powershell
C:\Users\hayab\.venvs\nsai-compliance\Scripts\python.exe scripts\run_cap_generation.py --provider cerebras `
  --config <CẤU HÌNH> --key-var <BIẾN KEY> --min-interval 30 --max-tokens 8000 --out-dir results\cap_official
```

| Ngày | Cửa sổ 1 (`CEREBRAS_API_KEY`) | Cửa sổ 2 (`CEREBRAS_API_KEY_2`) |
|---|---|---|
| 1 | Y | X |
| 2 | Y-noL12 | Y-noL3 |
| 3 | Y-retry1 | Y-noVac |
| 4 | Y-noDomain | Y-noDuty |
| 5 | R | N |
| 6 | Z | Z-noLegal |
| 7 | Z-noProcess | Z-noMass |
| 8 | Z-noNotes | Z-noHint |
| 9 | Y → `--out-dir results\cap_official_rep2` | X → `--out-dir results\cap_official_rep2` |
| 10 | Y → `--out-dir results\cap_official_rep3` | X → `--out-dir results\cap_official_rep3` |

Ngày 9–10 (thêm 2026-11-21, phân tích độ vững — xem `V2_DANG_KY_TRUOC.md`): lặp X và Y với ĐÚNG lệnh trên, chỉ đổi
`--out-dir`. Câu trả lời LLM không tất định (chỉ ~20% câu trả lời vòng 1 giống hệt giữa hai lần chạy), nên một kết luận
X vs Y chỉ vững khi cùng chiều ở cả 3 lần.

**Chạy liên tục bằng hàng đợi (2026-11-21, thay cho chia theo ngày).** `scripts/run_queue.ps1` (không thuộc dấu code):
chạy lần lượt các cấu hình của một key; cấu hình còn ERROR (hết hạn mức ngày) → chờ 30 phút, chạy lại đúng lệnh (chỉ
khoản còn lỗi) tới khi 218/218, 0 ERROR mới sang cấu hình sau. Tắt / mở lại bất kỳ lúc nào: chạy lại đúng lệnh, cấu
hình đã xong được bỏ qua. Log mỗi cấu hình: `<thư mục>\run_<cấu hình>.log`. Tổng 18 lượt, ~9 lượt mỗi key (~9 ngày nếu
mỗi key ~1 cấu hình / ngày). Hai cửa sổ:
```powershell
# cửa sổ 1
.\scripts\run_queue.ps1 -KeyVar CEREBRAS_API_KEY -Jobs "Y-noL12","Y-retry1","Y-noDomain","R","Z","Z-noProcess","Z-noNotes","Y@results\cap_official_rep2","Y@results\cap_official_rep3"
# cửa sổ 2
.\scripts\run_queue.ps1 -KeyVar CEREBRAS_API_KEY_2 -Jobs "Y-noL3","Y-noVac","Y-noDuty","N","Z-noLegal","Z-noMass","Z-noHint","X@results\cap_official_rep2","X@results\cap_official_rep3"
```
Nếu PowerShell báo không cho chạy script: chạy trước `Set-ExecutionPolicy -Scope Process Bypass` (chỉ cửa sổ đó).

- Xong một cấu hình: dòng `Tổng hợp` phải có `'ERROR': 0`. Còn ERROR (VD hết hạn mức ngày giữa chừng) → hôm sau chạy
  lại ĐÚNG lệnh đó trước (chỉ chạy khoản còn lỗi), rồi mới sang cấu hình mới.
- Không dùng `--force`, không đổi `--min-interval` / `--max-tokens` giữa chừng (ghi trong meta).
- Bất kỳ lúc nào (không gọi API): `python scripts\run_pipeline.py post --pred-dir results\cap_official --configs X Y`
  — chấm những cấu hình đã có; T2 ở cuối phải 0 vi phạm.
- Tạm dừng OneDrive khi đang chạy. Tập Đức chạy SAU khi có gold Đức (AI #2 + phân xử).

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `docker: error during connect` | Docker Desktop chưa chạy | Mở Docker Desktop, chờ *Engine running* |
| `port is already allocated` | Đã có chương trình khác dùng cổng 7474/7687 | `docker ps` để xem; tắt container cũ |
| `The container name "/nsai-neo4j" is already in use` | Đã tạo container trước đó | Dùng `docker start nsai-neo4j` thay vì `docker run` |
| `check_setup`: `AuthError` | Mật khẩu trong `.env` khác mật khẩu lúc `docker run` | Sửa `.env` cho khớp |
| `check_setup`: `ServiceUnavailable` | Neo4j chưa khởi động xong | Chờ thêm 30 giây; xem `docker logs nsai-neo4j` |
| `ModuleNotFoundError` | Quên kích hoạt venv | Làm lại Bước 0 |
| `CẢNH BÁO: … đang bị khoá (VD OneDrive)` khi sinh luật | OneDrive đang đồng bộ file cache / kết quả | Không cần làm gì: chương trình thử lại, kết quả giữ trong bộ nhớ và ghi ở lần sau. Muốn tránh hẳn: **tạm dừng đồng bộ OneDrive** (biểu tượng OneDrive → Pause syncing) trong lúc chạy, hoặc dùng `--out-dir` ngoài OneDrive (VD `C:\nsai_runs\cap_v13`) rồi trỏ `--pred-dir` của các lệnh chấm vào đó |
| `LỖI: không ghi được predictions_….json` (exit 2) | File kết quả vẫn bị khoá ở lần ghi cuối | Câu trả lời LLM đã ở cache: chạy lại đúng lệnh đó thêm `--cache-only` (không tốn API) |
