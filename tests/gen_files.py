import json
from pathlib import Path
from typing import Any

import warehub
from warehub import CONFIG_FILE, SIMPLE_DIR, PYPI_DIR, Database, Project, Release, TEMPLATE_DIR, CURRENT_DIR, File, FILES_DIR


def get_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_FILE.read_text())
    
    if not isinstance(cfg, dict):
        raise ValueError('Invalid config format. Config must be a dict')
    
    if 'title' not in cfg:
        raise NameError('config does not specify a title')
    
    if 'url' not in cfg:
        raise NameError('config does not specify a url')
    
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
    
    for dir_path in [SIMPLE_DIR, PYPI_DIR]:
        delete_path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)

    generate_homepage(config)
    generate_simple_landing(config)
    generate_simple_projects(config)


def generate_homepage(config: dict[str, Any]) -> None:
    projects_listing = ''
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
        
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
            continue
        
        latest = releases[0]
        for release in releases:
            if release.version > latest.version:
                latest = release
        
        projects_listing += '\n'.join([
            f'',
            f'    <a class="card" href="simple/{project.name}/">',
            f'        {project.name}<span class="version">{latest.version}</span>',
            f'        <span class="description">{latest.summary}</span>',
            f'    </a>',
        ])
    
    template = TEMPLATE_DIR / 'homepage.html'
    template = template.read_text()
    
    for string, value in [
        ('%%WAREHUB_VERSION%%', warehub.__version__),
        ('%%TITLE%%', config['title']),
        ('%%URL%%', config['url']),
        ('%%DESCRIPTION%%', config['description']),
        ('%%IMAGE%%', config['image_url']),
        ('%%PACKAGES%%', projects_listing),
    ]:
        template = template.replace(string, value)
    
    file = CURRENT_DIR / 'index.html'
    file.write_text(template)


def generate_simple_landing(config: dict[str, Any]) -> None:
    projects_listing = ''
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
        
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
            continue
        
        latest = releases[0]
        for release in releases:
            if release.version > latest.version:
                latest = release
        
        projects_listing += '\n'.join([
            f'',
            f'    <a class="card" href="{project.name}/">',
            f'        {project.name}<span class="version">{latest.version}</span>',
            f'        <span class="description">{latest.summary}</span>',
            f'    </a>',
        ])
    
    template = TEMPLATE_DIR / 'simple_landing.html'
    template = template.read_text()
    
    for string, value in [
        ('%%WAREHUB_VERSION%%', warehub.__version__),
        ('%%TITLE%%', config['title']),
        ('%%URL%%', config['url']),
        ('%%DESCRIPTION%%', config['description']),
        ('%%IMAGE%%', config['image_url']),
        ('%%PACKAGES%%', projects_listing),
    ]:
        template = template.replace(string, value)
    
    file = SIMPLE_DIR / 'index.html'
    file.write_text(template)


def generate_simple_projects(config: dict[str, Any]) -> None:
    for project in Database.get(Project):
        releases = Database.get(Release, where=Release.project_id == project.id)
    
        if len(releases) < 1:
            # This should never happen because a project is always created
            # with at least one release, but you never know...
            print('Projects does not have any release:', project)
            continue
        
        latest = releases[0]
        file_listing = ''
        for release in releases:
            if release.version > latest.version:
                latest = release
            for file in Database.get(File, where=File.release_id == release.id):
                file_listing += '\n'.join([
                    f'',
                    f'    <a href="{config["url"]}/{FILES_DIR.name}/{file.name}">{file.name}</a>',
                    f'    <br/>',
                ])

        project_template = TEMPLATE_DIR / 'simple_project.html'
        project_template = project_template.read_text()

        for string, value in [
            ('%%WAREHUB_VERSION%%', warehub.__version__),
            ('%%TITLE%%', config['title']),
            ('%%URL%%', config['url']),
            ('%%NAME%%', project.name),
            ('%%VERSION%%', latest.version),
            ('%%HOMEPAGE%%', latest.home_page),
            ('%%AUTHOR%%', latest.author),
            ('%%DESCRIPTION%%', latest.description['raw']),
            ('%%FILES%%', file_listing),
        ]:
            project_template = project_template.replace(string, value)

        project_dir = SIMPLE_DIR / project.name
        project_dir.mkdir(parents=True, exist_ok=True)

        project_file = project_dir / 'index.html'
        project_file.write_text(project_template)


if __name__ == '__main__':
    generate_file_structure()
