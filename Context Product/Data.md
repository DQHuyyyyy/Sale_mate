# Data.md — Mô hình dữ liệu

Schema tham chiếu cho Postgres + Qdrant. Điều chỉnh theo tài liệu thật khi có.

## 1. Postgres (bảng chính)

```
users            (id, email, password_hash, full_name, role, is_active, created_at)
                 role ∈ {sale, admin, manager}

projects         (id, name, slug, description)
buildings        (id, project_id, name)               # Tòa A/B/C
unit_types       (id, project_id, code, bedrooms, area_min, area_max)  # 1PN/2PN/3PN

units            (id, project_id, building_id, code, unit_type_id, area, direction, floor)
                 # thông tin tĩnh của căn

inventory        (unit_id, status, held_until, updated_at)
                 status ∈ {available, held, sold}     # dữ liệu ĐỘNG (realtime)
                 # nếu có API tồn kho ngoài: bảng này là cache ngắn hạn / hoặc bỏ, gọi thẳng API

prices           (id, project_id, unit_id?|unit_type_id?, price, currency,
                  vat_included, effective_from, effective_to, source_doc_version_id)
                 # bảng giá CÓ CẤU TRÚC — nguồn giá chính xác, KHÔNG lấy từ RAG

documents        (id, project_id, title, doc_type, visibility, created_by, created_at)
                 doc_type ∈ {policy, pricebook, amenity, floorplan, other}
                 visibility ∈ {internal, public}

document_versions(id, document_id, version_no, file_path, effective_date,
                  is_active, superseded_by, ingest_status, ingest_error, indexed_at)
                 ingest_status ∈ {processing, done, error}

chat_sessions    (id, user_id, project_id, created_at)
messages         (id, session_id, role, content, route_intent, sources_json,
                  is_sensitive, created_at)
                 role ∈ {user, assistant}

sensitive_actions_log (id, message_id, user_id, action, payload_json, created_at)
                 action ∈ {approve_send, reject}      # bằng chứng HITL

feedback         (id, message_id, user_id, vote, comment, created_at)
                 vote ∈ {up, down}

doc_conflicts    (id, project_id, version_a, version_b, field, note, resolved)  # nâng cao
```

## 2. Qdrant — collection & payload

Một collection `documents_chunks`, vector = embedding của chunk.

**Payload (metadata) — bắt buộc để lọc quyền & version:**

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "version_id": "uuid",
  "version_no": 3,
  "project_id": "uuid",
  "building": "B",              // optional
  "unit_type": "2PN",          // optional
  "doc_type": "policy",
  "visibility": "internal",     // internal | public  → LỌC THEO QUYỀN
  "is_active": true,            // chỉ truy hồi bản còn hiệu lực
  "effective_date": "2026-07-12",
  "source_title": "Chính sách bán hàng",
  "page": 4,                    // để citation trỏ tới mục/trang
  "section": "Tiến độ thanh toán"
}
```

## 3. Mô hình phân quyền (RBAC → retrieval)

| Vai trò | Được truy hồi visibility |
|---|---|
| sale (in-house) | internal + public |
| sale (môi giới ngoài)* | public |
| manager | internal + public |
| admin | tất cả (quản trị) |

\* Nếu phân biệt môi giới ngoài, thêm trường phân loại trên `users`.

**Quy tắc bất biến:** filter `visibility` được đưa vào **truy vấn Qdrant**, không lọc sau khi đã lấy chunk. Kèm luôn `is_active = true`.

Ví dụ filter Qdrant:
```python
qdrant_filter = Filter(must=[
    FieldCondition(key="project_id", match=MatchValue(value=project_id)),
    FieldCondition(key="is_active", match=MatchValue(value=True)),
    FieldCondition(key="visibility", match=MatchAny(any=allowed_visibilities)),
])
```

## 4. Versioning & mâu thuẫn

- Upload bản mới cùng `document_id` → tạo `document_versions` mới, set bản cũ `is_active=false`, `superseded_by=version_mới`.
- Chunk trong Qdrant của bản cũ cũng set `is_active=false` (hoặc xóa) khi re-index.
- Truy hồi **chỉ** lấy `is_active=true`.
- Cảnh báo mâu thuẫn: so hai bản active cùng field (ví dụ chiết khấu) → ghi `doc_conflicts` → admin xử lý.

## 5. Lưu ý PII (nếu làm memory theo khách)

- Nếu lưu thông tin khách (tên, nhu cầu) cho cá nhân hóa: tách bảng riêng, cân nhắc ẩn danh, và giới hạn quyền truy cập. Đây là dữ liệu nhạy cảm — chỉ làm khi đã rõ yêu cầu pháp lý/nghiệp vụ.
