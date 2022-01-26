from __future__ import annotations

import json
import re
from dataclasses import Field, MISSING
from datetime import datetime
from pathlib import Path
from typing import Any, Type, TypeVar, Callable

IComparison = Callable[[dict[str, Any]], bool]


class DatabaseError(Exception):
    pass


class Comparison:
    def __init__(self, compare: IComparison):
        self.compare: IComparison = compare
    
    def __and__(self, other: Comparison):
        return Comparison(lambda data: self.compare(data) and other.compare(data))
    
    def __or__(self, other: Comparison):
        return Comparison(lambda data: self.compare(data) or other.compare(data))


class TableAttr(Field):
    # noinspection PyMissingConstructor
    def __init__(self, field: Field):
        for attr in Field.__slots__:
            setattr(self, attr, getattr(field, attr))
    
    @property
    def get_default(self) -> Any:
        if self.default_factory is MISSING:
            return self.default
        return self.default_factory()
    
    def __repr__(self) -> str:
        default = 'MISSING' if self.get_default is MISSING else self.get_default
        return f'TableAttr(name={self.name}, type={self.type}, default={default})'
    
    def __lt__(self, other: Any):
        return Comparison(lambda data: data[self.name] < other)
    
    def __le__(self, other: Any):
        return Comparison(lambda data: data[self.name] <= other)
    
    def __eq__(self, other: Any):
        try:
            pattern = re.compile(other)
            
            def func(data): return pattern.search(data[self.name]) is not None
        except (re.error, TypeError):
            def func(data): return data[self.name] == other
        return Comparison(func)
    
    def __ne__(self, other: Any):
        try:
            pattern = re.compile(other)
            
            def func(data): return pattern.search(data[self.name]) is None
        except (re.error, TypeError):
            def func(data): return data[self.name] != other
        return Comparison(func)
    
    def __gt__(self, other: Any):
        return Comparison(lambda data: data[self.name] > other)
    
    def __ge__(self, other: Any):
        return Comparison(lambda data: data[self.name] >= other)


class MetaTable(type):
    def __getattribute__(self, name):
        if name != '__dataclass_fields__' and name in (dict := getattr(self, '__dataclass_fields__', {})):
            return dict.setdefault(f'{name}_attr', TableAttr(dict[name]))
        return super().__getattribute__(name)


class Table(metaclass=MetaTable):
    def __post_init__(self):
        self._id = -1
        data = {}
        for field in getattr(self, '__dataclass_fields__', {}).values():
            data[field.name] = getattr(self, field.name)
        self.__data__ = data
    
    def __getattribute__(self, name):
        if name != '__data__' and name in (data := getattr(self, '__data__', {})):
            return data[name]
        return super().__getattribute__(name)
    
    def __setattr__(self, name, value):
        if name != '__data__' and name in (data := getattr(self, '__data__', {})):
            data[name] = value
            return
        super().__setattr__(name, value)
    
    @property
    def id(self):
        return self._id


TableType = TypeVar('TableType', bound=Table)


class Database:
    _file: Path = Path('data.json')
    _data: dict[str, Any] = None
    
    @classmethod
    def file(cls, new_file: Path = None) -> Path:
        if new_file is not None:
            cls._file = new_file
        return cls._file
    
    @classmethod
    def last_commit(cls) -> datetime:
        if cls._data is None:
            cls.rollback()
        return datetime.fromisoformat(cls._data['last_commit'])
    
    @classmethod
    def rollback(cls) -> None:
        cls._data = json.loads(cls._file.read_text()) if cls._file.exists() else {
            'last_commit': datetime.now().isoformat()
        }
    
    @classmethod
    def commit(cls) -> bool:
        try:
            cls._data['last_commit'] = datetime.now().isoformat()
            cls._file.write_text(json.dumps(cls._data, indent=2))
            return True
        except (IOError, Exception) as e:
            print(f'I/O error({e.errno}): {e.strerror}')
        return False
    
    @classmethod
    def get(cls, table: Type[TableType], where: Comparison | bool = None) -> list[TableType]:
        if cls._data is None:
            cls.rollback()
        
        table_name = table.__name__.lower()
        if table_name not in cls._data:
            return []
        
        pre_check = where is None or (isinstance(where, bool) and where)
        
        results: list[TableType] = []
        for id, table_entry in cls._data[table_name].items():
            if pre_check or where.compare(table_entry):
                entry = table(**table_entry)
                entry._id = int(id)
                entry.__data__ = table_entry
                results.append(entry)
        return results
    
    @classmethod
    def pop(cls, table: Type[TableType], where: Comparison | bool = None) -> list[TableType]:
        if cls._data is None:
            cls.rollback()
        
        table_name = table.__name__.lower()
        if table_name not in cls._data:
            return []
        
        pre_check = where is None or (isinstance(where, bool) and where)
        
        remove: list[str] = []
        results: list[TableType] = []
        for id, table_entry in cls._data[table_name].items():
            if pre_check or where.compare(table_entry):
                remove.append(id)
                results.append(table(**table_entry))
        for id in remove:
            del cls._data[table_name][id]
        return results
    
    @classmethod
    def put(cls, table: Type[TableType], *entries: TableType):
        if cls._data is None:
            cls.rollback()
        
        table_name = table.__name__.lower()
        
        if table_name not in cls._data:
            cls._data[table_name] = {}
        
        for entry in entries:
            if entry.id < 0:
                id = 0
                while str(id) in cls._data[table_name]:
                    id += 1
                entry._id = id
            cls._data[table_name][str(entry.id)] = entry.__data__
