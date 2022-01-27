from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import packaging.utils
import packaging.version

from .database import Table

__all__ = [
    'CURRENT_DIR',
    'FILES_DIR',
    'PROJECT_DIR',
    'SIMPLE_DIR',
    'PYPI_DIR',
    'WEB_DIR',
    'CONFIG_FILE',
    'DATABASE_FILE',
    'Project',
    'Release',
    'File',
    'FileName',
]

CURRENT_DIR: Path = Path('.')

FILES_DIR: Path = CURRENT_DIR / 'files'
PROJECT_DIR: Path = CURRENT_DIR / 'project'
SIMPLE_DIR: Path = CURRENT_DIR / 'simple'
PYPI_DIR: Path = CURRENT_DIR / 'pypi'
WEB_DIR: Path = CURRENT_DIR / 'web'

CONFIG_FILE: Path = CURRENT_DIR / 'config.json'
DATABASE_FILE: Path = CURRENT_DIR / 'data.json'


@dataclass
class Project(Table):
    name: str
    
    created: str = datetime.now().isoformat()
    documentation: Optional[str] = None
    total_size: int = 0
    
    def __repr__(self) -> str:
        return f'Project(name={self.name}, created={self.created})'
    
    @property
    def normalized_name(self):
        return packaging.utils.canonicalize_name(self.name)


@dataclass
class Release(Table):
    project_id: int
    version: str
    created: str = datetime.now().isoformat()
    author: Optional[str] = None
    author_email: Optional[str] = None
    maintainer: Optional[str] = None
    maintainer_email: Optional[str] = None
    summary: Optional[str] = None
    description: dict[str, str] = field(default_factory=dict)
    keywords: Optional[str] = None
    classifiers: list[str] = field(default_factory=list)
    license: Optional[str] = None
    platform: Optional[str] = None
    home_page: Optional[str] = None
    download_url: Optional[str] = None
    requires_python: Optional[str] = None
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    project_urls: list[str] = field(default_factory=list)
    uploader: Optional[str] = None  # User that created the issue
    uploaded_via: Optional[str] = None
    yanked: bool = False
    yanked_reason: Optional[str] = None
    
    @property
    def is_pre_release(self):
        return re.match(rf'(a|b|rc)(0|[1-9][0-9]*)', self.version) is not None
    
    @property
    def urls(self):
        _urls = {}
        
        if self.home_page:
            _urls['Homepage'] = self.home_page
        if self.download_url:
            _urls['Download'] = self.download_url
        
        for url_spec in self.project_urls:
            name, _, url = url_spec.partition(',')
            name = name.strip()
            url = url.strip()
            if name and url:
                _urls[name] = url
        
        return _urls
    
    # TODO
    # @property
    # def github_repo_info_url(self):
    #     for url in self.urls.values():
    #         parsed = urlparse(url)
    #         segments = parsed.path.strip("/").split("/")
    #         if parsed.netloc in {"github.com", "www.github.com"} and len(segments) >= 2:
    #             user_name, repo_name = segments[:2]
    #             return f"https://api.github.com/repos/{user_name}/{repo_name}"
    
    @property
    def has_meta(self):
        return any((
            self.license,
            self.keywords,
            self.author,
            self.author_email,
            self.maintainer,
            self.maintainer_email,
            self.requires_python,
        ))


@dataclass
class File(Table):
    release_id: int
    name: str
    python_version: Optional[str] = None
    package_type: Optional[str] = None
    comment_text: Optional[str] = None
    size: int = -1
    has_signature: bool = False
    md5_digest: Optional[str] = None
    sha256_digest: Optional[str] = None
    blake2_256_digest: Optional[str] = None
    upload_time: str = datetime.now().isoformat()
    uploaded_via: Optional[str] = None
    
    @property
    def pgp_name(self):
        return self.name + '.asc'


@dataclass
class FileName(Table):
    name: str


@dataclass(frozen=True)
class HtmlFile:
    path: Path
    
    @property
    def file(self) -> Path:
        return self.path / 'index.html'
    
    def make(self) -> None:
        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.touch(exist_ok=True)


@dataclass(frozen=True)
class JsonFile:
    path: Path
    
    @property
    def file(self) -> Path:
        return self.path / 'json' / 'index.json'
    
    @property
    def json(self) -> dict[str, Any]:
        with self.file.open('r') as file:
            return json.load(file)
    
    @json.setter
    def json(self, obj: dict[str, Any]) -> None:
        with self.file.open('r') as file:
            json.dump(obj, file)
    
    def make(self) -> None:
        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text('{}')
