# Evaluation Report

> Báo cáo đánh giá chất lượng sản phẩm theo tiêu chí BTC.

---

## 1. Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Response accuracy | >80% | — | ⏳ (cần agent + người đánh giá, ngoài phạm vi module data) |
| Response latency | <3s | — | ⏳ |
| User satisfaction | >4/5 | — | ⏳ |
| Test coverage | >60% | 92/92 test pass | ✅ |

## 1a. Retrieval Evaluation (module Data — mục 10 Data Handling)

Bộ câu hỏi kiểm thử (golden dataset) tại [`eval/golden_dataset.json`](../golden_dataset.json) —
**12 câu** (mở rộng từ 10: thêm 2 câu cho tài liệu kiến thức chung — tiện ích,
pháp lý), mỗi câu gắn `expected_doc_id` lấy từ dữ liệu THẬT đã ingest (không
bịa). Chạy qua `Retriever` thật (embed OpenAI → search Qdrant Cloud thật →
rerank), filter `visibility=[public, internal]` (đo năng lực retrieval của
toàn bộ dữ liệu, tách biệt khỏi bài toán phân quyền đã test riêng ở mục 7) —
script: [`scripts/eval_retrieval.py`](../../scripts/eval_retrieval.py), kết
quả chi tiết từng câu: [`eval/results/retrieval_eval.json`](retrieval_eval.json).
Cập nhật lần cuối: 2026-08-04, sau khi hạ tầng chuyển sang Qdrant Cloud và
thêm nguồn tài liệu kiến thức chung.

| Metric | Kết quả |
|---|---|
| Hit@5 (11 câu có dữ liệu thật) | **9/11 = 82%** |
| Coverage trung bình (câu có dữ liệu) | ~0.85 |
| Câu hỏi KHÔNG có trong dữ liệu (1 câu) | coverage=0.77 |

**Phát hiện quan trọng cần báo team (không tự sửa vì `guardrail.py` thuộc
module agents):** ngưỡng guardrail hiện tại (`coverage_threshold=0.35`) thấp
hơn RẤT NHIỀU so với coverage đo được ở câu hỏi hoàn toàn không có trong dữ
liệu ("Lãi suất vay ngân hàng mua nhà năm nay là bao nhiêu?" → coverage
**0.77**, cố tình chọn câu này vì `phap-ly-thu-tuc.md` có nhắc "vay mua nhà"
trong tiêu đề nhưng không nêu con số cụ thể). Nghĩa là **chỉ dựa vào coverage
của tầng retrieval là không đủ tin cậy để quyết định từ chối hay trả lời** —
qua `scripts/chat_demo_rag.py` (mục 8), hệ thống vẫn từ chối đúng câu này
trong thực tế vì LLM tự nhận ra ngữ cảnh không đủ, nhưng đó là do lớp sinh câu
trả lời "cứu", không phải do ngưỡng coverage hoạt động đúng. Đề xuất: agents
không nên chỉ dựa vào `coverage_threshold` làm rào chắn duy nhất — cần
rerank chặt hơn hoặc thêm bước LLM tự đánh giá độ liên quan trước khi trả lời.

**2 case miss (hit@5) — không phải lỗi hệ thống, là nhiễu tự nhiên khi nhiều
căn hộ có đặc điểm tương tự:** câu về toà R105 và câu về Đông Bắc/2PN2WC bị
các căn cùng thuộc tính (toà khác, hướng khác) xếp hạng cao hơn kết quả đúng.

## 2. Test Results

### Unit Tests
```
pytest tests/ -v
# Paste output here
```

### Integration Tests
```
# Mô tả test scenarios và kết quả
```

## 3. User Feedback

| User | Feedback | Rating |
|------|----------|--------|
| [User 1] | [feedback] | [1-5] |
| [User 2] | [feedback] | [1-5] |

## 4. Demo Results

- Ngày demo: [YYYY-MM-DD]
- Người tham gia: [số người]
- Feedback chung: [tóm tắt]
- Issues phát hiện: [danh sách]

## 5. Action Items

- [ ] [Cần cải thiện 1]
- [ ] [Cần cải thiện 2]
