"""Chạy toàn bộ luồng cào tài liệu chính sách theo `Link_data.xlsx`.

    python -m src.data.crawl_policy crawl     # Excel -> .docx  (rồi NGƯỜI duyệt)
    python -m src.data.crawl_policy convert   # .docx đã duyệt -> .md
    python -m src.data.crawl_policy preview   # .md -> báo cáo chunk, chưa nạp

Tách các lệnh có chủ đích: giữa crawl và convert là chỗ người đọc và sửa nội
dung; `preview` cho xem đúng những gì sắp vào Qdrant trước khi nạp. Gộp lại là
mất luôn chốt kiểm soát đó.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
from pathlib import Path

from src.core.logging import get_logger, setup_logging
from src.data.crawling.docx_io import THU_MUC_DOCX, THU_MUC_MD, docx_sang_md, ghi_docx
from src.data.crawling.vinhomes_market import tai_trang, trich_xuat
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.pipeline import _van_ban_nhung
from src.data.sources.knowledge_docs import load_knowledge_dir
from src.data.sources.link_plan import doc_ke_hoach

logger = get_logger(__name__)

FILE_PREVIEW = Path("data") / "raw" / "preview_chunks.md"


async def crawl() -> int:
    """Cào theo kế hoạch trong Excel, ghi ra .docx cho người duyệt."""
    ke_hoach = doc_ke_hoach()
    print(f"Kế hoạch: {len(ke_hoach)} tài liệu\n")

    html_da_tai: dict[str, str] = {}
    hut: list[str] = []

    for tai_lieu in ke_hoach:
        if not tai_lieu.can_crawl:
            # Nội dung đã điền sẵn trong Excel — đóng gói lại, không cào.
            ghi_docx(
                tieu_de=tai_lieu.ten,
                noi_dung=tai_lieu.noi_dung_co_san,
                url=tai_lieu.link,
                khu_vuc=tai_lieu.khu_vuc,
                thieu=[],
            )
            print(f"  [SẴN] {tai_lieu.ten}")
            continue

        if tai_lieu.link not in html_da_tai:
            try:
                html_da_tai[tai_lieu.link] = await tai_trang(tai_lieu.link)
            except Exception as exc:  # noqa: BLE001 - một link hỏng không chặn cả mẻ
                print(f"  [LỖI] {tai_lieu.ten}: {exc}")
                hut.append(tai_lieu.ten)
                continue

        ket_qua = trich_xuat(
            html_da_tai[tai_lieu.link],
            tieu_de=tai_lieu.ten,
            url=tai_lieu.link,
            muc_can_lay=tai_lieu.muc_can_lay,
        )
        if not ket_qua.co_noi_dung:
            print(f"  [HỤT] {tai_lieu.ten} — không lấy được nội dung nào")
            hut.append(tai_lieu.ten)
            continue

        ghi_docx(
            tieu_de=tai_lieu.ten,
            noi_dung=ket_qua.thanh_van_ban(),
            url=tai_lieu.link,
            khu_vuc=tai_lieu.khu_vuc,
            thieu=ket_qua.thieu,
        )
        canh_bao = f"  ⚠ thiếu: {', '.join(ket_qua.thieu)}" if ket_qua.thieu else ""
        print(f"  [OK]  {tai_lieu.ten}{canh_bao}")

    print(f"\n.docx nằm ở: {THU_MUC_DOCX}")
    print("Đọc và sửa nội dung, xong chạy: python -m src.data.crawl_policy convert")
    if hut:
        print(f"\nCẦN XỬ LÝ TAY {len(hut)} tài liệu: {', '.join(hut)}")
    return 0


def convert() -> int:
    """Đổi .docx đã duyệt thành .md có front-matter."""
    files = sorted(THU_MUC_DOCX.glob("*.docx"))
    if not files:
        print(f"Không có .docx nào trong {THU_MUC_DOCX}. Chạy 'crawl' trước.")
        return 1

    # section lấy từ Excel để trích nguồn hiện đúng nhóm thông tin.
    ke_hoach = doc_ke_hoach()
    section_theo_ten = {t.ten: (t.khu_vuc or t.ten) for t in ke_hoach}

    # Đổi tên một dòng trong Excel là file .docx cũ thành mồ côi. Nó vẫn nằm đó,
    # vẫn được chuyển sang .md, vẫn bị nạp vào Qdrant — và trợ lý trả lời bằng
    # nội dung của một tài liệu không còn trong kế hoạch. Báo để người dùng xoá.
    # Soát CẢ .docx lẫn .md: đổi tên một dòng Excel để lại bản cũ ở cả hai
    # thư mục. Bản .md mới là thứ đi thẳng vào Qdrant nên bỏ sót nó nguy hiểm
    # hơn — hai phiên bản cùng một chính sách, trợ lý trích bản nào cũng được.
    mo_coi = sorted(
        {
            p.stem
            for p in [*files, *THU_MUC_MD.glob("*.md")]
            if not p.name.startswith("~$") and p.stem not in section_theo_ten
        }
    )
    if mo_coi:
        print("CẢNH BÁO — .docx không còn trong Link_data.xlsx (có thể do đổi tên):")
        for ten in mo_coi:
            print(f"  · {ten}")
        print("  Xoá chúng đi, nếu không nội dung cũ vẫn bị nạp vào Qdrant.\n")

    for path in files:
        # Bỏ file tạm Word (~$ten.docx) — mở Word mà chưa đóng là có.
        if path.name.startswith("~$"):
            continue
        docx_sang_md(path, section=section_theo_ten.get(path.stem, ""))
        print(f"  {path.stem}")

    print(f"\n.md nằm ở: {THU_MUC_MD}")
    print("Nạp vào Qdrant: python -m src.cli ingest knowledge")
    return 0


def preview() -> int:
    """Ghi ra file đúng nội dung từng chunk sắp được nạp vào Qdrant.

    Đọc trên terminal thì tiếng Việt vỡ font và cuộn mất phần đầu; ghi ra .md
    để mở bằng editor, soát được cả nội dung lẫn chỗ chunk bị cắt.
    """
    tai_lieu = sorted(load_knowledge_dir(), key=lambda d: d.title)
    if not tai_lieu:
        print(f"Không có .md nào trong {THU_MUC_MD}. Chạy 'convert' trước.")
        return 1

    chunker = ParagraphChunker()
    dong = ["# Xem trước chunk sắp nạp vào Qdrant", ""]
    tong: list[int] = []

    for doc in tai_lieu:
        chunks = chunker.split(doc)
        tong.extend(len(c.text) for c in chunks)
        meta = doc.metadata
        dong += [
            f"## {doc.title}",
            "",
            f"- `doc_id` **{doc.doc_id}**",
            f"- `doc_kind` **{meta.get('doc_kind')}** · `visibility` {meta.get('visibility')}"
            f" · `version` {meta.get('version')}",
            f"- `section` {meta.get('section')!r} · `project` {meta.get('project')!r}",
            f"- nguồn: {meta.get('source_url') or '(trống)'}",
            f"- **{len(doc.text)} ký tự → {len(chunks)} chunk**",
            "",
        ]
        for chunk in chunks:
            thu_tu = chunk.id.split("::")[-1]
            dong += [
                f"### chunk {thu_tu} · {len(chunk.text)} ký tự",
                "",
                "```",
                chunk.text,
                "```",
                "",
                "<sub>văn bản đem nhúng (tiêu đề + mục ghép vào đầu):</sub>",
                "",
                "```",
                _van_ban_nhung(doc, chunk)[:200] + " …",
                "```",
                "",
            ]

    dong[1:1] = [
        "",
        f"{len(tai_lieu)} tài liệu · **{len(tong)} chunk** · "
        f"nhỏ nhất {min(tong)} · trung vị {int(statistics.median(tong))} · lớn nhất {max(tong)} ký tự",
        "",
        "Mỗi chunk dưới đây là một điểm trong Qdrant. Soát xem có chunk nào là "
        "chân trang, menu, hay nội dung của dự án khác không.",
    ]

    FILE_PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    FILE_PREVIEW.write_text("\n".join(dong), encoding="utf-8")
    print(f"Đã ghi: {FILE_PREVIEW.resolve()}")
    print(f"  {len(tai_lieu)} tài liệu → {len(tong)} chunk")
    return 0


def main() -> int:
    setup_logging("WARNING")  # giữ output gọn, chỉ hiện tiến trình
    lenh = sys.argv[1] if len(sys.argv) > 1 else ""
    if lenh == "crawl":
        return asyncio.run(crawl())
    if lenh == "convert":
        return convert()
    if lenh == "preview":
        return preview()
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
