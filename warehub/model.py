from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields, MISSING
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional, Callable

import packaging.utils
import packaging.version

DATA_FILE = Path('data.json')

SIMPLE_DIR = Path('simple')
PYPI_DIR = Path('pypi')

JSON = dict[str, Any]

_num = '[1-9][0-9]*'


def is_canonical(version: str) -> bool:
    return re.match(rf'^({_num}!)?(0|{_num})(\.(0|{_num}))*((a|b|rc)(0|{_num}))?(\.post(0|{_num}))?(\.dev(0|{_num}))?$', version) is not None


def is_pre_release(version: str) -> bool:
    return re.match(rf'(a|b|rc)(0|{_num})', version) is not None


class PackageType(Enum):
    bdist_dmg = auto()
    bdist_dumb = auto()
    bdist_egg = auto()
    bdist_msi = auto()
    bdist_rpm = auto()
    bdist_wheel = auto()
    bdist_wininst = auto()
    sdist = auto()


@dataclass
class Project:
    name: str
    
    created: datetime = datetime.now()
    documentation: str = ''
    total_size: int = 0
    releases: dict[str, Release] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return f'Project(name={self.name}, created={self.created})'
    
    @property
    def normalized_name(self):
        return packaging.utils.canonicalize_name(self.name)
    
    @property
    def all_versions(self) -> tuple[str, ...]:
        return tuple(self.releases)
    
    @property
    def latest_version(self) -> str:
        return versions[0] if len(versions := self.all_versions) > 0 else ''
    
    @classmethod
    def get(cls, name: str, data: dict[str, Any]) -> Project:
        if name not in data:
            return cls(name)
        
        args = {'name': name}
        for field in fields(cls):
            if field.name == 'name':  # Already in dict
                continue
            elif field.name not in data:
                args[field.name] = field.default_factory() if field.default is MISSING else field.default
            elif field.name == 'releases':  # Special Case
                releases = data[field.name]
                args[field.name] = {Release.get(release_name, releases) for release_name in releases}
            else:
                args[field.name] = data[field.name]
        return cls(**args)


@dataclass
class Release:
    # project_id: Project
    name: str  # This is the version
    author: str = ''
    author_email: str = ''
    maintainer: str = ''
    maintainer_email: str = ''
    home_page: str = ''
    license: str = ''
    summary: str = ''
    keywords: str = ''
    platform: str = ''
    download_url: str = ''
    requires_python: str = ''
    created: datetime = datetime.now()
    description: str = ''
    yanked: bool = False
    yanked_reason: str = ''
    classifiers: list[str] = field(default_factory=dict)
    files: list[File] = field(default_factory=dict)
    
    # dependencies = orm.relationship(
    #     "Dependency",
    #     backref="release",
    #     cascade="all, delete-orphan",
    #     passive_deletes=True,
    # )
    #
    # _requires = _dependency_relation(DependencyKind.requires)
    # requires = association_proxy("_requires", "specifier")
    #
    # _provides = _dependency_relation(DependencyKind.provides)
    # provides = association_proxy("_provides", "specifier")
    #
    # _obsoletes = _dependency_relation(DependencyKind.obsoletes)
    # obsoletes = association_proxy("_obsoletes", "specifier")
    #
    # _requires_dist = _dependency_relation(DependencyKind.requires_dist)
    # requires_dist = association_proxy("_requires_dist", "specifier")
    #
    # _provides_dist = _dependency_relation(DependencyKind.provides_dist)
    # provides_dist = association_proxy("_provides_dist", "specifier")
    #
    # _obsoletes_dist = _dependency_relation(DependencyKind.obsoletes_dist)
    # obsoletes_dist = association_proxy("_obsoletes_dist", "specifier")
    #
    # _requires_external = _dependency_relation(DependencyKind.requires_external)
    # requires_external = association_proxy("_requires_external", "specifier")
    #
    # _project_urls = _dependency_relation(DependencyKind.project_url)
    # project_urls = association_proxy("_project_urls", "specifier")
    
    uploader: str = ''  # User that created the issue
    uploaded_via: str = ''
    
    @property
    def is_pre_release(self):
        return is_pre_release(self.name)
    
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
    
    @classmethod
    def get(cls, name: str, project_data: dict[str, Any] = None) -> Release:
        if project_data is None:
            return cls(name)


class File:
    # release: Release
    python_version: str
    requires_python: str
    package_type: PackageType
    comment_text: str
    filename: str
    path: Path
    size: int
    has_signature: bool
    md5_digest: str
    sha256_digest: str
    blake2_256_digest: str
    upload_time: datetime = datetime.now()
    uploaded_via: str = ''
    
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
