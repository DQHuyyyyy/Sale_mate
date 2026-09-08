"""Test bộ chấm của eval câu trả lời.

Chỉ test phần chấm — KHÔNG gọi LLM, đúng quy ước `tests/conftest.py`. Phần gọi
model là thứ tốn tiền và không tất định; phần chấm mới là thứ quyết định con số
báo cáo có đáng tin không.
"""

from __future__ import annotations

import json

import pytest

from src.eval.answer import DATASET_PATH, TongKet, cham, so_sanh

_TU_CHOI = "Mình chưa có đủ dữ liệu để trả lời chính xác câu này."
_TRA_LOI = "Mật độ xây dựng của Ocean Park 1 là 19%, tổng diện tích 420 ha."


def _case(loai: str, **them: object) -> dict:
    return {"id": "AV-000", "loai": loai, "cau_hoi": "câu hỏi thử", **them}


class TestQuyetDinhTraLoiHayTuChoi:
    def test_phai_tra_loi_ma_tu_choi_thi_truot(self) -> None:
        """Đây chính là lỗi v7 sinh ra để chữa."""
        kq = cham(_case("phai_tra_loi", phai_neu=["19"]), _TU_CHOI)

        assert not kq.dat
        assert "vẫn từ chối" in kq.ly_do_truot

    def test_phai_tu_choi_ma_tra_loi_thi_truot(self) -> None:
        """Đây là lỗi v7 có nguy cơ gây ra — nặng hơn lỗi trên."""
        kq = cham(_case("phai_tu_choi"), "Phí quản lý khoảng 15.000 đồng mỗi mét vuông.")

        assert not kq.dat
        assert "phải từ chối" in kq.ly_do_truot

    def test_ngoai_pham_vi_phai_tu_choi(self) -> None:
        assert cham(_case("ngoai_pham_vi"), _TU_CHOI).dat
        assert not cham(_case("ngoai_pham_vi"), "Đất nền Đà Nẵng khoảng 40 triệu/m2.").dat

    def test_tra_loi_mot_phan_khong_duoc_tu_choi_ca_cau(self) -> None:
        kq = cham(_case("tra_loi_mot_phan", phai_neu=["19"]), _TU_CHOI)

        assert not kq.dat


class TestDuKienBatBuoc:
    def test_thieu_mot_chuoi_la_truot(self) -> None:
        kq = cham(_case("phai_tra_loi", phai_neu=["19", "420", "999"]), _TRA_LOI)

        assert not kq.dat
        assert "999" in kq.ly_do_truot

    def test_du_het_thi_dat(self) -> None:
        assert cham(_case("phai_tra_loi", phai_neu=["19", "420"]), _TRA_LOI).dat

    def test_so_khop_bo_dau(self) -> None:
        """Model viết "5 năm", bộ chấm phải khớp cả khi ghi "5 nam"."""
        assert cham(_case("phai_tra_loi", phai_neu=["5 nam"]), "Trần 6% trong 5 năm.").dat

    def test_khong_phan_biet_hoa_thuong(self) -> None:
        assert cham(_case("phai_tu_choi", khong_duoc_neu=["VIETCOMBANK"]), _TU_CHOI).dat
        assert not cham(_case("ngoai_pham_vi", khong_duoc_neu=["VIETCOMBANK"]), "Vietcombank cho vay.").dat


class TestChuoiBiCam:
    def test_neu_thu_khong_co_thi_truot_du_da_du_dukien(self) -> None:
        """Đủ dữ kiện bắt buộc KHÔNG bù được cho việc bịa thêm."""
        kq = cham(
            _case("phai_tra_loi", phai_neu=["19"], khong_duoc_neu=["420"]),
            _TRA_LOI,
        )

        assert not kq.dat
        assert "không có trong tài liệu" in kq.ly_do_truot

    def test_tu_choi_dung_cach_thi_dat(self) -> None:
        kq = cham(_case("phai_tu_choi", khong_duoc_neu=["/m2", "nghìn"]), _TU_CHOI)

        assert kq.dat
        assert kq.da_tu_choi


class TestBoDuLieu:
    """Bộ câu hỏi sai định dạng thì mọi con số báo cáo đều vô nghĩa."""

    def test_doc_duoc_va_du_truong_bat_buoc(self) -> None:
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        assert len(bo_cau) >= 15, "quá ít câu thì kết quả nhiễu hơn tín hiệu"
        for case in bo_cau:
            for truong in ("id", "loai", "cau_hoi", "vi_sao_bay"):
                assert case.get(truong), f"{case.get('id')} thiếu {truong}"

    def test_id_khong_trung(self) -> None:
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        ids = [c["id"] for c in bo_cau]

        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("loai", ["phai_tra_loi", "phai_tu_choi", "tra_loi_mot_phan", "ngoai_pham_vi"])
    def test_du_ca_bon_loai_bay(self, loai: str) -> None:
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        assert any(c["loai"] == loai for c in bo_cau), f"thiếu hẳn nhóm {loai}"

    def test_moi_loai_deu_co_rang_buoc_de_cham(self) -> None:
        """Câu không có `phai_neu` lẫn `khong_duoc_neu` thì chỉ đo được mỗi
        chuyện từ chối hay không — với nhóm `phai_tra_loi` là quá lỏng."""
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        for case in bo_cau:
            if case["loai"] == "phai_tra_loi":
                assert case.get("phai_neu"), f"{case['id']} thiếu phai_neu"


class TestSoSanh:
    def test_neu_ro_cau_doi_chieu(self) -> None:
        truoc, sau = TongKet(prompt_version="v6"), TongKet(prompt_version="v7")
        truoc.ghi_nhan(cham(_case("phai_tra_loi", phai_neu=["19"]), _TU_CHOI))
        sau.ghi_nhan(cham(_case("phai_tra_loi", phai_neu=["19"]), _TRA_LOI))

        bang = so_sanh(truoc, sau)

        assert "MISS -> OK" in bang
        assert "phai_tra_loi" in bang

    def test_canh_bao_khi_nhom_tu_choi_giam(self) -> None:
        """Cột phanh: nới quá tay phải hiện cảnh báo, không lẫn vào tổng điểm."""
        truoc, sau = TongKet(prompt_version="v6"), TongKet(prompt_version="v7")
        truoc.ghi_nhan(cham(_case("phai_tu_choi"), _TU_CHOI))
        sau.ghi_nhan(cham(_case("phai_tu_choi"), "Phí quản lý 15.000 đồng/m2."))

        assert "nới quá tay" in so_sanh(truoc, sau)


class TestChamCaDongNguon:
    """Câu trả lời đúng vẫn hỏng nếu dòng "Nguồn" sai.

    Ca thật 08/09/2026: hỏi căn VOP9999 (mã không tồn tại), trợ lý từ chối hoàn
    hảo — không bịa một chữ — nhưng dưới đó liệt kê "Chính sách hỗ trợ lãi suất
    chung của Vinhomes" cùng tổng quan Ocean Park 1 và 3. Sale đọc xong tưởng ba
    tài liệu ấy nói về VOP9999.

    Đo mỗi câu chữ thì lỗi này không bao giờ hiện ra số: mọi cột đều xanh.
    """

    def test_tu_choi_ma_van_trung_nguon_thi_truot(self) -> None:
        kq = cham(
            _case("phai_tu_choi", nguon_phai_rong=True),
            _TU_CHOI,
            ["Tổng quan dự án Vinhomes Ocean Park 1"],
        )

        assert not kq.dat
        assert "trưng nguồn không liên quan" in kq.ly_do_truot

    def test_tu_choi_va_khong_nguon_nao_thi_dat(self) -> None:
        assert cham(_case("phai_tu_choi", nguon_phai_rong=True), _TU_CHOI, []).dat

    def test_cau_khong_khai_thi_nguon_khong_bi_cham(self) -> None:
        """Luật chỉ áp cho câu khai tường minh — 26 câu cũ giữ nguyên cách chấm."""
        assert cham(_case("phai_tu_choi"), _TU_CHOI, ["Một tài liệu nào đó"]).dat

    def test_khong_truyen_nguon_thi_bo_qua(self) -> None:
        """Gọi kiểu cũ `cham(case, tra_loi)` vẫn chạy — bộ chấm test được mà
        không phải dựng cả pipeline truy hồi."""
        assert cham(_case("phai_tu_choi", nguon_phai_rong=True), _TU_CHOI).dat

    def test_bo_du_lieu_co_ca_ma_can_khong_ton_tai(self) -> None:
        """Bộ câu hỏi phải giữ được ca này, không chỉ luật chấm."""
        bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        assert any(c.get("nguon_phai_rong") for c in bo_cau), "thiếu ca kiểm dòng Nguồn"
