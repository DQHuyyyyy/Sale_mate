"""Script tải, lưu trữ và tìm kiếm RAG Nâng cao: Căn hộ + Ảnh + Khớp Chính sách bán hàng (Sales Policies).

Google Sheet: https://docs.google.com/spreadsheets/d/1IcXuR7dMN6Q0pxU39xXsbIsislaIECzxMZ3LuUCocAI/edit?usp=sharing

Chạy lệnh:
    .venv\\Scripts\\python.exe scripts/ingest_real_data.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import urllib.request

# Đảm bảo in ra được tiếng Việt trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm thư mục gốc dự án vào sys.path để import src
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.data.contracts import Chunk, RetrievalFilter
from src.data.ingestion.embedders import FakeEmbedder
from src.data.retrieval.rerankers import CrossEncoderReranker, FakeCrossEncoderReranker, PassthroughReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.memory_store import InMemoryVectorStore

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1IcXuR7dMN6Q0pxU39xXsbIsislaIECzxMZ3LuUCocAI/export?format=csv"
)

# Thư mục lưu dữ liệu cục bộ
DATA_DIR = ROOT_DIR / "data"
LOCAL_JSON_PATH = DATA_DIR / "vop_listings.json"


def parse_price(price_str: str) -> float | None:
    """Chuyển đổi chuỗi giá ('3,1 tỷ', '2,650 tỷ', '4 tỷ', '3,55') thành số float (tỷ VNĐ)."""
    if not price_str:
        return None
    cleaned = price_str.lower().replace("tỷ", "").replace("ty", "").strip()
    cleaned = cleaned.replace(",", ".")
    try:
        val = float(cleaned)
        if val > 100:  # Nếu dạng 2650 (triệu) -> 2.65 tỷ
            val = val / 1000.0
        return val
    except ValueError:
        return None


def parse_area(area_str: str) -> float | None:
    """Chuyển đổi diện tích ('49m2', '34.7m2', '63,7m2') thành float."""
    if not area_str:
        return None
    cleaned = area_str.lower().replace("m2", "").strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_bedrooms(type_str: str) -> int:
    """Trích xuất số phòng ngủ từ '1 PN, 1WC', 'Studio', '3 PN, 2WC'."""
    if not type_str:
        return 1
    type_upper = type_str.upper()
    if "STUDIO" in type_upper:
        return 1
    match = re.search(r"(\d+)\s*PN", type_upper)
    if match:
        return int(match.group(1))
    return 1


def build_sales_policies() -> list[Chunk]:
    """Khởi tạo danh sách các tài liệu Chính sách Bán hàng & Ưu đãi."""
    policies = [
        Chunk(
            id="POL-001",
            text="Chính sách Chiết khấu Thanh toán sớm: Chiết khấu trực tiếp 8% vào hợp đồng khi thanh toán đủ 95% giá trị căn hộ trong 15 ngày.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Thanh toán & Chiết khấu 2026",
            metadata={
                "doc_kind": "policy",
                "policy_code": "DISCOUNT_8PCT",
                "discount_pct": 8.0,
                "title": "Chiết khấu 8% thanh toán sớm",
            },
        ),
        Chunk(
            id="POL-002",
            text="Chính sách Hỗ trợ Lãi suất Ngân hàng: Ngân hàng hỗ trợ vay 70% giá trị căn hộ, Lãi suất 0% và ân hạn nợ gốc trong 24 tháng.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Hỗ trợ Vay Ngân hàng",
            metadata={
                "doc_kind": "policy",
                "policy_code": "LOAN_0PCT_24M",
                "title": "Vay ngân hàng 70%, 0% lãi suất trong 24 tháng",
            },
        ),
        Chunk(
            id="POL-003",
            text="Chính sách Quà tặng Tân gia VinFast: Tặng Voucher xe điện VinFast trị giá 70 triệu (cho Studio/1PN), 150 triệu (cho 2PN), 200 triệu (cho 3PN).",
            doc_id="DOC-POL-02",
            doc_title="Chương trình Quà tặng Mua nhà",
            metadata={
                "doc_kind": "policy",
                "policy_code": "VOUCHER_VINFAST",
                "title": "Tặng Voucher xe VinFast 70 - 200 triệu",
            },
        ),
        Chunk(
            id="POL-004",
            text="Chính sách Sổ đỏ & Pháp lý: 100% căn hộ bảng hàng có sẵn Sổ đỏ/Sổ hồng chính chủ, hỗ trợ công chứng sang tên ngay trong 7 ngày làm việc.",
            doc_id="DOC-POL-03",
            doc_title="Cam kết Pháp lý & Sang tên Sổ đỏ",
            metadata={
                "doc_kind": "policy",
                "policy_code": "LEGAL_TITLE_DEED",
                "title": "Sẵn Sổ đỏ, sang tên ngay trong 7 ngày",
            },
        ),
    ]
    return policies


def fetch_and_save_data() -> list[Chunk]:
    """Tải dữ liệu từ Google Sheets, thêm Ảnh + Chính sách, lưu xuống JSON và trả về Chunks."""
    print("[+] Dang tai du lieu tu Google Sheets...")
    req = urllib.request.Request(
        SHEET_CSV_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8")

    reader = csv.DictReader(io.StringIO(content))
    chunks: list[Chunk] = []
    raw_records: list[dict[str, Any]] = []

    for idx, row in enumerate(reader, 1):
        ma_can = row.get("Mã Căn \n(VOP)", "").strip() or f"VOP-{idx}"
        toa = row.get("Tòa ", "").strip() or row.get("Tòa", "").strip()
        tang = row.get("Tầng", "").strip()
        so_phong = row.get("Số phòng", "").strip()
        loai_can = row.get("Loại căn\n(PN, WC) Studio", "").strip() or row.get("Loại căn", "").strip()
        dien_tich_raw = row.get("Diện tích", "").strip()
        huong = row.get("Hướng phong thủy", "").strip()
        view = row.get("View", "").strip()
        so_do = row.get("Số đỏ", "").strip()
        gia_raw = row.get("Giá", "").strip()
        noi_that = row.get("Nội thất", "").strip()
        tinh_trang = row.get("Tình trạng (Còn/Hết)", "").strip()
        anh_raw = row.get("Ảnh", "").strip()

        # Tạo link ảnh đẹp cho căn hộ
        image_url = f"https://img.salesmate.vn/vop/{toa.lower()}_{so_phong}.jpg" if toa and so_phong else anh_raw

        price = parse_price(gia_raw)
        area = parse_area(dien_tich_raw)
        num_bedrooms = parse_bedrooms(loai_can)

        text_pieces = [
            f"Ma can: {ma_can}, Toa {toa}, Tang {tang}, Can {so_phong}.",
            f"Loai can: {loai_can}, Dien tich: {dien_tich_raw}.",
            f"Huong: {huong}, View: {view}.",
            f"Gia: {gia_raw}, So do: {so_do}, Noi that: {noi_that}.",
            f"Tinh trang: {tinh_trang}.",
        ]
        text_content = " ".join(p for p in text_pieces if p)

        metadata: dict[str, Any] = {
            "doc_kind": "listing",
            "ma_can": ma_can,
            "building": toa,
            "tang": tang,
            "so_phong": so_phong,
            "property_type": loai_can,
            "num_bedrooms": num_bedrooms,
            "price": price,
            "area": area,
            "huong": huong,
            "view": view,
            "so_do": so_do,
            "noi_that": noi_that,
            "tinh_trang": tinh_trang,
            "image_url": image_url,
        }

        chunk = Chunk(
            id=ma_can,
            text=text_content,
            doc_id="GOOGLE_SHEET_VOP",
            doc_title="Bang hang Vinhomes Ocean Park Real Data",
            metadata=metadata,
        )
        chunks.append(chunk)

        record = {
            "id": ma_can,
            "text": text_content,
            "metadata": metadata,
        }
        raw_records.append(record)

    # Nạp thêm các Chunks Chính sách Bán hàng
    policy_chunks = build_sales_policies()
    chunks.extend(policy_chunks)

    # Ghi ra file JSON cục bộ
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_records, f, ensure_ascii=False, indent=2)

    print(f"[+] Da tai va parse thanh cong {len(chunks) - len(policy_chunks)} can ho + {len(policy_chunks)} chinh sach ban hang.")
    print(f"[+] LU U TRU: Da luu file du lieu cuc bo tai -> {LOCAL_JSON_PATH.resolve()}\n")
    return chunks


async def interactive_loop(retriever: DefaultRetriever) -> None:
    """Chế độ nhập tìm kiếm tương tác kép (Lookup Căn hộ + Khớp Chính sách & Ảnh)."""
    print("=" * 70)
    print("🤖 CHẾ ĐỘ TÌM KIẾM KẾT HỢP: CAN HỘ + ANH + KHỚP CHÍNH SÁCH BÁN HÀNG")
    print("=" * 70)
    print("Gõ 'exit' hoặc 'q' để thoát.\n")

    while True:
        try:
            query = input("\n👉 Nhập từ khóa / yêu cầu (VD: 'view biển hồ biệt thự'): ").strip()
            if not query or query.lower() in ("exit", "q", "quit"):
                print("Chương trình kết thúc.")
                break

            price_min_raw = input("   Giá tối thiểu (tỷ VNĐ, bấm Enter bỏ qua): ").strip()
            price_max_raw = input("   Giá tối đa (tỷ VNĐ, bấm Enter bỏ qua): ").strip()
            bedrooms_raw = input("   Số phòng ngủ (1/2/3, bấm Enter bỏ qua): ").strip()
            building_raw = input("   Tòa (VD: S2, S109, R103, bấm Enter bỏ qua): ").strip()

            min_price = float(price_min_raw) if price_min_raw else None
            max_price = float(price_max_raw) if price_max_raw else None
            num_bedrooms = int(bedrooms_raw) if bedrooms_raw else None
            building = building_raw if building_raw else None

            # 1. Retrieval 1: Tìm kiếm căn hộ (doc_kind="listing")
            filters_listing = RetrievalFilter(
                doc_kind="listing",
                min_price=min_price,
                max_price=max_price,
                num_bedrooms=num_bedrooms,
                building=building,
            )
            res_listing = await retriever.retrieve(query, filters=filters_listing, top_k=12, top_n=3)

            # 2. Retrieval 2: Tìm kiếm các chính sách bán hàng liên quan (doc_kind="policy")
            filters_policy = RetrievalFilter(doc_kind="policy")
            res_policy = await retriever.retrieve(query, filters=filters_policy, top_k=10, top_n=3)

            print("\n" + "-" * 70)
            print(f"🔍 Đang truy vấn: '{query}'")
            print(f"📋 Điều kiện lọc: Giá=[{min_price or 0} - {max_price or '∞'} tỷ], Phòng={num_bedrooms or 'Tất cả'}, Tòa={building or 'Tất cả'}")
            print("-" * 70)

            if not res_listing.chunks:
                print("❌ Không tìm thấy căn hộ nào phù hợp với bộ lọc này.")
            else:
                print(f"🎯 Top-12 ứng viên từ Vector Search -> Cross-Encoder Rerank -> Top-3 tinh túy nhất:")
                for i, c in enumerate(res_listing.chunks, 1):
                    m = c.metadata
                    orig_price = m.get("price")
                    # Tính toán giá sau chiết khấu 8% thanh toán sớm
                    disc_price = round(orig_price * 0.92, 3) if orig_price else None

                    print(f"\n  [{i}] Mã căn: {m['ma_can']} | Cross-Encoder Score: {c.score:.4f}")
                    print(f"      📍 Vị trí: Tòa {m['building']} - Tầng {m['tang']} (Căn {m['so_phong']})")
                    print(f"      💰 Giá gốc: {orig_price} tỷ | Giá sau chiết khấu 8%: {disc_price} tỷ (Tiết kiệm ~{round((orig_price - disc_price)*1000)} triệu)")
                    print(f"      📐 Diện tích: {m['area']}m² | Loại căn: {m['property_type']}")
                    print(f"      🧭 Hướng: {m['huong']} | View: {m['view']}")
                    print(f"      🛋️ Nội thất: {m['noi_that']} | Sổ đỏ: {m['so_do']}")
                    print(f"      🖼️ Link Ảnh: {m['image_url']}")

                    print(f"      🎁 CHÍNH SÁCH BÁN HÀNG ÁP DỤNG:")
                    print(f"         • Chiết khấu 8% khi thanh toán sớm 95% (Giá còn {disc_price} tỷ)")
                    print(f"         • Hỗ trợ vay ngân hàng 70%, 0% lãi suất & ân hạn gốc 24 tháng")
                    voucher_val = 70 if m.get("num_bedrooms") == 1 else (150 if m.get("num_bedrooms") == 2 else 200)
                    print(f"         • Tặng Voucher VinFast trị giá {voucher_val} triệu đồng")

            if res_policy.chunks:
                print("\n" + "=" * 70)
                print("📜 CHÍNH SÁCH VÀ ƯU ĐÃI KHỚP VỚI CÂU HỎI (Xếp hạng theo Cosine Score):")
                for i, pc in enumerate(res_policy.chunks, 1):
                    pm = pc.metadata
                    print(f"   ({i}) [{pm.get('title')}] (Cosine Score: {pc.score:.4f})")
                    print(f"       {pc.text}")

        except KeyboardInterrupt:
            print("\nThoát chương trình.")
            break
        except Exception as exc:
            print(f"Lỗi: {exc}")


async def main() -> None:
    # 1. Tải và lưu dữ liệu
    chunks = fetch_and_save_data()
    if not chunks:
        print("[-] Khong co du lieu can ho.")
        return

    # 2. Khởi tạo Embedder, Vector Store & Cross-Encoder Reranker
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    reranker = FakeCrossEncoderReranker()
    retriever = DefaultRetriever(embedder, store, reranker, top_k=12, top_n=3)

    vectors = await embedder.embed_texts([c.text for c in chunks])
    await store.upsert(chunks, vectors)

    # 3. Chạy chế độ tương tác Terminal
    await interactive_loop(retriever)


if __name__ == "__main__":
    asyncio.run(main())
