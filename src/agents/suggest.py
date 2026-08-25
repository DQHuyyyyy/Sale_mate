"""Gợi ý câu hỏi tiếp theo — mở sẵn nước đi kế tiếp sau mỗi câu trả lời.

Đây là hệ thống hỗ trợ sale chốt căn, nên trả lời xong mà để khách tự nghĩ câu
kế tiếp là bỏ lỡ nhịp. Module này đọc state của lượt vừa xong rồi ráp vài câu
hỏi bấm được, gửi ra FE qua `data.options` của event `done`.

Hai tầng, cố ý xếp theo thứ tự này:

- **`goi_y_bang_model`** — model rẻ viết gợi ý bám vào chính câu vừa trả lời,
  nên đọc tự nhiên và đi đúng mạch câu chuyện. Đây là đường chạy mặc định.
- **`goi_y_tiep_theo`** — khuôn suy ra từ state, không gọi model. Làm lưới an
  toàn khi model hỏng, hết quota, hoặc viết ra toàn câu bị loại.

Ba luật xương sống, đừng gỡ cái nào:

1. **Mọi câu phải qua `_tra_loi_duoc`**, kể cả câu do model viết. Đây là chốt
   chặn thật lúc chạy, không phải chỉ là test: câu nào không tool nào nhận và
   cũng không phải tên tài liệu đã truy hồi thì bị loại. Nút bấm vào ngõ cụt
   còn tệ hơn không có nút. Dự án đã dính đúng lỗi này khi model chào "ưu đãi
   Ocean Park 1" trong khi kho chỉ có OP2 và OP3.
2. **Câu phải tự chứa đủ tiêu chí.** `build_args` của mọi tool chỉ đọc câu hiện
   tại, không nhớ lượt trước. "Liệt kê 20 căn đó" không tool nào nhận; phải là
   "Các căn dưới 4 tỷ ở Ocean Park 1". Không dùng từ thay thế.
3. **Gợi ý hỏng không được kéo theo câu trả lời.** Mọi lỗi ở đây đều nuốt và
   rơi về khuôn — khách mất dãy nút thì tiếc, mất câu trả lời thì hỏng.

Đích của dãy nút không phải là hỏi cho vui: nó dẫn khách từ danh sách về một
căn, từ một căn sang so sánh và tài chính, rồi tới giữ chỗ. Bước cuối đó có
thật — tool `dat_coc` ghi lead vào Postgres cho đội sale gọi lại.

Không đăng ký thành `@register_tool`: `ToolsNode` chạy TRƯỚC `generate` và kết
quả tool đi thẳng vào prompt. Gợi ý sinh ra SAU câu trả lời và không được vào
prompt — sai chỗ thì model sẽ coi gợi ý là dữ kiện.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.agents.state import AgentState
from src.agents.tools import registry
from src.agents.tools.khoan_vay import _VON_TU_CO
from src.agents.tools.search import _NGU_CANH_GIAO_DIEN, _doc_tien, extract_criteria
from src.core.logging import get_logger
from src.models.chat import ChatMessage, MessageRole

logger = get_logger(__name__)

# Số nút tối đa. Nhiều hơn thì người dùng phải đọc thay vì bấm, mất luôn ý nghĩa
# của việc gợi sẵn. Dùng chung với phương án của câu hỏi ngược ở `PlanNode`.
TOI_DA_PHUONG_AN = 4

PHAN_KHU = ("Ocean Park 1", "Ocean Park 2", "Ocean Park 3")

# Mã căn trong khối JSON mà `ToolsNode` nhét vào `tool_context`. Quét text thay
# vì parse JSON: có tiền lệ ở `PlanNode._da_co_ma_can`, và khối đó là do chính
# mình dump ra nên hình dạng ổn định.
_MA_CAN = re.compile(r'"unit_code":\s*"([A-Za-z]{2,4}\d{2,5})"')
_PHAN_KHU_TRONG_KET_QUA = re.compile(r'"subdivision":\s*"(Ocean Park [123])"')


def phuong_an_tu_tai_lieu(state: AgentState) -> list[str]:
    """Phương án lấy thẳng TÊN TÀI LIỆU đã truy hồi, không hỏi model.

    Vì sao không để model tự nghĩ: nó gợi ý thứ không tồn tại. Ca thật — kho chỉ
    có ưu đãi của Ocean Park 2 và 3, model vẫn chào "ưu đãi của Ocean Park 1".
    Người dùng bấm vào, agent tra không ra, lại hỏi ngược tiếp; hai lượt trôi đi
    mà không ai tiến thêm bước nào.

    Tên tài liệu là danh sách những gì THẬT SỰ có, đã xếp theo độ liên quan.

    Chúng cũng sẵn là cụm danh từ ("Ưu đãi của Vinhomes OceanPark 2"), đọc như
    một gợi ý bấm được — hơn hẳn câu hỏi đóng "Bạn có muốn biết… không?" mà
    bấm vào chỉ như đang trả lời "có".
    """
    ten = [(c.doc_title or "").strip() for c in state.get("chunks") or []]
    return list(dict.fromkeys(t for t in ten if t))[:TOI_DA_PHUONG_AN]


def _co_tool_nhan(cau: str) -> bool:
    """Có tool nào rút được tham số từ câu này không.

    Hỏi thẳng registry thay vì gọi `_extract_args` của từng module: đây đúng là
    cửa mà `ToolsNode` dùng để quyết tool nào chạy, nên nếu ở đây nhận thì lượt
    sau cũng nhận. Thêm tool mới là tự động được tính, không phải sửa file này.
    """
    for tool in registry.all():
        binding = registry.binding(tool.name)
        if binding is None:
            continue
        try:
            # CỐ Ý không truyền thực thể: gợi ý là câu người dùng sẽ bấm ở lượt
            # SAU, và lượt đó có ngữ cảnh riêng. Nới ở đây thì "liệt kê 20 căn
            # đó" lọt qua bộ lọc nhờ ngữ cảnh của lượt NÀY, rồi hỏng khi bấm.
            if binding.dung_args(cau) is not None:
                return True
        except Exception:  # noqa: BLE001 - một tool kén tham số không được chặn cả dãy gợi ý
            continue
    return False


# Chủ đề chỉ nằm trong kho TÀI LIỆU, không tool nào tra được.
_TU_KHOA_TAI_LIEU = ("ưu đãi", "tiện ích", "vị trí", "chính sách", "pháp lý", "tổng quan", "lãi suất")


def _hoi_ve_tai_lieu(cau: str) -> bool:
    thap = cau.lower()
    return any(tu in thap for tu in _TU_KHOA_TAI_LIEU)


def _khop_tai_lieu_da_co(cau: str, ten_tai_lieu: list[str]) -> bool:
    """Câu hỏi về tài liệu phải khớp một tài liệu THẬT SỰ truy hồi được.

    Khớp theo chủ đề + số phân khu, không đòi trùng từng chữ: model viết "Ưu đãi
    Ocean Park 3 có gì" còn tài liệu tên "Ưu đãi Vinhomes OceanPark 3".
    """
    thap = cau.lower()
    chu_de = [tu for tu in _TU_KHOA_TAI_LIEU if tu in thap]
    so = set(re.findall(r"\b([123])\b", thap))

    for ten in ten_tai_lieu:
        ten_thap = ten.lower()
        if not any(tu in ten_thap for tu in chu_de):
            continue
        if so and not (so & set(re.findall(r"\b([123])\b", ten_thap))):
            continue
        return True
    return False


def _tra_loi_duoc(cau: str, ten_tai_lieu: list[str]) -> bool:
    """Hệ thống có tra được câu này không — chốt chặn quan trọng nhất của module.

    Hai tầng, và tầng thứ hai sinh ra từ một lỗ hổng test bắt được: chỉ hỏi "có
    tool nào nhận không" là chưa đủ. "Ưu đãi Ocean Park 1 có gì" lọt qua tầng
    một vì `extract_criteria` thấy "Ocean Park 1" rồi rút ra phân khu — tool
    tìm căn sẽ chạy và trả về một danh sách căn hộ. Khách bấm vào chờ đọc ưu
    đãi, nhận về danh sách căn, mà kho lại không hề có tài liệu ưu đãi cho OP1.

    Nên câu hỏi về CHỦ ĐỀ TÀI LIỆU phải khớp một tài liệu đã truy hồi thật.
    """
    if _hoi_ve_tai_lieu(cau) and not _khop_tai_lieu_da_co(cau, ten_tai_lieu):
        return False
    return _co_tool_nhan(cau) or cau in ten_tai_lieu


# Nút bấm nằm trong khung chat hẹp. Quá ngần này ký tự là nút tràn thành một
# khối chữ, người dùng phải ĐỌC thay vì bấm — mất đúng lý do gợi sẵn tồn tại.
# Đã xảy ra thật: model trả về nguyên một đoạn ba câu và nó lên thẳng giao diện.
TOI_DA_KY_TU = 80

# Model hay quên mình đang viết lời KHÁCH và trượt sang giọng trợ lý ("Bạn có
# thể cho mình biết thêm…"). Bấm vào là khách tự hỏi chính mình.
_GIONG_TRO_LY = ("bạn có thể", "bạn muốn", "bạn cần", "hãy cho mình", "mình có thể giúp", "cho mình biết")


def _dung_khuon(cau: str) -> bool:
    """Đủ ngắn để bấm, và viết bằng giọng của khách."""
    if len(cau) > TOI_DA_KY_TU:
        return False
    thap = cau.lower()
    return not any(cum in thap for cum in _GIONG_TRO_LY)


def _chuan(cau: str) -> str:
    """Dạng so khớp: bỏ dấu, bỏ đuôi ngữ cảnh widget chèn, gộp khoảng trắng.

    `đ` phải thay tay. NFD tách được dấu của ư, ã, ê… vì chúng là chữ cái cộng
    dấu tổ hợp, nhưng `đ` là MỘT ký tự riêng (U+0111) không tách ra `d` được —
    nó rơi vào nhánh xoá ký tự lạ và "ưu đãi" thành "uu ai", không khớp với
    "uu dai" người dùng gõ không dấu.
    """
    sach = _NGU_CANH_GIAO_DIEN.sub(" ", cau).lower().replace("đ", "d")
    khong_dau = unicodedata.normalize("NFD", sach)
    khong_dau = "".join(k for k in khong_dau if unicodedata.category(k) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", khong_dau).strip()


def _da_hoi_roi(state: AgentState) -> set[str]:
    """Câu người dùng vừa hỏi, và vài lượt trước đó.

    Gợi lại đúng câu vừa trả lời là mời người dùng bấm để đọc lại thứ họ đang
    nhìn. Đã xảy ra thật: trả lời xong "Chính sách hỗ trợ lãi suất chung của
    Vinhomes" thì nút gợi ý duy nhất lại đúng câu đó — bấm vào là quay vòng.
    Gốc là `phuong_an_tu_tai_lieu` lấy tên tài liệu ĐÃ TRUY HỒI, mà tài liệu
    khớp nhất với câu hỏi thì đương nhiên là tài liệu vừa dùng để trả lời.
    """
    return {_chuan(state.get("query", "")), *(_chuan(c) for c in _cau_hoi_nguoi_dung(state)[:3])}


def _dan_vao_ngo_cut(cau: str, tieu_chi_rong: list[dict[str, Any]]) -> bool:
    """Câu này có lặp lại đúng bộ tiêu chí vừa chứng minh là KHÔNG có căn nào không.

    `_tra_loi_duoc` chỉ hỏi "có tool nào NHẬN câu này" — mà tool nhận không có
    nghĩa là tool RA được gì. Ca thật: hỏi "2 phòng ngủ và 3 vệ sinh ở Ocean
    Park 1" (kho không có căn 3 vệ sinh nào), rồi bốn nút gợi ý đều là "Đếm số
    căn 2PN, 3 vệ sinh…", "So sánh các căn 2PN, 3 vệ sinh…". Bấm cái nào cũng
    quay lại đúng chỗ vừa đứng.

    So theo QUAN HỆ BAO HÀM chứ không so bằng: gợi ý thường thêm tiêu chí (giá
    thấp nhất, diện tích lớn nhất) vào bộ đã rỗng — thêm điều kiện vào một tập
    rỗng thì vẫn rỗng.
    """
    if not tieu_chi_rong:
        return False
    cua_cau = extract_criteria(cau) or {}
    return any(
        rong and all(cua_cau.get(k) == v for k, v in rong.items() if k not in _KHONG_LOC) for rong in tieu_chi_rong
    )


# Trường đổi CÁCH TRÌNH BÀY chứ không đổi tập căn khớp. Để chúng tham gia so
# sánh thì "rẻ nhất" (thêm sort) bị coi là khác bộ rỗng và lọt qua.
_KHONG_LOC = frozenset({"sort", "limit"})


def _loc(cac_cau: list[str], state: AgentState) -> list[str]:
    """Bỏ câu trùng, sai khuôn, đã hỏi rồi, hoặc hệ thống không trả lời nổi."""
    ten_tai_lieu = phuong_an_tu_tai_lieu(state)
    da_hoi = _da_hoi_roi(state)
    rong = state.get("tieu_chi_rong") or []
    giu = [
        c
        for c in dict.fromkeys(c.strip() for c in cac_cau if c.strip())
        if _dung_khuon(c)
        and _chuan(c) not in da_hoi
        and _tra_loi_duoc(c, ten_tai_lieu)
        and not _dan_vao_ngo_cut(c, rong)
    ]
    return giu[:TOI_DA_PHUONG_AN]


def _so(gia_tri: float) -> str:
    """4.0 -> '4', 2.5 -> '2,5' — viết số kiểu Việt, bỏ đuôi .0 thừa."""
    lam_tron = round(float(gia_tri), 2)
    if lam_tron == int(lam_tron):
        return str(int(lam_tron))
    return f"{lam_tron}".replace(".", ",")


def _ma_can(state: AgentState) -> list[str]:
    """Mã căn XUẤT HIỆN TRONG LƯỢT NÀY. Không lấy từ đâu khác để khỏi bịa mã."""
    return list(dict.fromkeys(_MA_CAN.findall(state.get("tool_context", "") or "")))


def _phan_khu_dang_xet(state: AgentState) -> str | None:
    """Phân khu của lượt này — ưu tiên tiêu chí đã lọc, sau đó là dữ liệu trả về."""
    for args in (state.get("tool_filters") or {}).values():
        if isinstance(args, dict) and args.get("subdivision") in PHAN_KHU:
            return str(args["subdivision"])
    khop = _PHAN_KHU_TRONG_KET_QUA.search(state.get("tool_context", "") or "")
    return khop.group(1) if khop else None


def _tieu_chi_da_dung(state: AgentState) -> dict[str, Any]:
    """Gộp tham số của mọi tool đã chạy — để biết trục nào CHƯA lọc mà gợi ý."""
    gop: dict[str, Any] = {}
    for args in (state.get("tool_filters") or {}).values():
        if isinstance(args, dict):
            gop.update(args)
    return gop


def _duoi_gia(tieu_chi: dict[str, Any]) -> str:
    """Vế giá viết lại thành lời, rỗng nếu lượt này không lọc theo giá."""
    if tieu_chi.get("price_max") is not None:
        return f"dưới {_so(tieu_chi['price_max'])} tỷ"
    if tieu_chi.get("price_min") is not None:
        return f"trên {_so(tieu_chi['price_min'])} tỷ"
    return ""


def _theo_danh_sach_can(state: AgentState, ma: list[str]) -> list[str]:
    """Tool trả về nhiều căn — dẫn khách từ danh sách về một căn cụ thể."""
    tieu_chi = _tieu_chi_da_dung(state)
    khu = _phan_khu_dang_xet(state)
    o_khu = f" ở {khu}" if khu else ""
    gia = _duoi_gia(tieu_chi)
    ve_gia = f" {gia}" if gia else ""

    cau = [f"Xem chi tiết căn {ma[0]}"]
    if len(ma) >= 2:
        cau.append(f"So sánh căn {ma[0]} và căn {ma[1]}")
    # Chỉ gợi thu hẹp theo trục CHƯA lọc — gợi lại đúng thứ vừa lọc là mời người
    # dùng bấm để nhận lại y nguyên danh sách họ đang nhìn.
    if not tieu_chi.get("unit_type"):
        cau.append(f"Các căn 2 phòng ngủ{ve_gia}{o_khu}")
    cau.append(f"Căn rẻ nhất{ve_gia}{o_khu}")
    return cau


def _theo_mot_can(state: AgentState, ma: str) -> list[str]:
    """Đang xem đúng một căn — mở ra so sánh và điều kiện mua."""
    khu = _phan_khu_dang_xet(state)
    o_khu = f" ở {khu}" if khu else ""

    # Bước giữ chỗ đứng ĐẦU khi khách đã tụ về đúng một căn — đó là lúc gần
    # quyết định nhất. `dat_coc` nhận câu này dù chưa có số điện thoại, nên bấm
    # vào là trợ lý hỏi xin thông tin chứ không phải ngõ cụt.
    cau = [f"Đặt cọc giữ chỗ căn {ma}", f"Các căn khác{o_khu}", f"Căn rẻ nhất{o_khu}"]
    von = _von_tu_co_trong_lich_su(state)
    if von is not None:
        # Số vốn là con số KHÁCH TỰ NÊU ở lượt trước, không phải mình đặt ra.
        # Thiếu nó thì `tinh_khoan_vay` không chạy và nút bấm thành ngõ cụt.
        cau.append(f"Tôi có {_so(von)} tỷ, mua căn {ma} thì vay thế nào")
    return cau + phuong_an_tu_tai_lieu(state)


def _cau_hoi_nguoi_dung(state: AgentState) -> list[str]:
    """Các lượt NGƯỜI DÙNG đã gõ, mới nhất trước."""
    lich_su = state.get("history") or []
    return [m.content for m in reversed(lich_su) if m.role == MessageRole.USER and m.content]


def _von_tu_co_trong_lich_su(state: AgentState) -> float | None:
    """Số vốn khách đã tự nêu ở lượt trước, nếu có.

    Đọc lại bằng chính regex của tool vay để hai bên không hiểu khác nhau.
    """
    for cau in _cau_hoi_nguoi_dung(state):
        khop = _VON_TU_CO.search(cau)
        if khop is None:
            continue
        tien = _doc_tien(khop.group(1), khop.group(2))
        if tien is not None and tien > 0:
            return tien
    return None


def _tieu_chi_khoi_phuc(state: AgentState) -> dict[str, Any]:
    """Tiêu chí lấy lại từ câu hỏi TRƯỚC ĐÓ của người dùng.

    Chỉ dùng để DỰNG GỢI Ý, không truyền xuống tool. `extract_criteria` vẫn chỉ
    đọc câu hiện tại như cũ — nới chỗ đó ra là nới luôn rủi ro tra nhầm sang
    tiêu chí cũ mà người dùng đã bỏ.
    """
    for cau in _cau_hoi_nguoi_dung(state):
        tieu_chi = extract_criteria(cau)
        if tieu_chi:
            return tieu_chi
    return {}


def goi_y_khi_thieu_du_lieu(state: AgentState) -> list[str]:
    """Câu hỏi chưa đủ rõ — trải ra ba phân khu thay vì để khách vào ngõ cụt.

    Ca thật: "có bao nhiêu căn dưới 4 tỷ ở OP1" chạy tốt, rồi "liệt kê 20 căn
    đó" thì không tool nào nhận vì câu không còn tiêu chí nào. Khách nhận một
    lời từ chối cụt và phải tự đoán cách hỏi lại. Giờ tiêu chí được nhặt lại từ
    lượt trước và trả ra thành ba nút bấm được.
    """
    tieu_chi = _tieu_chi_khoi_phuc(state)
    gia = _duoi_gia(tieu_chi)
    ve_gia = f" {gia}" if gia else ""
    return _loc([f"Các căn{ve_gia} ở {khu}" for khu in PHAN_KHU], state)


def goi_y_ngoai_pham_vi() -> list[str]:
    """Câu ngoài phạm vi — chỉ dẫn về đúng thứ trợ lý tra được, không mở rộng."""
    return [f"Căn ở {khu}" for khu in PHAN_KHU]


def goi_y_tiep_theo(state: AgentState) -> list[str]:
    """Gợi ý sau một câu trả lời thành công. Tối đa 4 câu, đã lọc.

    Thứ tự xét đi từ cụ thể tới chung: có căn trong tay thì dẫn về chốt căn, chỉ
    có tài liệu thì mời đọc tài liệu liên quan, không có gì thì kéo về phạm vi.
    """
    ma = _ma_can(state)
    if len(ma) >= 2:
        return _loc(_theo_danh_sach_can(state, ma), state)
    if len(ma) == 1:
        return _loc(_theo_mot_can(state, ma[0]), state)

    theo_tai_lieu = phuong_an_tu_tai_lieu(state)
    if theo_tai_lieu:
        return _loc(theo_tai_lieu, state)

    return _loc(goi_y_ngoai_pham_vi(), state)


# ---------- Sinh bằng model ----------

_PROMPT_GOI_Y = """Bạn giúp một trợ lý bán căn hộ Vinhomes Ocean Park nghĩ ra câu hỏi \
tiếp theo mà KHÁCH sẽ bấm.

Khách vừa hỏi: {cau_hoi}

Trợ lý vừa trả lời: {cau_tra_loi}

Dữ kiện có thật của lượt này — chỉ được dùng đúng những thứ này:
- Mã căn đang nói tới: {ma_can}
- Phân khu: {phan_khu}
- Tiêu chí khách đã lọc: {tieu_chi}
- Tài liệu tra được: {tai_lieu}

Viết tối đa {toi_da} câu, mỗi câu một dòng, không đánh số, không giải thích.

Luật bắt buộc:
0. **Mỗi câu DƯỚI {toi_da_ky_tu} ký tự** — nó là chữ trên một nút bấm nhỏ, không
   phải một đoạn văn. Một ý một câu. Ví dụ đúng: "Căn rẻ nhất ở Ocean Park 2".
1. Viết như KHÁCH nói với trợ lý, không phải trợ lý nói với khách. Cấm mở đầu
   bằng "Bạn có thể…", "Bạn muốn…" — đó là giọng trợ lý.
2. Mỗi câu TỰ CHỨA đủ tiêu chí. Cấm "căn đó", "chỗ này", "như trên" — trợ lý
   không nhớ lượt trước, câu thiếu tiêu chí sẽ tra không ra.
3. Chỉ nhắc mã căn, phân khu, tên tài liệu có trong dữ kiện trên. Không bịa
   thêm mã căn, tên toà, tên tài liệu hay tiện ích nào khác.
4. Hệ thống chỉ tra được: tìm căn theo giá/diện tích/phòng ngủ/phân khu/hướng/
   view, xem chi tiết một căn, so sánh nhiều căn, đếm số căn, tính khoản vay,
   đọc tài liệu dự án, và ghi nhận đặt cọc. Đừng gợi ý thứ ngoài danh sách đó.
5. Dẫn khách tiến gần hơn tới việc CHỐT một căn: từ danh sách về một căn cụ thể,
   từ một căn sang so sánh hoặc tài chính, rồi mới tới giữ chỗ.
6. Chỉ thêm câu đặt cọc khi đã nói tới một mã căn cụ thể và khách có vẻ ưng.
   Đừng mời cọc khi khách mới bắt đầu xem.
"""


def _rut_gon(gia_tri: object, toi_da: int = 400) -> str:
    """Cắt bớt cho prompt gợi ý khỏi phình — nó chỉ cần biết đại ý."""
    chu = str(gia_tri or "").strip()
    return chu[:toi_da] if chu else "(không có)"


def _du_kien(state: AgentState, cau_tra_loi: str) -> str:
    ma = _ma_can(state)
    return _PROMPT_GOI_Y.format(
        cau_hoi=_rut_gon(state.get("query"), 200),
        cau_tra_loi=_rut_gon(cau_tra_loi, 900),
        ma_can=", ".join(ma[:6]) or "(không có)",
        phan_khu=_phan_khu_dang_xet(state) or "(chưa rõ)",
        tieu_chi=_rut_gon(_tieu_chi_da_dung(state), 200),
        tai_lieu=", ".join(phuong_an_tu_tai_lieu(state)) or "(không có)",
        toi_da=TOI_DA_PHUONG_AN,
        toi_da_ky_tu=TOI_DA_KY_TU,
    )


def _tach_dong(thô: str) -> list[str]:
    """Mỗi dòng một câu. Bỏ bullet, số thứ tự và ngoặc kép model hay thêm."""
    cau = []
    for dong in (thô or "").splitlines():
        sach = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", dong).strip().strip('"').strip()
        if sach:
            cau.append(sach)
    return cau


async def goi_y_bang_model(
    state: AgentState,
    llm: Any,
    cau_tra_loi: str,
    *,
    model: str | None = None,
) -> list[str]:
    """Gợi ý do model viết, đã lọc qua đúng bộ chốt chặn của khuôn tất định.

    Vì sao để model viết: khuôn cố định lộ ra ngay sau vài lượt — lượt nào cũng
    "Căn rẻ nhất ở Ocean Park 1" thì khách thôi không đọc nút nữa. Model bám
    được vào câu vừa trả lời nên gợi ý đi đúng mạch câu chuyện.

    Vì sao vẫn lọc: model bịa. Nó từng chào "ưu đãi Ocean Park 1" trong khi kho
    chỉ có OP2 và OP3. `_loc` giữ nguyên vai trò trọng tài — câu nào không tool
    nào nhận thì bỏ, bất kể model tự tin tới đâu.

    Model hỏng, hết quota hay trả rác thì rơi về khuôn tất định. Gợi ý là thứ
    làm mượt trải nghiệm, không đáng để làm hỏng cả câu trả lời.
    """
    try:
        thô = await llm.complete(
            [ChatMessage(role=MessageRole.USER, content=_du_kien(state, cau_tra_loi))],
            model=model,
            temperature=0.7,
            max_tokens=200,
        )
    except Exception:  # noqa: BLE001 - gợi ý hỏng không được kéo theo câu trả lời
        logger.warning("Không sinh được gợi ý bằng model, dùng khuôn tất định", exc_info=True)
        return goi_y_tiep_theo(state)

    tu_model = _loc(_tach_dong(thô), state)
    return tu_model or goi_y_tiep_theo(state)
