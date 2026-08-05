# Member Role Report - Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Công Hùng |
| MSSV | 01071 |
| Khóa/Lớp | K3 |
| Vai trò chính | Architecture Designer |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File phụ trách | Input | Output | Trạng thái |
| --- | --- | --- | --- | --- |
| Thiết kế kiến trúc multi-agent | `architecture.md` | README và business rules | Sơ đồ agent, handoff, quyền truy cập | Hoàn thành |
| Thiết kế orchestration và contract | `src/graph.py`, `src/state.py`, `src/schemas/` | Case input và báo cáo agent | Luồng fan-out/fan-in, repair, verifier | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp và kiểm thử | Database, policy, batch runner | Pipeline chạy được với PostgreSQL và 50 case demo |

## 3. Kết quả theo vai trò

| Nhiệm vụ | Artifact liên quan | Kết quả | Xác minh |
| --- | --- | --- | --- |
| Xây dựng kiến trúc sáu agent | `architecture.md`, `src/agents/` | Phân tách rõ coordinator, specialist, policy và verifier | E2E test |
| Thiết kế kiểm soát dữ liệu và output | `src/policy/`, `src/verification/`, `src/output/` | Policy quyết định deterministic, output chỉ ghi sau verify | 39 test passed |

Output chính là workflow LangGraph xử lý song song ba specialist, hợp nhất Evidence Board và tạo JSON hợp lệ sau bước xác minh.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Hệ thống cần phân tích tranh chấp Olist bằng nhiều agent nhưng vẫn bảo đảm kết quả tài chính, policy và evidence có thể kiểm chứng.

### Cách triển khai

Coordinator tạo ba task cho Order/Seller, Payment và Delivery agent. Ba nhánh chạy song song, chỉ dùng typed tools, sau đó hợp nhất tại Evidence Board. Policy Engine áp dụng sáu rule theo precedence; Verifier kiểm tra lại dữ liệu PostgreSQL trước khi ghi output atomically. Phiên bản này dùng `qwen/qwen-2.5-7b-instruct`, 7.61B parameters, temperature 0.1.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `CaseInput` từ `input/EC_*.json` và dữ liệu PostgreSQL |
| Output | JSON theo `FinalOutput` |
| Module phụ thuộc | Repository, typed tools, OpenRouter client, Policy Engine |
| Module sử dụng output | Output validator và submission generator |
| Điều kiện lỗi | Thiếu dữ liệu, sai evidence, sai finance/policy hoặc LLM trả sai schema |

### Cách xác minh

```powershell
python -m compileall -q src scripts tests
python -m scripts.validate_inputs
docker compose run --rm app pytest -q
```

- **Kết quả mong đợi:** 50 input hợp lệ và toàn bộ test pass.
- **Kết quả thực tế:** 50 input đúng phân bố `9/9/8/8/8/8`; 39 test passed.
- **Artifact/log:** `tests/`, `trace.jsonl`, `metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Kết quả LLM có thể không ổn định hoặc sai business rule.
- **Phương án cân nhắc:** Để LLM quyết định toàn bộ hoặc kết hợp LLM với deterministic core.
- **Phương án chọn:** LLM phân tích ngữ nghĩa; Policy Engine và Verifier quyết định cuối cùng.
- **Lý do:** Tăng tính đúng đắn, tái lập và khả năng audit.
- **Bằng chứng:** Unit, integration và E2E test đều pass.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Tổng item/payment bị nhân khi order có nhiều item và nhiều payment.
- **Nguyên nhân gốc:** Join trực tiếp hai bảng one-to-many tạo Cartesian multiplication.
- **Cách xử lý:** Aggregate item và payment riêng trước khi ghép.
- **Cách xác minh:** Integration test với order 2-item/2-payment đã pass.
- **Điều học được:** Luôn kiểm tra cardinality trước khi aggregate dữ liệu tài chính.

## 7. Hiểu biết về luồng end-to-end

CSV Olist được import vào PostgreSQL. Batch runner đọc case, Coordinator triage và giao task cho ba specialist chạy song song. Evidence Board hợp nhất báo cáo; Policy Agent áp dụng deterministic rules; Verifier kiểm tra schema, ID, evidence và tài chính. Case hợp lệ được ghi atomically vào `output/`, đồng thời tạo trace và metadata. Cuối cùng validator kiểm tra đủ 50 output trước khi tạo ZIP.

## 8. Cam kết của thành viên

- [x] Nội dung phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end.
- [x] Chỉ ghi kết quả đã được kiểm chứng.
- [x] Báo cáo không chứa API key, token hoặc secret.
- [x] Báo cáo không sao chép báo cáo của thành viên khác.

**Họ và tên:** Nguyễn Công Hùng  
**Ngày xác nhận:** 2026-08-05
