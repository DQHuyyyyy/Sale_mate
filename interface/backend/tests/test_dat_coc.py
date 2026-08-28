"""Kiểm thử route lead đặt cọc — van xả của cơ chế bốn trạng thái.

Giữ chỗ KHÔNG tự hết hạn, nên route này là cách duy nhất trả một căn về "Còn".
Nó hỏng hoặc phân quyền sai thì hoặc tồn kho teo dần không ai gỡ được, hoặc số
điện thoại khách thật phơi ra ngoài.

Không chạm database: `fetch_all` / `fetch_one` bị thay bằng hàm giả.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import dat_coc as dat_coc_router  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SALE = CurrentUser(id=7, username="sale01", full_name="Nguyễn Văn Sale", role="sale")
ADMIN = CurrentUser(id=1, username="admin", full_name="Trần Quản Trị", role="admin")
KHACH = CurrentUser(id=9, username="khach01", full_name="Khách Lẻ", role="user")

_LEAD = {
    "id": 1,
    "ma_can": "VOP397",
    "ho_ten": "Nguyễn Văn A",
    "so_dien_thoai": "0912345678",
    "ghi_chu": "",
    "trang_thai": "new",
    "created_at": datetime(2026, 8, 17, 5, 36, tzinfo=UTC),
    "sale_id": None,
}


@pytest.fixture(autouse=True)
def _khong_cham_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        dat_coc_router,
        "fetch_all",
        lambda *a, **k: [{**_LEAD, "tinh_trang_can": "reserved", "sale_ten": None}],
    )
    monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a, **k: _fetch_one(sql))
    yield
    app.dependency_overrides.clear()


def _fetch_one(sql: str):
    """Phân biệt ba câu truy vấn trong `doi_trang_thai` theo nội dung SQL."""
    if "inventory_units" in sql:
        return {"status": "available"}
    if "FROM users" in sql:
        return {"full_name": "Nguyễn Văn Sale"}
    return {**_LEAD, "trang_thai": "bo"}


def as_user(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestPhanQuyen:
    """Bảng lead chở số điện thoại khách thật — sai phân quyền là lộ dữ liệu."""

    @pytest.mark.parametrize("nguoi_dung", [SALE, ADMIN])
    def test_sale_va_admin_deu_xem_duoc(self, nguoi_dung: CurrentUser) -> None:
        """Sale nhận cọc, admin giám sát — chặn admin thì không ai nhìn toàn cảnh."""
        assert as_user(nguoi_dung).get("/api/dat-coc").status_code == 200

    def test_nguoi_dung_thuong_bi_chan(self) -> None:
        assert as_user(KHACH).get("/api/dat-coc").status_code == 403

    def test_chua_dang_nhap_bi_chan(self) -> None:
        app.dependency_overrides.clear()

        assert TestClient(app).get("/api/dat-coc").status_code in (401, 403)

    def test_nguoi_dung_thuong_khong_doi_duoc_trang_thai(self) -> None:
        r = as_user(KHACH).patch("/api/dat-coc/1", json={"trang_thai": "bo"})

        assert r.status_code == 403


class TestDoiTrangThai:
    def test_huy_lead_thi_can_ve_con(self) -> None:
        """Đây là VAN XẢ. Giữ chỗ không tự hết hạn nên không có đường này thì
        cách duy nhất nhả một căn là chạy SQL tay trên production."""
        r = as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "bo"})

        assert r.status_code == 200
        assert r.json()["trang_thai"] == "bo"
        assert r.json()["tinh_trang_can"] == "available"

    def test_trang_thai_la_thi_tra_422_chu_khong_500(self) -> None:
        """Bảng có CHECK constraint; để Postgres ném thì client nhận 500 vô nghĩa."""
        r = as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "khong_co_that"})

        assert r.status_code == 422

    def test_lead_khong_ton_tai_tra_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda *a, **k: None)

        r = as_user(SALE).patch("/api/dat-coc/999", json={"trang_thai": "da_coc"})

        assert r.status_code == 404


class TestDanhSach:
    def test_tra_kem_tinh_trang_can(self) -> None:
        """Sale cần thấy hệ quả của lead lên căn, không phải mở thêm màn hình."""
        r = as_user(SALE).get("/api/dat-coc")

        assert r.json()[0]["tinh_trang_can"] == "reserved"

    def test_loc_theo_trang_thai_khong_no(self) -> None:
        assert as_user(SALE).get("/api/dat-coc", params={"trang_thai": "new"}).status_code == 200

    def test_loc_theo_trang_thai_la_bi_chan(self) -> None:
        assert as_user(SALE).get("/api/dat-coc", params={"trang_thai": "bay"}).status_code == 422


class TestTaoLeadCongKhai:
    """Nút "Đặt cọc" trên trang căn hộ — khách vãng lai gọi được, không cần đăng nhập.

    Đây là biên DUY NHẤT người lạ ghi được vào bảng chứa thông tin cá nhân, nên
    mọi chốt chặn phải nằm ở đây.
    """

    @pytest.fixture(autouse=True)
    def _khong_dang_nhap(self):
        app.dependency_overrides.clear()
        yield

    def _dat(self, client: TestClient, **ghi_de):
        body = {"ma_can": "VOP001", "ho_ten": "Nguyễn Văn A", "so_dien_thoai": "0912345678"}
        return client.post("/api/dat-coc", json={**body, **ghi_de})

    def test_khach_chua_dang_nhap_van_dat_coc_duoc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bắt đăng nhập trước khi để lại số là chặn đúng người đang muốn mua."""
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))
        monkeypatch.setattr(dat_coc_router, "get_conn", _fake_conn)

        assert self._dat(TestClient(app)).status_code == 201

    def test_khong_tra_lai_so_dien_thoai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Response đi qua log truy cập, proxy và devtools. Khách vừa tự gõ số đó."""
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))
        monkeypatch.setattr(dat_coc_router, "get_conn", _fake_conn)

        assert "0912345678" not in self._dat(TestClient(app)).text

    def test_so_dien_thoai_sai_dinh_dang_bi_chan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))

        assert self._dat(TestClient(app), so_dien_thoai="123456789").status_code == 400

    def test_can_da_co_nguoi_giu_thi_tu_choi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Không hứa một căn cho hai người — cùng luật với tool `dat_coc`."""
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql, trang_thai_can="holding"))

        assert self._dat(TestClient(app)).status_code == 409

    def test_can_khong_ton_tai_tra_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: None)

        assert self._dat(TestClient(app)).status_code == 404

    def test_mot_so_khong_giu_qua_nhieu_can(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Phanh chống khoá sạch tồn kho.

        Lead `new` làm căn thành "Đang giữ chỗ" và giữ chỗ KHÔNG tự hết hạn, nên
        thiếu vế này thì một người gửi 100 request là cả kho thành "hết hàng"
        cho tới khi có người dọn tay.
        """
        monkeypatch.setattr(
            dat_coc_router,
            "fetch_one",
            lambda sql, *a: _tra_loi(sql, so_can_dang_giu=dat_coc_router.TOI_DA_GIU_MOI_SO),
        )

        assert self._dat(TestClient(app)).status_code == 429

    def test_ghi_ro_trang_thai_va_created_at(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bảng trên database thật do `ensure_table()` của lõi AI tạo chứ không
        phải migration 009, nên nó KHÔNG có DEFAULT nào. Bỏ hai cột này ra khỏi
        INSERT là NotNullViolation — đó là 500 đầu tiên của tính năng."""
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))
        monkeypatch.setattr(dat_coc_router, "get_conn", _fake_conn)
        _SQL_DA_CHAY.clear()

        self._dat(TestClient(app))

        cau = next(s for s in _SQL_DA_CHAY if "INSERT" in s)
        assert "trang_thai" in cau
        assert "created_at" in cau

    def test_ghi_chu_qua_dai_bi_chan(self) -> None:
        """Ô ghi chú là chỗ duy nhất người lạ nhập được văn bản tự do."""
        assert self._dat(TestClient(app), ghi_chu="x" * 5000).status_code == 422


def _tra_loi(sql: str, *, trang_thai_can: str = "available", so_can_dang_giu: int = 0):
    if "inventory_units" in sql:
        return {"status": trang_thai_can}
    if "count(" in sql:
        return {"so_can": so_can_dang_giu}
    return None


_SQL_DA_CHAY: list[str] = []


class _FakeCursor:
    """Trả kết quả theo câu SQL vừa chạy — `_chot_ban` đọc lead rồi đọc căn."""

    tinh_trang_can = "Còn"
    trang_thai_lead = "new"

    def __init__(self):
        self._sql = ""

    def execute(self, sql, *a, **k):
        _SQL_DA_CHAY.append(sql)
        self._sql = sql
        return None

    def fetchone(self):
        if "FROM dat_coc_lead" in self._sql:
            return {**_LEAD, "trang_thai": type(self).trang_thai_lead}
        if "FROM salemate_v1" in self._sql:
            return {"tinh_trang": type(self).tinh_trang_can, "gia_tri": 2.25}
        return {"id": 42}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_conn():
    return _FakeConn()


class TestChotBanTuLead:
    """Bấm "Đã bán" trên một lead = ghi sales_history + khoá căn + đánh dấu lead.

    Ba việc trong một transaction. Trước đây sale phải rời màn Giao dịch, mở
    trang căn hộ và GÕ LẠI tên với số điện thoại của chính khách đang nằm trong
    lead — thừa việc, và gõ sai thì `sales_history` mang tên một người khác với
    người thật sự mua mà không gì đối chiếu được.
    """

    @pytest.fixture(autouse=True)
    def _gia_lap(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(dat_coc_router, "numeric_columns_ready", lambda: True)
        monkeypatch.setattr(dat_coc_router, "get_conn", _fake_conn)
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))
        _SQL_DA_CHAY.clear()
        yield

    def test_ghi_sales_history_va_khoa_can(self) -> None:
        r = as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"})

        assert r.status_code == 200
        assert r.json()["trang_thai"] == "da_ban"
        assert any("INSERT INTO sales_history" in s for s in _SQL_DA_CHAY)
        assert any("UPDATE salemate_v1" in s for s in _SQL_DA_CHAY)

    def test_khoa_can_bang_for_update(self) -> None:
        """Hai người bấm bán cùng lúc thì chỉ một người thành công."""
        as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"})

        assert sum("FOR UPDATE" in s for s in _SQL_DA_CHAY) == 2

    def test_lead_khong_bi_xoa_sau_khi_ban(self) -> None:
        """Dòng lead ở lại — đó là lịch sử của một giao dịch có thật."""
        r = as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"})

        assert r.json()["ma_can"] == "VOP397"
        assert r.json()["so_dien_thoai"] == "0912345678"

    def test_admin_cung_chot_ban_duoc(self) -> None:
        assert as_user(ADMIN).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"}).status_code == 200

    def test_nguoi_dung_thuong_bi_chan(self) -> None:
        assert as_user(KHACH).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"}).status_code == 403

    def test_can_da_ban_roi_thi_tra_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_FakeCursor, "tinh_trang_can", "Hết")

        assert as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"}).status_code == 409

    def test_lead_da_ban_roi_thi_tra_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bấm hai lần không được đẻ ra hai bản ghi bán cho cùng một căn."""
        monkeypatch.setattr(_FakeCursor, "trang_thai_lead", "da_ban")

        assert as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"}).status_code == 409


class TestQuyenSoHuu:
    """Vai trò trả lời "có được đụng vào lead không", KHÔNG trả lời "lead NÀY".

    `require_sale_hoac_admin` chỉ kiểm vai trò, nên trước khi vá thì bất kỳ sale
    nào cũng PATCH được lead của sale khác — và `RETURNING` đưa luôn tên với số
    điện thoại khách của họ về. `lead_id` là số nguyên tăng dần nên không phải
    đoán gì.
    """

    @pytest.fixture
    def _bat_sql(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple]]:
        """Ghi lại (SQL, tham số) của mọi lời gọi để kiểm chính mệnh đề WHERE."""
        da_chay: list[tuple[str, tuple]] = []

        def ghi(sql: str, tham_so: tuple = (), *a, **k):
            da_chay.append((sql, tham_so))
            return _fetch_one(sql)

        monkeypatch.setattr(dat_coc_router, "fetch_one", ghi)
        return da_chay

    def _cau_update(self, da_chay: list[tuple[str, tuple]]) -> tuple[str, tuple]:
        return next((sql, ts) for sql, ts in da_chay if "UPDATE dat_coc_lead" in sql)

    def test_sale_bi_rang_theo_sale_id(self, _bat_sql: list[tuple[str, tuple]]) -> None:
        as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "bo"})

        sql, tham_so = self._cau_update(_bat_sql)
        assert "sale_id" in sql, "Câu UPDATE không có điều kiện sở hữu"
        assert SALE.id in tham_so, "Điều kiện sở hữu không nhận id của người đang gọi"

    def test_lead_chua_ai_nhan_van_doi_duoc(self, _bat_sql: list[tuple[str, tuple]]) -> None:
        """Tập được GHI phải trùng tập được ĐỌC ở `danh_sach`.

        Khách tự đặt trên portal thì `sale_id` rỗng. Siết thành `sale_id = %s`
        thuần là sale nhìn thấy khách vãng lai trong danh sách mà không gọi rồi
        chốt được — hỏng đúng luồng mà màn `/giao-dich` sinh ra để phục vụ.
        """
        as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "bo"})

        sql, _ = self._cau_update(_bat_sql)
        assert "sale_id IS NULL" in sql

    def test_admin_khong_bi_rang(self, _bat_sql: list[tuple[str, tuple]]) -> None:
        """Admin vốn nhìn toàn hệ thống ở `danh_sach`; ràng ở đây là mâu thuẫn."""
        as_user(ADMIN).patch("/api/dat-coc/1", json={"trang_thai": "bo"})

        sql, tham_so = self._cau_update(_bat_sql)
        assert "sale_id" not in sql.split("RETURNING")[0]
        assert tham_so == ("bo", 1)

    def test_lead_cua_sale_khac_tra_404_va_khong_lo_thong_tin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mệnh đề WHERE không khớp ⇒ `fetch_one` trả None ⇒ 404.

        Hai vế đều quan trọng: không ghi được, và không đọc được. Trước khi vá
        thì `RETURNING` trả về `ho_ten` với `so_dien_thoai` của khách thuộc sale
        khác ngay trong body 200.
        """
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda *a, **k: None)

        r = as_user(SALE).patch("/api/dat-coc/42", json={"trang_thai": "da_coc"})

        assert r.status_code == 404
        assert _LEAD["so_dien_thoai"] not in r.text
        assert _LEAD["ho_ten"] not in r.text

    def test_chot_ban_cung_bi_rang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Nhánh NẶNG nhất: nó ghi `sales_history` và khoá căn.

        Bỏ sót ở đây là một sale chốt được giao dịch trên khách của sale khác, và
        `sales_history` đứng tên người kia.
        """
        monkeypatch.setattr(dat_coc_router, "numeric_columns_ready", lambda: True)
        monkeypatch.setattr(dat_coc_router, "get_conn", _fake_conn)
        monkeypatch.setattr(dat_coc_router, "fetch_one", lambda sql, *a: _tra_loi(sql))
        _SQL_DA_CHAY.clear()

        as_user(SALE).patch("/api/dat-coc/1", json={"trang_thai": "da_ban"})

        doc_lead = next(s for s in _SQL_DA_CHAY if "FROM dat_coc_lead" in s)
        assert "sale_id" in doc_lead.split("FOR UPDATE")[0]


def test_khong_con_route_ghi_nhan_ban_ngoai_man_giao_dich() -> None:
    """Chốt bán CHỈ diễn ra ở màn Giao dịch, bằng cách chốt một lead.

    Gỡ nút trên trang căn hộ mà để lại `POST /api/sales` thì luật này chỉ đúng
    trên màn hình, không đúng trên API — bất kỳ ai có token vẫn khoá được một
    căn và ghi một giao dịch không gắn với khách nào.
    """
    duong_ban = {
        (route.path, phuong_thuc)
        for route in app.routes
        for phuong_thuc in getattr(route, "methods", set())
        if getattr(route, "path", "").startswith("/api/sales") and phuong_thuc == "POST"
    }

    assert duong_ban == set(), f"Còn đường ghi nhận bán ngoài màn Giao dịch: {duong_ban}"
