"""Sinh câu lệnh SQL tạo tài khoản (mật khẩu đã hash bcrypt).

Script KHÔNG kết nối database — nó chỉ in SQL ra màn hình để bạn dán vào
Supabase → SQL Editor. Mật khẩu nhập bằng tay, không nằm trong repo.

Chạy:
    cd backend
    pip install bcrypt
    python scripts/seed_users.py
"""

from __future__ import annotations

import getpass
import sys

import bcrypt

ROLES = ("admin", "sale")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def ask_user() -> str | None:
    username = input("username (Enter để dừng): ").strip()
    if not username:
        return None

    full_name = input("  họ tên: ").strip()
    role = input(f"  role {ROLES}: ").strip() or "sale"
    if role not in ROLES:
        print(f"  role phải là một trong {ROLES}. Bỏ qua tài khoản này.")
        return ""

    phone = input("  điện thoại (bỏ trống được): ").strip()
    email = input("  email (bỏ trống được): ").strip()

    password = getpass.getpass("  mật khẩu: ")
    if len(password) < 6:
        print("  mật khẩu tối thiểu 6 ký tự. Bỏ qua tài khoản này.")
        return ""
    if password != getpass.getpass("  nhập lại mật khẩu: "):
        print("  hai lần nhập không khớp. Bỏ qua tài khoản này.")
        return ""

    phone_sql = f"'{sql_escape(phone)}'" if phone else "NULL"
    email_sql = f"'{sql_escape(email)}'" if email else "NULL"

    return (
        "INSERT INTO users (username, password_hash, full_name, role, phone, email)\n"
        f"VALUES ('{sql_escape(username)}', '{hash_password(password)}', "
        f"'{sql_escape(full_name)}', '{role}', {phone_sql}, {email_sql})\n"
        "ON CONFLICT (username) DO NOTHING;"
    )


def main() -> int:
    print("Tạo tài khoản SalesMate — nhập lần lượt, Enter rỗng để kết thúc.\n")
    statements: list[str] = []

    while True:
        try:
            stmt = ask_user()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if stmt is None:
            break
        if stmt:
            statements.append(stmt)

    if not statements:
        print("Không có tài khoản nào được tạo.")
        return 1

    print("\n" + "=" * 60)
    print("-- Dán đoạn dưới đây vào Supabase → SQL Editor")
    print("=" * 60)
    for stmt in statements:
        print(stmt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
