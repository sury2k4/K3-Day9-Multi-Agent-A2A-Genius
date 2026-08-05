# Báo cáo cá nhân — K3 Day 09: Multi-Agent A2A

Phần kỹ thuật dưới đây phản ánh pipeline thực tế của repository này.

## 1. Thông tin cá nhân

| Trường | Nội dung |
| --- | --- |
| Họ và tên | Hoàng Quang Minh |
| MSSV | 2A202601301 |
| Khóa/Lớp | K3 / [Bổ sung lớp] |
| Vai trò | Data/policy pipeline và verification |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi công việc

Tôi phụ trách phần xử lý dữ liệu và quyết định policy xác định:

- `app/db.py`: ingest 9 CSV Olist vào PostgreSQL, schema source/run và truy vấn evidence.
- `app/agents.py`: tạo report Order/Seller, Payment và Delivery từ source rows.
- `app/policy.py`: áp dụng `EC_POLICY_V1`, tính tiền và tạo output candidate.
- `app/verifier.py`: kiểm tra schema, ID, evidence, entity scope, policy và financial resolution.
- `app/graph.py` và `app/main.py`: handoff LangGraph, repair/fallback, ghi output và chạy batch.

Kết quả bàn giao là 50 JSON trong `output/`, `trace.jsonl`, `metadata.json` và
`output.zip` chỉ chứa 50 JSON của batch chính thức.

## 3. Thiết kế kỹ thuật

Mỗi case đi qua các node `case_intake` → `coordinator` → ba nhánh domain song
song → `evidence_join` → `policy_engine` → `policy_agent` → `verifier` →
`output_writer`. Ba domain agent chỉ đọc PostgreSQL; `Policy Engine` là nguồn
quyết định authoritative. Qwen 3.5 9B qua OpenRouter chỉ tạo explanation không
được chấm điểm và không được phép thay đổi issue, refund, responsible party hay
evidence.

Các rule được áp dụng theo đúng thứ tự ưu tiên:

1. canceled/unavailable có payment: hoàn toàn bộ payment cho platform.
2. Giao trễ và seller bàn giao sau `shipping_limit_date`: hoàn freight cho seller vi phạm.
3. Giao trễ nhưng carrier nhận đúng hạn: hoàn freight cho logistics provider.
4. Nhiều payment row khớp item + freight trong sai số `0.10` BRL: giải thích hợp lệ.
5. Giao trong estimated date và payment khớp: bác claim hoàn tiền.

Mọi tiền được cộng từ toàn bộ payment/item rows và làm tròn 2 chữ số. Evidence
chỉ dùng ID dựng được từ CSV: `order`, `item`, `payment`, `seller` và `policy`.

## 4. Quyết định quan trọng

Tôi chọn policy engine xác định thay vì để LLM tự chọn refund. Dataset có khóa
quan hệ rõ ràng, trong khi Olist không có refund ledger hay tracking checkpoint.
Giải pháp này giảm hallucination, tái lập được kết quả và cho phép verifier
đối chiếu từng số tiền/evidence với PostgreSQL.

Tôi cũng giữ completion budget Qwen ở mức 8192 nhưng tắt hidden reasoning cho
phần explanation ngắn. Thử nghiệm reasoning cao/thấp làm model dùng gần hết
completion cho reasoning và trả về structured output bị cắt; điều đó làm tăng
rủi ro hard-gate dù model lớn hơn không thay đổi các trường được chấm.

## 5. Kiểm chứng

Các lệnh đã dùng:

```bash
docker compose run --rm app ingest
docker compose run --rm app run --require-official-batch
docker compose run --rm app validate --require-official-batch
.venv/bin/ruff check app scripts tests
.venv/bin/pytest -q
```

Verifier độc lập tái dựng report từ PostgreSQL rồi so sánh toàn bộ 50 output với
policy engine. Batch hiện tại đạt `50/50`, không có model fallback. ZIP được kiểm
tra có đúng 50 JSON, không có `.gitkeep`, không có directory entry thừa và root
artifact khớp bản sao trong `logging/`.

## 6. Lỗi đã xử lý

- Batch trước có nguy cơ giữ lại output JSON cũ; runner hiện xóa chỉ các
  `output/EC_*.json` không thuộc batch hiện tại trước khi chạy.
- Validator trước chỉ kiểm tra số lượng file; hiện kiểm tra chính xác tập tên
  `EC_001.json` đến `EC_050.json`.
- Repository hiện cache source rows/evidence trong một batch để tránh mở hàng
  trăm kết nối PostgreSQL lặp lại.
- Trace recorder có lock khi ghi JSONL để không trộn dòng giữa các nhánh song song.

## 7. Hiểu biết end-to-end

Input JSON cung cấp `claimed_order_id`. PostgreSQL join order với item và payment;
ba domain report chuyển facts có cấu trúc cho Evidence Join. Policy Engine dùng
facts đó để tạo candidate đầy đủ schema. Verifier kiểm tra lại candidate từ source
rows trước khi Output Writer publish JSON. LangGraph trace mỗi node, còn
Langfuse Cloud nhận callback quan sát khi credentials khả dụng. `logging/` và
root lưu lại trace/metadata của đúng lần chạy mới nhất.

## 8. Cam kết

- [ ] Tôi đã điền họ tên, MSSV và lớp.
- [x] Tôi đã kiểm tra output không chứa secret.
- [x] Tôi đã chạy test và validator sau thay đổi.
- [x] Tôi hiểu policy decision đến từ source data/code, không đến từ lời đoán của LLM.

**Họ và tên:** Hoàng Quang Minh
**Ngày xác nhận:** 2026-08-05
