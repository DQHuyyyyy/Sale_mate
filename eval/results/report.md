# Báo cáo Eval — SalesMate

> Chạy thật trên hệ thống sống: Qdrant Cloud + OpenAI thật, không mock. Cập
> nhật gần nhất: 2026-08-13. Tái tạo lại bằng `python -m src.cli eval
> retrieval` (đo retrieval) — phần "test case manual" bên dưới chạy trực tiếp
> `AgentService.answer()` (đầu-cuối, có generate + guardrail).

## 1. Retrieval — bộ câu hỏi vàng (35 câu, `eval/golden_dataset.json`)

```
Hit@n     : 20/28 = 71%   (7 câu còn lại là case out-of-context/phân quyền
                            không đo bằng expected_doc_id)
Ngưỡng coverage guardrail : 0.35
Coverage câu CÓ dữ liệu   : 0.744 – 1.000
Coverage câu KHÔNG dữ liệu: 0.629 – 0.933
```

**Phát hiện quan trọng (không phải bug mới, đã ghi nhận từ 11/08 — vẫn đúng
sau các lần sửa data gần nhất):** khoảng coverage của câu CÓ dữ liệu và câu
KHÔNG có dữ liệu **chồng lấn nhau** — không có ngưỡng `COVERAGE_THRESHOLD` nào
tách được hai nhóm một cách tin cậy. Hệ thống vẫn từ chối đúng các câu ngoài
phạm vi, nhưng cơ chế thật sự chặn là **LLM tự nhận ra thiếu dữ liệu ở bước
generate**, không phải ngưỡng coverage ở bước retrieval. Xem chi tiết từng câu:
[`retrieval_eval.json`](retrieval_eval.json).

## 2. Test case thủ công — agent thật đầu-cuối (6 câu, đủ điều kiện "≥5 test
case, output thực tế")

Gọi thẳng `AgentService.answer()` (đường thật, không stub) — model thật, Qdrant
Cloud thật, mã nguồn: `scripts` chạy tay, kết quả thô lưu ở
[`manual_eval_results.json`](manual_eval_results.json) trong lần chạy này.

### EV-001 — tra_cuu_đơn — ✅ đúng

> **Hỏi:** Căn hộ VOP398 tại tòa R103 có giá bán bao nhiêu tiền?
>
> **Trả lời:** Căn hộ VOP398 tại tòa R103 có giá bán là **3,1 tỷ đồng** và
> hiện đang còn trống [VOP398].
>
> **Nguồn:** `inventory:postgres` (tool tra tồn kho thật) + 5 tin meeyland liên
> quan tòa R103.

Đúng số liệu, có trích nguồn tool (giá/tình trạng đi qua tool tra CSDL thật,
đúng nguyên tắc "không bịa số" — không lấy giá từ vector store đã cũ).

### EV-006 — ràng_buộc_số — ✅ đúng

> **Hỏi:** Tìm căn hộ 2 phòng ngủ giá từ 3.0 tỷ đến 3.6 tỷ tại tòa S2
>
> **Trả lời:** Liệt kê đúng 3 căn khớp cả 3 điều kiện (phòng ngủ, khoảng giá,
> tòa): VOP118 (55m², 3,3 tỷ), VOP205 (55m², 3,26 tỷ), VOP639 (56m², 3,55 tỷ)
> — mỗi căn kèm trích nguồn `[mã căn]`.

Lọc kết hợp nhiều điều kiện đúng — xác nhận field cấu trúc (`price`/`building`/
`num_bedrooms`) hoạt động thật trên dữ liệu production, không chỉ trên test.

### EV-PERM-1 — phân_quyền — ✅ đúng

> **Hỏi:** Căn hộ VOP103 còn trống không, tình trạng thế nào?
>
> **Trả lời:** Căn hộ VOP103 hiện đã **được bán** rồi bạn nhé [VOP103].
>
> **Nguồn:** `inventory:postgres`.

Trạng thái còn/hết tra trực tiếp CSDL thật tại thời điểm hỏi (không phải bản
chụp Qdrant có thể cũ) — đúng thiết kế đã ghi trong `CLAUDE.md`.

### EV-NEG-1 — câu_hỏi_bẫy_out_of_context — ✅ đúng (từ chối đúng)

> **Hỏi:** Lãi suất vay ngân hàng hiện nay là bao nhiêu phần trăm?
>
> **Trả lời:** "Mình chưa có đủ dữ liệu để trả lời chính xác câu này..." —
> **từ chối đúng**, không bịa số lãi suất.

Dữ liệu thật sự không có case này (cố tình không viết vào tài liệu để làm câu
bẫy) — guardrail hoạt động đúng thiết kế.

### EV-KNOW-1 — mới_nguồn_dữ_liệu — ⚠️ từ chối SAI (dữ liệu có thật, retrieval không kéo trúng)

> **Hỏi:** Phí gửi ô tô hàng tháng ở khu Sapphire là bao nhiêu?
>
> **Trả lời:** "Mình chưa có đủ dữ liệu để trả lời chính xác câu này..." — **sai**,
> dữ liệu THẬT SỰ CÓ (tài liệu `knowledge:bang-gia-van-ban`, mục "Phí gửi xe":
> *"Ô tô | 1.250.000 đồng/tháng/xe"*, đã verify trực tiếp trên Qdrant Cloud).

**Nguyên nhân:** 5 chunk retrieval đều là tin đăng meeyland (`meeyland:*`),
không chunk nào thuộc tài liệu bảng giá — trùng đúng phát hiện đã ghi trong
`WORKLOG.md` ngày 11/08: câu hỏi tiện ích/phí dịch vụ dùng từ ngữ chung chung
dễ bị 700+ chunk tin đăng meeyland áp đảo trong top-n so với ~70 chunk tài
liệu kiến thức. Đây là **giới hạn chất lượng retrieval đã biết**, không phải
lỗi thiếu dữ liệu — báo lại để Phúc (chủ `src/rag/`) cân nhắc rerank/boost
theo loại tài liệu.

### EV-PROJ-1 — phân_biệt_dự_án — ⚠️ từ chối SAI (cùng nguyên nhân)

> **Hỏi:** Chính sách bán hàng dự án OCP2 (The Empire) hiện nay thế nào?
>
> **Trả lời:** "Mình chưa có đủ dữ liệu..." — **sai**, tài liệu
> `knowledge:chinh-sach-ban-hang-ocp2` tồn tại thật trong Qdrant (ingest ngày
> 11/08, verify retrieval riêng lẻ qua `src.cli eval retrieval` cho hit đúng
> ở EV-018 với cách diễn đạt khác — "chính sách bán hàng V.Ocean Park 2 chiết
> khấu"). Cùng nguyên nhân với EV-KNOW-1: câu hỏi diễn đạt tự nhiên (không có
> từ khoá "chiết khấu") bị chunk tin đăng meeyland lấn át.

**Kết luận 2 case ⚠️:** hệ thống **không bịa số** ngay cả khi retrieval thất
bại — đúng nguyên tắc cốt lõi của dự án — nhưng trải nghiệm người dùng bị ảnh
hưởng (từ chối oan). Đây là hướng cải thiện tiếp theo cho tầng RAG/rerank, đã
báo cho chủ module liên quan, không thuộc phạm vi sửa của Data Handling (dữ
liệu đã đúng, đã verify tồn tại thật trong Qdrant).

## 3. Tóm tắt

| | |
|---|---|
| Retrieval hit@n (bộ 35 câu) | 20/28 = 71% |
| Test case manual đầu-cuối | 6 câu, 4/6 đúng hoàn toàn, 2/6 từ chối oan (retrieval-quality, không phải data) |
| Không có trường hợp nào **bịa số** | ✅ xác nhận qua cả 6 case |
| Trích nguồn | ✅ mọi câu trả lời có dữ liệu đều kèm citation kiểm chứng được |
