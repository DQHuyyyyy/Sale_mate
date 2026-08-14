# Prompt sửa ảnh — phiên bản v1

> Gửi cho model SINH ẢNH (`gpt-image-2`). File chia thành các khối `## <tên>`;
> `src/designer/editor.py` ghép khối `chung` với đúng một khối thao tác.
>
> Vì sao tách theo thao tác: dặn model **xoá** một vật thể khác hẳn dặn nó
> **đổi màu** vật thể đó. Bản trước gộp làm một và nói "không thêm vật thể mới"
> cho mọi trường hợp — câu đó đẩy model vào thế bí khi phải xoá, vì xoá cái quạt
> thì bắt buộc phải vẽ lại phần sàn và thảm nằm sau nó. Kết quả là model trả về
> một vùng trống, và ảnh cuối có một khối đen giữa phòng.
>
> Khối `chung` là chỗ cấm mọi kiểu "trả về vùng trống". Đừng gỡ dòng nào ở đó.

## chung

Đây là ảnh chụp thật một căn hộ đang rao bán. Chỉnh sửa phải trông như ảnh chụp,
không phải ảnh ghép.

BẮT BUỘC — vùng được sửa phải là hình ảnh HOÀN CHỈNH và HỢP LÝ:

- TUYỆT ĐỐI KHÔNG để lại mảng đen, mảng trắng, mảng xám hay bất kỳ mảng màu
  phẳng nào.
- TUYỆT ĐỐI KHÔNG để lại vùng trong suốt, vùng trống, lỗ thủng hay vùng bị làm
  mờ để che.
- TUYỆT ĐỐI KHÔNG vẽ khung, viền, đường kẻ hay ô đánh dấu quanh vùng đã sửa.
- Nếu không thực hiện được yêu cầu, hãy trả lại ảnh gốc y nguyên. Một vùng
  trống còn tệ hơn nhiều so với không sửa gì.

Mọi thứ vẽ ra phải đúng logic hình ảnh của căn phòng:

- Đúng phối cảnh: đường sàn, đường tường, hướng các cạnh phải tiếp nối liền
  mạch với phần xung quanh.
- Đúng ánh sáng: cùng hướng sáng, cùng độ sáng, cùng tông màu với phần còn lại.
- Đúng bóng đổ: vật thể đứng trên sàn phải có bóng tiếp đất; bỏ vật thể đi thì
  bóng của nó cũng phải biến mất.
- Đúng tỉ lệ so với các vật thể xung quanh.
- Giữ nguyên hoàn toàn góc chụp, bố cục và mọi vật thể không được nhắc tới.

KHÔNG thêm chữ, logo, watermark hay chú thích vào ảnh.

## them

Đưa THÊM vật thể người dùng yêu cầu vào phòng, đặt đúng vị trí họ mô tả.

Mọi thứ đang có trong ảnh phải GIỮ NGUYÊN — không xoá, không thay, không xê
dịch, không đổi màu bất kỳ đồ đạc nào đã có sẵn. Vật mới chỉ được che khuất
phần nằm sau nó, đúng như một món đồ thật vừa được kê vào phòng.

Vật mới phải:

- đứng đúng mặt sàn, không lơ lửng và không lún vào sàn;
- đúng tỉ lệ so với đồ đạc quanh nó — lấy chiều cao cái bàn, cái ghế trong ảnh
  làm mốc để ước lượng;
- đúng phối cảnh: các cạnh đứng phải song song với cạnh đứng của tường và tủ
  sẵn có, các cạnh ngang hội tụ về đúng điểm tụ của căn phòng;
- nhận ánh sáng cùng hướng, cùng nhiệt độ màu với phần còn lại;
- có bóng tiếp đất và bóng đổ đúng hướng nguồn sáng trong ảnh.

Người dùng nêu kích thước hoặc thông số cụ thể ("tủ lạnh 2 ngăn, 200 lít") thì
dựng đúng loại đó, đúng tầm vóc đó so với căn phòng.

## xoa

Xoá hẳn vật thể được nêu ra khỏi ảnh, rồi **dựng lại nền phía sau nó** như thể
vật thể đó chưa từng có mặt.

Phần nền dựng lại phải nối tiếp tự nhiên với xung quanh: sàn tiếp tục đúng
hướng vân và đúng đường ghép gạch; thảm tiếp tục đúng hoa văn; tường tiếp tục
đúng màu và đúng vệt sáng; chân tường, phào, ổ điện bị che thì hiện ra lại.

Bóng đổ của vật thể bị xoá cũng phải mất theo. Không được để lại vệt mờ, vết
bóng còn sót, hay một mảng sàn sạch bất thường so với xung quanh.

Ở đây bạn ĐƯỢC PHÉP vẽ thêm phần nền — đó chính là việc cần làm. Điều bị cấm là
thêm một vật thể mới vào chỗ vừa xoá.

## thay_the

Thay vật thể được nêu bằng vật thể mới người dùng yêu cầu.

Vật thể mới phải đặt đúng chỗ vật thể cũ: cùng vị trí tiếp đất, cùng phương
hướng, tỉ lệ hợp lý so với đồ đạc xung quanh, và nhận ánh sáng từ cùng một
hướng. Nó phải có bóng tiếp đất riêng, đúng như một vật thật đặt trong phòng đó.

Phần nền quanh vật thể mới, nếu vật cũ che mất, phải được dựng lại liền mạch.
Không để viền cắt, không để hào quang sáng hay tối quanh vật thể mới.

## doi_thuoc_tinh

Giữ NGUYÊN vật thể: đúng hình dáng, đúng vị trí, đúng kích thước, đúng tư thế.
Chỉ đổi đúng thuộc tính người dùng nêu — màu sắc, chất liệu hoặc hoạ tiết.

Nếp gấp, đường may, vân chất liệu, phần sáng và phần tối trên vật thể phải giữ
nguyên cấu trúc cũ, chỉ đổi màu hoặc chất liệu theo yêu cầu.

Không thay vật thể bằng vật thể khác, không đổi kiểu dáng, không dịch chuyển nó.
