"""Test phần nhãn lần chạy, lịch sử hội thoại và quy đổi chi phí.

Không câu nào gọi model — đúng quy ước `tests/conftest.py`. Phần đáng test ở
đây là phần quyết định con số báo cáo có so sánh được với nhau hay không.
"""

from __future__ import annotations

import json

import pytest

from src.core.gia_model import BANG_GIA, chi_phi_usd
from src.eval.answer import (
    DATASET_PATH,
    TongKet,
    _doc_lich_su,
    _tinh_chi_phi,
    doc_ket_qua,
    duong_dan_ket_qua,
    so_sanh,
)
from src.models.chat import MessageRole
from src.services.llm import SoDoToken


class TestNhanLanChay:
    """Nhãn tách khỏi phiên bản prompt — nếu không, đổi model sẽ ghi đè kết quả."""

    def test_nhan_quyet_dinh_ten_file(self) -> None:
        assert duong_dan_ket_qua("baseline").name == "answer_eval_baseline.json"

    def test_thieu_nhan_thi_roi_ve_phien_ban_prompt(self) -> None:
        assert TongKet(prompt_version="v7").ten == "v7"

    def test_co_nhan_thi_uu_tien_nhan(self) -> None:
        assert TongKet(prompt_version="v7", nhan="pr4-luna").ten == "pr4-luna"

    def test_hai_cau_hinh_khac_nhau_khong_ghi_de_nhau(self) -> None:
        """Đây là lỗi bộ đo cũ: cùng prompt v7, khác model, cùng một file."""
        a = duong_dan_ket_qua(TongKet(prompt_version="v7", nhan="baseline").ten)
        b = duong_dan_ket_qua(TongKet(prompt_version="v7", nhan="pr4-luna").ten)

        assert a != b

    def test_doc_ket_qua_thieu_file_thi_bao_cach_khac_phuc(self) -> None:
        with pytest.raises(Exception, match="eval answer --label"):
            doc_ket_qua("nhan-khong-ton-tai-9x8y7z")


class TestDongCauHinh:
    """Con số không kèm cấu hình là con số không dùng lại được sau vài ngày."""

    def test_neu_ro_model_va_chi_phi(self) -> None:
        dong = TongKet(
            prompt_version="v7",
            nhan="pr4",
            model_answer="gpt-5.6-luna",
            model_fast="gpt-5.6-luna",
            token_vao=1000,
            token_ra=200,
            chi_phi_usd=0.00044,
        ).dong_cau_hinh()

        assert "gpt-5.6-luna" in dong
        assert "$0.0004" in dong

    def test_chua_do_chi_phi_thi_khong_bia_so_khong(self) -> None:
        assert "$" not in TongKet(prompt_version="v7").dong_cau_hinh()

    def test_bang_so_sanh_neu_ca_hai_cau_hinh(self) -> None:
        truoc = TongKet(prompt_version="v7", nhan="baseline", model_answer="gpt-4o")
        sau = TongKet(prompt_version="v7", nhan="pr4-luna", model_answer="gpt-5.6-luna")

        bang = so_sanh(truoc, sau)

        assert "gpt-4o" in bang
        assert "gpt-5.6-luna" in bang


class TestLichSu:
    """Bộ câu hỏi phải chở được lịch sử thì mới đo được việc giải tham chiếu."""

    def test_khong_khai_thi_rong(self) -> None:
        assert _doc_lich_su({"cau_hoi": "x"}) == []

    def test_doc_dung_vai_va_noi_dung(self) -> None:
        lich_su = _doc_lich_su(
            {
                "cau_hoi": "liệt kê 20 căn đó",
                "lich_su": [
                    {"role": "user", "content": "các căn dưới 4 tỷ ở Ocean Park 1"},
                    {"role": "assistant", "content": "Có 20 căn phù hợp."},
                ],
            }
        )

        assert [m.role for m in lich_su] == [MessageRole.USER, MessageRole.ASSISTANT]
        assert "Ocean Park 1" in lich_su[0].content


class TestChiPhi:
    def test_cong_theo_tung_model(self) -> None:
        so_do = SoDoToken()
        so_do.ghi_nhan("gpt-5.6-luna", 1_000_000, 0)
        so_do.ghi_nhan("gpt-5.6-luna", 0, 1_000_000)

        vao, ra, tien = _tinh_chi_phi(so_do)

        assert (vao, ra) == (1_000_000, 1_000_000)
        assert tien == pytest.approx(1.40)  # 0.20 vào + 1.20 ra

    def test_model_thieu_gia_thi_tra_none_chu_khong_tra_khong(self) -> None:
        """Trả 0.0 sẽ âm thầm kéo tổng chi phí xuống và làm hỏng bộ chặn ngân sách."""
        so_do = SoDoToken()
        so_do.ghi_nhan("model-la-hoac-moi-ra", 1000, 100)

        assert _tinh_chi_phi(so_do)[2] is None
        assert chi_phi_usd("model-la-hoac-moi-ra", token_vao=1000) is None

    def test_khong_co_bo_dem_thi_khong_bia_so(self) -> None:
        assert _tinh_chi_phi(None) == (0, 0, None)

    def test_gia_cache_re_hon_gia_vao(self) -> None:
        for ten, gia in BANG_GIA.items():
            if gia.vao_cache is not None:
                assert gia.vao_cache <= gia.vao, f"{ten}: giá đọc cache phải rẻ hơn giá vào"


class TestBoDuLieuVoiLichSu:
    def test_lich_su_neu_co_thi_dung_dinh_dang(self) -> None:
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        for case in bo_cau:
            for luot in case.get("lich_su", []):
                assert luot.get("role") in {"user", "assistant"}, case["id"]
                assert luot.get("content"), case["id"]

    def test_cau_co_lich_su_phai_ket_thuc_bang_luot_tro_ly(self) -> None:
        """Lịch sử kết thúc bằng lượt user thì `cau_hoi` thành hai lượt user
        liên tiếp — không giống hội thoại thật, đo ra số không tin được."""
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        for case in bo_cau:
            lich_su = case.get("lich_su")
            if lich_su:
                assert lich_su[-1]["role"] == "assistant", case["id"]
