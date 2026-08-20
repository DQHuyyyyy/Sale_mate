"""Test nhật ký theo phiên và bộ định dạng cho terminal.

Nhật ký là công cụ chẩn đoán — nó hỏng thì mình mất mắt đúng lúc cần nhìn nhất.
Nên nó phải: tách đúng phiên, không bao giờ làm sập app, và không nuốt mất
thông tin khi console không đọc được tiếng Việt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.core.logging import NhatKyPhienHandler, TextFormatter, trace


def _ban_ghi(message: str = "thử", **context: object) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, "t.py", 1, message, (), None)
    if context:
        record.context = context
    return record


class TestTachTheoPhien:
    def test_moi_phien_mot_file(self, tmp_path: Path) -> None:
        handler = NhatKyPhienHandler(tmp_path)

        for phien in ("aaaaaaaa1111", "bbbbbbbb2222"):
            with trace(session_id=phien):
                handler.emit(_ban_ghi())
        handler.close()

        assert len(list(tmp_path.glob("*.jsonl"))) == 2

    def test_ten_file_theo_ngay_gio_va_ma_phien(self, tmp_path: Path) -> None:
        handler = NhatKyPhienHandler(tmp_path)
        with trace(session_id="abcdef1234567890"):
            handler.emit(_ban_ghi())
        handler.close()

        ten = next(tmp_path.glob("*.jsonl")).name

        assert ten.endswith("_abcdef12.jsonl")
        # 2026-08-18_09-42-24_abcdef12.jsonl -> ba phần ngăn bởi "_"
        assert len(ten.split("_")) == 3

    def test_cung_phien_ghi_noi_vao_dung_mot_file(self, tmp_path: Path) -> None:
        handler = NhatKyPhienHandler(tmp_path)
        with trace(session_id="cccccccc3333"):
            for i in range(5):
                handler.emit(_ban_ghi(f"dòng {i}"))
        handler.close()

        tep = next(tmp_path.glob("*.jsonl"))

        assert len(tep.read_text(encoding="utf-8").strip().splitlines()) == 5

    def test_quay_lai_sau_khi_bi_dong_van_ghi_vao_file_cu(self, tmp_path: Path) -> None:
        """Chốt chặn: bộ nhớ đệm chỉ giữ vài file mở, nhưng TÊN file phải nhớ lâu hơn.

        Không tách hai thứ đó thì một phiên dài bị đẩy ra khỏi bộ đệm sẽ sang
        file mới, và lượt trò chuyện bị cắt làm đôi ở hai chỗ khác nhau.
        """
        handler = NhatKyPhienHandler(tmp_path)
        with trace(session_id="dddddddd4444"):
            handler.emit(_ban_ghi("đầu"))

        # Ép đẩy phiên trên ra khỏi bộ đệm bằng nhiều phiên khác.
        for i in range(NhatKyPhienHandler._GIU_MO_TOI_DA + 2):
            with trace(session_id=f"phien{i:08d}"):
                handler.emit(_ban_ghi())

        with trace(session_id="dddddddd4444"):
            handler.emit(_ban_ghi("cuối"))
        handler.close()

        tep = next(tmp_path.glob("*_dddddddd.jsonl"))
        noi_dung = tep.read_text(encoding="utf-8")

        assert "đầu" in noi_dung
        assert "cuối" in noi_dung

    def test_dong_log_khong_thuoc_phien_nao_thi_bo_qua(self, tmp_path: Path) -> None:
        """Log khởi động app không thuộc phiên nào — đừng tạo file rác cho chúng."""
        handler = NhatKyPhienHandler(tmp_path)

        handler.emit(_ban_ghi("đang khởi động"))
        handler.close()

        assert list(tmp_path.glob("*.jsonl")) == []

    def test_khong_tao_thu_muc_khi_chua_co_gi_de_ghi(self, tmp_path: Path) -> None:
        thu_muc = tmp_path / "chua_ton_tai"
        handler = NhatKyPhienHandler(thu_muc)

        handler.emit(_ban_ghi())
        handler.close()

        assert not thu_muc.exists()


class TestNoiDungGhiRa:
    def test_moi_dong_la_mot_json_hop_le(self, tmp_path: Path) -> None:
        handler = NhatKyPhienHandler(tmp_path)
        with trace(session_id="eeeeeeee5555", mode="answer"):
            handler.emit(_ban_ghi("so_sanh_can → có dữ liệu", buoc="tools"))
        handler.close()

        dong = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").strip()
        doc_duoc = json.loads(dong)

        assert doc_duoc["message"] == "so_sanh_can → có dữ liệu"
        assert doc_duoc["context"]["buoc"] == "tools"
        assert doc_duoc["context"]["mode"] == "answer"

    def test_giu_nguyen_tieng_viet_co_dau(self, tmp_path: Path) -> None:
        """`ensure_ascii=False` — file để người đọc, không phải để máy truyền đi."""
        handler = NhatKyPhienHandler(tmp_path)
        with trace(session_id="ffffffff6666"):
            handler.emit(_ban_ghi("độ phủ 0.673"))
        handler.close()

        assert "độ phủ" in next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")


class TestKhongLamSapApp:
    def test_thu_muc_khong_ghi_duoc_thi_khong_nem_loi(self, tmp_path: Path) -> None:
        """Nhật ký hỏng không được kéo theo lượt hỏi của khách."""
        chan = tmp_path / "tep_chu_khong_phai_thu_muc"
        chan.write_text("x", encoding="utf-8")
        handler = NhatKyPhienHandler(chan)
        handler.handleError = lambda record: None  # type: ignore[method-assign]

        with trace(session_id="gggggggg7777"):
            handler.emit(_ban_ghi())  # không được raise


class TestDinhDangTerminal:
    def test_hien_nhan_buoc_thanh_cot(self) -> None:
        dong = TextFormatter().format(_ban_ghi("nhãn=listing", buoc="router"))

        assert "router" in dong
        assert "nhãn=listing" in dong

    def test_rut_gon_session_id(self) -> None:
        """Mã phiên lặp ở mọi dòng — để nguyên 32 ký tự là chiếm hết bề ngang."""
        with trace(session_id="0123456789abcdef0123456789abcdef"):
            dong = TextFormatter().format(_ban_ghi())

        assert "[012345]" in dong
        assert "0123456789abcdef" not in dong

    def test_cat_gia_tri_qua_dai(self) -> None:
        dong = TextFormatter().format(_ban_ghi(buoc="retrieve", ten="x" * 200))

        assert "…" in dong
        assert len(dong) < 200

    @pytest.mark.parametrize("gia_tri", [None, "", [], {}])
    def test_bo_truong_rong(self, gia_tri: object) -> None:
        assert "trong=" not in TextFormatter().format(_ban_ghi(trong=gia_tri))
