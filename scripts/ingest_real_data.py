"""Script tải, lưu trữ và tìm kiếm RAG tương tác trực tiếp (Interactive CLI).

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
from src.data.retrieval.rerankers import PassthroughReranker
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


def fetch_and_save_data() -> list[Chunk]:
    """Tải dữ liệu từ Google Sheets, lưu xuống file `data/vop_listings.json` và trả về Chunks."""
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
            "noi_that": noi_that,
            "tinh_trang": tinh_trang,
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

    # Ghi ra file JSON cục bộ
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_records, f, ensure_ascii=False, indent=2)

    print(f"[+] Da tai va parse thanh cong {len(chunks)} can ho.")
    print(f"[+] LU U TRU: Da luu file du lieu cuc bo tai -> {LOCAL_JSON_PATH.resolve()}\n")
    return chunks


async def interactive_loop(retriever: DefaultRetriever) -> None:
    """Chế độ nhập tìm kiếm trực tiếp từ Terminal."""
    print("=" * 65)
    print("🤖 CHẾ ĐỘ TÌM KIẾM TƯƠNG TÁC (GÕ CÂU HỎI & BỘ LỌC CỦA BẠN)")
    print("=" * 65)
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

            filters = RetrievalFilter(
                min_price=min_price,
                max_price=max_price,
                num_bedrooms=num_bedrooms,
                building=building,
            )

            print("\n" + "-" * 65)
            print(f"🔍 Đang truy vấn: '{query}'")
            print(f"📋 Điều kiện lọc: Giá=[{min_price or 0} - {max_price or '∞'} tỷ], Phòng={num_bedrooms or 'Tất cả'}, Tòa={building or 'Tất cả'}")
            print("-" * 65)

            result = await retriever.retrieve(query, filters=filters, top_k=5)

            if not result.chunks:
                print("❌ Không tìm thấy căn hộ nào phù hợp với bộ lọc này.")
            else:
                print(f"🎯 Tìm thấy {len(result.chunks)} căn hộ phù hợp (Được xếp hạng theo Cosine Score):")
                for i, c in enumerate(result.chunks, 1):
                    m = c.metadata
                    print(f"\n  [{i}] Mã căn: {m['ma_can']} | Cosine Score: {c.score:.4f}")
                    print(f"      Tòa: {m['building']} | Giá: {m['price']} tỷ | DT: {m['area']}m² | Loại: {m['property_type']}")
                    print(f"      Hướng: {m['huong']} | View: {m['view']}")
                    print(f"      Nội thất: {m['noi_that']}")

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

    # 2. Khởi tạo Embedder & Vector Store
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    retriever = DefaultRetriever(embedder, store, PassthroughReranker())

    vectors = await embedder.embed_texts([c.text for c in chunks])
    await store.upsert(chunks, vectors)

    # 3. Chạy chế độ tương tác Terminal
    await interactive_loop(retriever)


if __name__ == "__main__":
    asyncio.run(main())
