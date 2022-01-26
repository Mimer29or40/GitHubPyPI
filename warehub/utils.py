import json
import os
import re
from typing import Any

__all__ = [
    'file_size_str',
    'Secrets',
]


def file_size_str(size: int) -> str:
    suffix = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    i = 0
    while size > 1024 and i < len(suffix) - 1:
        size = size // 1024
        i += 1
    return f'{size} {suffix[i]}'


class Secrets:
    def __init__(self, name: str = 'SECRETS', token: str = '##'):
        self._name = name
        self._token = token
        self._regex = re.compile(rf'^{token}(\w+){token}$')
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def token(self) -> str:
        return self._token
    
    @token.setter
    def token(self, token: str) -> None:
        self._token = token
        self._regex = re.compile(rf'^{token}(\w+){token}$')
    
    @property
    def secrets(self):
        return json.loads(os.environ[self._name]) if self._name in os.environ else {}
    
    def is_name(self, name: str) -> bool:
        """Returns True if the name is a secret name"""
        return self._regex.match(name) is not None
    
    def get_name(self, name: str) -> str:
        """Returns the name formatted as a secret name"""
        if self.is_name(name):
            return name
        return f'{self._token}{name}{self._token}'
    
    def get(self, name: str) -> Any:
        if (m := self._regex.match(name)) is not None:
            name = m.group(1)
            secrets = self.secrets
            if name not in secrets:
                raise KeyError(f'Requested secret not present: {name}')
            return secrets[name]
        else:
            raise ValueError(f'name \'{name}\' is not a secret name')
