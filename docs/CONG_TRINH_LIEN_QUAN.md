# Công trình liên quan — rà soát ban đầu để định vị đóng góp (2026-11-19)

> **Mức độ tin cậy:** mục 1–2 từ tìm kiếm web (đoạn trích). **Mục 3–4 (2026-11-20): đã đọc toàn văn** 4 bài
> (arXiv / IJCAI); bài benchmark 969 cặp không truy cập được. Nơi đăng của các bản arXiv chưa xác nhận.

## 1. Gần nhất với hệ thống

| ★ | Công trình | Làm gì | Giống mình | Khác mình (theo đoạn trích) |
|---|---|---|---|---|
| ★ | **LLM-Assisted Conformance Checking for Medical Processes** — [Springer, 10.1007/978-3-032-16708-8_14](https://link.springer.com/chapter/10.1007/978-3-032-16708-8_14) | LLM trích quy tắc chuẩn tắc từ hướng dẫn lâm sàng → đo log bệnh nhân có tuân thủ không (đột quỵ) | Cùng khung: văn bản quy phạm → quy tắc → đối chiếu log thật | Hướng dẫn y khoa (không phải luật nhiều văn bản dẫn chiếu chéo); tự mô tả là "bước đầu" |
| ★ | **Bridging Domain Knowledge and Process Discovery Using LLMs** — [arXiv 2408.17316](https://arxiv.org/pdf/2408.17316) | LLM sinh ràng buộc khai báo; kiểm cú pháp và tên activity theo log, sai thì hỏi lại; ca UWV (Hà Lan) | **Vòng sinh → kiểm cú pháp / activity → phản hồi ≈ Tầng 1–2 của mình** | Mục tiêu là *khám phá quy trình* có tri thức miền, không phải kiểm tuân thủ luật |
| ★ | **Extracting declarative constraints … from natural language descriptions with LLMs** — [ScienceDirect S0167923626000163](https://www.sciencedirect.com/science/article/abs/pii/S0167923626000163) | Benchmark câu → DECLARE: 969 cặp, 11 mẫu | Cùng đích DECLARE | Câu đơn lẻ đã "sạch"; không có log, không có khoản không quan sát được, không kiểm trên dữ liệu |
| ★ | **NeuroSTAR: Automata-guided Neuro-symbolic Specification Formalization** — [arXiv 2609.03161](https://arxiv.org/pdf/2609.03161) | NL → LTLf bằng LLM; dùng automata tìm vết mà các đặc tả thay thế bất đồng; thử trên luật giao thông Virginia (có dẫn chiếu chéo) | Luật có dẫn chiếu chéo → logic thời gian hữu hạn; dùng automata để kiểm | Không có log thật / đối chiếu tuân thủ (theo trích đoạn) |
| | LLM-based Process Constraints Generation with Context — [DiVA 1942070](http://www.diva-portal.org/smash/get/diva2:1942070/FULLTEXT01.pdf) | LLM sinh DECLARE từ schema log (± mô tả) cho conformance checking | Sinh DECLARE cho kiểm tuân thủ | Đầu vào là schema log, không phải văn bản luật |
| | Enhancing Legal Compliance and Regulation Analysis with LLMs — [arXiv 2404.17522](https://arxiv.org/pdf/2404.17522) | LLM phân tích tuân thủ / quy định | Miền luật | (chưa rõ — cần đọc) |
| | Unlocking Sustainability Compliance: EU Taxonomy for BPM — [arXiv 2408.11386](https://arxiv.org/pdf/2408.11386) | LLM few-shot phân loại ràng buộc quy định theo chiều quy trình | Văn bản quy định EU ↔ BPM | Phân loại, không trích ràng buộc kiểm được |

## 2. Nền: kiểm tuân thủ trên log, ngôn ngữ quy tắc

- Cross-Instance Regulatory Compliance Checking of Business Process Event Logs — [IEEE 10262376](https://ieeexplore.ieee.org/document/10262376/) (nghĩa vụ trải qua nhiều hồ sơ)
- Efficient Checking of Temporal Compliance Rules Over Business Process Event Logs — [arXiv 2112.04623](https://arxiv.org/pdf/2112.04623)
- Reviewing Conformance Checking Uses for Run-Time Regulatory Compliance — [ResearchGate 380889546](https://www.researchgate.net/publication/380889546_Reviewing_Conformance_Checking_Uses_for_Run-Time_Regulatory_Compliance)
- Evaluation of Compliance Rule Languages for Modelling Regulatory Compliance Requirements — [MDPI](https://www.mdpi.com/2674-113X/2/1/4): **Declare chỉ phủ luồng điều khiển, không phủ đủ dữ liệu / tài nguyên** — giới hạn mình cần thừa nhận (mình có điều kiện dữ liệu một phần).
- Finding Non-compliances with Declarative Process Constraints Through Semantic Technologies — [ResearchGate 333316954](https://www.researchgate.net/publication/333316954_Finding_Non-compliances_with_Declarative_Process_Constraints_Through_Semantic_Technologies) (Declare → SHACL; gần ý metamodel / kiểm tuân thủ ngữ nghĩa)
- Requirements and Challenges for the Application of Process Mining in the Building Permit Review — [Springer](https://link.springer.com/chapter/10.1007/978-3-032-18226-5_24) (chất lượng log cho kiểm tuân thủ)
- Neuro-symbolic pháp lý dùng SMT / ASP: [arXiv 2601.06181](https://arxiv.org/pdf/2601.06181), [arXiv 2512.12109](https://arxiv.org/pdf/2512.12109), [Nature s41598-026-65233-w](https://www.nature.com/articles/s41598-026-65233-w) (parser → AST có kiểu → bộ giải kiểm — cùng kiến trúc, khác miền)

## 3. Đọc toàn văn (2026-11-20)

| Công trình (đã đọc) | Đầu vào → đầu ra | Kiểm LLM thế nào | Có / không (so với mình) |
|---|---|---|---|
| **Norouzifar, Kourani, Dees, van der Aalst** — *Bridging Domain Knowledge and Process Discovery Using LLMs*, [arXiv 2408.17316](https://arxiv.org/abs/2408.17316) (2024; bản mở rộng [arXiv 2510.07161](https://arxiv.org/pdf/2510.07161)) | Mô tả quy trình / phản hồi chuyên gia (UWV, 144 046 hồ sơ) → ràng buộc khai báo cho IMr (8 mẫu kiểu Declare) | Kiểm cú pháp + **tên activity theo log**, lỗi → prompt mới chỉ rõ lỗi (số vòng không nêu) | **Có:** vòng Tầng 1–2 của mình. **Không:** kiểm rỗng / số hồ sơ vi phạm / miền giá trị, đọc ngược, mâu thuẫn giữa ràng buộc, từ chối, **không có chỉ số định lượng** (chỉ so mô hình bằng mắt), không luật, không KG |
| **Saha, Woodlief, Elbaum, Dwyer** — *NeuroSTAR*, [arXiv 2609.03161](https://arxiv.org/abs/2609.03161) (2026) | Yêu cầu NL + thư viện mệnh đề nguyên tử → LTLf; 108 điều luật giao thông Virginia | Cú pháp + mệnh đề ∈ thư viện, sửa lại; nhiều ứng viên → **automata hiệu (Spot) tìm vết phân biệt** (≤ 5/10), giám khảo LLM bỏ phiếu | **Có:** luật thật có dẫn chiếu chéo (cài trực tiếp điều được dẫn bằng cú pháp '§ 46.2-…', không đồ thị); kiểm bằng automata. **Không:** log / vết thật, từ chối; giới hạn chính họ tự nêu là **"AP vocabulary gap"** (thư viện mệnh đề không đủ diễn đạt) ≈ vấn đề tính quan sát được / Γ của mình |
| **Leonardi, Montani, Striani, Canessa, Ferrandi** — *LLM-Orchestrated Conformance Checking in Stroke Care…*, [arXiv 2606.09489](https://arxiv.org/abs/2606.09489) (2026; mở rộng AIME 2025) | Hướng dẫn đột quỵ Ý → 161 quy tắc IF-THEN (NotebookLM) → **lọc còn 50 quy tắc kiểm được trên dữ liệu** → script Python; vết do LLM trích từ 463 giấy ra viện | Bác sĩ duyệt quy tắc (1 vòng sửa prompt) và 20% vết; không kiểm cú pháp / kiểm thử script | **Có:** hiện tượng tính quan sát được (111/161 ≈ 69% bị loại vì dữ liệu không ghi) — nhưng do LLM lọc, **không đo với gold, không có nhãn bẫy, không có mức chuẩn**; chỉ số TCI (% vết tuân thủ), không đo độ đúng của trích xuất. **Không:** KG, dẫn chiếu chéo, hiệu lực thời gian, kiểm rỗng tự động |
| **Fionda, Ielo, Ricca** — *Are LLMs Fluent in Declarative Process Mining?*, [IJCAI 2025](https://www.ijcai.org/proceedings/2025/0501.pdf) | Declare → NL → Declare (dịch hai chiều) trên mô hình Declare **tổng hợp ngẫu nhiên** (5–20 ràng buộc, 3–10 activity) | Đánh giá (không phải vòng sửa): tương đương ngữ nghĩa LTLp (aaltaf), **độ giống trên mọi vết độ dài ≤ 10** (đếm mô hình ASP) | **Có:** ý *đọc ngược để kiểm độ trung thực* (≈ Tầng 3 của mình, nhưng họ dùng để chấm, mình dùng trong vòng sinh trên văn bản luật thật); *so ngữ nghĩa trên vết có giới hạn* (≈ cách kiểm tập ràng buộc). **Không:** văn bản thật, log, luật |
| Benchmark NL → Declare 969 cặp ([ScienceDirect S0167923626000163](https://www.sciencedirect.com/science/article/abs/pii/S0167923626000163)) | — | — | **KHÔNG truy cập được** (403, không thấy bản mở) — chỉ trích dẫn ở mức tóm tắt |

## 4. Định vị đóng góp (cập nhật sau khi đọc toàn văn)

**KHÔNG khẳng định là mới — trích dẫn đúng nguồn:**
- Vòng "LLM sinh → kiểm cú pháp / tên activity theo log → hỏi lại" — Norouzifar et al. 2024.
- Đọc ngược (dịch hai chiều) để kiểm độ trung thực — Fionda et al. IJCAI 2025 (họ dùng để đánh giá).
- So ngữ nghĩa ràng buộc trên vết có giới hạn / automata — Fionda et al. 2025; NeuroSTAR 2026.
- "Hướng dẫn / luật → quy tắc → đối chiếu dữ liệu thật" ở mức khung — Leonardi et al. 2026.
- Hiện tượng phần lớn quy định không kiểm được trên dữ liệu — Leonardi et al. (69% bị loại); NeuroSTAR ("AP vocabulary gap").
- "Graph-RAG tốt hơn RAG" — không mới; chỉ báo theo câu hỏi phụ B4 (cấu hình R).

**Đóng góp có thể bảo vệ (không thấy trong 4 bài đã đọc):**
1. **Đo tính quan sát được một cách có hệ thống:** gold có nhãn bẫy (218 khoản luật EU, 3 positive), mức chuẩn "luôn BASELESS" và tỉ lệ cân bằng — Leonardi et al. chỉ *lọc* bằng LLM, không đo độ đúng của việc lọc; không bài nào đánh giá khả năng *từ chối*.
2. **Log làm tín hiệu kiểm chứng TRONG vòng sinh:** ràng buộc rỗng (0 hồ sơ kích hoạt), vi phạm hàng loạt, miền giá trị thuộc tính — Norouzifar et al. chỉ kiểm tên activity.
3. **Kiểm mâu thuẫn GIỮA các ràng buộc** của các khoản khác nhau (Y v1.1: 2 cặp) — các bài trên so các bản dịch của CÙNG một yêu cầu.
4. **KG có metamodel cho cả hai tầng** + phiên bản luật theo năm + dẫn chiếu chéo nhiều văn bản (EU ↔ Đức) — không bài nào dùng KG; NeuroSTAR chỉ chèn điều được dẫn.
5. **Đánh giá định lượng, đăng ký trước, có ablation và McNemar** trên log thật (43 809 hồ sơ) — Norouzifar et al. không có chỉ số; Leonardi et al. không đo độ đúng trích xuất.
6. **Tài nguyên:** gold CAP–BPIC2018 + tập Đức theo năm.

**Việc tiếp (nếu cần thêm):** tìm "Req2LTL" (đã dùng trong `SemanticDecomposition`), van der Aa et al. CAiSE 2019 (trích xuất Declare từ văn bản, không LLM), [arXiv 2410.03255](https://arxiv.org/pdf/2410.03255) (benchmark LLM cho BPM có nhiệm vụ văn bản → Declare).
