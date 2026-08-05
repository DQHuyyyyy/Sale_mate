"""Test không chạm database và không gọi mạng."""

from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.core.security import (  # noqa: E402
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.routers.apartments import _format_area, _format_price  # noqa: E402


class TestPassword:
    def test_hash_khac_mat_khau_goc(self) -> None:
        hashed = hash_password("matkhau123")
        assert hashed != "matkhau123"
        assert hashed.startswith("$2")

    def test_dung_mat_khau_thi_qua(self) -> None:
        assert verify_password("matkhau123", hash_password("matkhau123"))

    def test_sai_mat_khau_thi_truot(self) -> None:
        assert not verify_password("saibet", hash_password("matkhau123"))

    def test_hash_hong_khong_lam_sap_request(self) -> None:
        assert not verify_password("matkhau123", "khong-phai-hash-bcrypt")

    def test_hai_lan_hash_ra_hai_gia_tri_khac_nhau(self) -> None:
        assert hash_password("matkhau123") != hash_password("matkhau123")


class TestToken:
    def test_giai_ma_lai_dung_thong_tin(self) -> None:
        payload = decode_access_token(create_access_token(7, "sale01", "sale"))
        assert payload is not None
        assert payload["user_id"] == 7
        assert payload["role"] == "sale"

    def test_token_bi_sua_thi_khong_giai_ma_duoc(self) -> None:
        token = create_access_token(7, "sale01", "sale")
        assert decode_access_token(token[:-2] + "ab") is None

    def test_chuoi_rac_thi_tra_none(self) -> None:
        assert decode_access_token("khong-phai-token") is None


class TestFormat:
    def test_gia_dung_dau_phay_thap_phan(self) -> None:
        assert _format_price(Decimal("1.8")) == "1,8 tỷ"
        assert _format_price(Decimal("5.55")) == "5,55 tỷ"

    def test_gia_tron_khong_thua_so_khong(self) -> None:
        assert _format_price(Decimal("4.000")) == "4 tỷ"

    def test_dien_tich(self) -> None:
        assert _format_area(Decimal("28")) == "28m2"
        assert _format_area(Decimal("55.5")) == "55,5m2"
