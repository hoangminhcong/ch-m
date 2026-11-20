# Kiến trúc hệ thống NSAI + Graph-RAG (KG làm gốc thay UML)

Tài liệu tổng quan: hệ thống gồm những tầng nào, dữ liệu chảy ra sao, module nào ở file nào, và cổng kiểm nào chặn ở
đâu. Chi tiết chạy: `HUONG_DAN_THUC_NGHIEM.md`; quyết định đánh giá: `V2_DANG_KY_TRUOC.md`.

## 1. Ý tưởng một câu

Văn bản luật và log sự kiện đều được đưa vào **một Knowledge Graph (KG) có metamodel đóng**; LLM chỉ được sinh ràng
buộc DECLARE **trong khuôn** mà KG quy định (Γ, danh mục loại chuẩn tắc, MAPS_TO), rồi mỗi ràng buộc phải qua chuỗi
kiểm ký hiệu (cú pháp, kiểu, log, dịch ngược) trước khi được ghi trở lại KG cùng bằng chứng.

## 2. Ba mức MDE

| Mức | Là gì | Ở đâu |
|---|---|---|
| **M2 — metamodel** | Lớp node, quan hệ được phép, thuộc tính bắt buộc, nguồn gốc (provenance) của cạnh; thế giới ĐÓNG | `src/kg/metamodel.py` (+ schema AST ràng buộc `src/mde/constraint_ast.py`) |
| **M1 — mô hình** | Các đồ thị cụ thể (bảng dưới) + Γ (chiếu từ KG) | `data/processed/*.json` |
| **M0 — dữ liệu** | Log BPIC2018 (43 809 hồ sơ, 2,5 triệu event) | `data/interim/bpic2018_*.parquet` |

Kiểm M1 theo M2: `scripts/check_kg_metamodel.py` (cổng B3, thoát mã 1 nếu vi phạm).

## 3. Các tầng của KG (M1)

| Tầng | Node | Cạnh | File | Dựng bằng |
|---|---|---|---|---|
| **Pháp lý** | Article, Paragraph, Annex, DefinedTerm | HAS_PARAGRAPH, REFERS_TO, DEFINES, USES_TERM | `cap_legal_graph(_v2).json`, `de_legal_graph.json` | `legal_graph_builder.py`, `legal_enrichment.py`, `de_legal_graph.py` |
| **Tiến trình** | Activity, Attribute | DIRECTLY_FOLLOWS, HAS_ATTRIBUTE | `bpic2018_process_graph.json` | `process_graph_builder.py` |
| **Cầu nối** | DocumentType | OF_DOCTYPE, RELATED_DOCTYPE, MAPS_TO (khoản → loại giấy tờ) | `cap_mapping_graph.json`, `de_mapping_graph.json` | `mapping_graph_builder.py` (ontology người duyệt) |
| **Chuẩn tắc** | Norm (khung chuẩn tắc của cấu hình N; cả khoản không diễn đạt được: `expressible=false`) | GROUNDED_IN, FORMALIZED_AS → VerifiedConstraint | `<pred-dir>/verified_constraints_<cfg>.json` | `constraint_export.py` |
| **Ràng buộc** | VerifiedConstraint | GROUNDED_IN, ON, CONFLICTS_WITH, IMPLIES, DUPLICATE_OF | `<pred-dir>/verified_constraints_<cfg>.json` | `constraint_export.py` |

**KG đầy đủ một cấu hình** (5 tầng, kiểm metamodel trên toàn bộ): `scripts/build_full_kg.py` → `<pred-dir>/kg_full_<cfg>.json`;
nạp Neo4j: `python scripts/load_kg_to_neo4j.py <pred-dir>/kg_full_<cfg>.json --replace`.

Γ (môi trường kiểu, Tầng 2) **không viết tay**: `src/mde/schema_from_kg.py::gamma_from_kg` chiếu tầng Tiến trình SAU
khi KG qua metamodel; `build_gamma_from_kg.py --check` xác nhận Γ trên đĩa đúng là phép chiếu của KG hiện tại.

## 4. Năm giai đoạn của pipeline

```
 (1) Dựng tri thức        (2) Truy xuất            (3) Sinh (LLM)          (4) Kiểm chứng ký hiệu        (5) Giải thích / đánh giá
 luật → tầng Pháp lý      Y: đồ thị (REFERS_TO,   khung chuẩn tắc (N)  →  Tầng 1 cú pháp / Tầng 2 Γ     proof trace, REVIEW (M9),
 log  → tầng Tiến trình   DEFINES, MAPS_TO)       + ràng buộc DECLARE     D nghĩa vụ, N1–N4 khung       phễu kiểm chứng, chấm điểm
 ontology → Cầu nối       R: BM25 (đối chứng)                             B rỗng, v2 vi phạm hàng loạt  (B1, McNemar), đối chiếu
 metamodel kiểm tất cả    X: không ngữ cảnh                               Tầng 3 dịch ngược + giám khảo  từng hồ sơ (TN7)
```

| Giai đoạn | Module chính | Script |
|---|---|---|
| 1 | `src/preprocessing/*`, `src/kg/*_builder.py`, `metamodel.py`, `schema_from_kg.py` | `build_cap_graphs.py`, `build_gamma_from_kg.py`, `build_mapping_graph.py`, `check_kg_metamodel.py` |
| 2 | `src/neural/graph_context.py` (Y, Z, BM25 cho R) | — |
| 3 | `src/symbolic/domain_profiles.py` (prompt), `src/evaluation/real_llm_client.py` (vòng sinh–kiểm) | `run_cap_generation.py` |
| 4 | `src/mde/typing_environment.py` (Tầng 1–2), `obligation_gate.py` (D), `norm_frame.py` (N1–N4), `log_grounding.py` (B), `process_checks.py` (v2), `verbalizer_roundtrip.py` (Tầng 3), `declare4py_verifier.py` (engine trên log) | — |
| 5 | `proof_trace.py`, `review_flags.py`, `verification_funnel.py`, `cap_scoring.py`, `constraint_set_checks.py`, `cap_conformance.py` | `run_pipeline.py post` (gồm mọi script phân tích) |

## 5. Thứ tự kiểm trong một vòng sinh (`run_single_rule_with_real_llm`)

```
LLM trả JSON
 → D   obligation_analysis hợp lệ? no_constraint → BASELESS
 → N1  khung chuẩn tắc đúng định dạng?            (chỉ cấu hình N)
 → N2  loại chuẩn tắc diễn đạt được?  không → BASELESS theo code
 → 1–2 Tầng 1 (JSON / danh mục đóng) + Tầng 2 (Γ: activity, thuộc tính, kiểu, miền giá trị C)
 → D   nhất quán phân tích ↔ ràng buộc (phản hồi 1 lần)
 → N3  thời hạn đã trích có trong ràng buộc?
 → N5  mẫu DECLARE hợp loại chuẩn tắc?            (phản hồi mỗi vòng)
 → N4  activity được KG hỗ trợ (MAPS_TO)? (phản hồi 1 lần)
 → B   rỗng trên log? (phản hồi 1 lần)
 → v2  thuộc tính sai mức / năm / vi phạm hàng loạt   (chỉ cấu hình Z)
 → 3   Entity Matcher (số, ngày) + giám khảo dịch ngược → PASSED | BASELESS | sửa lại
Lỗi ở bất kỳ bước nào → phản hồi chẩn đoán cho LLM, sang vòng sau (tối đa max_retry = 5).
```

## 6. Cấu hình (ablation)

| Cấu hình | Khác Y ở điểm nào |
|---|---|
| X | không ngữ cảnh đồ thị |
| **Y** | cấu hình chính v1 (đồ thị + D + B + C + E + Tầng 1–3) |
| Y-noL12 / -noL3 / -retry1 / -noVac / -noDomain / -noDuty | tắt đúng một thành phần |
| R | ngữ cảnh BM25 cùng ngân sách ký tự (B4) |
| N | + khung chuẩn tắc N1–N4 (B6) |
| Z, Z-no* | v2: định nghĩa / phạm vi trong ngữ cảnh, kiểm tầng Tiến trình, ghi chú giám khảo, gợi ý MAPS_TO |

## 7. Cổng kiểm và dấu dữ liệu

- **Trước khi sinh** (`run_pipeline.py pre`): metamodel → Γ khớp KG → cầu nối khớp ontology → in dấu dữ liệu.
- **Phiên bản code**: metadata mỗi file kết quả ghi `code.sha256` (mọi .py trong src/ và scripts/) và mã commit git
  nếu có; `score_cap` báo khi các cấu hình sinh bằng code khác nhau.
- **Khi sinh**: mỗi file kết quả và mỗi khoản ghi `inputs_id` (SHA-256 các file đầu vào); chạy tiếp khi dữ liệu đã
  đổi → dừng. Ghi kết quả nguyên tử (chịu được khoá file OneDrive).
- **Khi chấm**: `score_cap.py` dừng nếu thiếu khoản, còn ERROR, lẫn lần chạy hoặc lẫn phiên bản dữ liệu.

## 8. Trạng thái module so với kế hoạch M1–M11

| Module | Trạng thái |
|---|---|
| M1 tầng Pháp lý, M3 tầng Tiến trình, M5 Graph-RAG, M6 vòng sinh, M7 kiểm trên log, M11 đánh giá | có |
| M2 trích chuẩn tắc | khung chuẩn tắc (N1–N5) + node Norm trong KG |
| M4 nối khái niệm | tầng Cầu nối (MAPS_TO, ontology đã duyệt) |
| M8 kiểm trên Neo4j | `src/kg/cypher_compiler.py`: 17 mẫu, nhóm, điều kiện, điều kiện ngày, thời hạn ngày / tuần / tháng / ngày làm việc / giờ theo Quy định 1182/71 (chưa: 29/02; tháng khi không tính theo lịch). Khớp engine từng hồ sơ: 123/123 luật giả lập (vét cạn + ca biên thời gian), 247/247 luật v1.1 (8 cấu hình × 2 000 hồ sơ) — `scripts/verify_cypher_compiler.py` |
| M9 đối chiếu / REVIEW | nhãn REVIEW (B7) |
| M10 giải thích | proof trace; chưa đánh giá chất lượng giải thích (thuộc phần đánh giá, tạm gác) |

## 9. Kiểm cả tập ràng buộc (B2)

`src/symbolic/constraint_set_checks.py`: mỗi mẫu là một DFA; tích hai DFA, duyệt mọi trạng thái đến được → kết luận
chính xác mọi độ dài vết (CONFLICT, CONFLICT_IF_ACTIVATED, IMPLIES, DUPLICATE). Điều kiện đặt theo quy ước engine
(họ Precedence: trên B; Choice / Exclusive Choice: trên cả A và B; họ Alternate ngắt ở A / B bất kỳ, không xét điều
kiện — cả hai sửa 2026-11-20 khi đối chiếu với engine). `tests/test_set_checks_vs_engine.py` so thẳng với engine
(điều kiện mức hồ sơ và mức event).

## 10. Mã cũ BPIC2017 (tạm vô hiệu)

`experiment_runner.py` tách thành `semantic_equivalence.py`, `cegis_diagnostic.py`, `vanilla_rag_baseline.py`;
dữ liệu bộ đề `benchmark_builder.py` → `bpic2017_benchmark_rules.py` (nội dung giữ nguyên, tên cũ vẫn import được).

## 11. Ghi chú trung thực về Graph-RAG và Neo4j

- **Truy xuất lúc sinh luật đọc KG dạng JSON** (`src/neural/graph_context.py` duyệt cạnh REFERS_TO / DEFINES / USES_TERM
  trên `*_legal_graph*.json`), không truy vấn Neo4j. Neo4j dùng để **xem / trình bày** KG đầy đủ và để **kiểm luật bằng
  Cypher** (M8, khớp engine từng hồ sơ). "Graph-RAG" trong bài = truy xuất theo cấu trúc đồ thị, không phải theo
  vector; so sánh với RAG truyền thống là cấu hình R (BM25, cùng ngân sách ký tự).
- **MAPS_TO có một nguồn**: tầng Cầu nối của KG (`mapping_graph_builder.load_bridge`) — dùng cho gợi ý Z, kiểm N4,
  tín hiệu S2 của REVIEW và KG đầy đủ. Ontology chỉ là đầu vào để DỰNG tầng Cầu nối; `run_pipeline.py pre` kiểm tầng
  này còn khớp ontology + đồ thị.
- **Giám khảo Tầng 3** mặc định dùng cùng model với bộ sinh (rủi ro tự chấm); có tuỳ chọn giám khảo khác model.
