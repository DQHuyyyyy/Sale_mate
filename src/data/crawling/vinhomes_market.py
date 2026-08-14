"""Cào trang giới thiệu dự án trên market.vinhomes.vn.

KHÁC hai crawler còn lại: `batdongsan.py` và `meeyland.py` cào TIN RAO (giá,
diện tích, số phòng của từng căn). File này cào BÀI GIỚI THIỆU — tổng quan, vị
trí, tiện ích, chính sách. Hai loại nội dung khác nhau nên tách hẳn, và dữ liệu
ra sẽ mang `doc_kind="policy"` để truy hồi lọc được.

Cách trích: khớp theo TIÊU ĐỀ trên trang, lấy từ tiêu đề đó tới tiêu đề cùng cấp
hoặc cao hơn kế tiếp. Trang đổi cách đặt tiêu đề thì mục đó ra rỗng — khi ấy
crawler BÁO RÕ mục nào hụt thay vì trả file thiếu nội dung mà không ai biết.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup, Tag

from src.core.logging import get_logger

logger = get_logger(__name__)

# Trang chặn client không có User-Agent trình duyệt.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
_HEADINGS = ("h1", "h2", "h3", "h4")

# "Phần thẻ ưu đãi" không phải tiêu đề mà là một khối riêng — bắt theo class.
#
# `voucher` là class THẬT của khối cần lấy (`section-voucher` > `widget-voucher`).
# Thiếu nó thì chỉ còn `floating-discount` (banner quảng cáo bám màn hình) và
# `card-offer` (thẻ link tải tài liệu) — hai thứ đó có chữ "ưu đãi" nên trông
# như đúng, nhưng không chứa danh sách ưu đãi nào.
_CLASS_UU_DAI = re.compile(r"voucher|discount|uu-dai|promo|offer|incentive", re.I)
# Khối chính ưu tiên hơn banner: tìm thấy nó thì bỏ qua mọi khối khác.
_CLASS_UU_DAI_CHINH = re.compile(r"widget-voucher|section-voucher", re.I)
_TU_KHOA_UU_DAI = ("ưu đãi", "chiết khấu", "khuyến mãi", "quà tặng")

# Khối phải có ít nhất ngần này ký tự NGOÀI phần nhãn thì mới coi là có nội dung.
_TOI_THIEU_SAU_NHAN = 40

# Số thứ tự giai đoạn ở cuối tên, ví dụ "... Ocean Park 1".
_BO_SO_CUOI = re.compile(r"\s+\d+$")


@dataclass
class KetQuaCrawl:
    """Nội dung lấy được cho một tài liệu, kèm những mục không lấy được."""

    tieu_de: str
    url: str
    phan: list[tuple[str, str]] = field(default_factory=list)  # (tiêu đề, nội dung)
    thieu: list[str] = field(default_factory=list)

    @property
    def co_noi_dung(self) -> bool:
        return any(noi_dung.strip() for _, noi_dung in self.phan)

    def thanh_van_ban(self) -> str:
        khoi = [f"## {ten}\n\n{noi_dung}".strip() for ten, noi_dung in self.phan if noi_dung.strip()]
        return "\n\n".join(khoi)


def _chuan_hoa(text: str) -> str:
    """Bỏ dấu, gộp khoảng trắng, viết thường — để so tiêu đề không phụ thuộc dấu."""
    khong_dau = unicodedata.normalize("NFD", text)
    khong_dau = "".join(c for c in khong_dau if unicodedata.category(c) != "Mn")
    return " ".join(khong_dau.lower().split())


def _text(node: Tag) -> str:
    return " ".join(node.get_text(" ").split())


def _noi_dung_sau_heading(heading: Tag) -> str:
    """Lấy mọi thứ từ sau tiêu đề tới tiêu đề cùng cấp hoặc cao hơn kế tiếp."""
    cap = int(heading.name[1])
    doan: list[str] = []

    for el in heading.next_elements:
        if not isinstance(el, Tag):
            continue
        if el.name in _HEADINGS and int(el.name[1]) <= cap:
            break
        # Chỉ lấy khối văn bản lá, tránh lấy trùng khi thẻ lồng nhau.
        #
        # PHẢI có `div`: phần mô tả của mục "Vị trí" nằm trong
        # `<div class="ewa-rteLine">` chứa HTML dạng chuỗi. Bỏ div ra thì lấy
        # trúng mỗi widget bản đồ ("Biển Hồ Nước Mặn · 1,59 km · 5 phút") mà
        # mất sạch đoạn mô tả cùng các gạch đầu dòng về kết nối giao thông.
        if el.name in ("p", "li", "td", "div", "h3", "h4") and not el.find(["p", "li", "div"]):
            for t in _go_the_html(_text(el)):
                if not t or t in doan:
                    continue
                doan.append(f"- {t}" if el.name == "li" and not t.startswith("- ") else t)

    return "\n\n".join(doan)


def _tim_heading(soup: BeautifulSoup, muc_tieu: str) -> Tag | None:
    """Tìm tiêu đề khớp nhất. So sau khi bỏ dấu nên 'Vị trí' khớp 'Vi tri'."""
    can = _chuan_hoa(muc_tieu)
    ung_vien = [(h, _chuan_hoa(_text(h))) for h in soup.find_all(_HEADINGS)]

    for h, t in ung_vien:
        if t == can:
            return h

    # Chỉ nhận tiêu đề CHỨA cụm cần tìm. Chiều ngược lại (tiêu đề nằm trong
    # nhãn) trông có vẻ khoan dung nhưng sai hẳn nghĩa: tìm "Điểm nổi bật
    # Vinhomes Ocean Park" mà khớp vào <h2>Vinhomes Ocean Park</h2> ở đầu trang,
    # rồi lấy về nguyên cái menu điều hướng. Đã xảy ra thật.
    chua = sorted((h for h, t in ung_vien if can in t), key=lambda h: len(_text(h)))
    if chua:
        return chua[0]

    # Thử lại sau khi bỏ số thứ tự dự án ở cuối. Excel gọi giai đoạn đầu là
    # "Vinhomes Ocean Park 1" nhưng trang chỉ ghi "Vinhomes Ocean Park" — không
    # nới chỗ này thì mục đó rơi xuống nhánh "lấy cả thân bài" và kéo về 13.000
    # ký tự gồm cả menu lẫn bài viết khác.
    can_bo_so = _BO_SO_CUOI.sub("", can).strip()
    if can_bo_so == can:
        return None

    gan = sorted(
        (h for h, t in ung_vien if can_bo_so and (can_bo_so in t or t == can_bo_so)),
        key=lambda h: len(_text(h)),
    )
    return gan[0] if gan else None


def _tim_khoi_theo_nhan(soup: BeautifulSoup, nhan: str) -> Tag | None:
    """Tìm khối bắt đầu bằng `nhan` dù nó KHÔNG phải thẻ tiêu đề.

    Trang này để "Thông tin chi tiết" và "Điểm nổi bật" trong `<div>` chứ không
    trong `<h*>`. Chỉ tìm heading là hụt sạch những mục đó.

    Lấy khối nhỏ nhất mà CÓ NỘI DUNG THẬT sau nhãn. Nếu chỉ lấy "nhỏ nhất" thì
    trúng ngay thẻ chứa mỗi chữ nhãn — bỏ dòng nhãn đi là còn lại rỗng, và mục
    bị báo hụt dù nội dung nằm ngay khối cha kế bên.
    """
    can = _chuan_hoa(nhan)
    khop = [
        el
        for el in soup.find_all(["div", "section", "p", "article"])
        if _chuan_hoa(_text(el)).startswith(can) and len(_text(el)) > len(nhan) + _TOI_THIEU_SAU_NHAN
    ]
    return min(khop, key=lambda el: len(_text(el))) if khop else None


def _go_the_html(text: str) -> list[str]:
    """Tách một chuỗi CÓ CHỨA thẻ HTML thành các dòng sạch.

    Trang này nhúng HTML dưới dạng chuỗi (kiểu `v-html`), nên `get_text()` trả
    về nguyên `<ul> <li>…` chứ không phải nội dung. Không gỡ thì file Word đầy
    thẻ và câu trả lời của trợ lý cũng vậy.
    """
    if "<" not in text:
        return [text]

    ben_trong = BeautifulSoup(text, "html.parser")
    dong: list[str] = []

    # Duyệt theo THỨ TỰ TÀI LIỆU, lấy cả `li` lẫn đoạn văn ngoài danh sách.
    # Chỉ vét `li` là mất hai dòng chú thích "(*) Áp dụng từ ngày…" nằm ngay sau
    # danh sách — mà đó mới là phần nêu điều kiện áp dụng của ưu đãi.
    # CHỈ duyệt thẻ khối. Thêm `span` vào đây là mỗi dòng ra hai lần — một lần
    # từ `li`, một lần từ `span` nằm trong chính nó — và những mẩu rời như "5.1"
    # tách khỏi câu cũng thành một dòng riêng vô nghĩa.
    da_co: set[str] = set()
    for el in ben_trong.find_all(["li", "p", "div"]):
        if el.find(["li", "p", "div"]):
            continue
        t = " ".join(el.get_text(" ").split())
        if not t or t in da_co:
            continue
        da_co.add(t)
        dong.append(f"- {t}" if el.name == "li" else t)

    if dong:
        return dong

    con_lai = " ".join(ben_trong.get_text(" ").split())
    return [con_lai] if con_lai else []


def _khoi_thanh_van_ban(khoi: Tag, nhan: str) -> str:
    """Đổi khối HTML thành text đọc được, giữ cặp nhãn–giá trị thành từng dòng."""
    dong: list[str] = []
    for el in khoi.find_all(["li", "p", "div", "td"]):
        # Chỉ lấy nút LÁ (không chứa khối con) để khỏi lặp nội dung cha–con.
        if el.find(["li", "p", "div", "td"]):
            continue
        for t in _go_the_html(_text(el)):
            if t and t not in dong:
                dong.append(t)

    if not dong:
        dong = [_text(khoi)]

    # Bỏ chính dòng nhãn để không lặp lại tiêu đề trong nội dung.
    can = _chuan_hoa(nhan)
    dong = [d for d in dong if _chuan_hoa(d) != can]
    return "\n\n".join(dong)


def _lay_the_uu_dai(soup: BeautifulSoup) -> str:
    """Lấy khối ưu đãi — một thẻ riêng trên trang, không phải mục có tiêu đề."""
    # Khối chính trước: lấy TRỌN nó, giữ nguyên thứ tự dòng như trên trang,
    # kể cả phần sau nút "Thu gọn" và hai dòng chú thích (*) (**) — chúng nêu
    # điều kiện áp dụng, bỏ đi là ưu đãi thành lời hứa suông.
    chinh = soup.find(class_=_CLASS_UU_DAI_CHINH)
    if chinh is not None:
        dong: list[str] = []
        for el in chinh.find_all(["li", "p", "h2", "h3", "div", "span"]):
            if el.find(["li", "p", "div"]):
                continue
            for t in _go_the_html(_text(el)):
                if t and t not in dong:
                    dong.append(t)
        if dong:
            return "\n\n".join(dong)

    thay: list[str] = []
    for el in soup.find_all(class_=_CLASS_UU_DAI):
        t = _text(el)
        if t and t not in thay:
            thay.append(t)

    # Vét thêm theo từ khoá, phòng khi trang đổi tên class.
    if not thay:
        for el in soup.find_all(["p", "li", "h3"]):
            t = _text(el)
            if any(tu in t.lower() for tu in _TU_KHOA_UU_DAI) and t not in thay:
                thay.append(t)

    return "\n\n".join(f"- {t}" for t in thay[:20])


async def tai_trang(url: str, *, timeout: float = 30.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": _UA})
        response.raise_for_status()
        return response.text


def trich_xuat(html: str, *, tieu_de: str, url: str, muc_can_lay: list[str]) -> KetQuaCrawl:
    """Trích các mục yêu cầu ra khỏi HTML.

    `muc_can_lay` là chỉ dẫn tiếng Việt lấy thẳng từ Excel, ví dụ "Điểm nổi bật
    Vinhomes Ocean Park 2" hay "lấy hết các thông tin của heading này". Chỉ dẫn
    chung chung thì rơi về chính tên tài liệu làm tiêu đề cần tìm.
    """
    soup = BeautifulSoup(html, "html.parser")
    for the in soup(["script", "style", "noscript"]):
        the.decompose()

    ket_qua = KetQuaCrawl(tieu_de=tieu_de, url=url)
    muc = muc_can_lay or [tieu_de]

    for chi_dan in muc:
        if "ưu đãi" in chi_dan.lower():
            noi_dung = _lay_the_uu_dai(soup)
            ket_qua.phan.append((tieu_de, noi_dung)) if noi_dung else ket_qua.thieu.append(chi_dan)
            continue

        # "lấy hết các thông tin của heading này" không phải tên mục — nó nói
        # "lấy nguyên phần dưới tiêu đề trùng tên tài liệu".
        can_tim = tieu_de if _chuan_hoa(chi_dan).startswith("lay het") else chi_dan

        heading = _tim_heading(soup, can_tim)
        if heading is not None:
            noi_dung = _noi_dung_sau_heading(heading)
            if noi_dung.strip():
                ket_qua.phan.append((_text(heading), noi_dung))
                continue

        # Không phải tiêu đề thì thử tìm khối văn bản mở đầu bằng nhãn đó.
        khoi = _tim_khoi_theo_nhan(soup, can_tim)
        if khoi is not None:
            noi_dung = _khoi_thanh_van_ban(khoi, can_tim)
            if noi_dung.strip():
                ket_qua.phan.append((can_tim, noi_dung))
                continue

        ket_qua.thieu.append(chi_dan)

    # Bài viết (blog) không có tiêu đề trùng tên tài liệu — tên trong Excel là
    # tên ta đặt, không phải chữ trên trang. Không khớp được mục nào thì lấy cả
    # thân bài, còn hơn trả về file rỗng.
    if not ket_qua.co_noi_dung:
        than_bai = _lay_than_bai(soup)
        if than_bai:
            ket_qua.phan.append((tieu_de, than_bai))
            ket_qua.thieu.clear()

    return ket_qua


def _lay_than_bai(soup: BeautifulSoup) -> str:
    """Lấy phần thân của một bài viết.

    Chọn khối có NHIỀU thẻ <p> nhất — quảng cáo và menu có thể dài nhưng thưa
    thẻ p, còn thân bài thì dày. Đếm p đáng tin hơn đếm ký tự.
    """
    ung_vien = soup.find_all(["article", "main", "div", "section"])
    if not ung_vien:
        return ""

    tot_nhat = max(ung_vien, key=lambda el: len(el.find_all("p")))
    doan = []
    for el in tot_nhat.find_all(["p", "li", "h2", "h3"]):
        if el.find(["p", "li"]):
            continue
        t = _text(el)
        if len(t) > 30 and t not in doan:
            doan.append(f"- {t}" if el.name == "li" else t)
    return "\n\n".join(doan)
