from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

import packaging.utils
import packaging.version

from warehub.database import Table

SIMPLE_DIR = Path('simple')
PYPI_DIR = Path('pypi')

JSON = dict[str, Any]

_num = '[1-9][0-9]*'


def is_canonical(version: str) -> bool:
    return re.match(rf'^({_num}!)?(0|{_num})(\.(0|{_num}))*((a|b|rc)(0|{_num}))?(\.post(0|{_num}))?(\.dev(0|{_num}))?$', version) is not None


def is_pre_release(version: str) -> bool:
    return re.match(rf'(a|b|rc)(0|{_num})', version) is not None


class PackageType(Enum):
    none = auto()
    bdist_dmg = auto()
    bdist_dumb = auto()
    bdist_egg = auto()
    bdist_msi = auto()
    bdist_rpm = auto()
    bdist_wheel = auto()
    bdist_wininst = auto()
    sdist = auto()


@dataclass
class Project(Table):
    name: str
    
    created: str = ''
    documentation: str = None
    total_size: int = 0
    
    def __repr__(self) -> str:
        return f'Project(name={self.name}, created={self.created})'
    
    @property
    def normalized_name(self):
        return packaging.utils.canonicalize_name(self.name)
    
    # @property
    # def all_versions(self) -> tuple[str, ...]:
    #     return tuple(self.releases)
    #
    # @property
    # def latest_version(self) -> str:
    #     return versions[0] if len(versions := self.all_versions) > 0 else ''


@dataclass
class Release(Table):
    project_id: int = -1
    version: str = ''
    created: str = ''
    author: str = ''
    author_email: str = ''
    maintainer: str = ''
    maintainer_email: str = ''
    summary: str = ''
    description: dict[str, str] = field(default_factory=dict)
    keywords: str = ''
    classifiers: list[str] = field(default_factory=list)
    license: str = ''
    platform: str = ''
    home_page: str = ''
    download_url: str = ''
    requires_python: str = ''
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    uploader: str = ''  # User that created the issue
    uploaded_via: str = ''
    yanked: bool = False
    yanked_reason: str = ''
    
    @property
    def is_pre_release(self):
        return re.match(rf'(a|b|rc)(0|{_num})', self.version) is not None
    
    @property
    def urls(self):
        _urls = {}
        
        if self.home_page:
            _urls["Homepage"] = self.home_page
        if self.download_url:
            _urls["Download"] = self.download_url
        
        for urlspec in self.project_urls:
            name, _, url = urlspec.partition(",")
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
    release_id: int = -1
    name: str = None
    path: str = None
    python_version: str = None
    package_type: PackageType = PackageType.none
    comment_text: str = None
    size: int = -1
    has_signature: bool = False
    md5_digest: Optional[str] = None
    sha256_digest: Optional[str] = None
    blake2_256_digest: Optional[str] = None
    upload_time: str = ''
    uploaded_via: str = None
    
    @property
    def pgp_path(self):
        return self.path / '.asc'


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
    def json(self) -> JSON:
        with self.file.open('r') as file:
            return json.load(file)
    
    @json.setter
    def json(self, obj: JSON) -> None:
        with self.file.open('r') as file:
            json.dump(obj, file)
    
    def make(self) -> None:
        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text('{}')
