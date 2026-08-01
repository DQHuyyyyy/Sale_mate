"""Dependency container — chỗ duy nhất gắn interface với implementation.

Vì sao cần: 4 người làm 4 module song song. Mỗi module chỉ import *contracts*
(Protocol) của module khác, không bao giờ import class cụ thể. Container là nơi
duy nhất biết "Protocol nào chạy bằng class nào" (xem src/bootstrap.py).

Nhờ vậy:
- Đổi Qdrant sang Chroma = sửa 1 dòng ở bootstrap, không đụng code gọi.
- Test ghi đè bằng container.override(...) mà không cần monkeypatch rải rác.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from src.core.exceptions import ConfigurationError

T = TypeVar("T")


class Container:
    """Registry nhẹ, khởi tạo lười (lazy) và cache singleton."""

    def __init__(self) -> None:
        self._factories: dict[Any, Callable[[], Any]] = {}
        self._singletons: dict[Any, Any] = {}
        self._overrides: dict[Any, Any] = {}
        self._transient: set[Any] = set()

    def register(self, key: Any, factory: Callable[[], Any], *, singleton: bool = True) -> None:
        """Đăng ký cách tạo ra một dịch vụ.

        Args:
            key: Protocol/class dùng làm khoá tra cứu.
            factory: Hàm không tham số trả về instance.
            singleton: True thì chỉ tạo một lần rồi tái sử dụng.
        """
        self._factories[key] = factory
        self._singletons.pop(key, None)
        if singleton:
            self._transient.discard(key)
        else:
            self._transient.add(key)

    def register_instance(self, key: Any, instance: Any) -> None:
        """Đăng ký sẵn một instance đã tạo."""
        self._factories[key] = lambda: instance
        self._singletons[key] = instance

    def resolve(self, key: type[T]) -> T:
        """Lấy instance cho một Protocol/class đã đăng ký."""
        if key in self._overrides:
            return self._overrides[key]

        if key in self._singletons:
            return self._singletons[key]

        factory = self._factories.get(key)
        if factory is None:
            raise ConfigurationError(
                f"Chưa đăng ký dịch vụ cho {getattr(key, '__name__', key)!r}. Kiểm tra src/bootstrap.py."
            )

        instance = factory()
        if key not in self._transient:
            self._singletons[key] = instance
        return instance

    def override(self, key: Any, instance: Any) -> None:
        """Thay thế tạm thời một dịch vụ — dùng trong test."""
        self._overrides[key] = instance

    def clear_overrides(self) -> None:
        self._overrides.clear()

    def reset(self) -> None:
        """Xoá sạch mọi đăng ký. Dùng giữa các test suite."""
        self._factories.clear()
        self._singletons.clear()
        self._overrides.clear()
        self._transient.clear()

    def is_registered(self, key: Any) -> bool:
        return key in self._factories or key in self._overrides


container = Container()
"""Container dùng chung toàn ứng dụng."""
