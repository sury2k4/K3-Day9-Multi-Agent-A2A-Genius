# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                                    |
| --------------- | ---------------------------------------------------------------------------- |
| Họ và tên       | Nguyễn Hoàng Khôi                                                            |
| MSSV            | 2A202601383                                                                  |
| Khóa/Lớp        | K3                                                                            |
| Vai trò chính   | Thiết kế kiến trúc & triển khai toàn bộ pipeline multi-agent (orchestration, data access, policy engine, LLM integration) |
| Ngày hoàn thành | 2026-08-05                                                                    |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------- | -------------------- | ----------------- | ------------------- | ------------ |
| Kiến trúc multi-agent | `architecture.md` | Yêu cầu README mục 7 | Sơ đồ 7-node, bảng vai trò, bảng quyền truy cập dữ liệu, luồng handoff | Hoàn thành |
| Data access layer | `src/data_loader.py` | 9 CSV Olist trong `data/` | `CaseBundle` theo `order_id` (order/items/payments/sellers) + index ID hợp lệ cho Verifier | Hoàn thành |
| Fact extraction theo domain | `src/facts.py` | `CaseBundle` | `order_facts`, `delivery_facts`, `payment_facts` (thuần Python, không qua LLM) | Hoàn thành |
| Rule engine EC_POLICY_V1 | `src/policy_rules.py` | 3 bộ facts trên | `primary_issue`, `root_cause_code`, `responsible_parties`, refund, action theo đúng bảng ưu tiên README mục 4 | Hoàn thành |
| 6 agent + LangGraph orchestration | `src/agents/*.py`, `src/graph.py`, `src/state.py` | `CaseState` (TypedDict) | Handoff tuần tự 7 bước: coordinator_intake → order_seller → delivery → payment → policy → coordinator_finalize → verifier | Hoàn thành |
| LLM client (OpenRouter) | `src/llm_client.py` | System prompt + JSON facts | Narrative 1 câu/agent, có retry + fail-fast khi hết quota | Hoàn thành |
| Batch runner + logging | `main.py`, `src/tracing.py` | `input/EC_001..050.json` | `output/EC_xxx.json`, `logging/trace.jsonl`, `logging/metadata.json` | Hoàn thành |

Toàn bộ các phần trên do tôi trực tiếp thiết kế và code trong phiên làm việc ngày 2026-08-05, chạy thật trên bộ 50 case chính thức do ban tổ chức cấp.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả và bằng chứng |
| ----------- | -------------------------------- | ------------------------ |
| Phát hiện `.gitignore` của repo nhóm đang loại trừ nhầm `logging/trace.jsonl` (file bắt buộc phải nộp theo README mục 8) | Repo chung (ảnh hưởng mọi thành viên khi commit) | Đã xóa dòng `logging/trace.jsonl` khỏi `.gitignore`; xác nhận file này vẫn nằm trong `git ls-files` |
| Sinh 100 case thử nghiệm từ chính `data/*.csv` (không dùng để nộp) để kiểm thử pipeline trước khi có input chính thức | Cá nhân, dùng làm smoke test | Tất cả `claimed_order_id` được đối chiếu tồn tại thật trong `orders.csv` trước khi dùng |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| ------------------------ | ------------------------------ | -------------------- | ---------------- |
| Xây dựng và chạy pipeline multi-agent trên 50 case chính thức | `main.py` → `output/EC_001..050.json` | 50/50 file output đúng schema mục 6 README | Script validate độc lập (đối chiếu `data/*.csv`): 50 file, **0 lỗi** (primary_issue hợp lệ, entity/evidence/causes/actions đúng giới hạn, evidence ID tồn tại thật, tiền làm tròn 2 chữ số, `case_status` khớp refund) |
| Phát hiện và sửa lỗi model OpenRouter bị gỡ khỏi free tier, sau đó là lỗi hết hạn mức ngày | `src/config.py`, `src/llm_client.py` | Đổi sang `nvidia/nemotron-nano-9b-v2:free` (9B, dense); thêm cơ chế fail-fast khi gặp lỗi hạn mức theo ngày | So sánh thời gian chạy: trước khi sửa một case bị treo >150s do retry vô ích; sau khi sửa, batch 50 case hoàn tất trong 20.5s (`logging/metadata.json.run.elapsed_seconds`) |

Một output cụ thể tạo ra: `output/EC_001.json` — phân loại `late_delivery_seller`, xác định đúng seller vi phạm `shipping_limit_date`, `recommended_refund_brl` bằng đúng tổng `freight_value` của đơn, `evidence_ids` đều trỏ tới bản ghi có thật trong `data/olist_order_items_dataset.csv` và `data/olist_sellers_dataset.csv`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần việc của tôi giải quyết toàn bộ pipeline: từ việc đọc 1 case khiếu nại (`input/EC_xxx.json`), đối chiếu nhiều bảng CSV Olist, cho tới khi xuất ra kết luận đúng schema (`output/EC_xxx.json`) — đúng như yêu cầu ở README mục 1: nhiều agent phải phân tích từng domain dữ liệu riêng rồi handoff bằng chứng cho một agent điều phối, ưu tiên dữ liệu kiểm chứng được thay vì tin lời khiếu nại hoặc tự bịa sự kiện.

### Cách triển khai

Nguyên tắc cốt lõi: **tách rời phần tính toán xác định khỏi phần suy luận ngôn ngữ**.

- Mọi con số và ID xuất hiện trong output (tổng tiền, entity id, evidence id, root cause) được tính bằng Python thuần từ CSV (`facts.py`, `policy_rules.py`).
- LLM (qua `llm_client.py`) chỉ được giao đọc facts đã tính sẵn và viết 1 câu diễn giải tiếng Việt, lưu vào `trace.jsonl` — không có quyền thay đổi kết quả.
- 7 node LangGraph chạy tuần tự, mỗi agent chỉ được truy cập đúng domain dữ liệu của mình (bảng quyền truy cập chi tiết trong `architecture.md` mục 4): Order & Seller Agent chỉ đọc `orders.csv` + `order_items.csv` + `sellers.csv`; Delivery Agent chỉ đọc ngày giao trong `orders.csv`; Payment Agent chỉ đọc `order_payments.csv` + giá/phí ship trong `order_items.csv`; Policy Agent không đọc CSV nào, chỉ nhận facts đã handoff.
- Policy Agent áp đúng bảng ưu tiên 6 nhánh của `EC_POLICY_V1` (canceled/unavailable trước, sau đó late_delivery_seller > late_delivery_logistics > valid_split_payment > unsupported_late_claim).
- Verifier Agent là gate xác định cuối: kiểm tra giới hạn mảng, tồn tại evidence ID trong index CSV, khoảng `confidence`, làm tròn tiền, tính nhất quán `case_status` ↔ refund — tự sửa khi sai, LLM chỉ thêm 1 câu nhận xét cho trace.

### Input, output và contract

| Thành phần | Mô tả |
| ------------ | ------- |
| Input | `input/EC_xxx.json`: `case_id`, `opened_at`, `customer_request.{language, message, claimed_order_id}`, `policy_version` |
| Output | `output/EC_xxx.json` theo đúng schema mục 6 README (assessment, affected_entities, root_cause_analysis, evidence_ids, financial_resolution, resolution_actions) |
| Module phụ thuộc | `data/*.csv` (9 file Olist) |
| Module sử dụng output | `main.py` ghi file; không có module downstream nào khác trong phạm vi bài lab |
| Điều kiện lỗi cần xử lý | (1) `claimed_order_id` không tồn tại trong `orders.csv` → fallback `no_action`, `confidence` thấp, `evidence_ids` rỗng thay vì bịa bằng chứng; (2) LLM lỗi hoặc hết hạn mức API → pipeline vẫn tiếp tục với facts xác định, chỉ để trống phần narrative, không chặn việc ghi output |

### Cách xác minh

```bash
python main.py                              # chạy toàn bộ 50 case, ghi output/ + logging/
python main.py EC_001 EC_009 EC_017          # smoke test một tập con
```

- **Kết quả mong đợi:** 50 file `output/EC_001.json`..`EC_050.json`, mỗi file đúng schema, `logging/trace.jsonl` có 7 dòng/case (350 dòng), `logging/metadata.json` phản ánh đúng model/framework/runtime của lượt chạy mới nhất.
- **Kết quả thực tế:** `logging/metadata.json` ghi `cases_total: 50, cases_ok: 50, cases_error: 0, elapsed_seconds: 20.5`; script validate độc lập trên toàn bộ `output/*.json` (đối chiếu ngược lại `data/*.csv`) báo **0 lỗi**.
- **Artifact/log:** `output/EC_001.json`, `logging/trace.jsonl` (350 dòng), `logging/metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần quyết định LLM (model ≤10B theo ràng buộc bài lab) sẽ đóng vai trò gì trong pipeline — quyết định toàn bộ kết luận, hay chỉ hỗ trợ một phần — trong khi 90% trọng số chấm điểm (mục 8 README) phụ thuộc vào số liệu tài chính và evidence ID chính xác tuyệt đối.
- **Các phương án đã cân nhắc:**
  1. Để LLM tự đọc dữ liệu CSV liên quan và tự suy luận toàn bộ `primary_issue`, số tiền hoàn, evidence ID.
  2. Tách bạch: mọi số liệu/ID được tính bằng Python xác định theo đúng bảng luật `EC_POLICY_V1`; LLM chỉ nhận facts đã tính sẵn để viết narrative, không được thay đổi kết quả.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Bảng luật `EC_POLICY_V1` là quyết định cứng, không mơ hồ (README xác nhận bộ 50 case chính thức không có tình huống mơ hồ giữa nhiều seller); để một model ≤10B tự tính tổng tiền, làm tròn, hoặc tự bịa evidence ID sẽ tạo rủi ro sai số học và hallucination ảnh hưởng trực tiếp tới 90% điểm case (primary_issue/confidence 20%, entities 20%, root cause 15%, evidence 15%, financial 20%). Tách bạch giúp output luôn đúng bất kể LLM có sẵn sàng hay không.
- **Bằng chứng quyết định phù hợp:** Trong lượt chạy thật, tài khoản OpenRouter hết hạn mức miễn phí theo ngày khiến toàn bộ 300/300 lời gọi LLM của batch 50 case thất bại (xem mục 6), nhưng script validate độc lập trên `output/` vẫn báo **0 lỗi** — chứng minh kiến trúc tách bạch giúp kết quả chấm điểm không phụ thuộc vào tính sẵn sàng của LLM bên ngoài.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  - Lỗi 1: `{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: qwen/qwen-2.5-7b-instruct","code":404}}`
  - Lỗi 2 (sau khi đổi model): `RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit exceeded: free-models-per-day. Add 5 credits to unlock 1000 free model requests per day', 'code': 429, ...}}`
- **Lệnh hoặc bước tái hiện:** `python main.py EC_001 EC_009 EC_017` (smoke test) rồi `python main.py` (chạy 50 case) — theo dõi `logging/trace.jsonl` thấy thời gian mỗi case tăng dần bất thường (28.6s → 110s → 155s → 157s).
- **Nguyên nhân gốc:** (1) OpenRouter đã gỡ `qwen/qwen-2.5-7b-instruct:free` khỏi danh sách model miễn phí; (2) tài khoản OpenRouter miễn phí chỉ có hạn mức 50 request/ngày, đã dùng hết trong lúc test thăm dò model, và code khi đó retry 4 lần kèm exponential backoff cho **mọi** loại lỗi kể cả lỗi hạn mức theo ngày (vốn không thể tự hết trong vài giây), gây lãng phí thời gian tích lũy qua từng case.
- **Cách xử lý:**
  1. Gọi trực tiếp `GET /api/v1/models` của OpenRouter để tìm model free hiện còn khả dụng và ≤10B tham số dense → chọn `nvidia/nemotron-nano-9b-v2:free` (9B).
  2. Thêm cờ `_daily_quota_exhausted` trong `src/llm_client.py`: khi gặp `RateLimitError` có nội dung "per-day"/"daily", dừng retry ngay và bỏ qua tức thì mọi lời gọi LLM còn lại trong lượt chạy đó thay vì lặp lại một lỗi chắc chắn không tự hết.
  3. Giảm `MAX_RETRIES` (4→3) và `REQUEST_TIMEOUT_S` (60→25) trong `src/config.py` để các lỗi tạm thời khác cũng thất bại nhanh hơn.
- **Cách xác minh sau khi sửa:** Chạy lại `python main.py`; `logging/metadata.json` ghi nhận `elapsed_seconds: 20.5` cho cả 50 case (thay vì có nguy cơ treo hàng chục phút); script validate độc lập trên `output/*.json` vẫn báo 0 lỗi.
- **Điều học được:** Với LLM API free-tier, cần phân biệt lỗi tạm thời (đáng retry) và lỗi hạn mức cứng theo ngày (retry không có tác dụng, nên fail-fast); đồng thời không nên để phần output được chấm điểm phụ thuộc vào tính sẵn sàng của một dịch vụ LLM bên ngoài.

Chưa xử lý xong (tại thời điểm viết báo cáo):

- **Phạm vi bị ảnh hưởng:** `logging/trace.jsonl` của lượt chạy 50 case chính thức gần nhất có narrative LLM rỗng ở hầu hết các bước do tài khoản OpenRouter hết hạn mức miễn phí trong ngày (reset sau ~19 giờ, không kịp trước checkpoint), dù `output/` vẫn đúng 100%.
- **Những gì đã loại trừ:** Không phải lỗi code (đã xác nhận bằng script validate 0 lỗi trên output); không phải lỗi mạng/timeout (lỗi 429 trả về gần như tức thì kèm rõ nguyên nhân "free-models-per-day").
- **Bước tiếp theo:** Nạp thêm credit vào tài khoản OpenRouter (theo gợi ý chính lỗi 429 đưa ra: "Add 5 credits to unlock 1000 free model requests per day") rồi chạy lại `python main.py` để `trace.jsonl` có đầy đủ narrative LLM thật cho cả 50 case trước khi nộp bài.

## 7. Hiểu biết về luồng end-to-end

> Ghi chú: bộ câu hỏi gốc của mẫu báo cáo (Crossref, vector index, retrieval/answer quality...) thuộc về một bài lab RAG/data-quality khác, không khớp với bài Multi-Agent Dispute Resolution này. Tôi trả lời theo đúng tinh thần từng câu hỏi nhưng ánh xạ sang khái niệm tương ứng của bài lab hiện tại để không bịa nội dung không có thật.

Giải thích ngắn gọn bằng lời của tôi:

1. **Dữ liệu đi từ CSV Olist đến output JSON như thế nào?** `data/*.csv` được nạp một lần vào bộ nhớ (`data_loader.py`), lập index theo `order_id`/`item_id`/`payment_id`/`seller_id`. Với mỗi case, `claimed_order_id` được tra cứu để lấy `CaseBundle`; từng agent tính `facts` riêng theo domain (`facts.py`); `policy_rules.py` áp bảng luật để ra kết luận; Coordinator gộp lại đúng schema; Verifier đối chiếu ngược lại các index CSV trước khi ghi `output/EC_xxx.json`.
2. **"Evaluation set" và "ground-truth" tương đương ở đây là gì?** Bộ 50 case `input/EC_001..050.json` đóng vai trò evaluation set; ground-truth chính là dữ liệu Olist CSV thật — mọi `evidence_id` bắt buộc phải trỏ tới một bản ghi có thật (được Verifier Agent đối chiếu trực tiếp với `valid_order_ids`/`valid_item_keys`/`valid_payment_keys`/`valid_seller_ids` nạp từ CSV), không được tự sinh.
3. **Quality checks khác gì so với một hệ thống có "freshness monitoring"?** Bài lab này dùng dữ liệu tĩnh (không có khái niệm dữ liệu mới liên tục đổ về), nên không có freshness monitoring. Quality check ở đây là Verifier Agent chạy **sau mỗi case** để kiểm tra tồn tại evidence ID, giới hạn số lượng mảng, khoảng `confidence`, làm tròn tiền, và tính nhất quán `case_status` ↔ refund — kiểm tra theo từng lần chạy, không theo lịch định kỳ.
4. **Vì sao phải dùng cùng một bộ input cho mọi lần chạy (kể cả trước/sau khi sửa lỗi)?** Khi đổi model do lỗi 404 rồi lỗi 429, tôi luôn chạy lại trên đúng cùng 50 file `input/EC_001..050.json` để có thể so sánh công bằng kết quả trước và sau khi sửa lỗi (số case chạy thành công, thời gian chạy, số lỗi validate) — nếu đổi input giữa các lần chạy sẽ không biết thay đổi kết quả là do sửa lỗi hay do input khác đi.
5. **"Sửa lỗi" (khắc phục blocker) được coi là thành công dựa trên artifact/metric nào?** Dựa trên hai bằng chứng cụ thể: (a) `logging/metadata.json` với `cases_ok: 50, cases_error: 0, elapsed_seconds: 20.5` (so với việc bị treo hàng chục/hàng trăm giây mỗi case trước khi sửa); (b) script validate độc lập chạy trên toàn bộ `output/EC_001..050.json`, đối chiếu ngược lại `data/*.csv`, báo **0 lỗi** ở mọi tiêu chí (schema, giới hạn mảng, evidence tồn tại thật, làm tròn tiền, nhất quán refund/case_status).

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Hoàng Khôi
**Ngày xác nhận:** 2026-08-05
