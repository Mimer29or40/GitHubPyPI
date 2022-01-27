import cgi
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Optional

import readme_renderer.markdown
import readme_renderer.rst

import warehub
from .database import Database
from .model import CONFIG_FILE, PROJECT_DIR, SIMPLE_DIR, PYPI_DIR, Project, Release, File, FILES_DIR, WEB_DIR, CURRENT_DIR
from .utils import delete_path

__all__ = [
    'generate_file_structure',
]


def get_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_FILE.read_text())
    
    if not isinstance(cfg, dict):
        raise ValueError('Invalid config format. Config must be a dict')
    
    if 'url' not in cfg:
        raise NameError('config does not specify a url')
    
    if 'title' not in cfg:
        raise NameError('config does not specify a title')
    
    if 'description' not in cfg:
        cfg['description'] = 'Welcome to your private Python package index!'
    
    if 'image_url' not in cfg:
        cfg['image_url'] = 'https://pypi.org/static/images/logo-small.95de8436.svg'
    
    return cfg


def generate_file_structure():
    config = get_config()
    
    for dir_path in [PROJECT_DIR, SIMPLE_DIR, PYPI_DIR]:
        delete_path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
    
    generate_pages(config)
    
    generate_simple(config)
    
    generate_json(config)


def generate_pages(config: dict[str, Any]) -> None:
    def generate_release(path: Path, project: Project, release: Release, show_version: bool = False) -> str:
        renderers = {
            'text/plain':    None,
            'text/x-rst':    readme_renderer.rst,
            'text/markdown': readme_renderer.markdown,
        }
        
        links = ''
        for name, url in release.urls.items():
            indent = ' ' * 20
            links += f'\n{indent}<li><a href="{url}" rel="nofollow">{name}</a></li>'
        
        meta = ''
        for name, check, string in {
            ('License', release.license, release.license),
            ('Author', release.author, f'<a href="mailto:{release.author_email}">{release.author}</a>'),
            ('Maintainer', release.maintainer, f'<a href="mailto:{release.maintainer_email}">{release.maintainer}</a>'),
            ('Requires', release.requires_python, release.requires_python),
            ('Platform', release.platform, release.platform),
        }:
            if check is not None:
                indent = ' ' * 16
                meta += f'\n{indent}<p class="elem"><strong>{name}: </strong>{string}</p>'
        
        classifiers: DefaultDict[str, list[str]] = defaultdict(list)
        for classifier in release.classifiers:
            group, tag = classifier.split(' :: ', 1)
            classifiers[group].append(tag)
        
        classifiers_str = ''
        for group, tags in classifiers.items():
            tags_str = ''
            for tag in sorted(tags):
                indent = ' ' * 28
                tags_str += f'\n{indent}<li>{tag}</li>'
            indent = ' ' * 20
            classifiers_str += '\n'.join([
                f'',
                f'{indent}<li>',
                f'{indent}    <strong>{group}</strong>',
                f'{indent}    <ul>{tags_str}',
                f'{indent}    </ul>',
                f'{indent}</li>',
            ])
        
        description = release.description['raw']
        content_type, params = cgi.parse_header(release.description['content_type'])
        renderer = renderers.get(content_type, readme_renderer.rst)
        
        if description in {None, "UNKNOWN\n\n\n"}:
            description = ''
        elif renderer:
            description = renderer.render(description, **params) or ''
        
        releases = ''
        for r in Database.get(Release, where=Release.project_id == project.id):
            indent = ' ' * 16
            # TODO - Pre-Release?, Yanked?, etc
            releases += '\n'.join([
                f'',
                f'{indent}<a class="card" href="{r.version}/">',
                f'{indent}    <span class="version">{r.version}</span>',
                f'{indent}</a>',
            ])
        
        files = ''
        for f in Database.get(File, where=File.release_id == release.id):
            indent = ' ' * 16
            files += '\n'.join([
                f'',
                f'{indent}<a class="card" href="{config["url"]}/{FILES_DIR.name}/{f.name}">',
                f'{indent}    {f.name}',
                f'{indent}</a>',
            ])
        
        template = WEB_DIR / 'release.html'
        template = template.read_text()
        
        for string, value in [
            ('%%WAREHUB_VERSION%%', warehub.__version__),
            ('%%URL%%', config['url']),
            ('%%TITLE%%', config['title']),
            ('%%IMAGE%%', config['image_url']),
            ('%%NAME%%', project.name),
            ('%%VERSION%%', release.version),
            ('%%PIP_VERSION%%', f'=={release.version}' if show_version else ''),
            ('%%SUMMARY%%', release.summary or ''),
            ('%%LINKS%%', links),
            ('%%META%%', meta),
            ('%%CLASSIFIERS%%', classifiers_str),
            ('%%DESCRIPTION%%', description),
            ('%%RELEASES%%', releases),
            ('%%FILES%%', files),
        ]:
            template = template.replace(string, value)
        
        file = path / 'index.html'
        file.write_text(template)
    
    projects_listing = ''
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
        
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
        
        project_dir = PROJECT_DIR / project.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        latest = releases[0]
        for release in releases:
            if release.version > latest.version:
                latest = release
            
            release_dir = project_dir / release.version
            release_dir.mkdir(parents=True, exist_ok=True)
            
            generate_release(release_dir, project, release, True)
        
        generate_release(project_dir, project, latest)
        
        indent = ' ' * 8
        projects_listing += '\n'.join([
            f'',
            f'{indent}<a class="card" href="{PROJECT_DIR.name}/{project.name}/">',
            f'{indent}    {project.name}<span class="version">{latest.version}</span>',
            f'{indent}    <span class="description">{latest.summary}</span>',
            f'{indent}</a>',
        ])
    
    homepage_template = WEB_DIR / 'homepage.html'
    homepage_template = homepage_template.read_text()
    
    for string, value in [
        ('%%WAREHUB_VERSION%%', warehub.__version__),
        ('%%URL%%', config['url']),
        ('%%TITLE%%', config['title']),
        ('%%DESCRIPTION%%', config['description']),
        ('%%IMAGE%%', config['image_url']),
        ('%%PACKAGES%%', projects_listing),
    ]:
        homepage_template = homepage_template.replace(string, value)
    
    homepage = CURRENT_DIR / 'index.html'
    homepage.write_text(homepage_template)


def generate_simple(config: dict[str, Any]) -> None:
    def create_simple(link_list: str) -> str:
        template = WEB_DIR / 'simple.html'
        template = template.read_text()
        
        for string, value in [
            ('%%WAREHUB_VERSION%%', warehub.__version__),
            ('%%TITLE%%', config['title']),
            ('%%IMAGE%%', config['image_url']),
            ('%%LIST%%', link_list),
        ]:
            template = template.replace(string, value)
        return template
    
    project_list = ''
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
        
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
            continue
        
        f_list = ''
        for release in releases:
            if not release.yanked:
                for file in Database.get(File, where=File.release_id == release.id):
                    f_list += f'\n    <a href="{config["url"]}/{FILES_DIR.name}/{file.name}">{file.name}</a><br/>'
        
        project_dir = SIMPLE_DIR / project.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        template = create_simple(f_list)
        
        project_file = project_dir / 'index.html'
        project_file.write_text(template)
        
        project_list += f'\n    <a class="card" href="{project.name}/">{project.name}</a><br/>'
    
    template = create_simple(project_list)
    
    landing = SIMPLE_DIR / 'index.html'
    landing.write_text(template)


def generate_json(config: dict[str, Any]) -> None:
    def create_json(path: Path, project: Project, release: Release):
        dir = path / 'json'
        dir.mkdir(parents=True, exist_ok=True)
        
        releases = {}
        for r in Database.get(Release, where=Release.project_id == project.id):
            releases[r.version] = [
                {
                    'filename':             f.name,
                    'python_version':       f.python_version,
                    'packagetype':          f.package_type,
                    'comment_text':         f.comment_text,
                    'size':                 f.size,
                    'has_sig':              f.has_signature,
                    'md5_digest':           f.md5_digest,
                    'digests':              {
                        'md5':        f.md5_digest,
                        'sha256':     f.sha256_digest,
                        'blake2_256': f.blake2_256_digest,
                    },
                    'downloads':            (-1),
                    'upload_time':          f.upload_time,
                    'upload_time_iso_8601': f.upload_time + 'Z',
                    'url':                  f'{config["url"]}/{FILES_DIR.name}/{f.name}',
                    'requires_python':      r.requires_python if r.requires_python else None,
                    'yanked':               r.yanked,
                    'yanked_reason':        r.yanked_reason or None,
                }
                for f in Database.get(File, where=File.release_id == r.id)
            ]
        
        file = dir / 'index.json'
        file.write_text(json.dumps({
            'info':            {
                'name':                     project.name,
                'version':                  release.version,
                'summary':                  release.summary,
                'description_content_type': release.description['content_type'],
                'description':              release.description['raw'],
                'keywords':                 release.keywords,
                'license':                  release.license,
                'classifiers':              release.classifiers,
                'author':                   release.author,
                'author_email':             release.author_email,
                'maintainer':               release.maintainer,
                'maintainer_email':         release.maintainer_email,
                'requires_python':          release.requires_python,
                'platform':                 release.platform,
                'downloads':                {'last_day': -1, 'last_week': -1, 'last_month': -1},
                'package_url':              f'{config["url"]}/{PROJECT_DIR.name}/{project.name}',
                'project_url':              f'{config["url"]}/{PROJECT_DIR.name}/{project.name}',
                'project_urls':             release.urls,
                'release_url':              f'{config["url"]}/{PROJECT_DIR.name}/{project.name}/{release.version}',
                'requires_dist':            release.dependencies['requires_dist'],
                'docs_url':                 None,
                'bugtrack_url':             None,
                'home_page':                release.home_page,
                'download_url':             release.download_url,
                'yanked':                   release.yanked,
                'yanked_reason':            release.yanked_reason or None,
            },
            'urls':            releases[release.version],
            'releases':        releases,
            'vulnerabilities': [],
            'last_serial':     (-1),
        }, indent=4))
    
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
        
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
            continue
        
        project_dir = PYPI_DIR / project.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        latest: Optional[Release] = None
        for release in releases:
            if not release.yanked:
                if latest is None or release.version > latest.version:
                    latest = release
                
                create_json(project_dir / release.version, project, release)
        
        if latest is not None:
            create_json(project_dir, project, latest)


if __name__ == '__main__':
    generate_file_structure()
