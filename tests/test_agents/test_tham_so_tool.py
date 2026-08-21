"""Test tầng chịu lỗi cho tham số tool do model sinh ra.

Ca thật: model điền `sort="price"` (schema chỉ nhận 4 giá trị Literal), pydantic
từ chối, tool trả `failure`, agent mất SẠCH dữ liệu — trong khi `price_max` và
`unit_type` đi kèm đều hợp lệ và đủ để trả lời.

Nguyên tắc "không bịa" của dự án thực thi bằng KIẾN TRÚC, không bằng cách tin
model. Hai vế: nói cho model biết giá trị hợp lệ (`_mo_ta_tham_so`), và làm hậu
quả vô hại khi nó vẫn đoán (`doc_tham_so`). Thiếu vế hai là lại đang tin model.
"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, Field, ValidationError

from src.agents.nodes.plan import _describe_tools, _mo_ta_tham_so
from src.agents.tools.args import doc_tham_so
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.search import SearchArgs


class _Args(BaseModel):
    ten: str | None = Field(default=None, description="Tên gì đó")
    so: int | None = Field(default=None, ge=1)
    thu_tu: Literal["tang", "giam"] | None = None


class _CoBatBuoc(BaseModel):
    bat_buoc: float = Field(description="Không có thì không tính được")
    tuy_chon: int | None = None


# ---------- Bỏ trường sai, giữ trường đúng ----------


def test_gia_tri_ngoai_literal_bi_bo_phan_con_lai_van_dung_duoc():
    args, bo_qua = doc_tham_so(_Args, {"ten": "abc", "thu_tu": "price"}, co_the_bo={"thu_tu"})

    assert args.ten == "abc"  # tiêu chí hợp lệ KHÔNG được mất theo
    assert args.thu_tu is None
    assert bo_qua == ["thu_tu"]


def test_bo_nhieu_truong_sai_cung_luc():
    args, bo_qua = doc_tham_so(_Args, {"ten": "abc", "so": 0, "thu_tu": "linh tinh"}, co_the_bo={"so", "thu_tu"})

    assert args.ten == "abc"
    assert sorted(bo_qua) == ["so", "thu_tu"]


def test_khong_co_gi_sai_thi_khong_bo_gi():
    args, bo_qua = doc_tham_so(_Args, {"ten": "abc", "so": 5, "thu_tu": "tang"})

    assert bo_qua == []
    assert args.so == 5


def test_truong_la_hoan_toan_bi_bo():
    """Model bịa hẳn một tham số không tồn tại."""
    args, bo_qua = doc_tham_so(SearchArgs, {"price_max": 3.0, "mau_son": "xanh"})

    assert args.price_max == 3.0
    assert bo_qua == ["mau_son"]


# ---------- Trường bắt buộc thì vẫn phải báo lỗi ----------


def test_thieu_truong_bat_buoc_van_raise():
    """Im lặng bỏ qua rồi trả kết quả sai còn tệ hơn báo lỗi."""
    with pytest.raises(ValidationError):
        doc_tham_so(_CoBatBuoc, {"tuy_chon": 3})


def test_truong_bat_buoc_sai_kieu_cung_raise():
    with pytest.raises(ValidationError):
        doc_tham_so(_CoBatBuoc, {"bat_buoc": "không phải số"})


# ---------- Model phải được biết giá trị hợp lệ ----------


def test_mo_ta_tham_so_neu_ro_gia_tri_cho_phep():
    """Bản đầu chỉ liệt kê TÊN tham số, nên model không có cách nào biết `sort`
    nhận gì và đành đoán."""
    mo_ta = _mo_ta_tham_so(SearchArgs.model_json_schema())

    assert "chỉ nhận: gia_tang | gia_giam | dien_tich_tang | dien_tich_giam" in mo_ta


def test_mo_ta_tham_so_giu_lai_description():
    mo_ta = _mo_ta_tham_so(SearchArgs.model_json_schema())

    assert "đơn vị TỶ đồng" in mo_ta


def test_mo_ta_tham_so_danh_dau_truong_bat_buoc():
    mo_ta = _mo_ta_tham_so(_CoBatBuoc.model_json_schema())

    assert "[bắt buộc]" in mo_ta
    assert "bat_buoc" in mo_ta


def test_tool_khong_co_tham_so_van_mo_ta_duoc():
    assert "(không có tham số)" in _mo_ta_tham_so({})


def test_describe_tools_khong_no_khi_registry_rong():
    assert _describe_tools(ToolRegistry()) == "(không có tool nào)"


def test_khong_khai_co_the_bo_thi_nghiem_ngat_nhu_cu():
    """Mặc định phải nghiêm ngặt: bỏ bừa trường LỌC là âm thầm nới câu hỏi."""
    with pytest.raises(ValidationError):
        doc_tham_so(_Args, {"ten": "abc", "thu_tu": "price"})


def test_truong_loc_sai_thi_hong_to_tieng_khong_tra_ve_ca_kho():
    """`inventory_lookup(unit_code=123)` mà bỏ `unit_code` thì tool hết bộ lọc và
    trả về TOÀN BỘ tồn kho — người dùng hỏi một căn, nhận cả kho, không dấu hiệu."""
    with pytest.raises(ValidationError):
        doc_tham_so(SearchArgs, {"price_max": "ba tỷ"}, co_the_bo={"sort", "limit"})
