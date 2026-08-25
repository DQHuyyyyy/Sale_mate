"""Test gợi ý câu hỏi tiếp theo.

Test quan trọng nhất ở đây là `TestTraLoiDuoc`: mọi câu gợi ý sinh ra phải có ít
nhất một tool nhận, hoặc là tên tài liệu đã truy hồi. Một nút bấm dẫn vào "chưa
có đủ dữ liệu" còn tệ hơn không có nút — nó dạy khách rằng gợi ý không đáng bấm.
"""

from __future__ import annotations

import json

import pytest

from src.agents.state import AgentState, Intent, initial_state
from src.agents.suggest import (
    TOI_DA_KY_TU,
    TOI_DA_PHUONG_AN,
    _co_tool_nhan,
    _loc,
    goi_y_bang_model,
    goi_y_khi_thieu_du_lieu,
    goi_y_ngoai_pham_vi,
    goi_y_tiep_theo,
    phuong_an_tu_tai_lieu,
)
from src.data.contracts import Chunk
from src.models.chat import ChatMessage, MessageRole


def _tool_context(*can: dict[str, str]) -> str:
    """Dựng khối tool_context đúng hình dạng `ToolsNode._format` sinh ra."""
    return "[inventory_search] Tra tồn kho\nKết quả:\n" + json.dumps(list(can), ensure_ascii=False)


def _state(
    *,
    tool_context: str = "",
    tool_filters: dict | None = None,
    chunks: list[Chunk] | None = None,
    history: list[ChatMessage] | None = None,
    intent: Intent = Intent.LISTING,
) -> AgentState:
    state = initial_state("câu hỏi", "s1", history or [])
    state["intent"] = intent
    state["tool_context"] = tool_context
    state["tool_filters"] = tool_filters or {}
    state["chunks"] = chunks or []
    return state


def _chunk(title: str) -> Chunk:
    return Chunk(id=title, doc_id=title, doc_title=title, text="nội dung", score=0.9)


def _hoi(noi_dung: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.USER, content=noi_dung)


_NHIEU_CAN = _tool_context(
    {"unit_code": "VOP758", "subdivision": "Ocean Park 1"},
    {"unit_code": "VOP285", "subdivision": "Ocean Park 1"},
    {"unit_code": "VOP619", "subdivision": "Ocean Park 1"},
)
_MOT_CAN = _tool_context({"unit_code": "VOP397", "subdivision": "Ocean Park 3"})


def _moi_tinh_huong() -> list[tuple[str, list[str]]]:
    """Mọi tình huống đại diện, kèm gợi ý sinh ra — dùng chung cho test round-trip."""
    return [
        (
            "danh sách nhiều căn đã lọc giá + phân khu",
            goi_y_tiep_theo(
                _state(
                    tool_context=_NHIEU_CAN,
                    tool_filters={"inventory_search": {"price_max": 4.0, "subdivision": "Ocean Park 1"}},
                )
            ),
        ),
        ("danh sách nhiều căn không lọc gì", goi_y_tiep_theo(_state(tool_context=_NHIEU_CAN))),
        ("đúng một căn", goi_y_tiep_theo(_state(tool_context=_MOT_CAN))),
        (
            "đúng một căn, khách đã nêu vốn",
            goi_y_tiep_theo(_state(tool_context=_MOT_CAN, history=[_hoi("tôi có 1,5 tỷ")])),
        ),
        (
            "trả lời từ tài liệu",
            goi_y_tiep_theo(_state(chunks=[_chunk("Ưu đãi của Vinhomes OceanPark 2")])),
        ),
        ("ngoài phạm vi", goi_y_tiep_theo(_state(intent=Intent.GENERAL))),
        (
            "thiếu dữ liệu, khôi phục được tiêu chí",
            goi_y_khi_thieu_du_lieu(_state(history=[_hoi("có bao nhiêu căn dưới 4 tỷ ở OP1")])),
        ),
        ("thiếu dữ liệu, không khôi phục được gì", goi_y_khi_thieu_du_lieu(_state())),
    ]


class TestTraLoiDuoc:
    """Chốt chặn chính: bấm vào gợi ý nào cũng phải ra kết quả."""

    def test_moi_goi_y_deu_co_tool_nhan(self) -> None:
        for ten, cac_cau in _moi_tinh_huong():
            assert cac_cau, f"{ten}: không sinh ra gợi ý nào"
            for cau in cac_cau:
                assert _co_tool_nhan(cau), f"{ten}: không tool nào nhận câu {cau!r}"

    def test_ten_tai_lieu_van_qua_duoc_bo_loc(self) -> None:
        """Tên tài liệu đi đường truy hồi, không cần tool nào nhận."""
        state = _state(chunks=[_chunk("Hệ thống tiện ích tổng quan của Vinhome Ocean Park")])
        assert "Hệ thống tiện ích tổng quan của Vinhome Ocean Park" in goi_y_tiep_theo(state)


class TestKhongBia:
    def test_ma_can_phai_den_tu_luot_nay(self) -> None:
        """Chỉ được nhắc mã căn tool vừa trả về, không lấy từ đâu khác."""
        cac_cau = goi_y_tiep_theo(_state(tool_context=_NHIEU_CAN))

        for cau in cac_cau:
            for tu in cau.split():
                sach = tu.strip(",.")
                if sach.upper().startswith("VOP"):
                    assert sach in {"VOP758", "VOP285", "VOP619"}, f"mã lạ trong {cau!r}"

    def test_khong_co_chunk_thi_khong_goi_y_tai_lieu(self) -> None:
        """Hồi quy cho lỗi cũ: kho chỉ có ưu đãi OP2 và OP3, model từng chào OP1."""
        assert phuong_an_tu_tai_lieu(_state()) == []
        assert "Ưu đãi" not in " ".join(goi_y_tiep_theo(_state(intent=Intent.GENERAL)))

    def test_khong_goi_y_vay_khi_khach_chua_neu_von(self) -> None:
        """`tinh_khoan_vay` đòi có vốn; thiếu nó thì nút bấm là ngõ cụt."""
        cac_cau = goi_y_tiep_theo(_state(tool_context=_MOT_CAN))
        assert not any("vay" in cau.lower() for cau in cac_cau)

    def test_co_von_trong_lich_su_thi_dung_lai_dung_con_so_do(self) -> None:
        cac_cau = goi_y_tiep_theo(_state(tool_context=_MOT_CAN, history=[_hoi("tôi có 1,5 tỷ")]))

        vay = [c for c in cac_cau if "vay" in c.lower()]
        assert vay and "1,5 tỷ" in vay[0] and "VOP397" in vay[0]


class TestHinhDang:
    def test_toi_da_bon_cau_va_khong_trung(self) -> None:
        for ten, cac_cau in _moi_tinh_huong():
            assert len(cac_cau) <= TOI_DA_PHUONG_AN, ten
            assert len(cac_cau) == len(set(cac_cau)), f"{ten}: có câu trùng"

    def test_cau_tu_chua_tieu_chi_khong_dung_tu_thay_the(self) -> None:
        """ "Liệt kê 20 căn đó" là câu đã gây lỗi — build_args không đọc lượt trước."""
        for ten, cac_cau in _moi_tinh_huong():
            for cau in cac_cau:
                thap = cau.lower()
                assert " đó" not in thap and " này" not in thap, f"{ten}: {cau!r} dựa vào ngữ cảnh"


class TestThieuDuLieu:
    def test_trai_ra_ba_phan_khu_va_giu_lai_khoang_gia(self) -> None:
        """Đúng ca trong ảnh: hỏi 'dưới 4 tỷ ở OP1' rồi hỏi tiếp cụt lủn."""
        cac_cau = goi_y_khi_thieu_du_lieu(_state(history=[_hoi("có bao nhiêu căn dưới 4 tỷ ở OP1")]))

        assert cac_cau == [
            "Các căn dưới 4 tỷ ở Ocean Park 1",
            "Các căn dưới 4 tỷ ở Ocean Park 2",
            "Các căn dưới 4 tỷ ở Ocean Park 3",
        ]

    def test_khong_khoi_phuc_duoc_thi_van_co_loi_ra(self) -> None:
        cac_cau = goi_y_khi_thieu_du_lieu(_state())

        assert len(cac_cau) == 3
        assert all("Ocean Park" in cau for cau in cac_cau)

    def test_chi_doc_lich_su_cua_nguoi_dung(self) -> None:
        """Câu trợ lý tự nói không phải tiêu chí khách yêu cầu."""
        state = _state(history=[ChatMessage(role=MessageRole.ASSISTANT, content="Có 20 căn dưới 4 tỷ ở Ocean Park 1")])
        assert goi_y_khi_thieu_du_lieu(state) == goi_y_khi_thieu_du_lieu(_state())


class TestNgoaiPhamVi:
    def test_chi_dan_ve_dung_pham_vi_tra_cuu(self) -> None:
        """Trợ lý chỉ tra được Ocean Park — gợi ý không được mở ra ngoài đó."""
        cac_cau = goi_y_tiep_theo(_state(intent=Intent.GENERAL))

        assert cac_cau == goi_y_ngoai_pham_vi()
        assert all("Ocean Park" in cau for cau in cac_cau)


@pytest.mark.parametrize(
    "cau",
    [
        "Liệt kê 20 căn đó",
        "Xem thêm căn khác",
        "Cho tôi biết chi tiết",
    ],
)
def test_cau_khong_tu_chua_tieu_chi_bi_loai(cau: str) -> None:
    """Chính những câu này đã làm khách vào ngõ cụt — bộ lọc phải chặn."""
    assert not _co_tool_nhan(cau)


class _LLMGia:
    """Provider trả đúng một chuỗi, ghi lại prompt đã nhận."""

    def __init__(self, tra_ve: str = "", ném: Exception | None = None) -> None:
        self.tra_ve = tra_ve
        self.ném = ném
        self.prompt = ""

    async def complete(self, messages, **_: object) -> str:
        if self.ném is not None:
            raise self.ném
        self.prompt = messages[0].content
        return self.tra_ve

    async def stream(self, messages, **kwargs):  # pragma: no cover - không dùng
        yield self.tra_ve


class TestGoiYBangModel:
    """Model viết cho tự nhiên, nhưng vẫn phải qua đúng bộ chốt chặn."""

    @pytest.mark.asyncio
    async def test_giu_cau_model_viet_khi_tra_loi_duoc(self) -> None:
        llm = _LLMGia("Xem chi tiết căn VOP758\nCác căn dưới 3 tỷ ở Ocean Park 1")

        cac_cau = await goi_y_bang_model(_state(tool_context=_NHIEU_CAN), llm, "câu trả lời")

        assert cac_cau == ["Xem chi tiết căn VOP758", "Các căn dưới 3 tỷ ở Ocean Park 1"]

    @pytest.mark.asyncio
    async def test_bo_cau_model_bia(self) -> None:
        """Hồi quy: model từng chào 'ưu đãi Ocean Park 1' trong khi kho không có."""
        llm = _LLMGia("Ưu đãi Ocean Park 1 có gì\nXem chi tiết căn VOP758")

        cac_cau = await goi_y_bang_model(_state(tool_context=_NHIEU_CAN), llm, "câu trả lời")

        assert "Xem chi tiết căn VOP758" in cac_cau
        assert not any("Ưu đãi" in c for c in cac_cau)

    @pytest.mark.asyncio
    async def test_bo_dau_dau_dong_model_hay_them(self) -> None:
        llm = _LLMGia('1. Xem chi tiết căn VOP758\n- Căn rẻ nhất ở Ocean Park 1\n"Các căn ở Ocean Park 2"')

        cac_cau = await goi_y_bang_model(_state(tool_context=_NHIEU_CAN), llm, "x")

        assert cac_cau == [
            "Xem chi tiết căn VOP758",
            "Căn rẻ nhất ở Ocean Park 1",
            "Các căn ở Ocean Park 2",
        ]

    @pytest.mark.asyncio
    async def test_model_hong_thi_roi_ve_khuon(self) -> None:
        """Gợi ý hỏng không được kéo theo cả lượt trả lời."""
        state = _state(tool_context=_NHIEU_CAN)
        llm = _LLMGia(ném=RuntimeError("hết quota"))

        assert await goi_y_bang_model(state, llm, "x") == goi_y_tiep_theo(state)

    @pytest.mark.asyncio
    async def test_model_tra_rac_thi_roi_ve_khuon(self) -> None:
        state = _state(tool_context=_NHIEU_CAN)

        assert await goi_y_bang_model(state, _LLMGia("   \n \n"), "x") == goi_y_tiep_theo(state)

    @pytest.mark.asyncio
    async def test_prompt_chi_cho_model_thay_du_kien_that(self) -> None:
        """Model chỉ được nhắc mã căn có thật, nên phải thấy chúng trong prompt."""
        llm = _LLMGia("Xem chi tiết căn VOP758")

        await goi_y_bang_model(
            _state(tool_context=_NHIEU_CAN, tool_filters={"inventory_search": {"subdivision": "Ocean Park 1"}}),
            llm,
            "Có 3 căn phù hợp",
        )

        assert "VOP758" in llm.prompt
        assert "Ocean Park 1" in llm.prompt
        assert "Có 3 căn phù hợp" in llm.prompt


class TestDanToiChotCan:
    def test_mot_can_thi_buoc_giu_cho_dung_dau(self) -> None:
        """Khách đã tụ về một căn là lúc gần quyết định nhất."""
        cac_cau = goi_y_tiep_theo(_state(tool_context=_MOT_CAN))

        assert cac_cau[0] == "Đặt cọc giữ chỗ căn VOP397"

    def test_cau_dat_coc_phai_tra_loi_duoc(self) -> None:
        """Nút cọc mà không tool nào nhận thì chính là ngõ cụt bộ lọc đang chặn."""
        assert _co_tool_nhan("Đặt cọc giữ chỗ căn VOP397")

    def test_danh_sach_nhieu_can_thi_chua_moi_coc(self) -> None:
        """Khách mới đang duyệt, giục để lại số là chèo kéo."""
        cac_cau = goi_y_tiep_theo(_state(tool_context=_NHIEU_CAN))

        assert not any("cọc" in c.lower() for c in cac_cau)


class TestKhuonNut:
    """Gợi ý là chữ trên một nút bấm nhỏ, không phải một đoạn văn."""

    @pytest.mark.asyncio
    async def test_bo_cau_dai_thanh_doan_van(self) -> None:
        """Ca thật trên production: model trả về nguyên ba câu và nó lên giao diện."""
        doan_van = (
            "Mình muốn biết rõ hơn về một phân khu cụ thể trong dự án Vinhomes Ocean Park 2. "
            "Bạn có thể cho mình biết thêm thông tin về các tiêu chí như giá, diện tích hay "
            "số phòng ngủ không? Mình đang muốn so sánh một số căn hộ trong phân khu này."
        )
        llm = _LLMGia(f"{doan_van}\nCăn rẻ nhất ở Ocean Park 2")

        cac_cau = await goi_y_bang_model(_state(tool_context=_NHIEU_CAN), llm, "x")

        assert doan_van not in cac_cau
        assert "Căn rẻ nhất ở Ocean Park 2" in cac_cau

    @pytest.mark.asyncio
    async def test_bo_cau_viet_bang_giong_tro_ly(self) -> None:
        """Bấm vào câu giọng trợ lý là khách tự hỏi chính mình."""
        llm = _LLMGia("Bạn muốn xem căn nào ở Ocean Park 1?\nCăn rẻ nhất ở Ocean Park 1")

        cac_cau = await goi_y_bang_model(_state(tool_context=_NHIEU_CAN), llm, "x")

        assert cac_cau == ["Căn rẻ nhất ở Ocean Park 1"]

    def test_moi_khuon_tat_dinh_deu_du_ngan(self) -> None:
        for ten, cac_cau in _moi_tinh_huong():
            for cau in cac_cau:
                assert len(cau) <= TOI_DA_KY_TU, f"{ten}: {cau!r} dài {len(cau)} ký tự"


class TestKhongLapCauVuaHoi:
    """Gợi lại đúng câu vừa trả lời là mời người dùng bấm để đọc lại thứ đang nhìn."""

    def test_bo_goi_y_trung_cau_hien_tai(self) -> None:
        """Ca thật: trả lời xong tài liệu chính sách thì nút gợi ý lại đúng câu đó."""
        state = _state(chunks=[_chunk("Chính sách hỗ trợ lãi suất chung của Vinhomes")])
        state["query"] = "Chính sách hỗ trợ lãi suất chung của Vinhomes"

        assert goi_y_tiep_theo(state) == []

    def test_bo_ca_khi_lech_dau_va_hoa_thuong(self) -> None:
        state = _state(chunks=[_chunk("Ưu đãi của Vinhomes OceanPark 2")])
        state["query"] = "uu dai cua vinhomes oceanpark 2"

        assert goi_y_tiep_theo(state) == []

    def test_bo_goi_y_trung_cau_hoi_luot_truoc(self) -> None:
        state = _state(
            chunks=[_chunk("Vị trí Vinhomes Ocean Park 2")],
            history=[_hoi("Vị trí Vinhomes Ocean Park 2")],
        )
        state["query"] = "còn gì nữa không"

        assert goi_y_tiep_theo(state) == []

    def test_duoi_ngu_canh_widget_khong_lam_lech_so_khop(self) -> None:
        """FE chèn "(căn đang xem: X)" nên chuỗi không trùng từng ký tự."""
        state = _state(chunks=[_chunk("Vị trí Vinhomes Ocean Park 2")])
        state["query"] = "Vị trí Vinhomes Ocean Park 2 (căn đang xem: VOP437)"

        assert goi_y_tiep_theo(state) == []

    def test_cau_khac_thi_van_giu(self) -> None:
        state = _state(chunks=[_chunk("Vị trí Vinhomes Ocean Park 2")])
        state["query"] = "Ưu đãi Ocean Park 2"

        assert goi_y_tiep_theo(state) == ["Vị trí Vinhomes Ocean Park 2"]


class TestKhongMoiVaoNgoCut:
    """Gợi ý không được lặp lại bộ tiêu chí vừa chứng minh là rỗng.

    Ca thật: hỏi "2 phòng ngủ và 3 vệ sinh ở Ocean Park 1" — kho không có căn 3
    vệ sinh nào — rồi cả bốn nút gợi ý đều là "Đếm số căn 2PN, 3 vệ sinh…",
    "So sánh các căn 2PN, 3 vệ sinh…". Bấm cái nào cũng quay về chỗ vừa đứng.

    `_tra_loi_duoc` chỉ hỏi "có tool nào NHẬN câu này". Tool nhận không có nghĩa
    là tool RA được gì.
    """

    RONG = [{"unit_type": "2PN", "wc": 3, "subdivision": "Ocean Park 1"}]

    @pytest.fixture(autouse=True)
    def _tu_vung(self, monkeypatch):
        """`extract_criteria` rút loại căn từ từ vựng ĐỌC TỪ DB, mà fixture chung
        của bộ test cấp một SQLite rỗng. Không nạp thì `unit_type` luôn None và
        cả nhóm test này xanh giả."""
        from src.agents.tools.search import vocabulary

        monkeypatch.setattr(
            vocabulary,
            "_values",
            {"unit_type": ["1PN, 1WC", "2PN, 1WC", "2PN, 2WC", "Studio"], "building": [], "direction": []},
        )
        monkeypatch.setattr(vocabulary, "_loaded_at", float("inf"))

    def test_bo_cau_lap_lai_tieu_chi_rong(self) -> None:
        giu = _loc(["So sánh các căn 2PN, 3 vệ sinh ở Ocean Park 1"], {"tieu_chi_rong": self.RONG})

        assert giu == []

    def test_them_tieu_chi_vao_bo_rong_van_la_rong(self) -> None:
        """ "giá thấp nhất" chỉ đổi cách sắp xếp — tập căn vẫn rỗng."""
        giu = _loc(["Tìm căn 2PN, 3 vệ sinh giá thấp nhất ở Ocean Park 1"], {"tieu_chi_rong": self.RONG})

        assert giu == []

    def test_van_giu_cau_noi_long_tieu_chi(self) -> None:
        """Chốt ngược: bỏ bớt điều kiện thì có thể ra căn, đừng lọc oan."""
        cau = ["Tìm căn 2PN, 2 vệ sinh ở Ocean Park 1", "Tìm căn 2 phòng ngủ ở Ocean Park 1"]

        assert _loc(cau, {"tieu_chi_rong": self.RONG}) == cau

    def test_khong_co_tieu_chi_rong_thi_giu_nguyen_hanh_vi_cu(self) -> None:
        cau = ["So sánh các căn 2PN, 3 vệ sinh ở Ocean Park 1"]

        assert _loc(cau, {}) == cau
