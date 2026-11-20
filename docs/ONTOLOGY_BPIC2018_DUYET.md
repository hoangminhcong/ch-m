# Duyệt ontology loại giấy tờ BPIC2018 (v2, thành phần 6)

File cần duyệt: `data/review/bpic2018_ontology.json`. Claude soạn nháp ngày 2026-11-16 (`"status": "draft"`).
Hệ thống (cấu hình Z) **chỉ dùng ontology khi `"status": "approved"`**; khi chưa duyệt, Z vẫn chạy nhưng không có nghĩa
loại giấy tờ trong ghi chú cho giám khảo và không có dòng gợi ý MAPS_TO (script in cảnh báo, ghi vào metadata).

## Căn cứ của bản nháp

| Nguồn | Dùng cho |
|---|---|
| `DATA.xml` đi kèm BPIC2018: chi trả trực tiếp cho nông dân Đức, hệ thống IACS, phần mềm profil c/s; quy trình là các *tài liệu* có trạng thái và hành động, một số hành động chạy tự động | nghĩa chung |
| `data/processed/bpic2018_process_profile.json`: tên activity, năm hoạt động, tỉ lệ hồ sơ, vai trò | nghĩa từng loại, năm, quan hệ thay thế theo năm |
| Thuật ngữ định nghĩa trong 4 Quy định CAP | `legal_terms` (để nối khoản luật → loại giấy tờ) |

Mỗi loại giấy tờ có `confidence` (high / medium / low) và `basis` (vì sao suy ra như vậy). **Không có nguồn nào mô tả
chính thức nghĩa từng loại giấy tờ** — các mục `low` chỉ suy từ tên.

## Cần bạn kiểm (đánh dấu từng mục)

1. **`meaning` của 8 loại giấy tờ** — đúng với hiểu biết của bạn về quy trình IACS không? Sửa trực tiếp nếu sai.
   Ưu tiên kiểm 3 mục `low`: Reference alignment, Control summary, Department control parcels.
2. **`legal_terms`** — mỗi thuật ngữ có thật sự chỉ tới loại giấy tờ đó không? Thuật ngữ quá chung (VD `parcel`,
   `inspection`) làm nhiều khoản bị gắn nhầm; xoá nếu thấy rộng quá.
3. **`relations`** — 5 quan hệ, đặc biệt `uses_entitlements_from` (`low`).
4. **`applicant_initiated`** — 2 activity coi là do nông dân khởi phát (`mail income`, `Geo parcel document /
   Declared / create`). Có nên thêm các bước `Objection` (khiếu nại) không?

**Quy tắc quan trọng:** khi sửa, KHÔNG dựa vào các khoản gold (R1307:Art32(1), Art33(1), R809:Art22(1)) hay kết quả v1
— chỉ dựa vào hiểu biết về quy trình và văn bản luật. Ghi lại nếu bạn đã tham khảo nguồn nào khác.

## Duyệt

Sửa xong, đổi 3 trường đầu file:

```json
"status": "approved",
"approved_by": "<tên bạn>",
"approved_at": "<ngày, VD 2026-11-17>",
```

Trong bài: mô tả ontology là "do Claude soạn từ mô tả bộ dữ liệu và thống kê log, người duyệt", kèm số mục đã sửa.

## Kết quả duyệt (2026-11-20)

- **Đã duyệt nguyên bản nháp, 0 mục sửa** (gồm cả `legal_terms_de`), trong phiên làm việc 2026-11-20. Không tham
  khảo gold hay kết quả chạy. `approved_by` đang ghi "chủ dự án" — thay bằng tên người duyệt nếu cần ghi trong bài.
- Ontology đã được dựng thành **tầng Cầu nối của KG** (`python scripts/build_mapping_graph.py`):
  `data/processed/cap_mapping_graph.json`, `de_mapping_graph.json` — 8 `DocumentType`, cạnh `OF_DOCTYPE`
  (activity → loại giấy tờ), `RELATED_DOCTYPE` (5 quan hệ trên), `MAPS_TO` (khoản luật → loại giấy tờ, mang `terms`
  = thuật ngữ khớp). Kiểm metamodel trên hợp với đồ thị luật + tiến trình: tuân thủ.
- CAP: 399/979 khoản có văn bản có ≥ 1 cạnh MAPS_TO; trên phiếu 218 khoản, 122 khoản có dòng gợi ý. MAPS_TO trong
  KG trùng đúng 100% với dòng gợi ý mà Z đưa vào prompt (CAP 218/218, Đức 255/255 —
  `tests/test_mapping_graph.py`).
- **Rủi ro còn lại (chưa ai kiểm):** thuật ngữ rộng khớp nhiều khoản — `payment entitlement` 107, `on-the-spot check`
  96, `aid application` 89, `administrative checks` 58 (gắn cho 2 loại `low`: Control summary, Department control
  parcels); 53 khoản bị gắn ≥ 3 loại giấy tờ. Nếu sửa ontology: sửa file, chạy lại `build_mapping_graph.py`, và phải
  làm TRƯỚC khi chạy Z (ontology nằm trong dấu dữ liệu của Z — sửa sau sẽ bị chặn chạy tiếp).
