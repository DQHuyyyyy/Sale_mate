"""Kiểm thử phân quyền — phần dễ sai nhất và cũng nguy hiểm nhất.

Không chạm database: `fetch_all` bị thay bằng hàm giả. TestClient tạo không qua
context manager nên lifespan không chạy, connection pool không mở.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest  # noqa: E402
from app.core import han_muc as han_muc_mod  # noqa: E402
from app.core.deps import get_current_user, get_optional_user  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import apartments as apartments_router  # noqa: E402
from app.routers import chat as chat_router  # noqa: E402
from app.routers import sales as sales_router  # noqa: E402
from app.routers import users as users_router  # noqa: E402
from app.routers import zones as zones_router  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SALE = CurrentUser(id=7, username="sale01", full_name="Nguyễn Văn Sale", role="sale")
ADMIN = CurrentUser(id=1, username="admin", full_name="Trần Quản Trị", role="admin")


def _khong_cham_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Thay mọi lối đi xuống database bằng hàm giả.

    Route căn hộ còn hỏi schema qua `numeric_columns_ready` chứ không chỉ đọc dữ
    liệu — quên cái này là test sập với PoolClosed.
    """
    monkeypatch.setattr(apartments_router, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(apartments_router, "numeric_columns_ready", lambda: True)
    monkeypatch.setattr(zones_router, "fetch_all", lambda *args, **kwargs: [])


def as_user(user: CurrentUser) -> TestClient:
    """Client giả lập đã đăng nhập bằng `user`, bỏ qua khâu giải mã JWT."""
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestRouteAdmin:
    def test_sale_bi_chan_khoi_sales_all(self) -> None:
        response = as_user(SALE).get("/api/sales/all")
        assert response.status_code == 403
        assert "quản trị" in response.json()["detail"].lower()

    def test_sale_bi_chan_khoi_danh_sach_users(self) -> None:
        assert as_user(SALE).get("/api/users?role=sale").status_code == 403

    def test_admin_vao_duoc_sales_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sales_router, "fetch_all", lambda *args, **kwargs: [])
        assert as_user(ADMIN).get("/api/sales/all").status_code == 200

    def test_admin_vao_duoc_danh_sach_users(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(users_router, "fetch_all", lambda *args, **kwargs: [])
        assert as_user(ADMIN).get("/api/users?role=sale").status_code == 200


class TestQuanLyTaiKhoan:
    """Tạo và bật/tắt tài khoản sale — chỉ admin, và có giới hạn."""

    def test_sale_khong_tao_duoc_tai_khoan(self) -> None:
        response = as_user(SALE).post(
            "/api/users",
            json={"username": "sale99", "password": "matkhau123", "full_name": "Người mới"},
        )
        assert response.status_code == 403

    def test_sale_khong_tat_duoc_tai_khoan(self) -> None:
        assert as_user(SALE).patch("/api/users/2", json={"is_active": False}).status_code == 403

    def test_admin_khong_tu_tat_chinh_minh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            users_router,
            "fetch_one",
            lambda *args, **kwargs: {**ADMIN.model_dump(), "is_active": True},
        )
        response = as_user(ADMIN).patch(f"/api/users/{ADMIN.id}", json={"is_active": False})
        assert response.status_code == 400
        assert "chính mình" in response.json()["detail"]

    def test_khong_tat_duoc_tai_khoan_admin_khac(self, monkeypatch: pytest.MonkeyPatch) -> None:
        admin_khac = {**ADMIN.model_dump(), "id": 99, "username": "admin2", "is_active": True}
        monkeypatch.setattr(users_router, "fetch_one", lambda *args, **kwargs: admin_khac)
        response = as_user(ADMIN).patch("/api/users/99", json={"is_active": False})
        assert response.status_code == 403
        assert "sale" in response.json()["detail"]

    def test_tai_khoan_khong_ton_tai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(users_router, "fetch_one", lambda *args, **kwargs: None)
        assert as_user(ADMIN).patch("/api/users/12345", json={"is_active": False}).status_code == 404

    def test_username_qua_ngan_bi_tu_choi(self) -> None:
        response = as_user(ADMIN).post(
            "/api/users",
            json={"username": "ab", "password": "matkhau123", "full_name": "Tên"},
        )
        assert response.status_code == 422

    def test_mat_khau_qua_ngan_bi_tu_choi(self) -> None:
        response = as_user(ADMIN).post(
            "/api/users",
            json={"username": "sale99", "password": "123", "full_name": "Tên"},
        )
        assert response.status_code == 422

    def test_username_co_dau_cach_bi_tu_choi(self) -> None:
        response = as_user(ADMIN).post(
            "/api/users",
            json={"username": "sale 99", "password": "matkhau123", "full_name": "Tên"},
        )
        assert response.status_code == 422


class TestMyHistory:
    def test_sale_id_lay_tu_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_fetch_all(sql: str, params=None):
            captured["params"] = params
            return []

        monkeypatch.setattr(sales_router, "fetch_all", fake_fetch_all)
        assert as_user(SALE).get("/api/sales/my-history").status_code == 200
        assert captured["params"] == (SALE.id,)

    def test_sua_query_param_khong_doi_duoc_nguoi_xem(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_fetch_all(sql: str, params=None):
            captured["params"] = params
            return []

        monkeypatch.setattr(sales_router, "fetch_all", fake_fetch_all)
        # Cố tình nhét sale_id của người khác vào query.
        response = as_user(SALE).get("/api/sales/my-history?sale_id=999")
        assert response.status_code == 200
        assert captured["params"] == (SALE.id,)


class TestKhongCoToken:
    """Ranh giới giữa phần khách xem được và phần bắt buộc đăng nhập."""

    def test_route_noi_bo_van_doi_dang_nhap(self) -> None:
        client = TestClient(app)
        for path in (
            "/api/documents",
            "/api/sales/my-history",
            "/api/sales/all",
            "/api/users",
        ):
            assert client.get(path).status_code == 401, path

    def test_route_cong_khai_khong_doi_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Khách vãng lai xem được căn hộ và phân khu."""
        _khong_cham_database(monkeypatch)

        client = TestClient(app)
        for path in ("/api/apartments", "/api/zones", "/api/towers"):
            assert client.get(path).status_code == 200, path

    def test_token_rac_tren_route_cong_khai_van_xem_duoc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token hỏng thì coi như khách, không chặn — trang này vốn không cần đăng nhập."""
        _khong_cham_database(monkeypatch)
        response = TestClient(app).get("/api/apartments", headers={"Authorization": "Bearer khong-phai-token"})
        assert response.status_code == 200

    def test_them_can_ho_van_chi_admin(self) -> None:
        response = TestClient(app).post("/api/apartments", json={})
        assert response.status_code == 401


class TestHanMucChat:
    @staticmethod
    def _chuan_bi(monkeypatch: pytest.MonkeyPatch, *, bat_han_muc: bool) -> TestClient:
        async def fake_reply(message, history, session_id=None):
            return "trả lời mẫu"

        monkeypatch.setattr(chat_router, "generate_reply", fake_reply)
        # Neo cờ tường minh: `.env` của máy dev có thể đang tắt hạn mức để tự
        # test, và test không được đổi kết quả theo cấu hình từng máy.
        monkeypatch.setattr(han_muc_mod.settings, "chat_rate_limit_enabled", bat_han_muc)
        # Bộ đếm dùng chung cả tiến trình, phải làm sạch trước khi đo.
        chat_router._han_muc.khach._hits.clear()
        return TestClient(app)

    def test_khach_bi_chan_sau_khi_vuot_han_muc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = self._chuan_bi(monkeypatch, bat_han_muc=True)

        body = {"message": "chào", "history": []}
        for lan in range(chat_router.KHACH_MOI_NGAY):
            assert client.post("/api/chat", json=body).status_code == 200, lan

        response = client.post("/api/chat", json=body)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @staticmethod
    def _cau_cham_tran(client: TestClient) -> str:
        body = {"message": "chào", "history": []}
        for _ in range(chat_router.KHACH_MOI_NGAY):
            client.post("/api/chat", json=body)
        return client.post("/api/chat", json=body).json()["detail"]

    def test_noi_thang_la_het_luot_mien_phi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Câu chạm trần phải nói rõ CHUYỆN GÌ vừa xảy ra và VIỆC GÌ cần làm.

        Bản trước cố ý nói vòng — chỉ mời liên hệ chuyên viên tư vấn, không nhắc
        quota — với lý do không muốn dựng một bức tường trước mặt lead nóng nhất
        trong ngày. Đợt test 08/09/2026 đo được cái giá của cách nói đó: sale đọc
        lời mời như một câu trả lời nghiệp vụ và tưởng trợ lý KHÔNG BIẾT câu trả
        lời, rồi mất niềm tin vào chất lượng bot.

        Ba vế dưới đây là thứ giữ cho câu không trôi ngược về một lời mời mơ hồ.
        """
        loi = self._cau_cham_tran(self._chuan_bi(monkeypatch, bat_han_muc=True))

        assert str(chat_router.KHACH_MOI_NGAY) in loi
        assert "miễn phí" in loi.lower()
        assert "đăng nhập" in loi.lower()

    def test_khong_lo_dia_chi_lien_he_ca_nhan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Không địa chỉ email nào được lọt ra giao diện production.

        Hằng `EMAIL_TU_VAN` cũ giữ email CÁ NHÂN của một thành viên và nó hiện
        thẳng cho mọi khách vãng lai chạm trần. Dò dấu `@` chứ không dò đúng
        chuỗi cũ: mục tiêu là chặn cả lần sau ai đó dán một địa chỉ khác vào.
        """
        loi = self._cau_cham_tran(self._chuan_bi(monkeypatch, bat_han_muc=True))

        assert "@" not in loi
        assert not hasattr(han_muc_mod, "EMAIL_TU_VAN")

    def test_nhan_vien_khong_bi_bao_di_dang_nhap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Người ĐÃ đăng nhập chạm trần thì bảo họ đăng nhập là chỉ sai đường.

        Trần của nhân viên là phanh chống vòng lặp retry, không phải trần chi
        phí — câu của họ phải nói đúng chuyện đó.
        """
        client = self._chuan_bi(monkeypatch, bat_han_muc=True)
        app.dependency_overrides[get_optional_user] = lambda: SALE
        chat_router._han_muc.nhan_vien._hits.clear()

        body = {"message": "chào", "history": []}
        for _ in range(chat_router.NHAN_VIEN_MOI_10_PHUT):
            client.post("/api/chat", json=body)
        loi = client.post("/api/chat", json=body).json()["detail"]

        assert "đăng nhập" not in loi.lower()
        assert "@" not in loi

    def test_tat_han_muc_thi_goi_bao_nhieu_cung_duoc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cờ tắt phải thật sự bỏ qua bộ đếm, không chỉ nới rộng nó."""
        client = self._chuan_bi(monkeypatch, bat_han_muc=False)

        body = {"message": "chào", "history": []}
        for lan in range(chat_router.KHACH_MOI_NGAY + 5):
            assert client.post("/api/chat", json=body).status_code == 200, lan
