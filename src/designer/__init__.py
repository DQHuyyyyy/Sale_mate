"""Xử lý ảnh cho tính năng sửa ảnh của trợ lý.

    pipeline.py  hàm thuần — kích thước, mask, ghép đè, đóng nhãn. Không mạng.
    editor.py    điều phối: hỏi lại → khoanh vùng → gọi model → ghép.

Tách hai tầng vì `pipeline.py` là nơi quyết định ảnh ra có đúng hay không, và
nó test được đầy đủ mà không tốn một đồng nào gọi model.
"""
