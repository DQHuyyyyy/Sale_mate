# ADR-003: Định tuyến model hai tầng

**Ngày:** 2026-08-01
**Trạng thái:** Accepted — cấu trúc hai biến giữ nguyên, **giá trị đã đổi**
(xem "Cập nhật 2026-08-26" ở cuối)

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
LLM_MODEL_FAST=<model rẻ>      # router, phân loại nhạy cảm
LLM_MODEL_ANSWER=<model mạnh>  # câu trả lời cuối
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

## Cập nhật 2026-08-26 — hai tầng giờ dùng CÙNG một model

```
LLM_MODEL_FAST=gpt-5.6-luna
LLM_MODEL_ANSWER=gpt-5.6-luna
```

Thoạt nhìn là bỏ quyết định của ADR này, nhưng không phải: **cấu trúc hai biến
tách biệt vẫn còn nguyên**, chỉ là hiện tại chúng trỏ vào cùng một model. Vì sao
đáng giữ nguyên cấu trúc — đổi một tầng mà không đụng tầng kia vẫn là một dòng
biến môi trường.

Vì sao đổi được: khâu trả lời từng bị khoá ở model đắt vì đó là chỗ DUY NHẤT có
hồi quy thật khi hạ model — bản rẻ hồi đó bỏ mất toà/tầng/phòng và bỏ luôn luật
trích nguồn trên production. Điều kiện gỡ khoá là **phải đo**, và đã đo: 29 câu
golden dataset trên luna, chấm bằng `claude-sonnet-5` — 17 đạt / 2 không đạt,
dòng "Nguồn" đầy đủ ở mọi lượt có khẳng định
(`eval/results/diem_20260826-1609_batch3-sua.md`).

Hai hệ quả ở phần trên vẫn đúng, và có thêm một cái: **hai tầng cùng model thì
mất luôn tấm lưới "router sai thì câu trả lời vẫn ổn nhờ model mạnh"**. Nếu về
sau router phân loại tệ đi, đừng chỉ chỉnh prompt router — cân nhắc tách lại hai
model, đó chính là thứ cấu trúc này để dành cho.
