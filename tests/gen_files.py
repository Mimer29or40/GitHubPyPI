import cgi
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict

import readme_renderer.markdown
import readme_renderer.rst

import warehub
from warehub import CONFIG_FILE, SIMPLE_DIR, PYPI_DIR, Database, Project, Release, WEB_DIR, CURRENT_DIR, File, FILES_DIR, PROJECT_DIR


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


def delete_path(path: Path) -> None:
    if path.is_dir():
        for child in path.glob('*'):
            delete_path(child)
        path.rmdir()
    else:
        path.unlink(missing_ok=True)


def generate_file_structure():
    config = get_config()
    
    for dir_path in [PROJECT_DIR, SIMPLE_DIR, PYPI_DIR]:
        delete_path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
    
    generate_pages(config)
    
    generate_simple(config)
    
    generate_json(config)


def generate_pages(config: dict[str, Any]) -> None:
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
        releases_listing = ''
        for release in releases:
            if release.version > latest.version:
                latest = release
            
            release_dir = project_dir / release.version
            release_dir.mkdir(parents=True, exist_ok=True)
            
            release_template = generate_release(config, project, release)
            
            project_file = release_dir / 'index.html'
            project_file.write_text(release_template)
            
            releases_listing += '\n'.join([
                f'',
                f'    <a class="card" href="{release.version}/">',
                f'        <span class="version">{release.version}</span>',
                f'    </a>',
            ])
        
        project_template = generate_release(config, project, latest, releases_listing)
        
        project_file = project_dir / 'index.html'
        project_file.write_text(project_template)
        
        projects_listing += '\n'.join([
            f'',
            f'    <a class="card" href="{PROJECT_DIR.name}/{project.name}/">',
            f'        {project.name}<span class="version">{latest.version}</span>',
            f'        <span class="description">{latest.summary}</span>',
            f'    </a>',
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


def generate_release(config: dict[str, Any], project: Project, release: Release, releases_listing=None) -> str:
    renderers = {
        'text/plain':    None,
        'text/x-rst':    readme_renderer.rst,
        'text/markdown': readme_renderer.markdown,
    }
    
    links = ''
    if release.home_page is not None:
        links += f'\n                <li><a href="{release.home_page}" rel="nofollow">Homepage</a></li>'
    if release.download_url is not None:
        links += f'\n                <li><a href="{release.home_page}" rel="nofollow">Download</a></li>'
    for project_url in release.project_urls:
        name, url = project_url.split(', ')
        links += f'\n                <li><a href="{url}" rel="nofollow">{name}</a></li>'
    
    meta = ''
    if release.license is not None:
        meta += f'            <p class="elem"><strong>License: </strong>{release.license}</p>'
    if release.author is not None:
        meta += f'            <p class="elem"><strong>Author: </strong><a href="mailto:{release.author_email}">{release.author}</a></p>'
    if release.maintainer is not None:
        meta += f'            <p class="elem"><strong>Maintainer: </strong><a href="mailto:{release.maintainer_email}">{release.maintainer}</a></p>'
    if release.requires_python is not None:
        meta += f'            <p class="elem"><strong>Requires: </strong>{release.requires_python}</p>'
    if release.platform is not None:
        meta += f'            <p class="elem"><strong>Platform: </strong>{release.platform}</p>'
    
    classifiers: DefaultDict[str, list[str]] = defaultdict(list)
    for classifier in release.classifiers:
        group, tag = classifier.split(' :: ', 1)
        classifiers[group].append(tag)
    
    classifiers_str = ''
    for group, tags in classifiers.items():
        tags_str = ''
        for tag in sorted(tags):
            tags_str += f'\n                        <li>{tag}</li>'
        classifiers_str += '\n'.join([
            f'',
            f'                <li>',
            f'                    <strong>{group}</strong>',
            f'                    <ul>{tags_str}',
            f'                    </ul>',
            f'                </li>',
        ])
    
    description = release.description['raw']
    content_type, params = cgi.parse_header(release.description['content_type'])
    renderer = renderers.get(content_type, readme_renderer.rst)
    
    if description in {None, "UNKNOWN\n\n\n"}:
        description = ''
    elif renderer:
        description = renderer.render(description, **params) or ''
    
    template = WEB_DIR / ('release.html' if releases_listing is None else 'project.html')
    template = template.read_text()
    
    for string, value in [
        ('%%WAREHUB_VERSION%%', warehub.__version__),
        ('%%URL%%', config['url']),
        ('%%TITLE%%', config['title']),
        ('%%IMAGE%%', config['image_url']),
        ('%%NAME%%', project.name),
        ('%%VERSION%%', release.version),
        ('%%SUMMARY%%', release.summary or ''),
        ('%%LINKS%%', links),
        ('%%META%%', meta),
        ('%%CLASSIFIERS%%', classifiers_str),
        ('%%DESCRIPTION%%', description),
        ('%%RELEASES%%', releases_listing or ''),
    ]:
        template = template.replace(string, value)
    return template


def generate_simple(config: dict[str, Any]) -> None:
    def simple(list=None) -> str:
        template = WEB_DIR / 'simple.html'
        template = template.read_text()
        
        for string, value in [
            ('%%WAREHUB_VERSION%%', warehub.__version__),
            ('%%TITLE%%', config['title']),
            ('%%IMAGE%%', config['image_url']),
            ('%%LIST%%', list or ''),
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
        
        latest = releases[0]
        list = ''
        for release in releases:
            if release.version > latest.version:
                latest = release
            for file in Database.get(File, where=File.release_id == release.id):
                list += f'\n    <a href="/{FILES_DIR.name}/{file.name}">{file.name}</a><br/>'
        
        project_dir = SIMPLE_DIR / project.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        template = simple(list)
        
        project_file = project_dir / 'index.html'
        project_file.write_text(template)
        
        project_list += f'\n    <a class="card" href="{project.name}/">{project.name}</a><br/>'
    
    template = simple(project_list)
    
    landing = SIMPLE_DIR / 'index.html'
    landing.write_text(template)


def generate_json(config: dict[str, Any]) -> None:
    pass


if __name__ == '__main__':
    generate_file_structure()
