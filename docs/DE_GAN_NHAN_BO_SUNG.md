# Gán nhãn tập Đức — bổ sung cho HUONG_DAN_GAN_NHAN_CAP.md

Phiếu: `docs/DE_ITEM_CANDIDATES.md` (255 khoản InVeKoSV + DirektZahlDurchfV, mọi khoản, không lọc; 256 trước khi bỏ
khoản ảo DZDV §36 ngày 2026-11-19).
Mọi quy tắc của `docs/HUONG_DAN_GAN_NHAN_CAP.md` vẫn áp dụng (3 câu hỏi, ký hiệu ràng buộc, nhóm `{A | B}`, ngày
`ngày(A) <= 15/05/năm`, mục 10: gán bằng nhiều AI khác công ty rồi người kiểm). Dưới đây chỉ là phần khác.

## 1. Văn bản và năm

- Đây là văn bản **thực thi của Đức** cho các Quy định CAP — log BPIC2018 là của Đức, nên nhiều khoản cụ thể hơn
  Quy định EU (hạn chót, mẫu đơn, ai nộp cái gì).
- Mỗi khoản là văn bản **có hiệu lực ngày 15/5 của năm nộp đơn** (2015, 2016, 2017), dựng lại từ lịch sử phiên bản.
- Mã có `@năm` (VD `DE-InVeKoSV:§7(3)@2016`) = văn bản riêng của năm đó; không có `@` = giống nhau cả ba năm.
- **Không ghi điều kiện năm** (`case:year`) vào ràng buộc chỉ vì khoản có `@năm`. Bước chấm và bước phán quyết từng
  hồ sơ tự giới hạn ràng buộc vào hồ sơ của đúng các năm của khoản. Chỉ ghi điều kiện năm khi **chính văn bản** nói
  tới một năm cụ thể.

## 2. Ngôn ngữ

- Giữ nguyên tiếng Đức. Điều khoản EU được dẫn chiếu có kèm bản tiếng Anh.
- Từ hay gặp: *Sammelantrag* = đơn tổng hợp hằng năm (≈ Payment application); *Antragsjahr* = năm nộp đơn;
  *Betriebsinhaber* = chủ trang trại (nông dân); *Landesstelle* = cơ quan cấp bang (cơ quan chi trả);
  *Zahlungsansprüche* = quyền hưởng chi trả; *Parzelle / Schlag* = thửa đất; *bis zum 15. Mai* = chậm nhất ngày 15/5;
  *spätestens drei Tage vorher* = chậm nhất 3 ngày trước.
- Dùng AI dịch để hiểu thì được, nhưng **lý do** phải dựa trên nguyên văn tiếng Đức; ghi `(theo bản dịch)` nếu
  chỉ dựa vào bản dịch.

## 3. Dẫn chiếu

- "Cần điều tham chiếu" = Có / Một phần khi phải đọc khoản được dẫn chiếu (thường là điều khoản EU) mới viết được ràng
  buộc. Đây chính là Tier 4 — tập này có ~79 khoản dẫn chiếu tới 4 Quy định EU.
- Bộ tách dẫn chiếu xử lý danh sách khoản ("Absatz 1 und 2", "Absatz 1 bis 3") và chuỗi "§ 27 Absatz 2, des § 28
  oder des § 29 der Direktzahlungen-Durchführungsverordnung" (cả chuỗi thuộc văn bản nêu ở cuối) — sửa 2026-11-18.
  Dẫn chiếu tới một khoản không tách riêng được → kèm nguyên văn cả §.
- Hạn chế còn lại (2 chỗ, phiếu ghi "không tìm thấy nguyên văn"): DE-InVeKoSV:§16(2) ("§ 9a … in Verbindung mit § 6
  … des Marktorganisationsgesetzes") và DE-InVeKoSV:§34 ("§ 36 … des Gesetzes über Ordnungswidrigkeiten") — cả hai
  thực ra trỏ tới luật khác ngoài bộ.

## 4. Không được làm

- Không xem kết quả hệ thống (v1 hay v2) trước hoặc trong khi gán nhãn tập này.
- Không dùng gpt-oss-120b (model của hệ thống) hay họ của nó để gán nhãn.

## 5. Quy trình từng bước (2026-11-20)

**Bước 1 — chọn ≥ 2 AI của các công ty khác nhau** (VD Claude trên claude.ai + Gemini). Không dùng gpt-oss-120b hay
họ của nó. Không dùng cuộc trò chuyện / dự án đã có tài liệu, kết quả của đề tài (kể cả phiên Claude Code đang xây
hệ thống — nó đã thấy kết quả hệ thống). Ghi tên mô hình, phiên bản, ngày chạy.

**Bước 2 — mỗi đợt, mỗi AI: một cuộc trò chuyện MỚI**, đính kèm đúng 4 file:
`docs/HUONG_DAN_GAN_NHAN_CAP.md`, `docs/DE_GAN_NHAN_BO_SUNG.md`, `docs/CAP_VOCABULARY.md`, `docs/de_batches/dot_XX.md`
(18 đợt, ≤ 15 khoản / đợt). Dán câu lệnh dưới (giống hệt cho mọi đợt, mọi AI; = mục 10.4 của hướng dẫn chính, thêm
file bổ sung tiếng Đức):

```
Bạn là người gán nhãn cho một nghiên cứu khoa học về kiểm tra tuân thủ pháp luật trên nhật ký quy trình.

Tôi đính kèm 4 file:
- HUONG_DAN_GAN_NHAN_CAP.md: hướng dẫn gán nhãn (đọc kỹ toàn bộ trước khi làm, nhất là mục 3–7)
- DE_GAN_NHAN_BO_SUNG.md: phần bổ sung cho các khoản luật tiếng Đức (đọc kỹ; áp dụng cùng hướng dẫn chính)
- CAP_VOCABULARY.md: bảng tên activity và thuộc tính của log (chỉ được dùng đúng các tên trong bảng này)
- dot_XX.md: một đợt các khoản luật cần gán nhãn

Nhiệm vụ: gán nhãn TẤT CẢ các khoản trong file đợt, theo đúng hướng dẫn.

Yêu cầu bắt buộc:
1. Trả lời MỖI khoản bằng ĐÚNG MỘT dòng theo mẫu ở đầu file đợt: giữ nguyên mã khoản (kể cả phần @năm), các nhãn
   in đậm và dấu · ngăn cách; thay mọi chỗ ___ bằng câu trả lời:
   <mã khoản>: **Quan sát được:** … · **Ràng buộc mới:** … · **Cần điều tham chiếu:** … · **Độ chắc chắn:** … · **Lý do:** …
2. Quan sát được: chỉ ghi Có, Không hoặc Không chắc.
   Cần điều tham chiếu: chỉ ghi Có, Một phần, Không hoặc —.
   Độ chắc chắn: chỉ ghi Cao, TB hoặc Thấp.
3. Ràng buộc mới viết đúng cú pháp ở mục 4–5 của hướng dẫn; tên activity và thuộc tính PHẢI chép đúng từng chữ
   từ bảng từ vựng. Nhiều ràng buộc thì ngăn cách bằng dấu ;. Nếu Quan sát được không phải Có thì ghi —.
4. Mọi con số, ngày, thời hạn phải có trong khoản luật hoặc khoản được dẫn chiếu; giữ đúng đơn vị của luật
   (ngày / ngày làm việc / tuần / tháng), không quy đổi.
5. Với Precedence(A → B), điều kiện ngày ghi cho B. Với các mẫu khác, điều kiện ghi cho A.
6. Lý do: ngắn gọn (1–2 câu), nêu căn cứ trong NGUYÊN VĂN tiếng Đức của khoản; nếu chỉ dựa vào bản dịch thì ghi
   "(theo bản dịch)"; nếu dùng proxy thì ghi "proxy: <activity> ≈ <sự việc>"; nếu Cần điều tham chiếu là Có /
   Một phần thì ghi rõ chi tiết lấy từ khoản nào.
7. Phân vân vẫn phải chọn, ghi Độ chắc chắn: Thấp. Không bỏ trống khoản nào.
8. Chọn mẫu theo mục 5.1–5.3 của hướng dẫn: hạn chót / khoảng thời gian → Absence(A) với ngày(A) > mốc;
   "hồ sơ thuộc diện X phải có A" → Responded Existence(Payment application / Application / mail income → A) | X,
   KHÔNG viết Existence(A) | case:…; cùng một bước được ghi bằng activity khác nhau theo năm → nhóm {A1 | A2}.
9. KHÔNG ghi điều kiện năm (case:year) chỉ vì mã khoản có @năm (xem DE_GAN_NHAN_BO_SUNG.md mục 1).

Định dạng đầu ra: CHỈ các dòng trả lời, mỗi khoản một dòng, theo đúng thứ tự trong file đợt, đặt trong một
khối code. Không viết lời mở đầu, giải thích hay tóm tắt nào khác.
```
Sai định dạng → dùng "Prompt sửa lỗi" ở mục 10.4 của hướng dẫn chính (chỉ sửa định dạng, không bảo AI đổi ý).

**Bước 3 — gom kết quả:** mỗi AI một file, nối 18 đợt theo thứ tự, VD `DE_labels/CAP_ITEM_CANDIDATES_claude.txt`,
`DE_labels/CAP_ITEM_CANDIDATES_gemini.txt` (255 dòng mỗi file; tên sau `CAP_ITEM_CANDIDATES_` = tên AI trong báo cáo).
Để thư mục nhãn NGOÀI `results/`.

**Bước 4 — đối chiếu** (không gọi API):
```powershell
python scripts/compare_cap_labels.py --labels DE_labels/CAP_ITEM_CANDIDATES_claude.txt DE_labels/CAP_ITEM_CANDIDATES_gemini.txt --candidates data/review/de_item_candidates.json --out-dir data/review/de_ai_compare
```
→ `data/review/de_ai_compare/DOI_CHIEU.md` (đồng thuận, kappa, từng khoản bất đồng kèm nguyên văn) và
`CAP_ITEM_CANDIDATES_final_draft.txt` (khoản đồng thuận điền sẵn, khoản bất đồng để `___`).

**Bước 5 — người quyết** (phần duy nhất bạn phải tự làm): mở file nháp, (a) mọi dòng `# CẦN NGƯỜI QUYẾT`: đọc khoản
trong `DOI_CHIEU.md`, chọn đáp án của một AI hoặc tự viết; (b) mọi dòng `# KIỂM NGẪU NHIÊN` (≥ 26 khoản AI đồng
thuận): đọc lại, sửa nếu sai và **đếm số khoản đã sửa** (phải báo cáo). Lưu thành
`DE_labels/CAP_ITEM_CANDIDATES_final.txt`. Không xem kết quả hệ thống trong lúc này.

**Bước 6 — dựng và duyệt gold:**
```powershell
python scripts/build_cap_gold.py --labels DE_labels/CAP_ITEM_CANDIDATES_final.txt --candidates data/review/de_item_candidates.json --out-dir data/review/de_gold
# đọc data/review/de_gold/CAP_GOLD_REVIEW.md (dòng 'invalid' = ràng buộc viết sai cú pháp / tên → sửa file nhãn, chạy lại)
python scripts/build_cap_gold.py --labels DE_labels/CAP_ITEM_CANDIDATES_final.txt --candidates data/review/de_item_candidates.json --out-dir data/review/de_gold --approve "<tên bạn>"
```
Sau đó chạy hệ thống theo runbook C8 / C6e (gold: `data/review/de_gold/cap_gold_approved.json`).
