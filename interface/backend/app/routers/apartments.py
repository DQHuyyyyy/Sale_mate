from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from psycopg import errors as pg_errors

from app.core.columns import (
    COL_DIEN_TICH,
    COL_GIA,
    COL_HUONG,
    COL_LOAI_CAN,
    COL_NOI_THAT,
    COL_PHAN_KHU,
    COL_SO_DO,
    COL_SO_PHONG,
    COL_TANG,
    COL_TINH_TRANG,
    COL_TOA,
    COL_VIEW,
    TINH_TRANG_CON,
    normalize_sql,
)
from app.core.db import fetch_all, fetch_one, get_conn
from app.core.deps import get_optional_user, require_admin
from app.core.schema import numeric_columns_ready
from app.schemas.apartment import (
    PRICE_MAX,
    PRICE_MIN,
    ApartmentCreate,
    ApartmentDetail,
    ApartmentListItem,
)
from app.schemas.auth import CurrentUser
from app.services.storage import StorageError, delete_object, safe_file_name, upload_bytes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/apartments", tags=["apartments"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def apartment_columns() -> str:
    """Danh sách cột cho SELECT, map tên cột tiếng Việt sang field của response.

    Chưa chạy migration 001 thì `gia_tri`/`dien_tich_so` chưa tồn tại — trả NULL
    để response giữ nguyên hình dạng, frontend không phải phân biệt hai trường hợp.
    """
    if numeric_columns_ready():
        gia_tri = "a.gia_tri"
        dien_tich_so = "a.dien_tich_so"
    else:
        gia_tri = "NULL::numeric AS gia_tri"
        dien_tich_so = "NULL::numeric AS dien_tich_so"

    return f"""
    a.{"ma_can"},
    a.{COL_TOA}          AS toa,
    a.{COL_TANG}         AS tang,
    a.{COL_SO_PHONG}     AS so_phong,
    a.{COL_LOAI_CAN}     AS loai_can,
    a.{COL_DIEN_TICH}    AS dien_tich,
    {dien_tich_so},
    a.{COL_HUONG}        AS huong,
    a.{COL_VIEW}         AS "view",
    a.{COL_SO_DO}        AS so_do,
    a.{COL_GIA}          AS gia,
    {gia_tri},
    a.{COL_NOI_THAT}     AS noi_that,
    a.{COL_TINH_TRANG}   AS tinh_trang,
    iu.status            AS tinh_trang_chi_tiet,
    a.{COL_PHAN_KHU}     AS phan_khu
"""


# `tinh_trang` thô chỉ có Còn/Hết và vẫn là thứ điều khiển luồng BÁN — đừng đổi
# nghĩa của nó. `tinh_trang_chi_tiet` là ba mức suy ra trong VIEW
# `inventory_units` (migration 010), dùng để HIỂN THỊ.
#
# Đọc từ chính view mà chatbot đọc, không tự tính lại ở đây: hai nơi cùng suy ra
# một trạng thái là hai nơi để lệch, và lệch kiểu này thì portal nói "Còn" trong
# khi trợ lý nói "Đã đặt cọc" cho cùng một căn.
JOIN_TINH_TRANG = "LEFT JOIN inventory_units iu ON iu.unit_code = a.ma_can"


def _format_price(gia_tri: Decimal) -> str:
    """1.8 -> '1,8 tỷ'  |  4 -> '4 tỷ' — đúng cách viết tiếng Việt."""
    text = f"{gia_tri.normalize():f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} tỷ"


def _format_area(dien_tich_so: Decimal) -> str:
    text = f"{dien_tich_so.normalize():f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')}m2"


@router.get("", response_model=list[ApartmentListItem])
def search_apartments(
    tower: str | None = Query(default=None, description="Mã tòa, ví dụ S1"),
    price_min: float | None = Query(default=None, ge=PRICE_MIN, le=PRICE_MAX),
    price_max: float | None = Query(default=None, ge=PRICE_MIN, le=PRICE_MAX),
    price_max_exclusive: bool = Query(
        default=False,
        description='Loại luôn căn có giá bằng đúng price_max. Dùng cho câu "dưới X tỷ".',
    ),
    subdivision: str | None = Query(default=None, description="Phân khu, ví dụ 'Ocean Park 2'"),
    type: str | None = Query(default=None, description="Loại căn, ví dụ '2 PN, 1WC'"),
    wc: int | None = Query(default=None, ge=1, le=9, description="Số nhà vệ sinh"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: CurrentUser | None = Depends(get_optional_user),
) -> list[ApartmentListItem]:
    """Tìm kiếm căn hộ. Luôn chỉ trả căn "Tình trạng" = 'Còn'."""
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giá từ đang lớn hơn giá đến. Đổi lại hai ô giá giúp mình.",
        )

    has_price_filter = price_min is not None or price_max is not None
    if has_price_filter and not numeric_columns_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Chưa lọc được theo giá vì bảng căn hộ thiếu cột số gia_tri. "
                "Chạy interface/backend/migrations/001_alter_salemate_v1.sql "
                "rồi khởi động lại backend."
            ),
        )

    where = [f"a.{COL_TINH_TRANG} = %s"]
    params: list[object] = [TINH_TRANG_CON]

    if tower:
        where.append(f"a.{COL_TOA} = %s")
        params.append(tower)
    if subdivision:
        # Trợ lý S đẩy bộ lọc này lên URL sau khi trả lời "có 4 căn ở Ocean Park
        # 2 dưới 3 tỷ" — thiếu nó thì lưới bên trái vẫn hiện đủ 21 căn và người
        # dùng thấy hai con số vênh nhau.
        #
        # Chuẩn hoá trước khi so, giống `inventory_search` phía lõi AI: dữ liệu
        # ghi "Ocean Park 2" còn model có thể gửi "OceanPark 2" hay "ocean park 2".
        where.append(f"{normalize_sql(f'a.{COL_PHAN_KHU}')} = {normalize_sql('%s')}")
        params.append(subdivision)
    if type:
        # Khớp theo TIỀN TỐ, không phải bằng đúng — và đây là chỗ từng làm lưới
        # bên trái trả 0 căn trong khi trợ lý liệt kê đủ danh sách.
        #
        # Lõi AI trả `unit_type` là tiền tố "2PN" mỗi khi số phòng ngủ ứng với
        # NHIỀU giá trị thật trong DB (xem `_match_unit_type`) — mà 2PN có tới
        # hai: "2PN, 1WC" và "2PN, 2WC". So bằng đúng thì "2pn" không bao giờ
        # bằng "2pn,2wc", nên mọi câu hỏi theo số phòng ngủ đều ra rỗng.
        #
        # Tiền tố an toàn cho cả hai nguồn: dropdown trên form gửi nguyên chuỗi
        # đầy đủ ("2PN, 2WC") và chuỗi đó vẫn là tiền tố của chính nó.
        #
        # Luật này phải khớp `inventory_search` ở src/agents/tools/search.py —
        # hai bên lệch nhau là chat và lưới nói hai tập căn khác nhau.
        where.append(f"{normalize_sql(f'a.{COL_LOAI_CAN}')} LIKE {normalize_sql('%s')} || '%%'")
        params.append(type)
    if wc is not None:
        # Số vệ sinh nằm ở ĐUÔI chuỗi loại căn: "2PN, 1WC" -> "2pn,1wc".
        #
        # Bộ lọc RIÊNG chứ không gộp vào `type`, vì `type` khớp theo tiền tố nên
        # câu "căn 2 vệ sinh" — không nêu phòng ngủ — không diễn đạt được bằng
        # nó. Cùng luật với `inventory_search` ở src/agents/tools/search.py.
        where.append(f"{normalize_sql(f'a.{COL_LOAI_CAN}')} LIKE '%%' || %s")
        params.append(f"{wc}wc")
    # Chỉ ràng giá khi client thực sự gửi — nếu không, căn chưa parse được
    # gia_tri (NULL) vẫn hiện ra thay vì biến mất im lặng.
    if price_min is not None:
        where.append("a.gia_tri >= %s")
        params.append(price_min)
    if price_max is not None:
        # Trợ lý S bật cờ này khi người dùng nói "dưới 3 tỷ" — nghĩa là KHÔNG
        # gồm căn giá đúng 3 tỷ. Ô "Đến" trên form vẫn tính cả biên vì đó là một
        # khoảng, không phải một câu. Thiếu cờ thì chat đếm 21 còn lưới hiện 25
        # và người dùng thấy ngay hai con số vênh nhau.
        where.append("a.gia_tri < %s" if price_max_exclusive else "a.gia_tri <= %s")
        params.append(price_max)

    order_by = "a.gia_tri NULLS LAST, a.ma_can" if numeric_columns_ready() else "a.ma_can"

    sql = f"""
        SELECT {apartment_columns()},
               img.image_url AS thumbnail
        FROM salemate_v1 a
        {JOIN_TINH_TRANG}
        LEFT JOIN LATERAL (
            SELECT i.image_url
            FROM apartment_images i
            WHERE i.ma_can = a.ma_can AND i.image_url IS NOT NULL
            ORDER BY i.sort_order NULLS LAST, i.id
            LIMIT 1
        ) img ON TRUE
        WHERE {" AND ".join(where)}
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    return [ApartmentListItem(**row) for row in fetch_all(sql, tuple(params))]


def _load_detail(ma_can: str) -> ApartmentDetail:
    row = fetch_one(
        f"SELECT {apartment_columns()} FROM salemate_v1 a {JOIN_TINH_TRANG} WHERE a.ma_can = %s",
        (ma_can,),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy căn {ma_can}.",
        )

    images = fetch_all(
        """
        SELECT id, image_url, storage_path, file_name, sort_order, created_at
        FROM apartment_images
        WHERE ma_can = %s
        ORDER BY sort_order NULLS LAST, id
        """,
        (ma_can,),
    )
    return ApartmentDetail(**row, images=images)


@router.get("/{ma_can}", response_model=ApartmentDetail)
def get_apartment(
    ma_can: str,
    _: CurrentUser | None = Depends(get_optional_user),
) -> ApartmentDetail:
    return _load_detail(ma_can)


@router.post("", response_model=ApartmentDetail, status_code=status.HTTP_201_CREATED)
def create_apartment(
    payload: ApartmentCreate,
    _: CurrentUser = Depends(require_admin),
) -> ApartmentDetail:
    """Thêm căn hộ (admin).

    Cột text hiển thị được sinh từ cột số nên hai bên không bao giờ lệch nhau.
    Ảnh: truyền sẵn URL qua `image_urls`, hoặc upload file qua
    POST /api/apartments/{ma_can}/images.
    """
    columns = [
        "ma_can",
        COL_TOA,
        COL_TANG,
        COL_SO_PHONG,
        COL_LOAI_CAN,
        COL_DIEN_TICH,
        COL_HUONG,
        COL_VIEW,
        COL_SO_DO,
        COL_GIA,
        COL_NOI_THAT,
        COL_TINH_TRANG,
    ]
    values: list[object] = [
        payload.ma_can,
        payload.toa,
        payload.tang,
        payload.so_phong,
        payload.loai_can,
        _format_area(payload.dien_tich_so),
        payload.huong,
        payload.view,
        payload.so_do,
        _format_price(payload.gia_tri),
        payload.noi_that,
        payload.tinh_trang,
    ]
    # KHÔNG ghi gia_tri / dien_tich_so: đó là cột GENERATED, Postgres tự tính từ
    # hai cột text ở trên. Ghi vào là lỗi ngay.
    placeholders = ", ".join(["%s"] * len(values))

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO salemate_v1 ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
            for order, url in enumerate(payload.image_urls):
                cur.execute(
                    """
                    INSERT INTO apartment_images (ma_can, image_url, sort_order)
                    VALUES (%s, %s, %s)
                    """,
                    (payload.ma_can, url, order),
                )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mã căn {payload.ma_can} đã tồn tại. Dùng mã khác.",
        ) from exc

    return _load_detail(payload.ma_can)


@router.post("/{ma_can}/images", response_model=ApartmentDetail)
async def upload_apartment_images(
    ma_can: str,
    files: list[UploadFile] = File(...),
    _: CurrentUser = Depends(require_admin),
) -> ApartmentDetail:
    """Upload ảnh lên Supabase Storage rồi ghi vào apartment_images (admin).

    Không có trong API.md — thêm để form "Thêm căn hộ" upload được file thật
    mà không phải đưa service role key ra frontend.
    """
    exists = fetch_one("SELECT 1 AS ok FROM salemate_v1 WHERE ma_can = %s", (ma_can,))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy căn {ma_can}. Tạo căn trước rồi mới thêm ảnh.",
        )

    next_order = fetch_one(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM apartment_images WHERE ma_can = %s",
        (ma_can,),
    )
    order = int(next_order["next"]) if next_order else 0

    for upload in files:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {upload.filename} không phải ảnh JPG/PNG/WEBP/GIF.",
            )
        content = await upload.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Ảnh {upload.filename} lớn hơn 8MB. Nén lại rồi thử lại.",
            )

        storage_path = f"{ma_can}/{safe_file_name(upload.filename)}"
        try:
            url = upload_bytes(storage_path, content, upload.content_type)
        except StorageError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO apartment_images
                    (ma_can, image_url, storage_path, file_name, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (ma_can, url, storage_path, upload.filename, order),
            )
        order += 1

    return _load_detail(ma_can)


def _lay_anh(ma_can: str, image_id: int) -> dict:
    """Đọc một dòng ảnh, ràng buộc đúng căn.

    Ràng cả `ma_can` chứ không chỉ `id`: thiếu vế đó thì URL
    /api/apartments/VOP103/images/9999 sửa được ảnh của căn bất kỳ.
    """
    row = fetch_one(
        "SELECT id, storage_path FROM apartment_images WHERE id = %s AND ma_can = %s",
        (image_id, ma_can),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ảnh #{image_id} của căn {ma_can}.",
        )
    return row


def _danh_lai_thu_tu(cur, ma_can: str, anh_bia: int | None = None) -> None:
    """Đánh lại `sort_order` thành 0,1,2… cho mọi ảnh của một căn.

    `anh_bia` được kéo lên đầu, các ảnh còn lại giữ nguyên thứ tự tương đối.

    Một câu UPDATE duy nhất chứ không "swap hai dòng": ảnh nhập từ Google Drive
    hầu hết có sort_order = 0 nên không có thứ tự nào để swap — thứ tự thật do
    `id` quyết định, tức thứ tự file nằm trong folder Drive. Đánh lại toàn bộ
    làm cột này nói đúng những gì nó hứa ở migration 000: "0 = ảnh đại diện".
    """
    cur.execute(
        """
        WITH thu_tu AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY (id = %s) DESC, sort_order NULLS LAST, id
                   ) - 1 AS moi
            FROM apartment_images
            WHERE ma_can = %s
        )
        UPDATE apartment_images i
        SET sort_order = t.moi
        FROM thu_tu t
        WHERE i.id = t.id AND i.sort_order IS DISTINCT FROM t.moi
        """,
        (anh_bia, ma_can),
    )


@router.patch("/{ma_can}/images/{image_id}/dai-dien", response_model=ApartmentDetail)
def set_cover_image(
    ma_can: str,
    image_id: int,
    _: CurrentUser = Depends(require_admin),
) -> ApartmentDetail:
    """Đặt một ảnh làm ảnh đại diện (admin).

    Ảnh đại diện KHÔNG phải một cột riêng — nó là dòng có `sort_order` nhỏ nhất,
    đúng thứ mà cả lưới tìm kiếm lẫn trang chi tiết đang đọc. Giữ một nguồn sự
    thật như vậy thì bìa trên thẻ tìm kiếm và ảnh đầu trong gallery không bao giờ
    lệch nhau; thêm cột `cover_image_id` là dựng ra nơi thứ hai để lệch.
    """
    _lay_anh(ma_can, image_id)

    with get_conn() as conn, conn.cursor() as cur:
        _danh_lai_thu_tu(cur, ma_can, anh_bia=image_id)

    return _load_detail(ma_can)


@router.delete("/{ma_can}/images/{image_id}", response_model=ApartmentDetail)
def delete_apartment_image(
    ma_can: str,
    image_id: int,
    _: CurrentUser = Depends(require_admin),
) -> ApartmentDetail:
    """Xoá một ảnh khỏi căn (admin).

    Xoá dòng DB TRƯỚC, xoá object trên Storage sau và không chặn nếu bước đó
    hỏng: thứ người dùng muốn là ảnh biến mất khỏi trang, mà trang đọc từ DB.
    Một file mồ côi trong bucket thì không ai nhìn thấy, còn báo lỗi sau khi
    dòng đã xoá thì người dùng bấm lại một việc đã xong.

    Căn không còn ảnh nào là trạng thái hợp lệ — frontend hiện khung nhà thay thế.
    """
    anh = _lay_anh(ma_can, image_id)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM apartment_images WHERE id = %s AND ma_can = %s", (image_id, ma_can))
        # Xoá xong còn lỗ trống ở giữa dãy số. Ordering vẫn đúng, nhưng để cột
        # này luôn là 0,1,2… thì lần đọc sau không phải đoán.
        _danh_lai_thu_tu(cur, ma_can)

    if anh.get("storage_path"):
        try:
            delete_object(str(anh["storage_path"]))
        except StorageError:
            logger.warning(
                "Đã xoá ảnh #%s của căn %s khỏi DB nhưng còn file %s trong bucket",
                image_id,
                ma_can,
                anh["storage_path"],
            )

    return _load_detail(ma_can)
