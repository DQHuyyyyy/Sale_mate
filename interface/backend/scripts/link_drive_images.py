"""Nối ảnh trên Google Drive vào bảng `apartment_images`.

Cột `Ảnh` trong `salemate_v1` chứa TÊN FOLDER ("1. R103"), không phải link.
Script này quét folder cha trên Drive, khớp tên folder với từng căn, lấy id của
từng ảnh rồi ghi URL vào DB.

KHÔNG tải và KHÔNG đẩy file — ảnh vẫn nằm trên Drive, DB chỉ giữ link.
Nhờ vậy không tốn dung lượng Supabase (free tier 1GB) dù mỗi căn bao nhiêu ảnh.

Chạy:
    python interface/backend/scripts/link_drive_images.py --dry-run --limit 5
    python interface/backend/scripts/link_drive_images.py --dry-run
    python interface/backend/scripts/link_drive_images.py      # ghi vào DB

Chạy lại bao nhiêu lần cũng không nhân đôi bản ghi.

Cần trong .env:
    SUPABASE_URL=https://<ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=eyJ...
    DRIVE_API_KEY=AIza...              # Google Cloud → Credentials → API key
    DRIVE_PARENT_FOLDER_ID=<link hoặc id folder CHA chứa mọi folder căn>

Điều kiện: folder cha phải để chế độ "Bất kỳ ai có đường liên kết".
Không cần Service Account — API key là đủ để đọc file công khai.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

IMAGE_WIDTH = 1600
SOURCE_TABLE = "salemate_v1"
IMAGE_TABLE = "apartment_images"
FOLDER_COLUMN = "Ảnh"

_DRIVE_ID_PATTERN = re.compile(r"/folders/([A-Za-z0-9_-]{10,})|[?&]id=([A-Za-z0-9_-]{10,})")


def extract_folder_id(value: str) -> str:
    """Nhận cả link Drive lẫn id trần — dán nguyên link từ trình duyệt là chuyện tự nhiên.

    >>> extract_folder_id("https://drive.google.com/drive/folders/1QT65Bcq_xyz?usp=sharing")
    '1QT65Bcq_xyz'
    >>> extract_folder_id("1QT65Bcq_xyz")
    '1QT65Bcq_xyz'
    """
    value = value.strip()
    match = _DRIVE_ID_PATTERN.search(value)
    if match:
        return match.group(1) or match.group(2)
    return value


def build_image_url(file_id: str, width: int = IMAGE_WIDTH) -> str:
    """Dựng URL hiển thị ảnh công khai trên Drive.

    Dùng endpoint thumbnail vì nó cho chỉ định chiều rộng và đi qua CDN của
    Google. Endpoint `uc?export=view` cũ hay bị chặn khi lượt xem tăng.

    DB lưu cả `drive_file_id` nên sau này muốn đổi dạng URL, hoặc chuyển hẳn
    sang Supabase Storage, đều không phải quét lại Drive.
    """
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"


def normalize(name: str) -> str:
    """Chuẩn hoá tên folder để khớp: bỏ khoảng trắng thừa, không phân biệt hoa thường."""
    return re.sub(r"\s+", " ", str(name or "")).strip().casefold()


def build_drive(api_key: str):
    from googleapiclient.discovery import build

    return build("drive", "v3", developerKey=api_key, cache_discovery=False)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def list_children(drive, parent_id: str, *, folders_only: bool) -> list[dict]:
    """Liệt kê folder con hoặc ảnh trong một folder."""
    kind = "mimeType='application/vnd.google-apps.folder'" if folders_only else "mimeType contains 'image/'"
    items: list[dict] = []
    page_token = None
    while True:
        response = (
            drive.files()
            .list(
                q=f"'{parent_id}' in parents and {kind} and trashed=false",
                fields="nextPageToken, files(id, name, mimeType)",
                orderBy="name_natural" if not folders_only else "name",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        items.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return items


def fetch_units(supabase) -> list[dict]:
    """Lấy mã căn và tên folder ảnh từ bảng nguồn."""
    rows: list[dict] = []
    start, step = 0, 1000
    while True:
        response = (
            supabase.table(SOURCE_TABLE).select(f'ma_can, "{FOLDER_COLUMN}"').range(start, start + step - 1).execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < step:
            return rows
        start += step


def save_images(supabase, records: list[dict]) -> int:
    """Ghi vào DB theo lô. Trùng (ma_can, drive_file_id) thì cập nhật."""
    written = 0
    for start in range(0, len(records), 200):
        batch = records[start : start + 200]
        supabase.table(IMAGE_TABLE).upsert(batch, on_conflict="ma_can,drive_file_id").execute()
        written += len(batch)
    return written


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    parser = argparse.ArgumentParser(description="Nối ảnh Drive vào apartment_images")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in, không ghi DB")
    parser.add_argument("--limit", type=int, help="Chỉ xử lý N căn đầu")
    parser.add_argument("--width", type=int, default=IMAGE_WIDTH, help="Chiều rộng ảnh")
    args = parser.parse_args()

    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DRIVE_API_KEY", "DRIVE_PARENT_FOLDER_ID")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"Thiếu biến trong .env: {', '.join(missing)}")
        if "DRIVE_API_KEY" in missing:
            print(
                "\nLấy DRIVE_API_KEY:\n"
                "  1. console.cloud.google.com → tạo project (hoặc dùng project sẵn có)\n"
                "  2. APIs & Services → Library → bật 'Google Drive API'\n"
                "  3. APIs & Services → Credentials → Create credentials → API key\n"
                "  Không cần Service Account, không cần thẻ tín dụng."
            )
        return 1

    from supabase import create_client

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    drive = build_drive(os.environ["DRIVE_API_KEY"])

    parent_id = extract_folder_id(os.environ["DRIVE_PARENT_FOLDER_ID"])
    print(f"Folder cha: {parent_id}")

    folders = list_children(drive, parent_id, folders_only=True)
    folder_map = {normalize(f["name"]): f for f in folders}
    print(f"Drive: {len(folders)} folder con")

    if not folders:
        print(
            "\n⚠️  Không thấy folder con nào. Ba nguyên nhân thường gặp:\n"
            "   · ID đang trỏ vào folder của MỘT căn, không phải folder cha\n"
            "   · Folder chưa để chế độ 'Bất kỳ ai có đường liên kết'\n"
            "   · API key chưa được bật quyền Google Drive API"
        )
        return 1

    units = fetch_units(supabase)
    if args.limit:
        units = units[: args.limit]
    print(f"DB: {len(units)} căn\n")

    records: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    not_found: list[str] = []
    no_image: list[str] = []

    for index, unit in enumerate(units, start=1):
        code = (unit.get("ma_can") or "").strip()
        folder_name = (unit.get(FOLDER_COLUMN) or "").strip()
        if not code or not folder_name:
            stats["thiếu dữ liệu"] += 1
            continue

        folder = folder_map.get(normalize(folder_name))
        if folder is None:
            not_found.append(f"{code} → '{folder_name}'")
            continue

        images = list_children(drive, folder["id"], folders_only=False)
        if not images:
            no_image.append(f"{code} → '{folder_name}'")
            continue

        for order, image in enumerate(images):
            records.append(
                {
                    "ma_can": code,
                    "drive_file_id": image["id"],
                    "file_name": image["name"],
                    "image_url": build_image_url(image["id"], args.width),
                    "sort_order": order,
                }
            )
        stats["có ảnh"] += 1
        print(f"[{index}/{len(units)}] {code:10s} {len(images):3d} ảnh   ({folder_name})")

    print(f"\n{'=' * 60}")
    print(f"Căn có ảnh:        {stats['có ảnh']}")
    print(f"Tổng ảnh nối được: {len(records)}")
    if stats["có ảnh"]:
        print(f"Trung bình:        {len(records) / stats['có ảnh']:.1f} ảnh/căn")
    if not_found:
        print(f"\n⚠️  {len(not_found)} căn không thấy folder trên Drive:")
        for item in not_found[:10]:
            print(f"     {item}")
        if len(not_found) > 10:
            print(f"     … và {len(not_found) - 10} căn nữa")
    if no_image:
        print(f"\n⚠️  {len(no_image)} folder rỗng: {no_image[:5]}")
    print(f"{'=' * 60}\n")

    if args.dry_run:
        print("--dry-run: chưa ghi vào DB.")
        if records:
            print(f"Ví dụ URL: {records[0]['image_url']}")
        return 0

    if not records:
        print("Không có ảnh nào để ghi.")
        return 1

    written = save_images(supabase, records)
    print(f"✅ Đã ghi {written} bản ghi vào `{IMAGE_TABLE}`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
