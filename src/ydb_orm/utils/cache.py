"""
Утилиты для кэширования prepared statements и объектов
"""

from typing import Dict, Any, Optional, Generic, TypeVar
from threading import Lock
import time

K = TypeVar('K')
V = TypeVar('V')


class SimpleCache(Generic[K, V]):
    """Потокобезопасный кэш с базовым TTL"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Инициализация кэша

        Args:
            max_size: Максимальное количество элементов
            default_ttl: Время жизни элементов в секундах (по умолчанию 5 минут)
        """
        self._cache: Dict[K, Dict[str, Any]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = Lock()
        self._access_order: list[K] = []  # Для LRU политики

    def set(self, key: K, value: V, ttl: Optional[int] = None) -> None:
        """
        Сохранение значения в кэш

        Args:
            key: Ключ
            value: Значение
            ttl: Время жизни в секундах (None = использовать default_ttl)
        """
        with self._lock:
            # Проверка размера кэша (LRU eviction)
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._evict_oldest()

            # Сохранение значения с временем истечения
            expire_time = time.time() + (ttl or self._default_ttl)
            self._cache[key] = {
                'value': value,
                'expires_at': expire_time,
                'created_at': time.time()
            }

            # Обновление порядка доступа
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    def get(self, key: K) -> Optional[V]:
        """
        Получение значения из кэша

        Args:
            key: Ключ

        Returns:
            Значение или None если не найдено или истекло
        """
        with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]

            # Проверка срока действия
            if time.time() > item['expires_at']:
                self._delete(key)
                return None

            # Обновление порядка доступа (используем LRU)
            self._access_order.remove(key)
            self._access_order.append(key)

            return item['value']

    def delete(self, key: K) -> bool:
        """
        Удаление значения из кэша

        Args:
            key: Ключ

        Returns:
            True если элемент был удален, False если не найден
        """
        with self._lock:
            return self._delete(key)

    def _delete(self, key: K) -> bool:
        """Внутренний метод удаления без блокировки"""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return True
        return False

    def _evict_oldest(self) -> None:
        """Удаление самого старого элемента (LRU)"""
        if self._access_order:
            oldest_key = self._access_order[0]
            self._delete(oldest_key)

    def clear(self) -> None:
        """Очистка всего кэша"""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()

    def size(self) -> int:
        """Текущий размер кэша"""
        with self._lock:
            return len(self._cache)

    def cleanup(self) -> int:
        """
        Очистка просроченных элементов

        Returns:
            Количество удаленных элементов
        """
        removed = 0
        current_time = time.time()

        with self._lock:
            keys_to_remove = []
            for key, item in self._cache.items():
                if current_time > item['expires_at']:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._delete(key)
                removed += 1

        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        with self._lock:
            total_size = len(self._cache)
            now = time.time()

            # Считаем просроченные
            expired = 0
            avg_age = 0

            if total_size > 0:
                for item in self._cache.values():
                    if now > item['expires_at']:
                        expired += 1
                    avg_age += (now - item['created_at'])
                avg_age /= total_size

            return {
                'total_items': total_size,
                'expired_items': expired,
                'average_age_seconds': avg_age,
                'max_size': self._max_size,
                'default_ttl': self._default_ttl
            }


# Глобальные экземпляры кэшей для различных целей
_prepared_stmt_cache: Optional[SimpleCache[str, Any]] = None
_query_cache: Optional[SimpleCache[str, Any]] = None


def get_prepared_stmt_cache() -> SimpleCache[str, Any]:
    """Получение кэша для prepared statements"""
    global _prepared_stmt_cache
    if _prepared_stmt_cache is None:
        # Для prepared statements ставим больше размер и дольше TTL
        _prepared_stmt_cache = SimpleCache(max_size=5000, default_ttl=3600)  # 1 час
    return _prepared_stmt_cache


def get_query_cache() -> SimpleCache[str, Any]:
    """Получение кэша для результатов запросов"""
    global _query_cache
    if _query_cache is None:
        # Для результатов запросов короче TTL
        _query_cache = SimpleCache(max_size=1000, default_ttl=60)  # 1 минута
    return _query_cache


async def clear_all_caches() -> None:
    """Асинхронная очистка всех кэшей"""
    # Можем запустить в отдельном потоке если нужно
    if _prepared_stmt_cache:
        _prepared_stmt_cache.clear()
    if _query_cache:
        _query_cache.clear()