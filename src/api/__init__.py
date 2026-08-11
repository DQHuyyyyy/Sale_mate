"""HTTP layer của LÕI AI (cổng 8001).

Cấu trúc:
    deps.py     Dependency injection lấy dịch vụ từ container
    errors.py   Đổi lỗi nghiệp vụ thành HTTP response
    v1/         Router theo phiên bản: health · chat

Lõi AI chỉ trả lời câu hỏi. Dữ liệu căn hộ, đăng nhập, quản trị tài liệu thuộc
API sản phẩm ở `interface/backend` (cổng 8000).

Router KHÔNG chứa business logic — chỉ nhận request, gọi service, trả response.
"""
