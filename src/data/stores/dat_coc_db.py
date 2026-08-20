"""Lưu lead đặt cọc — khách để lại số điện thoại để đội sale gọi chốt.

Đây là đầu ra có giá trị nhất của cả trợ lý: tư vấn hay tới đâu mà không giữ
được thông tin liên hệ thì khách đóng tab là mất.

Cùng khuôn với `inventory_db.py`: SQLAlchemy Core (không ORM) để chạy được cả
trên SQLite (test) lẫn Postgres (thật), và engine dựng một lần theo tiến trình.

⚠️ Bảng này chứa thông tin cá nhân của khách thật. Không log nội dung bản ghi —
`trace()` gắn session_id vào mọi dòng log, số điện thoại lọt vào đó là lọt ra
ngoài phạm vi bảng có RLS. Xem migration 009.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    desc,
    func,
    select,
)
from sqlalchemy.engine import Engine

from src.core.config import get_settings

metadata = MetaData()

dat_coc_lead_table = Table(
    "dat_coc_lead",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ma_can", String, nullable=False),
    Column("ho_ten", String, nullable=False, default=""),
    Column("so_dien_thoai", String, nullable=False),
    Column("ghi_chu", String, nullable=False, default=""),
    Column("session_id", String, nullable=False, default=""),
    # `server_default` chứ không chỉ `default`: `default` là mặc định phía
    # PYTHON, chỉ áp dụng khi ghi QUA SQLAlchemy. Route portal ghi bằng SQL
    # thuần và đã ăn NotNullViolation vì cột không có DEFAULT thật trong DDL.
    Column("trang_thai", String, nullable=False, server_default="new"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


# Trạng thái lead ĐANG giữ căn — khớp migration 010 và bản ở portal backend.
_DANG_GIU = ("new", "da_goi", "da_coc")

# Số căn một số điện thoại được giữ cùng lúc. Người mua thật cân nhắc vài căn là
# chuyện bình thường, ba là rộng rãi.
TOI_DA_GIU_MOI_SO = 3


class DatCocDB:
    """Ghi và đọc lead đặt cọc. Đồng bộ — bên gọi async tự bọc `asyncio.to_thread`."""

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(database_url)

    def ensure_table(self) -> None:
        """Tạo bảng — CHỈ trên SQLite của test. Trên Postgres thì tuyệt đối không.

        ⚠️ Đây là chỗ đã gây ra một sự cố thật. Hàm này chạy ở đầu MỌI thao tác,
        và trên database thật nó đã lặng lẽ tạo `dat_coc_lead` trước khi ai kịp
        chạy migration 009. Bảng SQLAlchemy dựng ra KHÁC bảng migration khai:

        - `default="new"` của SQLAlchemy là mặc định phía PYTHON, không sinh ra
          `DEFAULT` trong DDL → INSERT bằng SQL thuần (route portal) ném
          NotNullViolation.
        - Không có CHECK trên `trang_thai` → nhận mọi chuỗi, và migration 010
          suy trạng thái căn từ đúng cột đó.
        - Không có unique index chống trùng → chốt chặn "bấm hai lần" biến mất.
        - **Không có RLS** → bảng chứa tên và số điện thoại khách thật nằm mở.

        Migration là nguồn sự thật của schema trên Postgres. Test dùng SQLite
        in-memory nên vẫn cần tạo bảng, và ở đó không có migration nào chạy.
        """
        if self._engine.dialect.name == "postgresql":
            return
        metadata.create_all(self._engine, tables=[dat_coc_lead_table])

    def da_co_hom_nay(self, ma_can: str, so_dien_thoai: str) -> bool:
        """Cùng số, cùng căn, cùng ngày thì coi là đã ghi rồi.

        Trợ lý chạy lại tool khi người dùng gõ lại câu cũ, và migration 009 có
        unique index chặn ở tầng DB. Hỏi trước thì báo cho khách được câu tử tế
        ("mình đã ghi nhận rồi") thay vì để insert ném lỗi ra giữa cuộc trò
        chuyện.
        """
        self.ensure_table()
        hom_nay = datetime.now(UTC).date()
        stmt = select(dat_coc_lead_table.c.created_at).where(
            dat_coc_lead_table.c.ma_can == ma_can,
            dat_coc_lead_table.c.so_dien_thoai == so_dien_thoai,
        )
        with self._engine.connect() as conn:
            for (tao_luc,) in conn.execute(stmt):
                if tao_luc is not None and _ngay(tao_luc) == hom_nay:
                    return True
        return False

    def so_can_dang_giu(self, so_dien_thoai: str) -> int:
        """Số căn KHÁC NHAU mà một số điện thoại đang giữ.

        Phanh chống khoá sạch tồn kho: một lead còn hiệu lực làm căn thành
        "Đã đặt cọc", và cọc không tự hết hạn, nên không chặn thì một người gửi được trăm
        yêu cầu và cả kho thành "hết hàng" cho tới khi có người dọn tay.

        `interface/backend/app/routers/dat_coc.py` có bản y hệt cho nút bấm trên
        portal. Hai service tách nhau nên không dùng chung được — nhưng chặn một
        bên thôi là vô nghĩa, đường còn lại vẫn mở.
        """
        self.ensure_table()
        stmt = select(dat_coc_lead_table.c.ma_can).where(
            dat_coc_lead_table.c.so_dien_thoai == so_dien_thoai,
            dat_coc_lead_table.c.trang_thai.in_(_DANG_GIU),
        )
        with self._engine.connect() as conn:
            return len({ma for (ma,) in conn.execute(stmt)})

    def ghi_lead(
        self,
        *,
        ma_can: str,
        so_dien_thoai: str,
        ho_ten: str = "",
        ghi_chu: str = "",
        session_id: str = "",
    ) -> int:
        """Ghi một lead, trả về id để báo lại cho khách làm mã tra cứu."""
        self.ensure_table()
        with self._engine.begin() as conn:
            ket_qua = conn.execute(
                dat_coc_lead_table.insert().values(
                    ma_can=ma_can,
                    ho_ten=ho_ten,
                    so_dien_thoai=so_dien_thoai,
                    ghi_chu=ghi_chu,
                    session_id=session_id,
                    trang_thai="new",
                    created_at=datetime.now(UTC),
                )
            )
        khoa = ket_qua.inserted_primary_key
        return int(khoa[0]) if khoa else 0

    def danh_sach(self, *, gioi_han: int = 100) -> list[dict[str, Any]]:
        """Lead mới nhất trước — thứ đội sale cần gọi ngay nằm trên đầu."""
        self.ensure_table()
        stmt = select(dat_coc_lead_table).order_by(desc(dat_coc_lead_table.c.created_at)).limit(gioi_han)
        with self._engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt)]


def _ngay(gia_tri: Any):
    """Lấy phần ngày, chịu được cả datetime lẫn chuỗi SQLite trả về."""
    if isinstance(gia_tri, datetime):
        return gia_tri.date()
    return datetime.fromisoformat(str(gia_tri)).date()


@lru_cache
def get_dat_coc_db() -> DatCocDB:
    """Singleton theo tiến trình — tránh tạo pool mới mỗi lần tool chạy."""
    return DatCocDB(get_settings().database_url)
