"""Đo QUYẾT ĐỊNH trả lời hay từ chối, trên bộ câu hỏi đối kháng.

Khác `retrieval.py`: file kia chỉ đo tầng truy hồi (embed → search → rerank) và
KHÔNG gọi LLM, nên đổi prompt xong chạy nó thì con số không nhúc nhích. Ở đây đo
đúng thứ prompt quyết định — cầm tài liệu rồi thì trả lời hay im.

Bộ câu hỏi cố ý KHÔNG có happy case. Mỗi câu là một cái bẫy, và bẫy theo hai
hướng ngược nhau:

- `phai_tra_loi` — tài liệu CÓ, nhưng cách hỏi lệch cách viết. Bẫy từ chối oan.
- `phai_tu_choi` — tài liệu KHÔNG có, nhưng chủ đề gần giống. Bẫy bịa.
- `tra_loi_mot_phan` — nửa có nửa không. Sai cả hai phía đều bị bắt.
- `ngoai_pham_vi` — ngoài hẳn Ocean Park.

Chấm cả DÒNG NGUỒN, không chỉ câu chữ. Câu khai `nguon_phai_rong` (tuỳ chọn) đòi
lượt đó không được trưng nguồn nào — sinh ra từ ca VOP9999: trợ lý từ chối hoàn
hảo mà dưới đó vẫn liệt kê ba tài liệu không liên quan, và sale đọc xong tưởng
chúng nói về căn vừa hỏi. Đo mỗi câu chữ thì lỗi ấy không bao giờ hiện ra số.

Chấm bằng luật tất định, KHÔNG dùng LLM làm giám khảo: giám khảo model thêm một
nguồn nhiễu nữa vào đúng thứ đang muốn đo, tốn tiền gấp đôi, và bản thân nó cũng
cần được kiểm chứng. Câu hỏi ở đây — "từ chối hay trả lời, có bịa số không" —
trả lời được bằng luật khách quan.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import LLMProvider
from src.agents.graph import CONTEXT_NODES, build_nodes
from src.agents.nguon import _khong_dau, la_loi_tu_choi, loc_nguon_da_dung
from src.agents.nodes.generate import build_messages
from src.agents.prompts import load_prompt
from src.agents.state import initial_state
from src.bootstrap import configure
from src.core.config import Settings
from src.core.container import container
from src.core.exceptions import ConfigurationError
from src.core.gia_model import chi_phi_usd
from src.core.logging import get_logger
from src.models.chat import ChatMessage, MessageRole
from src.rag.contracts import Retriever

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "eval" / "answer_dataset.json"
RESULT_DIR = ROOT / "eval" / "results"

# Loại nào thì câu trả lời PHẢI là một lời từ chối.
_PHAI_TU_CHOI = {"phai_tu_choi", "ngoai_pham_vi"}
_PHAI_TRA_LOI = {"phai_tra_loi", "tra_loi_mot_phan"}


class KetQuaCau(BaseModel):
    id: str
    loai: str
    cau_hoi: str
    cau_tra_loi: str = ""
    dat: bool = False
    ly_do_truot: str = ""
    da_tu_choi: bool = False
    # Dòng "Nguồn" mà người dùng THẬT SỰ nhìn thấy — đã qua `loc_nguon_da_dung`,
    # không phải danh sách thô của truy hồi. Rỗng mặc định nên file kết quả cũ
    # vẫn đọc lại được.
    nguon: list[str] = Field(default_factory=list)


class TongKet(BaseModel):
    prompt_version: str
    # Nhãn của LẦN CHẠY, khác phiên bản prompt. Cần tách hai thứ vì từ nay còn
    # đổi cả model chứ không riêng prompt: hai lần chạy cùng prompt v7 mà khác
    # model sẽ ghi đè lên nhau nếu vẫn đặt tên file theo prompt_version.
    nhan: str = ""
    model_answer: str = ""
    model_fast: str = ""
    token_vao: int = 0
    token_ra: int = 0
    chi_phi_usd: float | None = None
    tong_so: int = 0
    so_dat: int = 0
    theo_loai: dict[str, list[int]] = Field(default_factory=dict)  # loai -> [dat, tong]
    cau: list[KetQuaCau] = Field(default_factory=list)

    @property
    def ten(self) -> str:
        """Tên đem hiển thị: ưu tiên nhãn, không có thì rơi về phiên bản prompt."""
        return self.nhan or self.prompt_version

    def ghi_nhan(self, kq: KetQuaCau) -> None:
        self.cau.append(kq)
        self.tong_so += 1
        self.so_dat += int(kq.dat)
        muc = self.theo_loai.setdefault(kq.loai, [0, 0])
        muc[0] += int(kq.dat)
        muc[1] += 1

    def dong_cau_hinh(self) -> str:
        """Một dòng nói rõ con số vừa đo ra từ cấu hình nào.

        Thiếu dòng này thì hai file kết quả trông giống hệt nhau, và sau vài
        ngày không ai nhớ nổi cái nào chạy model gì.
        """
        phan = [f"prompt {self.prompt_version}"]
        if self.model_answer:
            phan.append(f"answer={self.model_answer}")
        if self.model_fast:
            phan.append(f"fast={self.model_fast}")
        if self.token_vao or self.token_ra:
            phan.append(f"token {self.token_vao}→{self.token_ra}")
        if self.chi_phi_usd is not None:
            phan.append(f"${self.chi_phi_usd:.4f}")
        return " · ".join(phan)

    def bang(self) -> str:
        dong = [
            f"[{self.ten}] {self.so_dat}/{self.tong_so} đạt",
            f"  {self.dong_cau_hinh()}",
            "",
        ]
        for loai, (dat, tong) in sorted(self.theo_loai.items()):
            dong.append(f"  {loai:<24} {dat}/{tong}")
        truot = [c for c in self.cau if not c.dat]
        if truot:
            dong.append("")
            dong.append("TRƯỢT:")
            dong += [f"  {c.id}  {c.ly_do_truot}" for c in truot]
        return "\n".join(dong)


def cham(case: dict[str, Any], cau_tra_loi: str, nguon: list[str] | None = None) -> KetQuaCau:
    """Chấm một câu. Thuần, không I/O — đây là phần test được mà không tốn tiền.

    Dùng lại `la_loi_tu_choi` của `src/agents/nguon.py`, chính hàm ĐANG CHẠY THẬT
    lúc runtime để quyết định có hiện nguồn hay không. Viết bộ dò thứ hai ở đây
    là mở đường cho eval và sản phẩm hiểu "từ chối" theo hai kiểu khác nhau.

    `nguon` là dòng "Nguồn" người dùng thật sự nhìn thấy. Chấm cả nó vì câu trả
    lời đúng vẫn hỏng nếu phần nguồn sai: ca VOP9999 từ chối hoàn hảo mà dưới đó
    liệt kê ba tài liệu không liên quan, và sale đọc xong tưởng chúng nói về căn
    đó. Câu khai `nguon_phai_rong` là câu bắt đúng chuyện này.

    Tuỳ chọn, mặc định `None` = không kiểm — bộ chấm vẫn gọi được từ test thuần
    mà không phải dựng cả pipeline truy hồi.
    """
    kq = KetQuaCau(
        id=case["id"],
        loai=case["loai"],
        cau_hoi=case["cau_hoi"],
        cau_tra_loi=cau_tra_loi,
        da_tu_choi=la_loi_tu_choi(cau_tra_loi),
        nguon=list(nguon or []),
    )
    sach = _khong_dau(cau_tra_loi)

    if kq.loai in _PHAI_TU_CHOI and not kq.da_tu_choi:
        kq.ly_do_truot = "phải từ chối nhưng đã trả lời"
    elif kq.loai in _PHAI_TRA_LOI and kq.da_tu_choi:
        kq.ly_do_truot = "có dữ liệu mà vẫn từ chối"
    else:
        thieu = [c for c in case.get("phai_neu", []) if _khong_dau(c) not in sach]
        cam = [c for c in case.get("khong_duoc_neu", []) if _khong_dau(c) in sach]
        if thieu:
            kq.ly_do_truot = f"thiếu dữ kiện bắt buộc: {', '.join(thieu)}"
        elif cam:
            kq.ly_do_truot = f"nêu thứ không có trong tài liệu: {', '.join(cam)}"
        elif case.get("nguon_phai_rong") and kq.nguon:
            kq.ly_do_truot = f"trưng nguồn không liên quan: {', '.join(kq.nguon)}"

    kq.dat = not kq.ly_do_truot
    return kq


def _doc_lich_su(case: dict[str, Any]) -> list[ChatMessage]:
    """Dựng lịch sử hội thoại của một câu, nếu bộ dữ liệu có khai.

    Vì sao cần: `build_args` của tool chỉ đọc câu HIỆN TẠI, nên câu tham chiếu
    ngữ cảnh ("liệt kê 20 căn đó") không tool nào nhận. Muốn đo được việc router
    giải tham chiếu bằng lịch sử thì bộ câu hỏi phải chở được lịch sử đã.

    Trường `lich_su` là TUỲ CHỌN — 20 câu cũ không có nó và vẫn chạy y như trước.
    """
    tho = case.get("lich_su") or []
    return [ChatMessage(role=MessageRole(m["role"]), content=m["content"]) for m in tho]


async def _tra_loi_mot_cau(
    cau_hoi: str,
    prompt: str,
    settings: Settings,
    nodes: dict[str, Any],
    llm: LLMProvider,
    lich_su: list[ChatMessage] | None = None,
) -> tuple[str, list[str]]:
    """Chạy đúng đường sản phẩm: router → tools → retrieve → prompt → model.

    Trả về cả câu trả lời lẫn dòng "Nguồn" đã lọc, vì phần nguồn cũng là thứ
    người dùng nhìn thấy và cũng sai được một cách độc lập với câu chữ.

    Cố ý KHÔNG ép `needs_retrieval`: để router tự quyết đúng như lúc chạy thật.
    Ép bật sẽ che mất một lớp hành vi có thật — câu ngoài phạm vi bị xếp nhãn
    `general` thì vốn không truy hồi gì, và việc model có bịa từ kiến thức nền
    khi ngữ cảnh RỖNG hay không chính là thứ nhóm `ngoai_pham_vi` cần đo.

    Dùng `CONTEXT_NODES` thay vì liệt kê tay ba node: đó là bài học đã ghi trong
    `graph.py` — có lần liệt kê tay rồi thêm node `tools` mà quên cập nhật, cả
    một đường đi lặng lẽ bỏ qua tool.
    """
    state = initial_state(cau_hoi, "eval", lich_su)
    for ten in CONTEXT_NODES:
        # `.get` chứ không `[]`: node `orchestrate` chỉ tồn tại khi bật cờ.
        node = nodes.get(ten)
        if node is not None:
            state.update(await node(state))

    tra_loi = await llm.complete(
        build_messages(state, system=prompt),
        model=settings.llm_model_answer,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    tra_loi = tra_loi.strip()

    # Gộp hai đường sinh nguồn rồi lọc bằng CHÍNH hàm chạy thật lúc runtime —
    # cùng lý do bộ chấm dùng lại `la_loi_tu_choi`. Dựng bộ lọc thứ hai ở đây là
    # đo một sản phẩm khác với sản phẩm đang chạy.
    citations = [*state.get("citations", []), *state.get("tool_citations", [])]
    nguon = loc_nguon_da_dung(citations, tra_loi, co_du_lieu_tool=bool(state.get("tool_context")))
    return tra_loi, [c.title for c in nguon]


def duong_dan_ket_qua(nhan: str) -> Path:
    return RESULT_DIR / f"answer_eval_{nhan}.json"


def doc_ket_qua(nhan: str) -> TongKet:
    """Đọc lại một lần chạy đã ghi ra file.

    Nhờ có hàm này mà `--doi-chieu` so được hai lần chạy khác CẤU HÌNH MODEL,
    chuyện `--compare` cũ không làm được: nó chạy cả hai bản trong cùng một tiến
    trình, mà model thì lấy từ `Settings` — một tiến trình chỉ có một cấu hình.
    """
    duong_dan = duong_dan_ket_qua(nhan)
    if not duong_dan.exists():
        raise ConfigurationError(
            f"Chưa có kết quả nhãn '{nhan}'. Chạy trước: python -m src.cli eval answer --label {nhan}"
        )
    return TongKet.model_validate_json(duong_dan.read_text(encoding="utf-8"))


def _tinh_chi_phi(so_do: Any) -> tuple[int, int, float | None]:
    """Cộng token và quy ra USD. Một model thiếu giá là cả lượt không có số."""
    if so_do is None:
        return 0, 0, None

    tong = 0.0
    biet_gia = True
    for model, (vao, ra) in so_do.theo_model.items():
        phan = chi_phi_usd(model, token_vao=vao, token_ra=ra)
        if phan is None:
            biet_gia = False
            continue
        tong += phan
    return so_do.vao, so_do.ra, (tong if biet_gia else None)


async def run_answer_eval(prompt_version: str, *, nhan: str | None = None) -> TongKet:
    """Chạy toàn bộ bộ câu hỏi với một phiên bản prompt, ghi kết quả ra file."""
    configure()
    settings = container.resolve(Settings)

    if not settings.has_openai_key:
        raise ConfigurationError("Eval câu trả lời cần OPENAI_API_KEY — nó gọi model thật.")
    if not DATASET_PATH.exists():
        raise ConfigurationError(f"Không tìm thấy bộ câu hỏi: {DATASET_PATH}")

    prompt = load_prompt(f"system_{prompt_version}")
    bo_cau = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    tong_ket = TongKet(
        prompt_version=prompt_version,
        nhan=nhan or prompt_version,
        model_answer=settings.llm_model_answer,
        model_fast=settings.llm_model_fast,
    )

    # Dựng node MỘT lần: chúng không giữ trạng thái giữa các câu, dựng lại mỗi
    # câu chỉ tốn thời gian và tạo thêm client thừa.
    llm = container.resolve(LLMProvider)
    nodes = build_nodes(llm, container.resolve(Retriever), settings)

    # Bộ đếm là chi tiết cài đặt của OpenAIProvider, không nằm trong Protocol —
    # dò mềm để provider giả lập trong test vẫn chạy qua đây được.
    so_do = getattr(llm, "so_do_token", None)
    if so_do is not None:
        so_do.dat_lai()

    for case in bo_cau:
        try:
            tra_loi, nguon = await _tra_loi_mot_cau(case["cau_hoi"], prompt, settings, nodes, llm, _doc_lich_su(case))
        except Exception as exc:  # noqa: BLE001 - một câu hỏng không được dừng cả lượt đo
            logger.warning("Câu %s lỗi: %s", case["id"], exc)
            tra_loi, nguon = "", []
        kq = cham(case, tra_loi, nguon)
        tong_ket.ghi_nhan(kq)
        logger.info("[%s] %s %s", "OK  " if kq.dat else "MISS", case["id"], kq.ly_do_truot)

    tong_ket.token_vao, tong_ket.token_ra, tong_ket.chi_phi_usd = _tinh_chi_phi(so_do)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    duong_dan = duong_dan_ket_qua(tong_ket.nhan)
    duong_dan.write_text(tong_ket.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Chi tiết: %s", duong_dan)
    return tong_ket


def so_sanh(truoc: TongKet, sau: TongKet) -> str:
    """Bảng trước/sau, nêu rõ câu nào đổi chiều.

    Cột `phai_tu_choi` là cột phanh: nó KHÔNG ĐƯỢC giảm. Tăng `phai_tra_loi` mà
    đánh đổi bằng `phai_tu_choi` là đổi lỗi từ chối oan lấy lỗi bịa — nặng hơn
    hẳn, vì khách không có cách nào biết trợ lý đang bịa.
    """
    a_ten, b_ten = truoc.ten[:12], sau.ten[:12]
    dong = [
        f"TRƯỚC  {truoc.ten}: {truoc.dong_cau_hinh()}",
        f"SAU    {sau.ten}: {sau.dong_cau_hinh()}",
        "",
        f"{'Loại':<24} {a_ten:>12} {b_ten:>12} {'Đổi':>6}",
        "-" * 58,
    ]
    for loai in sorted(set(truoc.theo_loai) | set(sau.theo_loai)):
        a_dat, a_tong = truoc.theo_loai.get(loai, [0, 0])
        b_dat, b_tong = sau.theo_loai.get(loai, [0, 0])
        chenh = b_dat - a_dat
        canh_bao = "  ⚠ nới quá tay" if chenh < 0 and loai in _PHAI_TU_CHOI else ""
        dong.append(f"{loai:<24} {f'{a_dat}/{a_tong}':>12} {f'{b_dat}/{b_tong}':>12} {chenh:>+6}{canh_bao}")
    dong.append("-" * 58)
    dong.append(f"{'TỔNG':<24} {f'{truoc.so_dat}/{truoc.tong_so}':>12} {f'{sau.so_dat}/{sau.tong_so}':>12}")

    cu = {c.id: c for c in truoc.cau}
    doi_chieu = [(cu[c.id], c) for c in sau.cau if c.id in cu and cu[c.id].dat != c.dat]
    if doi_chieu:
        dong += ["", "CÂU ĐỔI CHIỀU:"]
        for a, b in doi_chieu:
            mui_ten = "MISS -> OK  " if b.dat else "OK   -> MISS"
            dong.append(f"  {b.id}  {mui_ten}  {b.cau_hoi[:44]}")
            if not b.dat:
                dong.append(f"          vì: {b.ly_do_truot}")
    return "\n".join(dong)
