# ADR-003: Định tuyến model hai tầng

**Ngày:** 2026-08-01
**Trạng thái:** Accepted

## Bối cảnh

Mỗi lượt hỏi của người dùng cần ít nhất hai lần gọi LLM: một lần **phân loại**
câu hỏi (cần tra tài liệu? hỏi giá? pháp lý?) và một lần **sinh câu trả lời**.

Hai việc này khác hẳn nhau về yêu cầu:

| | Phân loại | Sinh câu trả lời |
|---|---|---|
| Output | 1 từ | vài trăm token |
| Chất lượng cần | vừa đủ | cao nhất có thể |
| Ảnh hưởng độ trễ | nằm chặn đầu, người dùng chờ | có streaming nên cảm nhận nhẹ hơn |

Dùng cùng một model mạnh cho cả hai là vừa chậm vừa đắt một cách vô ích.

## Các lựa chọn

1. **Một model mạnh cho tất cả** — đơn giản nhất, nhưng router tốn ~10x chi phí
   và cộng thêm độ trễ vào đúng chỗ người dùng đang chờ.
2. **Một model rẻ cho tất cả** — nhanh và rẻ, nhưng câu trả lời cuối kém, mà đây
   lại chính là thứ người dùng đánh giá.
3. **Hai tầng: model rẻ cho router, model mạnh cho câu trả lời.**

## Quyết định

Chọn phương án 3, cấu hình qua hai biến môi trường tách biệt:

```
LLM_MODEL_FAST=gpt-4o-mini     # router, phân loại nhạy cảm
LLM_MODEL_ANSWER=gpt-4o        # câu trả lời cuối
```

Thêm một lớp nữa trước cả hai: **luật từ khoá**. Câu hỏi chứa "sổ đỏ", "thủ tục",
"giá"… được phân loại ngay bằng luật, không gọi LLM lần nào — xem
`src/agents/nodes/router.py`.

## Lý do

1. Ba tầng (luật → model rẻ → model mạnh) cắt được phần lớn lượt gọi LLM thừa.
2. Router trả về nhãn sai thì đã có fallback về `general`, không làm hỏng luồng.
3. Cấu hình bằng biến môi trường nên đổi model không cần sửa code, và mỗi môi
   trường (dev/staging/prod) dùng model khác nhau được.

## Hệ quả

- Phải theo dõi tỉ lệ router phân loại đúng. Nếu model rẻ sai nhiều, chi phí sửa
  sai (truy hồi thừa, câu trả lời lệch) sẽ lớn hơn khoản tiết kiệm được.
- Luật từ khoá phải giữ ngắn và dễ đọc. Khi nó phình ra thành hàng trăm dòng thì
  đó là dấu hiệu nên bỏ luật, để model làm hết.
