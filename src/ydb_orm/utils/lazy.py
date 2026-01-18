"""
Утилиты для реализации ленивой загрузки
"""

from typing import Any, Callable, Generic, TypeVar, Optional
import asyncio

T = TypeVar('T')


class LazyLoader(Generic[T]):
    """Обёртка для ленивой загрузки значения"""

    __slots__ = ('_loader', '_value', '_loaded', '_lock')

    def __init__(self, loader: Callable[[], T]):
        """
        Инициализация ленивого загрузчика

        Args:
            loader: Функция для загрузки значения
        """
        self._loader = loader
        self._value: Optional[T] = None
        self._loaded = False
        self._lock = asyncio.Lock()

    async def get(self) -> T:
        """
        Получение значения (с ленивой загрузкой)

        Returns:
            Загруженное значение
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:  # Double-check
                    self._value = await self._loader()
                    self._loaded = True

        return self._value

    def is_loaded(self) -> bool:
        """Проверка, загружено ли значение"""
        return self._loaded

    def reset(self) -> None:
        """Сброс загруженного значения"""
        self._loaded = False
        self._value = None


class AsyncLazyLoader(LazyLoader[T]):
    """Ленивый загрузчик для асинхронных функций"""

    async def get(self) -> T:
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    # Для асинхронных загрузчиков
                    if asyncio.iscoroutinefunction(self._loader):
                        self._value = await self._loader()
                    else:
                        self._value = self._loader()
                    self._loaded = True

        return self._value


def lazy_property(func: Callable[[Any], T]) -> property:
    """
    Декоратор для ленивых свойств

    Args:
        func: Функция для вычисления значения

    Returns:
        Свойство с ленивой загрузкой
    """
    attr_name = f"_lazy_{func.__name__}"

    @property
    def _lazy_property(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, LazyLoader(lambda: func(self)))
        return getattr(self, attr_name)

    return _lazy_property


def async_lazy_property(func: Callable[[Any], T]) -> property:
    """
    Декоратор для асинхронных ленивых свойств

    Args:
        func: Асинхронная функция для вычисления значения

    Returns:
        Свойство с асинхронной ленивой загрузкой
    """
    attr_name = f"_async_lazy_{func.__name__}"

    @property
    def _async_lazy_property(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, AsyncLazyLoader(lambda: func(self)))
        return getattr(self, attr_name)

    return _async_lazy_property