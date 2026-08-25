"""Node chạy tool — cầu nối giữa agent và dữ liệu CÓ CẤU TRÚC.

Vì sao cần node này, trong khi đã có RAG: giá và tình trạng căn thay đổi theo
thời gian. Nhét chúng vào vector store nghĩa là trả lời khách bằng một bản chụp
cũ. Tool đọc thẳng nguồn sự thật ngay lúc hỏi.

Node KHÔNG biết tool nào tồn tại. Nó hỏi registry "có tool nào nhận nhãn này
không", rồi để từng tool tự quyết qua `build_args`. Thêm tool mới là thêm một
file trong tools/, không ai phải sửa file này lẫn graph.py.

Node không bao giờ làm đứt luồng: tool trả `ToolResult.failure(...)` chứ không
raise, và tool nào hỏng thì chỉ mình nó bị bỏ qua, các tool khác vẫn chạy.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.contracts import AgentTool, ToolResult
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.logging import get_logger
from src.models.chat import Citation

logger = get_logger(__name__)

# Trường KHÔNG BAO GIỜ được vào log. Cùng danh sách với luật "số điện thoại không
# đi vào `data` của tool" ở `tools/dat_coc.py`: `data` chảy vào prompt rồi vào log
# của nhà cung cấp LLM, còn log ở đây chảy vào file trên đĩa. Cả hai đều là chỗ
# dữ liệu khách hàng không nên nằm lại.
_TRUONG_NHAY_CAM = frozenset({"so_dien_thoai", "ho_ten", "email", "ghi_chu"})


def _tieu_chi_an_toan(args: dict[str, Any]) -> str:
    """Tiêu chí đã dùng, bỏ trường nhạy cảm. Rỗng thì trả '-'."""
    giu = {k: v for k, v in args.items() if k not in _TRUONG_NHAY_CAM and v not in (None, "", [], {})}
    so_an = sum(1 for k in args if k in _TRUONG_NHAY_CAM)
    mo_ta = ", ".join(f"{k}={v}" for k, v in giu.items())
    if so_an:
        mo_ta += f"{', ' if mo_ta else ''}{so_an} trường riêng tư đã ẩn"
    return mo_ta or "-"


_EMPTY: dict[str, Any] = {"tool_context": "", "tool_citations": [], "tools_ran": [], "tool_filters": {}}


def _ma_can_trong(result: ToolResult) -> list[str]:
    """Mã căn có trong kết quả tool, giữ thứ tự và bỏ trùng.

    Dùng làm NHÃN NGUỒN. Trước đây nguồn của tool lấy câu đầu trong description
    ("Tra tình trạng căn hộ THẬT theo thời gian thực…") — đúng về mặt kỹ thuật
    nhưng người đọc không kiểm chứng được gì từ nó. Mã căn thì bấm vào mở đúng
    căn đó.

    Phải đi XUỐNG một tầng: `inventory_search` không trả thẳng mảng căn mà trả
    `{tong_so_khop, day_du, can_hien_thi: [...]}`. Bản đầu chỉ dò tầng ngoài nên
    không thấy mã nào, rơi vào nhánh dự phòng, và cả cái description dài ngoằng
    của tool leo lên dòng "Nguồn" trước mặt người dùng.
    """
    ma: list[str] = []
    for hang in _cac_hang(result.data):
        gia_tri = hang.get("unit_code")
        if gia_tri:
            ma.append(str(gia_tri))
    return list(dict.fromkeys(ma))


def _cac_hang(data: Any) -> list[dict[str, Any]]:
    """Mọi dict có thể chứa một căn, dù tool gói nó ở tầng nào."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return []
    if data.get("unit_code"):
        return [data]
    return [r for v in data.values() if isinstance(v, list) for r in v if isinstance(r, dict)]


def _nguon_cua_tool(tool: AgentTool, result: ToolResult) -> list[Citation]:
    """Nguồn cho một kết quả tool — một mã căn một nguồn, hoặc nhãn chung.

    Kết quả TỔNG HỢP không có mã căn nào (đếm số căn, tính khoản vay), nên nhãn
    phải là một cụm chữ người đọc hiểu: "Dữ liệu tồn kho". Bản trước lấy câu đầu
    trong `description` và dòng "Nguồn" hiện nguyên "Đếm số căn còn trống / đã
    bán trong tồn kho, tổng hợp theo toà và loại căn" — mô tả dành cho model,
    không dành cho khách.

    `nhan_nguon` là thuộc tính TUỲ CHỌN, đọc bằng `getattr`: `AgentTool` là hợp
    đồng đóng băng, tool nào cần nhãn riêng thì tự khai, còn lại rơi về tên tool.
    """
    goc = result.source or tool.name
    ma = _ma_can_trong(result)
    if ma:
        return [Citation(doc_id=goc, title=m, kind="db") for m in ma]

    # Tool đọc số từ một TÀI LIỆU thì nguồn phải là tài liệu đó, không phải tên
    # tool. `tinh_khoan_vay` lấy trần lãi suất và các gói 18/24/30/36/60 tháng
    # từ `chinh_sach_vay.json`, mà file đó khai sẵn `doc_id` trỏ về tài liệu gốc
    # — chính là để câu trả lời trích ngược được. Trước đây dòng "Nguồn" hiện
    # `"tinh_khoan_vay"`: một cái tên máy, bấm vào không ra gì, và người đọc
    # không biết con số 6%/năm đến từ đâu để kiểm.
    #
    # ⚠️ Vẫn `kind="db"` dù trỏ vào một tài liệu. Hai khái niệm khác nhau, đừng
    # gộp:
    #
    #   `kind`         — nguồn này ĐẾN TỪ đâu: "db" = tool đã chạy và đã dùng,
    #                    "doc" = truy hồi lấy về (có thể không liên quan).
    #   tiền tố doc_id — nguồn này TRỎ VÀO đâu: `knowledge:` mở được trang tài
    #                    liệu, `inventory:`/`tool:` thì không.
    #
    # Đặt `kind="doc"` ở đây là tự bắn vào chân: `loc_nguon_da_dung` yêu cầu
    # nguồn tài liệu phải được model gọi tên tường minh mới giữ — luật đó đúng
    # cho chunk truy hồi (chỉ "đã tra"), nhưng sai cho tool (đã DÙNG thật). Câu
    # trả lời nói "chính sách 6%/năm đã hết hiệu lực" mà model không nhắc đúng
    # tên tài liệu là mất sạch nguồn cho chính khẳng định đó.
    if goc.startswith("knowledge:"):
        return [Citation(doc_id=goc, title=goc.split(":", 1)[1], kind="db")]

    return [Citation(doc_id=goc, title=getattr(tool, "nhan_nguon", "") or tool.name, kind="db")]


def _format(tool: AgentTool, result: ToolResult) -> str:
    """Ghép kết quả thành text cho prompt.

    Dùng JSON thay vì câu văn: model đọc số từ JSON ít sai hơn, và không phải
    bịa thêm chữ nối — hợp với nguyên tắc không bịa số.

    ⚠️ KHÔNG bọc tên tool trong ngoặc vuông. Prompt dạy trích nguồn cũng bằng
    ngoặc vuông (`[Mã căn]`), nên `[inventory_summary]` đứng đầu khối ngữ cảnh
    bị model hiểu là một ví dụ trích dẫn và chép y nguyên vào câu trả lời — đo
    được: "Ocean Park 3 còn 30 căn đang bán. [inventory_summary]". FE rút dấu đó
    ra rồi dựng thành dòng "Nguồn: inventory_summary", đúng cái nhãn máy móc mà
    `nhan_nguon` sinh ra để thay thế.

    Bỏ ngoặc vuông vẫn CHƯA đủ: model bị prompt bắt trích nguồn cho mọi khẳng
    định, mà câu trả lời tổng hợp ("còn 30 căn") không có mã căn lẫn tên tài
    liệu nào — nên nó lấy định danh duy nhất nhìn thấy được, tức tên tool. Vì
    vậy tool tổng hợp phải NÓI THẲNG nhãn nên trích, và nhãn đó chính là cái
    `_nguon_cua_tool` sẽ gắn vào dòng "Nguồn".
    """
    body = json.dumps(result.data, ensure_ascii=False, default=str)
    khoi = f"Tool {tool.name} — {tool.description}\nKết quả:\n{body}"
    nhan = getattr(tool, "nhan_nguon", "")
    return f"{khoi}\nTrích nguồn cho dữ liệu này bằng: [{nhan}]" if nhan else khoi


class ToolsNode(BaseNode):
    """Chạy các tool khai là phục vụ intent hiện tại."""

    name = "tools"

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        # Cho tiêm registry để test dựng bảng tool riêng, không đụng bảng toàn cục.
        self._registry = registry or default_registry

    async def execute(self, state: AgentState) -> dict[str, Any]:
        candidates = self._registry.for_intent(state.get("intent"))
        if not candidates:
            return _EMPTY

        query = state.get("query", "")
        # Thực thể do router giải tham chiếu từ lịch sử. Rỗng ở lượt đầu, và khi
        # rỗng thì mọi builder rơi về đúng hành vi cũ: regex trên câu hiện tại.
        entities = state.get("entities") or {}
        blocks: list[str] = []
        citations: list[Citation] = []
        ran: list[str] = []
        tieu_chi: dict[str, Any] = {}
        rong: list[dict[str, Any]] = []

        for tool, binding in candidates:
            args = binding.dung_args(query, entities)
            if args is None:
                continue

            # DEBUG chứ không INFO: trên terminal dòng này trùng với phần tóm
            # tắt phát ra ngay sau đó. Giữ lại cho file nhật ký vì nó ghi
            # THỜI ĐIỂM BẮT ĐẦU từng tool — cần khi một tool chạy chậm bất
            # thường và muốn biết nó ngốn bao lâu.
            #
            # Không ghi args ở đây: chúng đến từ câu người dùng gõ. Phần tóm
            # tắt có ghi tiêu chí nhưng đã lọc trường riêng tư.
            logger.debug("Bắt đầu tool %s", tool.name)
            ran.append(tool.name)
            # Giữ lại tiêu chí đã dùng để tầng trên đồng bộ bộ lọc trên trang
            # tìm kiếm — người dùng hỏi "căn 2-3 tỷ" thì danh sách bên ngoài
            # cũng phải hiện đúng khoảng đó, không để hai bên nói hai kiểu.
            tieu_chi.setdefault(tool.name, args)
            result = await tool.run(**args)

            if not result.ok:
                logger.warning("Tool %s lỗi: %s", tool.name, result.error)
                continue
            if not result.data:
                logger.info("Tool %s không tìm thấy dữ liệu khớp", tool.name)
                continue

            # Tra xong mà không căn nào khớp là một KẾT LUẬN, và tầng gợi ý phải
            # biết để không mời người dùng bấm vào đúng ngõ cụt đó. Đã xảy ra
            # thật: hỏi "2 phòng ngủ 3 vệ sinh ở Ocean Park 1" (kho không có căn
            # 3 vệ sinh nào) và nút gợi ý là "So sánh các căn 2PN, 3 vệ sinh ở
            # Ocean Park 1".
            if isinstance(result.data, dict) and result.data.get("tong_so_khop") == 0:
                rong.append(args)

            blocks.append(_format(tool, result))
            citations.extend(_nguon_cua_tool(tool, result))

        if not blocks:
            # Vẫn báo tool nào đã chạy dù không ra dữ liệu — stream cần biết để
            # nói "đã tra nhưng không thấy", khác hẳn với "chưa tra gì".
            return {**_EMPTY, "tools_ran": ran, "tool_filters": tieu_chi, "tieu_chi_rong": rong}

        # Không trả "metadata" ở đây: BaseNode dùng setdefault để gắn thời gian
        # chạy, trả sẵn khoá đó là nuốt mất số đo của mọi node.
        return {
            "tool_context": "\n\n".join(blocks),
            "tool_citations": citations,
            "tools_ran": ran,
            "tool_filters": tieu_chi,
            "tieu_chi_rong": rong,
        }

    def tom_tat(self, result: dict[str, Any]) -> str:
        """Tool nào chạy, với tiêu chí gì, có ra dữ liệu không.

        CÓ ghi tiêu chí, khác chú thích ở `execute` vốn cấm ghi `args`. Lý do
        nới: `tool_filters` vốn đã được gửi thẳng ra frontend qua `data.filters`
        để đồng bộ bộ lọc, nên nó không phải bí mật. Thứ THẬT SỰ nhạy cảm là tên
        và số điện thoại khách trong `dat_coc` — chúng bị loại theo tên trường.
        """
        ran = result.get("tools_ran") or []
        if not ran:
            return "không tool nào nhận câu này"

        loc = result.get("tool_filters") or {}
        mo_ta = " · ".join(f"{ten}({_tieu_chi_an_toan(loc.get(ten, {}))})" for ten in ran)
        return f"{mo_ta} → {'có dữ liệu' if result.get('tool_context') else 'KHÔNG khớp gì'}"
