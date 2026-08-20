"""Lead đặt cọc — chatbot ghi vào, sale và admin xử lý ở đây.

Đây là VAN XẢ của cơ chế ba trạng thái. Giữ chỗ không tự hết hạn (quyết định
sản phẩm), nên nếu không có route đổi trạng thái thì cách duy nhất trả một căn
về "Còn" là chạy SQL tay trên production.

Trạng thái CĂN không nằm ở đây — nó suy ra từ chính bảng này trong VIEW
`inventory_units` (migration 010). Sale đổi `trang_thai` của lead là căn đổi
theo ngay, cả ở portal lẫn ở chatbot, không ai phải đồng bộ gì.

⚠️ Route nào ở file này cũng trả SỐ ĐIỆN THOẠI khách thật. Không mở cho anon,
không log nội dung trả về.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors

from app.core.columns import COL_TINH_TRANG, TINH_TRANG_CON, TINH_TRANG_HET
from app.core.db import fetch_all, fetch_one, get_conn
from app.core.deps import get_optional_user, require_sale_hoac_admin
from app.core.schema import numeric_columns_ready
from app.schemas.auth import CurrentUser
from app.schemas.dat_coc import DatCocLead, DoiTrangThaiLead, KetQuaTaoLead, TaoLead, TrangThaiLead

router = APIRouter(prefix="/api/dat-coc", tags=["dat-coc"])

# Số căn một số điện thoại được giữ cùng lúc.
#
# ⚠️ Đây là phanh chống KHOÁ SẠCH TỒN KHO. Một lead còn hiệu lực làm căn thành
# "Đã đặt cọc" và cọc không tự hết hạn, nên nếu không chặn thì bất kỳ ai cũng gửi
# được 100 request và cả kho thành "hết hàng" cho tới khi có người dọn tay.
#
# Người mua thật cân nhắc vài căn là chuyện bình thường, ba là rộng rãi.
TOI_DA_GIU_MOI_SO = 3

# Trạng thái lead ĐANG giữ căn — khớp migration 010.
_DANG_GIU = ("new", "da_goi", "da_coc")

_COT = """
    l.id, l.ma_can, l.ho_ten, l.so_dien_thoai, l.ghi_chu,
    l.trang_thai, l.created_at, l.sale_id,
    u.full_name AS sale_ten,
    iu.status AS tinh_trang_can
"""


def chuan_hoa_sdt(tho: str) -> str:
    """Bỏ ký tự ngăn cách, quy +84 về 0.

    Chép nguyên luật của `src/agents/tools/dat_coc.py`. Hai service tách nhau
    nên không import chung được, nhưng hai bên PHẢI nhận đúng một tập số: lệch
    thì cùng một khách gọi qua chat được mà bấm nút thì bị từ chối, và bảng có
    hai định dạng số cho cùng một người nên unique index chống trùng thất bại.
    """
    so = re.sub(r"[^\d+]", "", tho)
    if so.startswith("+84"):
        return "0" + so[3:]
    if so.startswith("84") and len(so) == 11:
        return "0" + so[2:]
    return so


@router.post("", response_model=KetQuaTaoLead, status_code=status.HTTP_201_CREATED)
def tao_lead(payload: TaoLead, nguoi_tao: CurrentUser | None = Depends(get_optional_user)) -> KetQuaTaoLead:
    """Khách bấm "Đặt cọc" trên trang căn hộ. KHÔNG cần đăng nhập.

    Cố ý mở cho khách vãng lai: bắt đăng nhập trước khi để lại số là chặn đúng
    người đang muốn mua. Widget chat vốn đã ghi lead mà không cần tài khoản, nên
    nút này không mở thêm bề mặt nào mới — chỉ làm nó dễ thấy hơn.

    Sale ĐANG ĐĂNG NHẬP bấm nút này thì lead ghi thêm `sale_id` — họ đang đặt hộ
    một khách ngồi trước mặt, và đó là cơ sở để admin biết lead nào của ai.
    `get_optional_user` chứ không phải `get_current_user`: thiếu token vẫn phải
    chạy được.

    Bù lại, mọi chốt chặn phải nằm ở đây: định dạng số, tình trạng căn, và trần
    số căn một người giữ cùng lúc.
    """
    sdt = chuan_hoa_sdt(payload.so_dien_thoai)
    if not re.fullmatch(r"0\d{9}", sdt):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số điện thoại chưa đúng. Nhập dạng 09xxxxxxxx giúp mình.",
        )

    ma_can = payload.ma_can.upper()
    can = fetch_one("SELECT status FROM inventory_units WHERE unit_code = %s", (ma_can,))
    if can is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy căn {ma_can}.",
        )
    if can["status"] != "available":
        # Không hứa một căn cho hai người. Cùng luật với tool `dat_coc` của lõi AI.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Căn {ma_can} hiện đã có người đặt cọc hoặc đã bán. Bạn chọn căn khác giúp mình.",
        )

    dang_giu = fetch_one(
        "SELECT count(DISTINCT ma_can) AS so_can FROM dat_coc_lead "
        "WHERE so_dien_thoai = %s AND trang_thai = ANY(%s)",
        (sdt, list(_DANG_GIU)),
    )
    if dang_giu and dang_giu["so_can"] >= TOI_DA_GIU_MOI_SO:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Số này đang giữ chỗ {TOI_DA_GIU_MOI_SO} căn rồi. "
                "Đội sale sẽ liên hệ để chốt trước khi bạn giữ thêm căn mới."
            ),
        )

    try:
        with get_conn() as conn, conn.cursor() as cur:
            # Ghi THẲNG `trang_thai` và `created_at`, không dựa vào DEFAULT của
            # cột. Bảng trên database thật do `ensure_table()` của lõi AI tạo
            # ra chứ không phải migration 009, nên nó KHÔNG có DEFAULT nào —
            # bỏ hai cột này ra là NotNullViolation, và đó là 500 đầu tiên của
            # tính năng. Migration 011 vá lại schema, nhưng câu INSERT không nên
            # phụ thuộc vào việc migration nào đã chạy ở môi trường nào.
            cur.execute(
                "INSERT INTO dat_coc_lead "
                "(ma_can, ho_ten, so_dien_thoai, ghi_chu, session_id, sale_id, trang_thai, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'new', now()) RETURNING id",
                (
                    ma_can,
                    payload.ho_ten.strip(),
                    sdt,
                    payload.ghi_chu.strip(),
                    "portal",
                    nguoi_tao.id if nguoi_tao and nguoi_tao.role == "sale" else None,
                ),
            )
            lead_id = cur.fetchone()["id"]
    except pg_errors.UniqueViolation:
        # Unique index (ma_can, so_dien_thoai, ngày) của migration 009. Bấm hai
        # lần là bấm nhầm, không phải hai khách — trả lời tử tế thay vì 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Yêu cầu giữ chỗ căn {ma_can} của số này đã được ghi nhận hôm nay rồi.",
        ) from None

    return KetQuaTaoLead(
        id=lead_id,
        ma_can=ma_can,
        loi_nhan="Đã ghi nhận yêu cầu giữ chỗ. Đội sale sẽ liên hệ với bạn trong thời gian sớm nhất.",
    )


@router.get("", response_model=list[DatCocLead])
def danh_sach(
    nguoi_xem: CurrentUser = Depends(require_sale_hoac_admin),
    trang_thai: TrangThaiLead | None = Query(default=None, description="Lọc theo trạng thái lead"),
    ma_can: str | None = Query(default=None, description="Lọc theo một mã căn"),
) -> list[DatCocLead]:
    """Lead mới nhất trước — sale mở màn hình là để gọi người vừa để lại số.

    Admin thấy TẤT CẢ, sale chỉ thấy lead của chính mình. Lead của khách vãng
    lai (`sale_id` rỗng) cũng vào tầm nhìn của sale — đó là khách chưa ai nhận,
    và để họ nằm đó không ai gọi thì cả tính năng vô nghĩa.
    """
    dieu_kien: list[str] = []
    tham_so: list[object] = []
    if nguoi_xem.role != "admin":
        dieu_kien.append("(l.sale_id = %s OR l.sale_id IS NULL)")
        tham_so.append(nguoi_xem.id)
    if trang_thai:
        dieu_kien.append("l.trang_thai = %s")
        tham_so.append(trang_thai)
    if ma_can:
        dieu_kien.append("l.ma_can = %s")
        tham_so.append(ma_can.upper())

    where = f"WHERE {' AND '.join(dieu_kien)}" if dieu_kien else ""
    rows = fetch_all(
        f"""
        SELECT {_COT}
        FROM dat_coc_lead l
        LEFT JOIN inventory_units iu ON iu.unit_code = l.ma_can
        LEFT JOIN users u ON u.id = l.sale_id
        {where}
        ORDER BY l.created_at DESC
        """,
        tuple(tham_so),
    )
    return [DatCocLead(**row) for row in rows]


@router.patch("/{lead_id}", response_model=DatCocLead)
def doi_trang_thai(
    lead_id: int,
    payload: DoiTrangThaiLead,
    nguoi_doi: CurrentUser = Depends(require_sale_hoac_admin),
) -> DatCocLead:
    """Đổi trạng thái một lead.

    Đây là chỗ nhả một căn về "Còn" (`bo`), và cũng là chỗ CHỐT BÁN (`da_ban`).
    """
    if payload.trang_thai == "da_ban":
        row = _chot_ban(lead_id, nguoi_doi)
    else:
        row = fetch_one(
            """
            UPDATE dat_coc_lead SET trang_thai = %s WHERE id = %s
            RETURNING id, ma_can, ho_ten, so_dien_thoai, ghi_chu, trang_thai, created_at, sale_id
            """,
            (payload.trang_thai, lead_id),
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lead #{lead_id}.",
        )

    # Đọc lại tình trạng căn SAU khi cập nhật: nó là hệ quả của chính thay đổi
    # vừa rồi, và sale cần thấy ngay để biết mình vừa nhả hay vừa khoá một căn.
    can = fetch_one("SELECT status FROM inventory_units WHERE unit_code = %s", (row["ma_can"],))
    sale = fetch_one("SELECT full_name FROM users WHERE id = %s", (row["sale_id"],)) if row["sale_id"] else None
    return DatCocLead(
        **row,
        sale_ten=sale["full_name"] if sale else None,
        tinh_trang_can=can["status"] if can else None,
    )


def _chot_ban(lead_id: int, nguoi_doi: CurrentUser) -> dict | None:
    """Chốt bán từ một lead: ghi `sales_history`, khoá căn, đánh dấu lead.

    Ba thao tác trong MỘT transaction, và căn bị khoá `FOR UPDATE` — cùng khuôn
    với `POST /api/sales`, nên hai người bấm bán cùng lúc thì chỉ một người
    thành công.

    Tên và số điện thoại lấy từ CHÍNH lead, không bắt nhập lại. Bắt gõ lại là
    thừa việc và mở đường cho một lỗi im lặng: `sales_history` mang tên một
    khách khác với người thật sự mua, mà không gì đối chiếu được.

    Giá ghi theo GIÁ NIÊM YẾT. Màn Giao dịch không có ô nhập giá — muốn ghi giá
    thương lượng khác thì dùng "Ghi nhận đã bán" ở trang căn hộ, chỗ đó có ô đó.
    """
    gia_tri_select = "gia_tri" if numeric_columns_ready() else "NULL::numeric AS gia_tri"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, ma_can, ho_ten, so_dien_thoai, ghi_chu, trang_thai, created_at, sale_id "
            "FROM dat_coc_lead WHERE id = %s FOR UPDATE",
            (lead_id,),
        )
        lead = cur.fetchone()
        if lead is None:
            return None
        if lead["trang_thai"] == "da_ban":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Lead #{lead_id} đã được chốt bán rồi.",
            )

        cur.execute(
            f"SELECT {COL_TINH_TRANG} AS tinh_trang, {gia_tri_select} "
            "FROM salemate_v1 WHERE ma_can = %s FOR UPDATE",
            (lead["ma_can"],),
        )
        can = cur.fetchone()
        if can is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy căn {lead['ma_can']}.",
            )
        if can["tinh_trang"] != TINH_TRANG_CON:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Căn {lead['ma_can']} đã bán rồi. Tải lại danh sách để xem căn còn.",
            )

        # Ai được ghi công: sale phụ trách lead, còn không thì người đang bấm.
        # `sales_history.sale_id` là NOT NULL nên phải có một trong hai — admin
        # chốt hộ một lead của khách vãng lai thì admin đứng tên, và đó là sự
        # thật: chính họ là người thao tác.
        cur.execute(
            """
            INSERT INTO sales_history (ma_can, sale_id, customer_name, customer_phone, sold_price)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                lead["ma_can"],
                lead["sale_id"] or nguoi_doi.id,
                lead["ho_ten"] or None,
                lead["so_dien_thoai"],
                can["gia_tri"],
            ),
        )
        cur.execute(
            f"UPDATE salemate_v1 SET {COL_TINH_TRANG} = %s WHERE ma_can = %s",
            (TINH_TRANG_HET, lead["ma_can"]),
        )
        cur.execute("UPDATE dat_coc_lead SET trang_thai = 'da_ban' WHERE id = %s", (lead_id,))

    return {**lead, "trang_thai": "da_ban"}
