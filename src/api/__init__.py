"""Module INTERFACE (backend) — HTTP layer.

Chủ sở hữu: phuc

Cấu trúc:
    deps.py     Dependency injection lấy dịch vụ từ container
    errors.py   Đổi lỗi nghiệp vụ thành HTTP response
    v1/         Router theo phiên bản: health · chat · portal

Router KHÔNG chứa business logic — chỉ nhận request, gọi service, trả response.
"""
