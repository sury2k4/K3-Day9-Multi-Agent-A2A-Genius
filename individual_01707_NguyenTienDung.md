# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                          |
| --------------- | --------------------------------- |
| Họ và tên       | Nguyễn Tiến Dũng                  |
| MSSV            | 2A202601707                       |
| Khóa/Lớp        | K3 / E403                         |
| Vai trò chính   | Triển khai pipeline multi-agent, policy, runner & nộp output |
| Ngày hoàn thành | 2026-08-05                        |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ---------------- | ---------- |
| Cấu hình runtime & model ≤10B | `src/config.py`, `.env.example`, `logging/metadata.json` | API key OpenRouter/Langfuse (chỉ trong `.env`) | Model name trong code + metadata | Hoàn thành |
| PostgreSQL + ingest Olist CSV | `docker-compose.yml`, `src/db/*`, `scripts/ingest_data.py` | `data/*.csv` | Bảng `orders`, `order_items`, `order_payments`, … | Hoàn thành |
| Domain agents (Order/Payment/Delivery) | `src/agents/domain.py`, `src/db/queries.py` | `order_id` từ case | Report fact có cấu trúc | Hoàn thành |
| Policy EC_POLICY_V1 + Verifier | `src/policy/ec_policy_v1.py`, `src/policy/verify.py` | Domain reports | Candidate output JSON | Hoàn thành |
| LangGraph orchestration | `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/graph.py` | Case JSON | Luồng handoff agent | Hoàn thành |
| Batch runner + output nộp bài | `scripts/run_all_cases.py`, `output/`, `output.zip` | `input/EC_001..EC_050.json` | 50 JSON + zip đúng `output/EC_*.json` | Hoàn thành |
| Observability Langfuse + local trace | `src/observability/*`, `logging/trace.jsonl` | Mỗi lần chạy case | Trace UI + `trace.jsonl` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Đồng bộ input chính thức từ đề / nhánh nhóm | Module input của nhóm | Thay practice input bằng 50 case bài cấp |
| Chỉnh cấu trúc zip nộp điểm | Nộp bài collective | Zip chứa path `output/EC_001.json` … `output/EC_050.json` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Nạp dữ liệu Olist vào Postgres | `scripts/ingest_data.py` | ~99k orders, payments, items… | Query `SELECT COUNT(*) FROM orders` |
| Chạy full graph 50 case | `scripts/run_all_cases.py` | `output/EC_001.json` … `EC_050.json` | Verifier pass 50/50 trong log runner |
| Xuất file nộp chấm | `output.zip` | Đúng 50 file dưới prefix `output/` | Portal nhận zip (không còn lỗi cấu trúc) |
| Ghi metadata & trace | `logging/metadata.json`, `logging/trace.jsonl` | Model/framework/runtime + 50 dòng trace | Mở file logging; xem Langfuse Tracing |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

File `output/EC_001.json` (và bộ 50 file tương ứng): với order giao trễ do seller bàn giao sau `shipping_limit_date`, hệ thống kết luận `late_delivery_seller`, hoàn `freight_total_brl`, action `refund_freight`, kèm evidence `order:` / `item:` / `payment:` / `seller:` / `policy:SELLER_HANDOFF_AFTER_LIMIT`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Trong khiếu nại e-commerce, không thể tin một chiều lời khách. Cần đối chiếu nhiều nguồn (order, item, payment, delivery), áp `EC_POLICY_V1` theo thứ tự ưu tiên, rồi xuất JSON đúng schema để chấm. Đồng thời phải có multi-agent handoff thật (không nhét hết vào một prompt) và có thể quan sát bằng Langfuse.

### Cách triển khai

1. Ingest CSV Olist vào PostgreSQL (Docker).
2. LangGraph nhận case → Coordinator fan-out 3 domain agent đọc SQL song song.
3. Evidence Join gộp fact → Policy áp 6 rule deterministic (canceled/unavailable → late seller/logistics → split payment → reject late claim).
4. Verifier chạy lại policy và kiểm schema/ID/tiền trước khi ghi file.
5. Model ≤10B (khai báo trong `src/config.py`) chỉ hỗ trợ tinh chỉnh confidence; không được bịa evidence. Join/tính tiền/policy nằm trong code.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `input/EC_NNN.json`: `case_id`, `opened_at`, `customer_request.claimed_order_id`, `policy_version` |
| Output | `output/EC_NNN.json`: assessment, affected_entities, root_cause_analysis, evidence_ids, financial_resolution, resolution_actions |
| Module phụ thuộc | PostgreSQL Olist, OpenRouter (optional refine), Langfuse |
| Module sử dụng output | Portal chấm điểm (zip `output/`), audit `trace.jsonl` |
| Điều kiện lỗi cần xử lý | Order không có item (unavailable): totals = 0; verification fail → repair 1 vòng rồi fail có kiểm soát |

### Cách xác minh

```powershell
docker compose up -d
.\.venv\Scripts\python scripts\ingest_data.py
.\.venv\Scripts\python scripts\run_all_cases.py
.\.venv\Scripts\python scripts\langfuse_smoke.py
```

- **Kết quả mong đợi:** 50 output JSON; verifier pass; Langfuse có `case:EC_*`.
- **Kết quả thực tế:** Runner báo `Failed verifications: 0/50`; portal nhận zip; điểm lab đạt khoảng 90–94 tùy lần chỉnh evidence/entity (đã học được không cắt entity quá tay).
- **Artifact/log:** `output/`, `output.zip`, `logging/trace.jsonl`, `logging/metadata.json` (không chứa secret).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Dùng LLM sinh toàn bộ kết luận case, hay khóa quyết định bằng rule deterministic trên SQL?
- **Các phương án đã cân nhắc:** (1) LLM tự suy luận issue/refund từ message khách; (2) SQL + `EC_POLICY_V1` deterministic, LLM chỉ hỗ trợ phụ.
- **Phương án đã chọn:** Phương án (2).
- **Lý do:** Đề yêu cầu ưu tiên dữ liệu kiểm chứng; evidence bịa = false positive; model bị giới hạn ≤10B; reproducibility cao hơn.
- **Bằng chứng quyết định phù hợp:** Cùng input chính thức chạy lại cho cùng issue/refund; thay model (Llama/Qwen) gần như không đổi primary_issue/tiền — đúng kỳ vọng khi policy nằm trong code.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Portal báo `ZIP phải chứa đúng output/EC_001.json đến output/EC_050.json.`
- **Lệnh hoặc bước tái hiện:** Nén bằng cách zip thẳng các file `EC_*.json` ở root archive.
- **Nguyên nhân gốc:** Thiếu thư mục prefix `output/` bên trong zip.
- **Cách xử lý:** Tạo zip với `arcname=output/EC_xxx.json`.
- **Cách xác minh sau khi sửa:** Portal nhận file và chấm điểm được.
- **Điều học được:** Format nộp bài cũng là một phần contract; đúng schema JSON thôi chưa đủ.

Một lỗi khác đã gặp: cắt `seller_ids`/`item_ids` khỏi entities để “gọn evidence” làm điểm tụt mạnh (~94 → ~91). Đã khôi phục đủ entity liên quan order.

## 7. Hiểu biết về luồng end-to-end

(Các câu trong template gốc thuộc lab khác; dưới đây là luồng Day 9 — Multi-Agent Olist Dispute.)

1. **Dữ liệu đi đâu?** CSV Olist trong `data/` được ingest vào PostgreSQL; mỗi case input mang `claimed_order_id` để agent query/join.
2. **Đánh giá chất lượng thế nào?** Portal chấm 50 output theo 6 nhóm: assessment+confidence, entities, root cause/parties, evidence, financial, actions; điểm trung bình các case.
3. **Quality checks khác monitoring chỗ nào?** Verifier trong graph kiểm schema/ID/policy/tiền trước khi ghi `output/`; Langfuse + `trace.jsonl` dùng để quan sát runtime, không thay verifier.
4. **Vì sao phải dùng đúng bộ input chính thức?** Ground-truth/chấm điểm gắn với đúng 50 `claimed_order_id` bài cấp; tự gen practice chỉ để thử pipeline, không nộp.
5. **Repair/thành công dựa trên gì?** Verification `passed=true`, đủ 50 JSON, zip đúng cấu trúc; Langfuse có trace `case:EC_*` của lượt chạy mới nhất.

**Câu trả lời (tóm tắt):** Pipeline = ingest Postgres → LangGraph multi-agent đọc SQL → policy deterministic → verifier → output JSON + trace; thành công khi 50 case hợp lệ theo contract đề và có thể tái lập bằng runner.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Tiến Dũng  
**Ngày xác nhận:** 2026-08-05
