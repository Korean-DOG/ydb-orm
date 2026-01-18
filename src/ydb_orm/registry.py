"""
Реестр моделей для разрешения зависимостей
"""

from typing import Dict, Type, Optional, Set
from weakref import WeakValueDictionary


class ModelRegistry:
    """Реестр зарегистрированных моделей"""

    _models: Dict[str, Type] = {}
    _model_by_tablename: Dict[str, Type] = {}
    _instances: Dict[str, 'ModelRegistry'] = WeakValueDictionary()

    def __new__(cls, name: str = "default"):
        if name not in cls._instances:
            instance = super().__new__(cls)
            instance._name = name
            instance._models = {}
            instance._model_by_tablename = {}
            cls._instances[name] = instance
        return cls._instances[name]

    def register(self, model_cls: Type) -> None:
        """
        Регистрация модели в реестре

        Args:
            model_cls: Класс модели для регистрации
        """
        model_name = model_cls.__name__
        table_name = getattr(model_cls, '__tablename__', model_name.lower())

        self._models[model_name] = model_cls
        self._model_by_tablename[table_name] = model_cls

        # Устанавливаем обратную ссылку
        setattr(model_cls, '_registry', self)

    def get_model(self, name: str) -> Optional[Type]:
        """
        Получение модели по имени класса

        Args:
            name: Имя класса модели

        Returns:
            Класс модели или None если не найден
        """
        return self._models.get(name)

    def get_model_by_table(self, table_name: str) -> Optional[Type]:
        """
        Получение модели по имени таблицы

        Args:
            table_name: Имя таблицы в БД

        Returns:
            Класс модели или None если не найден
        """
        return self._model_by_tablename.get(table_name)

    def get_all_models(self) -> Set[Type]:
        """
        Получение всех зарегистрированных моделей

        Returns:
            Множество классов моделей
        """
        return set(self._models.values())


# Глобальный реестр по умолчанию
default_registry = ModelRegistry()


# Декоратор для автоматической регистрации
def register_model(model_cls: Type) -> Type:
    """
    Декоратор для автоматической регистрации модели

    Args:
        model_cls: Класс модели

    Returns:
        Тот же класс с регистрацией
    """
    default_registry.register(model_cls)
    return model_cls