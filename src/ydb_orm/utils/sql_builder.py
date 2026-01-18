"""
Утилиты для построения SQL условий
"""

from dataclasses import dataclass
from typing import Any, List


@dataclass
class Condition:
    """Структурированное условие для фильтрации"""
    field: str
    operator: str = "="
    value: Any = None

    def __str__(self) -> str:
        """Строковое представление условия"""
        if self.operator == "=":
            return f"{self.field} = {repr(self.value)}"
        elif self.operator == "!=":
            return f"{self.field} != {repr(self.value)}"
        elif self.operator == ">":
            return f"{self.field} > {repr(self.value)}"
        elif self.operator == ">=":
            return f"{self.field} >= {repr(self.value)}"
        elif self.operator == "<":
            return f"{self.field} < {repr(self.value)}"
        elif self.operator == "<=":
            return f"{self.field} <= {repr(self.value)}"
        elif self.operator == "in":
            values = ", ".join(repr(v) for v in self.value)
            return f"{self.field} IN ({values})"
        elif self.operator == "like":
            return f"{self.field} LIKE {repr(self.value)}"
        elif self.operator == "between":
            return f"{self.field} BETWEEN {repr(self.value[0])} AND {repr(self.value[1])}"
        else:
            return f"{self.field} {self.operator} {repr(self.value)}"


def build_where_conditions(conditions: List[Condition]) -> str:
    """
    Построение WHERE clause из списка условий

    Args:
        conditions: Список объектов Condition

    Returns:
        SQL WHERE clause
    """
    if not conditions:
        return ""

    where_parts = []
    for cond in conditions:
        where_parts.append(str(cond))

    return " AND ".join(where_parts)


# Удобные фабричные функции для создания условий
def eq(field: str, value: Any) -> Condition:
    """Создание условия равенства"""
    return Condition(field, "=", value)


def ne(field: str, value: Any) -> Condition:
    """Создание условия неравенства"""
    return Condition(field, "!=", value)


def gt(field: str, value: Any) -> Condition:
    """Создание условия 'больше'"""
    return Condition(field, ">", value)


def ge(field: str, value: Any) -> Condition:
    """Создание условия 'больше или равно'"""
    return Condition(field, ">=", value)


def lt(field: str, value: Any) -> Condition:
    """Создание условия 'меньше'"""
    return Condition(field, "<", value)


def le(field: str, value: Any) -> Condition:
    """Создание условия 'меньше или равно'"""
    return Condition(field, "<=", value)


def in_(field: str, values: List[Any]) -> Condition:
    """Создание условия IN"""
    return Condition(field, "in", values)


def like(field: str, pattern: str) -> Condition:
    """Создание условия LIKE"""
    return Condition(field, "like", pattern)


def between(field: str, lower: Any, upper: Any) -> Condition:
    """Создание условия BETWEEN"""
    return Condition(field, "between", (lower, upper))