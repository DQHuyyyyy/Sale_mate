"""Đối chiếu câu trả lời với DATABASE — cách chấm mà golden dataset chỉ định.

Cột "Cách chấm" của nhóm Tool-use ghi "Đối chiếu trực tiếp với DB tại thời điểm
chạy test (exact match số liệu)". Module này làm đúng việc đó, và làm một cách
ĐỘC LẬP: nó tự mở kết nối Postgres và tự viết SQL, KHÔNG gọi lại
`inventory_search` hay bất kỳ tool nào của agent.

Vì sao độc lập là điều kiện bắt buộc: dùng chính tool để kiểm tool là phép kiểm
vòng tròn — tool lọc sai thì kết quả kiểm cũng sai y hệt và bài đo báo "đạt".
Đúng bug B01 mà case T03 sinh ra để bắt: chat trả 9 căn còn bộ lọc giao diện trả
0, hai bên cùng đọc một database mà ra hai con số.

⚠️ Module này KHÔNG được sửa hệ thống. Nó chỉ đọc. Mọi phép kiểm ở đây phải chấp
nhận hệ thống như nó đang là — nếu một câu trả lời sai thì ghi FAIL, không nới
luật cho nó đạt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Số trong câu trả lời model viết: "3,350 tỷ", "63m2", "43 m²".
_TIEN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tỷ|tỉ)", re.IGNORECASE)
_MA_CAN = re.compile(r"\b([A-Z]{2,4}\d{2,5})\b")


@dataclass
class KetQuaDoiChieu:
    """Một phép đối chiếu. `dat=None` nghĩa là không kiểm được, không phải đạt."""

    dat: bool | None
    giai_thich: str
    su_that_db: str = ""


def _ket_noi() -> Any:
    """Mở kết nối Postgres bằng cấu hình của portal backend.

    Import trong hàm: máy không có `psycopg` hoặc không có `DATABASE_URL` vẫn
    chạy được phần chấm rule-based và Judge, chỉ mất riêng phần đối chiếu DB.
    """
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "interface" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    import psycopg  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    return psycopg.connect(settings.database_url)


def _hoi(sql: str, tham_so: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with _ket_noi() as conn, conn.cursor() as cur:
        cur.execute(sql, tham_so)
        return cur.fetchall()


def _tien_trong(cau: str) -> set[float]:
    """Các số tiền (đơn vị tỷ) model viết ra. '3,350 tỷ' -> 3.35."""
    ra: set[float] = set()
    for so, _ in _TIEN.findall(cau):
        try:
            ra.add(round(float(so.replace(",", ".")), 3))
        except ValueError:
            continue
    return ra


def _ma_can_trong(cau: str) -> list[str]:
    return list(dict.fromkeys(_MA_CAN.findall(cau)))


# ---------- Từng phép kiểm ----------


def _t01_studio_op3_duoi_gia(cau_tra_loi: str) -> KetQuaDoiChieu:
    """Studio ở Ocean Park 3 dưới 2,3 tỷ — liệt kê phải khớp ĐÚNG tập DB."""
    rows = _hoi(
        """
        SELECT unit_code FROM inventory_units
        WHERE subdivision = 'Ocean Park 3' AND unit_type = 'Studio'
          AND price_value < 2.3 AND status <> 'sold'
        ORDER BY price_value
        """
    )
    that = {r[0] for r in rows}
    noi = set(_ma_can_trong(cau_tra_loi))
    thua, thieu = noi - that, that - noi
    return KetQuaDoiChieu(
        dat=not thua and not thieu,
        giai_thich=("khớp đúng tập DB" if not thua and not thieu else f"thừa {sorted(thua)}, thiếu {sorted(thieu)}"),
        su_that_db=f"{len(that)} căn: {sorted(that)}",
    )


def _t02_gia_va_tinh_trang_vop518(cau_tra_loi: str) -> KetQuaDoiChieu:
    rows = _hoi("SELECT price_value, status FROM inventory_units WHERE unit_code = 'VOP518'")
    if not rows:
        return KetQuaDoiChieu(None, "VOP518 không có trong DB — case cần sửa dataset")
    gia, trang_thai = float(rows[0][0]), rows[0][1]

    dung_gia = gia in _tien_trong(cau_tra_loi)
    con = "còn" in cau_tra_loi.lower()
    dung_trang_thai = con if trang_thai == "available" else not con
    return KetQuaDoiChieu(
        dat=dung_gia and dung_trang_thai,
        giai_thich=f"giá {'đúng' if dung_gia else 'SAI'}, tình trạng {'đúng' if dung_trang_thai else 'SAI'}",
        su_that_db=f"{gia} tỷ · {trang_thai}",
    )


def _t04_so_sanh_khong_hoan_doi(cau_tra_loi: str) -> KetQuaDoiChieu:
    """Hai căn phải đủ mặt, và số liệu KHÔNG được tráo cho nhau.

    Kiểm chống tráo bằng thứ tự xuất hiện: giá của căn nào phải đứng gần tên căn
    đó hơn. Đây là lỗi hay gặp nhất khi model tổng hợp bảng so sánh.
    """
    rows = _hoi("SELECT unit_code, price_value, area_value FROM inventory_units WHERE unit_code IN ('VOP518','VOP703')")
    if len(rows) != 2:
        return KetQuaDoiChieu(None, "Thiếu VOP518 hoặc VOP703 trong DB")
    that = {r[0]: (float(r[1]), float(r[2])) for r in rows}

    thieu = [m for m in that if m not in cau_tra_loi]
    if thieu:
        return KetQuaDoiChieu(False, f"thiếu hẳn {thieu}", su_that_db=str(that))

    loi: list[str] = []
    for ma, (gia, _dt) in that.items():
        vi_tri_gia = _vi_tri_gan_nhat(cau_tra_loi, gia)
        if vi_tri_gia is None:
            loi.append(f"{ma}: không thấy giá {gia}")
        elif _gan_ma_khac(cau_tra_loi, vi_tri_gia, ma, list(that)):
            loi.append(f"{ma}: giá {gia} đứng cạnh căn KHÁC — nghi tráo số liệu")
    return KetQuaDoiChieu(dat=not loi, giai_thich="; ".join(loi) or "hai căn đủ, không tráo", su_that_db=str(that))


def _vi_tri_gan_nhat(cau: str, gia: float) -> int | None:
    """Vị trí đầu tiên con số này xuất hiện, chấp nhận cả '3,35' và '3,350'."""
    for dang in (f"{gia:g}".replace(".", ","), f"{gia:.3f}".rstrip("0").rstrip(".").replace(".", ",")):
        vi_tri = cau.find(dang)
        if vi_tri != -1:
            return vi_tri
    return None


def _gan_ma_khac(cau: str, vi_tri_gia: int, ma_dung: str, tat_ca: list[str]) -> bool:
    """Mã căn nào đứng gần con số này nhất — nếu không phải mã đúng thì nghi tráo."""
    gan_nhat, kc_min = None, 10**9
    for ma in tat_ca:
        for khop in re.finditer(re.escape(ma), cau):
            kc = abs(khop.start() - vi_tri_gia)
            if kc < kc_min:
                gan_nhat, kc_min = ma, kc
    return gan_nhat != ma_dung


def _t05_re_nhat_2pn_op1(cau_tra_loi: str) -> KetQuaDoiChieu:
    rows = _hoi(
        """
        SELECT unit_code, price_value FROM inventory_units
        WHERE subdivision = 'Ocean Park 1' AND unit_type LIKE '2PN%%' AND status <> 'sold'
        ORDER BY price_value LIMIT 1
        """
    )
    if not rows:
        return KetQuaDoiChieu(None, "Không có căn 2PN nào ở Ocean Park 1")
    ma, gia = rows[0][0], float(rows[0][1])
    return KetQuaDoiChieu(
        dat=ma in cau_tra_loi,
        giai_thich=f"{'nêu đúng' if ma in cau_tra_loi else 'KHÔNG nêu'} căn rẻ nhất {ma}",
        su_that_db=f"{ma} — {gia} tỷ",
    )


PHEP_KIEM = {
    "T01": _t01_studio_op3_duoi_gia,
    "T02": _t02_gia_va_tinh_trang_vop518,
    "T04": _t04_so_sanh_khong_hoan_doi,
    "T05": _t05_re_nhat_2pn_op1,
}

# ---------- T03: chat vs bộ lọc giao diện ----------

URL_PORTAL_MAC_DINH = "http://127.0.0.1:8000"


def t03_chat_vs_bo_loc_ui(dong: dict[str, Any], base_url: str = URL_PORTAL_MAC_DINH) -> KetQuaDoiChieu:
    """Case P0: danh sách trong chat phải khớp bộ lọc `/tim-kiem` cùng tiêu chí.

    Gọi ĐÚNG endpoint mà trang tìm kiếm gọi (`GET /api/apartments`), với đúng bộ
    lọc mà `ToolsNode` đã ghi lại ở `tool_filters` — nên đây là phép so hai
    đường đọc cùng một database, không phải so hai lần chạy cùng một đường.

    Bug B01 mà case này sinh ra để bắt: chat trả 9 căn còn lưới bên trái hiện 0,
    cùng điều kiện Ocean Park 1 + 2PN.
    """
    import httpx  # noqa: PLC0415

    loc = _bo_loc_inventory_search(dong)
    if not loc:
        return KetQuaDoiChieu(None, "Lượt này không ghi lại bộ lọc của inventory_search")

    tham_so = {
        k: v
        for k, v in {
            "subdivision": loc.get("subdivision"),
            "type": loc.get("unit_type"),
            "tower": loc.get("building"),
            "price_min": loc.get("price_min"),
            "price_max": loc.get("price_max"),
            "price_max_exclusive": "true" if loc.get("price_max_nghiem_ngat") else None,
            "wc": loc.get("wc"),
        }.items()
        if v is not None
    }
    try:
        res = httpx.get(f"{base_url}/api/apartments", params=tham_so, timeout=30.0)
        res.raise_for_status()
        ui = {c["ma_can"] for c in res.json()}
    except Exception as exc:  # noqa: BLE001 - portal chưa chạy thì để "chưa kết luận"
        return KetQuaDoiChieu(None, f"Không gọi được bộ lọc UI: {type(exc).__name__}: {exc}")

    chat = set(_ma_can_trong(dong.get("cau_tra_loi", "")))
    thua, thieu = chat - ui, ui - chat
    return KetQuaDoiChieu(
        dat=not thua and not thieu,
        giai_thich=(
            f"chat {len(chat)} căn, UI {len(ui)} căn — khớp"
            if not thua and not thieu
            else f"chat {len(chat)} vs UI {len(ui)}; chat thừa {sorted(thua)}, thiếu {sorted(thieu)}"
        ),
        su_that_db=f"bộ lọc gửi UI: {tham_so}",
    )


def _bo_loc_inventory_search(dong: dict[str, Any]) -> dict[str, Any]:
    for buoc in dong.get("buoc", []):
        loc = (buoc.get("filters") or {}).get("inventory_search")
        if loc:
            return loc
    return {}


# ---------- Đa lượt: lượt sau phải nằm trong lượt trước ----------


def tap_con_cua_luot_truoc(dong_sau: dict[str, Any], dong_truoc: dict[str, Any]) -> KetQuaDoiChieu:
    """Kết quả lượt 2 phải nằm trong TẬP KHỚP của lượt 1 — kỳ vọng của M01b.

    ⚠️ "Tập kết quả lượt 1" là **43 căn khớp tiêu chí**, KHÔNG phải 30 căn được
    đem ra hiển thị. Bản đầu so với danh sách mã trong câu chữ của lượt 1 và báo
    FAIL cho VOP927 — trong khi VOP927 có thật ở Ocean Park 2 và đúng là view
    biển hồ, chỉ nằm ngoài 30 căn được in ra. Chấm oan một hành vi ĐÚNG còn tệ
    hơn để nó "chưa kết luận": nó cử người đi sửa thứ đang chạy tốt.

    Nên phép kiểm dựng lại tập khớp từ DB theo đúng bộ lọc lượt 1 đã ghi, rồi
    kiểm thêm điều kiện lọc của lượt 2 (view có chữ "hồ").
    """
    loc = _bo_loc_inventory_search(dong_truoc)
    sau = _ma_can_trong(dong_sau.get("cau_tra_loi", ""))
    if not sau:
        return KetQuaDoiChieu(None, "Lượt sau không nêu mã căn nào để đối chiếu")
    if not loc.get("subdivision"):
        return KetQuaDoiChieu(None, "Lượt trước không ghi lại phân khu để dựng tập khớp")

    rows = _hoi(
        "SELECT unit_code, view FROM inventory_units WHERE subdivision = %s AND status <> 'sold'",
        (loc["subdivision"],),
    )
    tap_khop = {r[0]: (r[1] or "") for r in rows}

    ngoai = [m for m in sau if m not in tap_khop]
    khong_ho = [m for m in sau if m in tap_khop and "hồ" not in tap_khop[m].lower()]
    loi = [
        x
        for x in (f"ngoài tập lượt 1: {ngoai}" if ngoai else "", f"không phải view hồ: {khong_ho}" if khong_ho else "")
        if x
    ]
    return KetQuaDoiChieu(
        dat=not loi,
        giai_thich=("; ".join(loi) if loi else f"cả {len(sau)} căn đều thuộc tập lượt 1 và đúng view hồ"),
        su_that_db=f"tập khớp lượt 1: {len(tap_khop)} căn ({loc['subdivision']})",
    )


def dung_pham_vi(dong: dict[str, Any], phan_khu: str, loai_can: str) -> KetQuaDoiChieu:
    """Mọi mã căn nêu ra phải thuộc đúng phân khu và loại căn — kỳ vọng của M03b.

    Kiểm bằng DB chứ không bằng bộ lọc mà agent tự ghi: agent kế thừa sai tiêu
    chí thì bộ lọc của nó cũng sai theo, và phép kiểm sẽ hợp thức hoá cái sai đó.
    """
    ma = _ma_can_trong(dong.get("cau_tra_loi", ""))
    if not ma:
        return KetQuaDoiChieu(None, "Không nêu mã căn nào để đối chiếu")

    rows = _hoi(
        "SELECT unit_code, subdivision, unit_type FROM inventory_units WHERE unit_code = ANY(%s)",
        (ma,),
    )
    lac = [f"{u} ({s}, {t})" for u, s, t in rows if s != phan_khu or not t.startswith(loai_can)]
    thieu = [m for m in ma if m not in {r[0] for r in rows}]
    loi = lac + [f"{m} không có trong DB" for m in thieu]
    return KetQuaDoiChieu(
        dat=not loi,
        giai_thich=(f"cả {len(ma)} căn đúng {phan_khu} / {loai_can}" if not loi else "; ".join(loi)),
        su_that_db=f"yêu cầu: {phan_khu} · {loai_can}",
    )


def doi_chieu(ma: str, cau_tra_loi: str) -> KetQuaDoiChieu | None:
    """Chạy phép kiểm của case, hoặc None nếu case này không có phép kiểm DB."""
    ham = PHEP_KIEM.get(ma)
    if ham is None:
        return None
    try:
        return ham(cau_tra_loi)
    except Exception as exc:  # noqa: BLE001 - không kết nối được DB thì để "chưa kết luận"
        return KetQuaDoiChieu(None, f"Không đối chiếu được: {type(exc).__name__}: {exc}")
