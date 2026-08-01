# API.md — Hợp đồng API

Base URL (local): `http://localhost:8000`. Tất cả (trừ auth) yêu cầu `Authorization: Bearer <token>`.

## 1. Auth

```
POST /auth/login      body: {email, password}         → {access_token, user}
POST /auth/logout                                       → 204
GET  /auth/me                                           → {id, full_name, role, projects}
```

## 2. Chat (Sale)

```
POST /chat            body: {session_id?, project_id, message}
                      → SSE stream (xem mục 6)
GET  /chat/sessions                                     → [{id, project_id, created_at, preview}]
GET  /chat/sessions/{id}/messages                       → [Message]
```

`Message` (assistant):
```json
{
  "id": "uuid",
  "role": "assistant",
  "content": "…",
  "route_intent": "inventory",
  "sources": [
    {"type":"doc","title":"Chính sách bán hàng","version":"v3","date":"2026-07-12","visibility":"internal","page":4},
    {"type":"live","title":"Tồn kho căn hộ","updated_seconds_ago":28},
    {"type":"db","title":"Bảng giá tháng 07","version":"v2","date":"2026-07-20"}
  ],
  "inventory": [
    {"code":"B-12.05","unit_type":"2PN","area":68,"direction":"ĐN","price":"3,85 tỷ","status":"available"}
  ],
  "is_sensitive": false,
  "draft": null
}
```

Nếu `is_sensitive = true`, `draft` chứa nội dung tin gửi khách và **client phải hiện cổng HITL**, không tự gửi.

## 3. HITL (duyệt tin gửi khách)

```
POST /messages/{id}/approve   body: {edited_content?}   → {status:"sent", logged_at}
POST /messages/{id}/reject    body: {reason?}           → {status:"rejected"}
```
Cả hai ghi vào `sensitive_actions_log`.

## 4. Documents (Admin)

```
POST   /documents             multipart: file + {project_id, title, doc_type,
                              visibility, building?, unit_type?, effective_date}
                              → {document_id, version_id, ingest_status:"processing"}
GET    /documents?project_id=…                          → [Document + latest version]
GET    /documents/{id}                                  → Document + versions[]
DELETE /documents/{id}                                  → 204
POST   /documents/{id}/reindex                          → {ingest_status:"processing"}
GET    /documents/{id}/ingest-status                    → {status, error?}
```

## 5. Tool endpoints (agent gọi nội bộ; cũng có thể expose cho debug)

```
GET /inventory?project_id=…&building=…&unit_type=…&unit_code=…
    → [{code, unit_type, area, direction, price, status, updated_at}]   # REALTIME

GET /prices?project_id=…&unit_code=…            (hoặc &unit_type=…)
    → {price, currency, vat_included, effective_from, source_version}   # từ DB
```

**Tool schema cho LLM (function calling):**
```json
{"name":"inventory_lookup",
 "parameters":{"project_id":"str","building":"str?","unit_type":"str?","unit_code":"str?"}}
{"name":"price_lookup",
 "parameters":{"project_id":"str","unit_code":"str?","unit_type":"str?"}}
```

## 6. Streaming (SSE) cho /chat

Trả `text/event-stream`, các event:
```
event: route      data: {"intent":"inventory"}          # dòng định tuyến (hiện RouteLine)
event: token      data: {"text":"…"}                    # stream nội dung
event: inventory  data: [ {unit…} ]                     # thẻ tồn kho (nếu có)
event: sources    data: [ {source…} ]                   # chip nguồn
event: sensitive  data: {"draft":"…"}                   # kích hoạt cổng HITL
event: done       data: {"message_id":"uuid"}
```

## 7. Định dạng lỗi (chuẩn hoá)

```json
{ "error": { "code": "forbidden", "message": "Bạn không có quyền xem tài liệu này." } }
```
Mã thường dùng: `unauthorized` (401), `forbidden` (403), `not_found` (404),
`validation_error` (422), `ingest_failed` (500). Thông điệp bằng tiếng Việt, chỉ rõ cách xử lý.

## 8. Quy ước chung

- Thời gian ISO 8601; tiền tệ VND.
- Không đặt dữ liệu nhạy cảm trên query string.
- Endpoint tài liệu/tồn kho luôn kiểm quyền theo vai trò trước khi trả.
