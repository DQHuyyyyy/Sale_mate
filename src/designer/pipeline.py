"""Xử lý ảnh tại máy — hàm thuần, không gọi mạng, không tốn tiền model.

Đây là nơi bảo đảm hai yêu cầu mà MODEL KHÔNG BẢO ĐẢM ĐƯỢC:

1. **Chỉ đổi phần được nhắc tới.** Tài liệu OpenAI nói rõ `mask` chỉ là gợi ý,
   model "có thể không theo đúng hình dạng mask" — dòng gpt-image vẽ lại toàn bộ
   khung ảnh chứ không vá vào một vùng. Nên vùng ngoài mask được giữ nguyên bằng
   cách TA tự ghép: lấy pixel gốc, chỉ dán phần trong mask từ ảnh model trả về.
   Đó là bảo đảm tất định, không phải lời hứa của model.

2. **Không méo ảnh.** Model trả ảnh ở kích thước ta yêu cầu; ta yêu cầu đúng tỷ
   lệ ảnh gốc (làm tròn theo ràng buộc của API), rồi resize về đúng W×H gốc.

Hai ràng buộc của API mà `chuan_hoa_kich_thuoc` phải tôn trọng: mỗi cạnh là bội
số 16, và tỷ lệ khung không quá 2:1 — vượt ngưỡng đó model bám mask kém hẳn.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat

# API đòi mỗi cạnh là bội số 16.
BOI_SO = 16
# Trên tỷ lệ này model bám mask kém hẳn. Ảnh căn hộ thường 4:3 hoặc 16:9 nên
# gần như không bao giờ chạm ngưỡng; có chạm thì bị ép về đúng 2:1 và bước ghép
# đè sẽ kéo lại đúng khung gốc.
TY_LE_TOI_DA = 2.0
# Làm mềm mép vùng ghép. Không có nó thì chỗ nối lộ thành một đường sắc nét khi
# model đổi ánh sáng tổng thể — mắt bắt ngay dù nội dung đúng.
VIEN_MEM = 6


@dataclass(frozen=True)
class Vung:
    """Khung chữ nhật cần sửa, theo toạ độ pixel của ẢNH GỐC."""

    trai: int
    tren: int
    phai: int
    duoi: int

    @property
    def hop_le(self) -> bool:
        return self.phai > self.trai and self.duoi > self.tren

    def theo_ty_le(self, tu: tuple[int, int], den: tuple[int, int]) -> Vung:
        """Đổi toạ độ sang hệ của một kích thước ảnh khác."""
        kx, ky = den[0] / tu[0], den[1] / tu[1]
        return Vung(
            trai=int(self.trai * kx),
            tren=int(self.tren * ky),
            phai=int(self.phai * kx),
            duoi=int(self.duoi * ky),
        )

    def noi_rong(self, them: int, trong: tuple[int, int]) -> Vung:
        """Nới khung ra vài pixel, không vượt biên ảnh.

        Cần vì mép ghép được làm mềm: không nới thì phần mềm ăn vào trong vùng
        sửa, làm nhạt chính chỗ người dùng muốn đổi.
        """
        rong, cao = trong
        return Vung(
            trai=max(0, self.trai - them),
            tren=max(0, self.tren - them),
            phai=min(rong, self.phai + them),
            duoi=min(cao, self.duoi + them),
        )

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.trai, self.tren, self.phai, self.duoi)


def chuan_hoa_kich_thuoc(rong: int, cao: int, *, canh_toi_da: int) -> tuple[int, int]:
    """Kích thước hợp lệ để gửi model, giữ tỷ lệ gốc sát nhất có thể.

    Thứ tự CÓ CHỦ Ý: thu nhỏ trước, ép tỷ lệ sau, làm tròn bội số 16 sau cùng.
    Làm tròn trước rồi mới thu nhỏ thì kết quả lại lệch khỏi bội số.
    """
    if rong <= 0 or cao <= 0:
        raise ValueError("Kích thước ảnh phải lớn hơn 0.")

    ty_le = max(rong, cao) / canh_toi_da
    if ty_le > 1:
        rong, cao = rong / ty_le, cao / ty_le

    # Ép về tối đa 2:1 bằng cách kéo cạnh DÀI xuống, không kéo cạnh ngắn lên —
    # phóng to là bịa thêm pixel không có thật.
    if rong > cao * TY_LE_TOI_DA:
        rong = cao * TY_LE_TOI_DA
    elif cao > rong * TY_LE_TOI_DA:
        cao = rong * TY_LE_TOI_DA

    return _lam_tron(rong), _lam_tron(cao)


def _lam_tron(gia_tri: float) -> int:
    """Về bội số 16 gần nhất, tối thiểu một bội số."""
    return max(BOI_SO, int(round(gia_tri / BOI_SO)) * BOI_SO)


def doc_anh(du_lieu: bytes) -> Image.Image:
    """Đọc bytes thành ảnh RGB.

    Ép về RGB vì ảnh nguồn có thể là PNG có alpha hoặc ảnh xám; các bước sau đều
    giả định ba kênh màu, và gpt-image-2 không nhận nền trong suốt.
    """
    anh = Image.open(io.BytesIO(du_lieu))
    return anh.convert("RGB")


def doc_anh_tren_nen(du_lieu: bytes, nen: Image.Image) -> Image.Image:
    """Đọc ảnh model trả về, phần TRONG SUỐT lấy lại từ ảnh gốc.

    Đây là chốt chống lỗi đã gặp thật: model không vẽ gì vào vùng được sửa mà
    trả về một lỗ trong suốt. `.convert("RGB")` trần biến lỗ đó thành ĐEN THUẦN,
    và ảnh cuối có một khối đen giữa phòng khách.

    Trong suốt nghĩa là "tôi không làm được chỗ này", nên câu trả lời đúng là
    giữ nguyên ảnh gốc ở đó — không phải tô đen, cũng không phải tô trắng.
    """
    anh = Image.open(io.BytesIO(du_lieu))
    if anh.mode not in ("RGBA", "LA") and "transparency" not in anh.info:
        return anh.convert("RGB")

    anh = anh.convert("RGBA")
    lot = nen.convert("RGB")
    if lot.size != anh.size:
        lot = lot.resize(anh.size, Image.LANCZOS)

    ket_qua = lot.copy()
    ket_qua.paste(anh, (0, 0), anh)  # dùng chính alpha làm mặt nạ
    return ket_qua


def ty_le_doi(goc: Image.Image, moi: Image.Image, *, nguong: int = 12) -> float:
    """Tỉ lệ pixel thực sự khác nhau giữa hai ảnh, 0..1.

    Dùng để không nói dối: model trả về gần y hệt ảnh gốc mà trợ lý vẫn báo "đã
    chỉnh xong" thì đó là khẳng định sai — vi phạm nguyên tắc số 1 của dự án.

    `nguong` bỏ qua sai khác li ti do nén lại và resize; chỉ đếm thay đổi mắt
    người nhìn ra được.
    """
    a, b = _cung_co(goc, moi)
    khac = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > nguong else 0)
    return ImageStat.Stat(khac).mean[0] / 255


def ty_le_be_phang(goc: Image.Image, moi: Image.Image) -> float:
    """Tỉ lệ pixel BỊ BIẾN thành đen thuần hoặc trắng thuần, 0..1.

    Dấu hiệu model bỏ cuộc: nó trả về một mảng màu phẳng thay cho nội dung. Chỉ
    đếm pixel MỚI thành đen/trắng — ảnh phòng ngủ ban đêm vốn đã có nhiều vùng
    rất tối, đếm cả chúng thì ảnh bình thường cũng bị coi là hỏng.
    """
    a, b = _cung_co(goc, moi)
    # subtract: giữ chỗ MỚI phẳng, bỏ chỗ vốn đã phẳng từ đầu.
    moi_phang = ImageChops.subtract(_mat_na_phang(b), _mat_na_phang(a))
    return ImageStat.Stat(moi_phang).mean[0] / 255


def _cung_co(goc: Image.Image, moi: Image.Image) -> tuple[Image.Image, Image.Image]:
    a = goc.convert("RGB")
    b = moi.convert("RGB")
    return a, (b if b.size == a.size else b.resize(a.size, Image.LANCZOS))


def _mat_na_phang(anh: Image.Image) -> Image.Image:
    """Mặt nạ các pixel đen thuần hoặc trắng thuần."""
    xam = anh.convert("L")
    return ImageChops.lighter(
        xam.point(lambda v: 255 if v <= 6 else 0),
        xam.point(lambda v: 255 if v >= 249 else 0),
    )


def xuat_png(anh: Image.Image) -> bytes:
    bo_dem = io.BytesIO()
    anh.save(bo_dem, format="PNG")
    return bo_dem.getvalue()


def dung_mask(kich_thuoc: tuple[int, int], vung: Vung) -> bytes:
    """PNG mask gửi kèm cho API: TRONG SUỐT ở vùng được phép sửa.

    Quy ước của OpenAI ngược với trực giác — alpha = 0 nghĩa là "sửa chỗ này",
    phần đục là phần giữ lại. Viết sai chỗ này thì model sửa đúng phần đáng lẽ
    phải giữ, mà kết quả vẫn trông "hợp lý" nên rất khó lần ra.

    Mask gửi API để mép SẮC. Việc làm mềm mép chỉ áp dụng lúc ghép tại máy —
    hai việc khác nhau, đừng gộp.
    """
    mask = Image.new("RGBA", kich_thuoc, (0, 0, 0, 255))
    if vung.hop_le:
        trong_suot = Image.new("RGBA", (vung.phai - vung.trai, vung.duoi - vung.tren), (0, 0, 0, 0))
        mask.paste(trong_suot, (vung.trai, vung.tren))
    return xuat_png(mask)


def ghep_de(goc: Image.Image, moi: Image.Image, vung: Vung, *, vien_mem: int = VIEN_MEM) -> Image.Image:
    """Dán phần TRONG vùng của ảnh model lên ảnh gốc, giữ nguyên phần ngoài.

    Đây là chốt bảo đảm "chỉ sửa cái được nhắc tới". Model có vẽ lại cả căn
    phòng cũng không sao — những gì nằm ngoài khung này là pixel gốc, từng điểm
    một, vì ta không hề chạm vào.

    `moi` được resize về đúng kích thước `goc` trước khi ghép, nên ảnh ra luôn
    đúng tỷ lệ khung hình ban đầu.
    """
    if not vung.hop_le:
        return goc.copy()

    if moi.size != goc.size:
        moi = moi.resize(goc.size, Image.LANCZOS)

    # Viền mềm phải NHỎ so với vùng sửa, và vùng được nới ra đúng bằng viền
    # trước khi làm mờ. Thiếu hai bước này thì với khung nhỏ (cái rèm, cái quạt)
    # phần mờ ăn tới tận giữa khung: thay đổi người dùng yêu cầu hiện ra nhợt
    # nhạt, còn họ thì tưởng model làm dở. Đã gặp đúng lỗi này lúc viết test.
    mem = _vien_vua(vung, vien_mem)
    no_ra = vung.noi_rong(mem, goc.size)

    alpha = Image.new("L", goc.size, 0)
    ImageDraw.Draw(alpha).rectangle(no_ra.as_tuple(), fill=255)
    if mem > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(mem))

    ket_qua = goc.copy()
    ket_qua.paste(moi.convert("RGB"), (0, 0), alpha)
    return ket_qua


def _vien_vua(vung: Vung, mong_muon: int) -> int:
    """Viền mềm không vượt 1/6 cạnh ngắn của vùng — giữ lõi vùng ăn màu đủ đậm."""
    canh_ngan = min(vung.phai - vung.trai, vung.duoi - vung.tren)
    return max(0, min(mong_muon, canh_ngan // 6))


def dong_nhan(anh: Image.Image, chu: str) -> Image.Image:
    """Đóng nhãn "ảnh do AI tạo" vào chính pixel.

    Burn vào ảnh chứ không phủ bằng HTML: người dùng chụp màn hình hoặc lưu ảnh
    rồi gửi cho khách thì lớp phủ HTML biến mất, còn thứ họ gửi đi là một tấm
    ảnh trông y như hiện trạng thật của căn hộ. Đây là portal tự nhận là "xác
    thực" nên chỗ này không được làm nửa vời.
    """
    ket_qua = anh.convert("RGB")
    ve = ImageDraw.Draw(ket_qua, "RGBA")

    co_chu = max(12, ket_qua.width // 45)
    font = _font(co_chu)
    trai, tren, phai, duoi = ve.textbbox((0, 0), chu, font=font)
    rong_chu, cao_chu = phai - trai, duoi - tren

    dem = co_chu // 2
    x0 = ket_qua.width - rong_chu - dem * 3
    y0 = ket_qua.height - cao_chu - dem * 3
    ve.rectangle((x0, y0, ket_qua.width, ket_qua.height), fill=(0, 0, 0, 140))
    ve.text((x0 + dem, y0 + dem - tren), chu, font=font, fill=(255, 255, 255, 235))
    return ket_qua


def _font(co: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Font có dấu tiếng Việt, rơi về font mặc định nếu máy không có.

    Nhãn là chốt an toàn — thiếu font thì vẫn phải đóng được nhãn, kể cả khi chữ
    xấu. Không bao giờ để lỗi font làm ảnh thoát ra mà không có nhãn.
    """
    for ten in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(ten, co)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=co)
    except TypeError:  # Pillow cũ chưa nhận tham số size
        return ImageFont.load_default()
