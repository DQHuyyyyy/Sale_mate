"""Kiểm thử quản lý ảnh căn hộ — đặt ảnh đại diện và xoá ảnh.

Không chạm database: `fetch_one`/`fetch_all`/`get_conn` đều bị thay bằng hàm giả,
và câu SQL chạy ra được ghi lại để kiểm tra.

Trọng tâm là ba chỗ sai thì nguy hiểm: sale sửa được ảnh, sửa được ảnh của căn
khác qua URL, và ảnh đã xoá khỏi DB nhưng lỗi Storage làm request trả lỗi khiến
admin bấm lại một việc đã xong.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import apartments as apartments_router  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402
from app.services.storage import StorageError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SALE = CurrentUser(id=7, username="sale01", full_name="Nguyễn Văn Sale", role="sale")
ADMIN = CurrentUser(id=1, username="admin", full_name="Trần Quản Trị", role="admin")

MA_CAN = "VOP397"
CAN = {"ma_can": MA_CAN, "toa": "S1", "gia": "2,7 tỷ", "tinh_trang": "Còn"}


class _Cursor:
    """Ghi lại mọi câu SQL thay vì chạy chúng."""

    def __init__(self, nhat_ky: list[tuple[str, object]]) -> None:
        self.nhat_ky = nhat_ky

    def execute(self, sql: str, params: object = None) -> None:
        self.nhat_ky.append((" ".join(sql.split()), params))

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _Conn:
    def __init__(self, nhat_ky: list[tuple[str, object]]) -> None:
        self.nhat_ky = nhat_ky

    def cursor(self) -> _Cursor:
        return _Cursor(self.nhat_ky)

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


@pytest.fixture
def nhat_ky(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object]]:
    """Chặn mọi lối xuống database, trả về danh sách SQL đã chạy."""
    ghi: list[tuple[str, object]] = []
    monkeypatch.setattr(apartments_router, "numeric_columns_ready", lambda: True)
    monkeypatch.setattr(apartments_router, "get_conn", lambda: _Conn(ghi))
    monkeypatch.setattr(apartments_router, "fetch_all", lambda *args, **kwargs: [])
    return ghi


def _dat_anh(monkeypatch: pytest.MonkeyPatch, anh: dict | None) -> None:
    """`fetch_one` phục vụ hai câu hỏi khác nhau — tách theo bảng được hỏi."""

    def gia_lap(sql: str, params: object = None) -> dict | None:  # noqa: ARG001
        return anh if "apartment_images" in sql else CAN

    monkeypatch.setattr(apartments_router, "fetch_one", gia_lap)


def as_user(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------- Phân quyền ----------


class TestPhanQuyen:
    def test_sale_khong_dat_duoc_anh_dai_dien(self) -> None:
        response = as_user(SALE).patch(f"/api/apartments/{MA_CAN}/images/3/dai-dien")
        assert response.status_code == 403

    def test_sale_khong_xoa_duoc_anh(self) -> None:
        assert as_user(SALE).delete(f"/api/apartments/{MA_CAN}/images/3").status_code == 403

    def test_khach_chua_dang_nhap_bi_chan(self) -> None:
        response = TestClient(app).patch(f"/api/apartments/{MA_CAN}/images/3/dai-dien")
        assert response.status_code == 401


# ---------- Ràng buộc ảnh phải thuộc đúng căn ----------


class TestRangBuocMaCan:
    def test_anh_khong_thuoc_can_thi_404(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        """Thiếu vế `ma_can` trong WHERE thì URL của căn này sửa được ảnh căn kia."""
        _dat_anh(monkeypatch, None)

        response = as_user(ADMIN).patch(f"/api/apartments/{MA_CAN}/images/9999/dai-dien")

        assert response.status_code == 404
        assert not nhat_ky, "Không được đụng tới dữ liệu khi ảnh không thuộc căn"

    def test_cau_tra_cuu_anh_rang_ca_hai_dieu_kien(self, monkeypatch: pytest.MonkeyPatch) -> None:
        da_hoi: list[str] = []

        def gia_lap(sql: str, params: object = None) -> dict | None:  # noqa: ARG001
            if "apartment_images" in sql:
                da_hoi.append(" ".join(sql.split()))
                return None
            return CAN

        monkeypatch.setattr(apartments_router, "fetch_one", gia_lap)
        as_user(ADMIN).delete(f"/api/apartments/{MA_CAN}/images/5")

        assert da_hoi and "WHERE id = %s AND ma_can = %s" in da_hoi[0]


# ---------- Đặt ảnh đại diện ----------


class TestDatAnhDaiDien:
    def test_anh_duoc_chon_len_dau_bang_mot_cau_update(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        _dat_anh(monkeypatch, {"id": 42, "storage_path": None})

        response = as_user(ADMIN).patch(f"/api/apartments/{MA_CAN}/images/42/dai-dien")

        assert response.status_code == 200
        assert len(nhat_ky) == 1, "Đánh lại thứ tự phải gọn trong một câu UPDATE"
        sql, params = nhat_ky[0]
        assert "UPDATE apartment_images" in sql
        # Ảnh được chọn kéo lên đầu, phần còn lại giữ nguyên thứ tự tương đối.
        assert "ORDER BY (id = %s) DESC, sort_order NULLS LAST, id" in sql
        assert params == (42, MA_CAN)

    def test_tra_ve_can_da_cap_nhat(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        """Frontend dựng lại gallery từ response, không gọi thêm một vòng nữa."""
        _dat_anh(monkeypatch, {"id": 42, "storage_path": None})

        data = as_user(ADMIN).patch(f"/api/apartments/{MA_CAN}/images/42/dai-dien").json()

        assert data["ma_can"] == MA_CAN
        assert "images" in data


# ---------- Xoá ảnh ----------


class TestXoaAnh:
    def test_xoa_dong_db_va_danh_lai_thu_tu(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        _dat_anh(monkeypatch, {"id": 42, "storage_path": None})

        assert as_user(ADMIN).delete(f"/api/apartments/{MA_CAN}/images/42").status_code == 200

        cac_sql = [sql for sql, _ in nhat_ky]
        assert any(sql.startswith("DELETE FROM apartment_images") for sql in cac_sql)
        assert any("UPDATE apartment_images" in sql for sql in cac_sql)

    def test_anh_google_drive_khong_goi_storage(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        """Ảnh cũ không có object nào trong bucket để mà xoá."""
        _dat_anh(monkeypatch, {"id": 42, "storage_path": None})

        def khong_duoc_goi(path: str) -> None:
            raise AssertionError(f"Không được gọi Storage cho ảnh Drive: {path}")

        monkeypatch.setattr(apartments_router, "delete_object", khong_duoc_goi)
        assert as_user(ADMIN).delete(f"/api/apartments/{MA_CAN}/images/42").status_code == 200

    def test_anh_tren_storage_thi_xoa_ca_object(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        _dat_anh(monkeypatch, {"id": 42, "storage_path": f"{MA_CAN}/anh.jpg"})
        da_xoa: list[str] = []
        monkeypatch.setattr(apartments_router, "delete_object", da_xoa.append)

        assert as_user(ADMIN).delete(f"/api/apartments/{MA_CAN}/images/42").status_code == 200
        assert da_xoa == [f"{MA_CAN}/anh.jpg"]

    def test_storage_hong_van_tra_200(self, monkeypatch: pytest.MonkeyPatch, nhat_ky: list) -> None:
        """Dòng DB đã xoá, trang đọc từ DB — báo lỗi ở đây là bắt bấm lại việc đã xong."""
        _dat_anh(monkeypatch, {"id": 42, "storage_path": f"{MA_CAN}/anh.jpg"})

        def hong(path: str) -> None:  # noqa: ARG001
            raise StorageError("Supabase Storage từ chối xoá file (HTTP 500).")

        monkeypatch.setattr(apartments_router, "delete_object", hong)

        assert as_user(ADMIN).delete(f"/api/apartments/{MA_CAN}/images/42").status_code == 200
