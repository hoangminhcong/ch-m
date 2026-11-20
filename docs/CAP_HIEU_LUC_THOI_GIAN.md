# Hiệu lực theo thời gian của văn bản CAP — đối chiếu với log 2015–2017 (2026-11-19)

**Câu hỏi:** gold CAP được gán nhãn trên **bản gốc** của 4 Quy định (PDF CELEX 2013/2014), nhưng log BPIC2018 thuộc
các năm nộp đơn 2015–2017. Nếu một khoản bị sửa đổi trong giai đoạn đó, nhãn (và đầu vào của hệ thống) có thể không
khớp với luật thực sự áp dụng cho hồ sơ. (Ý tưởng từ Dang et al., ISDS 2026: cạnh có mốc thời gian.)

**Cách kiểm:** `python scripts/check_cap_versions.py` — lấy danh sách bản hợp nhất từ Cellar (Văn phòng Xuất bản
EU), chọn bản có hiệu lực ngày 15/5 mỗi năm (hạn nộp đơn), tách khoản bằng đúng bộ tách của hệ thống, so ở mức chữ
(bỏ dấu cách, dấu câu, số chú thích).

| Văn bản | 2015 | 2016 | 2017 |
|---|---|---|---|
| R1306 | hợp nhất 2014-01-01 | 2014-01-01 | 2014-01-01 |
| R1307 | hợp nhất 2015-01-01 | 2015-06-03 | 2015-06-03 |
| R640 | bản gốc | bản gốc | **hợp nhất 2016-08-22** |
| R809 | bản gốc | **hợp nhất 2016-01-01** | **hợp nhất 2016-08-22** |

## Kết quả (218 khoản trên phiếu)

- **3 khoản positive và 8 khoản không chắc chắn: nguyên văn giống hệt ở cả 3 năm** (khác biệt duy nhất là số thứ tự
  chú thích, VD R1307:Art24(1) '( 1 )' → '( 22 )').
- **18 khoản có sửa đổi nội dung thật — cả 18 đều là bẫy:**
  - R640 (bản 2017): Art2(1) (thêm định nghĩa 'animal passport'), Art7(1), Art19(3), Art21(2), Art24(3) (thêm khoản
    3a), Art28(4), Art30(3) (thêm 3a), Art31(2), Art31(3), Art35(7) (thay 'the rules laid down by the Commission on
    the basis of Article 57(2) …' bằng 'Article 28 of Implementing Regulation (EU) No 908/2014').
  - R809 (bản 2016 và 2017): Art10, Art17(1), Art31(3) ('sample' → 'population'), Art34(2) (thêm cách chọn mẫu ngẫu
    nhiên 0,6–0,75%), Art36(3), Art36(4), Art36(5), Art42(1).
- 5 khoản chỉ khác chữ số (đánh số chú thích / định nghĩa): R1306:Art62(2), R640:Art5(2), Art9(1), Art13(2), Art20.

## Ý nghĩa và việc cần người dùng quyết

- Kết quả chính (positive) **không bị ảnh hưởng** bởi hiệu lực thời gian. Đây là mối đe dọa tính hợp lệ đã được kiểm
  và **đóng** cho các khoản positive / không chắc chắn — nên ghi vào bài.
- 18 khoản bẫy: bản sửa đổi đều là quy tắc của Nhà nước / Ủy ban (mẫu kiểm tra, sổ đăng ký, phương pháp tính) — khả
  năng nhãn đổi từ bẫy sang positive thấp, nhưng **chưa được kiểm bởi người**. Lựa chọn:
  (a) ghi nhận là giới hạn, giữ nhãn (đề xuất — nhãn bẫy không phụ thuộc chi tiết đã sửa);
  (b) người xem lại 18 khoản trên bản 2016/2017 và ghi kết quả.
- Hệ thống hiện đưa **bản gốc** cho LLM ở mọi năm. Với tập Đức, phiên bản theo năm đã có sẵn (mỗi khoản mang `years`).

## Phát hiện phụ (đã sửa trong v1.2, xem `docs/V2_DANG_KY_TRUOC.md`)

Đối chiếu với bản hợp nhất làm lộ hai lỗi tách văn bản của chính mình: chú thích '… p 48).' còn lẫn trong R809:Art5,
và PDF R640 mất gạch nối ở 17 chỗ ngắt từ ('legisla tion').

## Độ nhạy và đoạn văn cho bài (2026-11-20, A5)

Danh sách máy đọc được: `data/review/cap_temporal_versions.json` (`python scripts/check_cap_versions.py`).
`score_cap.py` tự in bảng **"B5 — độ nhạy theo hiệu lực thời gian"**: chấm lại sau khi bỏ 18 khoản có sửa đổi.
Trên v1.1: **không kết luận nào đổi** — Y 171/192 (89,1%); noL3, retry1, noDuty vẫn kém Y có ý nghĩa; X vs Y,
noL12, noVac, noDomain vẫn không có ý nghĩa; Y vẫn thua luôn-BASELESS (0 / 18). Y trả BASELESS đúng cho cả 18 khoản
có sửa đổi. Chạy lại sau khi có v1.2.

**Vì sao không đưa bản hợp nhất theo năm vào CAP (khác tập Đức):** đổi đầu vào = chạy lại toàn bộ, mà kiểm chứng trên
cho thấy không khoản positive / không chắc chắn nào bị ảnh hưởng và kết luận không đổi khi bỏ các khoản bị ảnh hưởng.
Tập Đức đã có phiên bản theo năm từ đầu (`years`), nên đó là nơi hệ thống được đánh giá với luật theo đúng năm.

**Đoạn văn (Threats to validity) — tiếng Anh, dán vào bài:**

> *Temporal validity.* The CAP gold standard and the system both use the original texts of the four regulations,
> whereas the log covers application years 2015–2017. We compared every sheet clause with the consolidated version
> in force on 15 May of each year (EUR-Lex/Cellar). All positive and uncertain clauses are textually identical in all
> three years; 18 clauses, all labelled as traps, were amended (mainly sampling and register rules of Implementing
> Regulation 809/2014 and Delegated Regulation 640/2014), and 5 differ only in footnote numbering. Re-scoring without
> the 18 amended clauses changes none of the conclusions (all significant and non-significant paired comparisons keep
> their status). The German set, in contrast, is built from the version in force in each log year.
