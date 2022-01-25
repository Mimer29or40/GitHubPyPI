from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field, fields, asdict, MISSING
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import Optional

import packaging.utils
import requests

from .database import Database
from .model import Project, Release, File
from .package import Package

__version__ = '1.0.0'

from .secrets import Secrets
from .utils import file_size_str

ONE_MB = 1024 * 1024
ONE_GB = 1024 * 1024 * 1024

MAX_FILE_SIZE = 100 * ONE_MB
MAX_SIG_SIZE = 8 * 1024
MAX_PROJECT_SIZE = 10 * ONE_GB

PATH_HASHER = "blake2_256"

secrets = Secrets()

default_domain = 'https://api.github.com'
default_username = secrets.get_name('USERNAME')
default_password = secrets.get_name('PASSWORD')


@dataclass(frozen=True)
class Argument:
    names: tuple[str, ...]
    help: str = ''


@dataclass(frozen=True)
class Arguments:
    repository: str = field(
        metadata=asdict(Argument(
            names=('repository',),
            help='The path of the github repository. {user}/{repo_name}'
        ))
    )
    domain: str = field(
        default=default_domain,
        metadata=asdict(Argument(
            names=('-d', '--domain'),
            help=f'The domain of the github api. '
                 f'[Default: {default_domain}]'
        ))
    )
    username: str = field(
        default=default_username,
        metadata=asdict(Argument(
            names=('-u', '--username'),
            help=f'The username to use to login to github. '
                 f'Surround with {secrets.token} to get from environment (case sensitive). '
                 f'[Default: {default_username}]'
        ))
    )
    password: str = field(
        default=default_password,
        metadata=asdict(Argument(
            names=('-p', '--password'),
            help=f'The password to use to login to github. '
                 f'Surround with {secrets.token} to get from environment (case sensitive). '
                 f'[Default: {default_password}]'
        ))
    )


def github(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub github',
        description='Parses the args provided the github environment variable'
    )
    
    parser.parse_args(argv)
    
    if 'GITHUB_CONTEXT' not in os.environ:
        raise KeyError(f'\'GITHUB_CONTEXT\' is not in environment. Did you mean to run \'cli\'')
    
    # Get the context from the environment variable
    context = json.loads(os.environ['GITHUB_CONTEXT'])
    
    arguments: dict[str, Argument] = {f.name: Argument(**f.metadata) for f in fields(Arguments)}
    
    args = []
    for line in context['event']['issue']['body'].replace('\r', '').split('\n'):
        if (match := re.match(r'- \*\*(\w+):\*\*\s*(.*)', line)) is not None:
            if (name := match.group(1).lower()) in arguments:
                pre = arguments[name].names[0]
                if '-' not in pre:
                    args.append(match.group(2))
                else:
                    args.extend([pre, match.group(2)])
    cli(args)


def cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub cli',
    )
    
    for field in fields(Arguments):
        argument = Argument(**field.metadata)
        parser.add_argument(
            *argument.names,
            metavar=field.name,
            default=None if field.default is MISSING else field.default,
            help=argument.help,
        )
    
    handle_arguments(Arguments(**vars(parser.parse_args(argv))))


commands = {c.__name__: c for c in {
    github,
    cli
}}


def handle_arguments(args: Arguments):
    pprint(args)
    
    repository_url = f'{args.domain}/repos/{args.repository}'
    
    username = secrets.get(u) if secrets.is_name(u := args.username) else u
    password = secrets.get(p) if secrets.is_name(p := args.password) else p
    
    auth = (username or '', password or '') if username or password else None

    print(f'Downloading Releases from: {repository_url}')
    response = requests.get(f'{repository_url}/releases', auth=auth)
    releases_obj = response.json()
    if response.status_code != requests.codes.ok:
        raise LookupError(f'Could not get information on release for \'{args.repository}\':\n\t{releases_obj["message"]}')
    
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        
        files: list[Path] = []
        for info in releases_obj:
            for asset in info['assets']:
                file_url = asset['browser_download_url']

                print(f'Downloading File: {file_url}')
                download = requests.get(file_url, auth=auth)
                if download.status_code != requests.codes.ok:
                    raise LookupError(f'Could not download \'{file_url}\': {download.status_code}')
                
                downloaded_file = temp_dir / Path(file_url).name
                downloaded_file.write_bytes(download.content)
                
                files.append(downloaded_file)
        
        # Determine if the user has passed in pre-signed distributions
        signatures: dict[str, Path] = {f.name: f for f in files if f.suffix == '.asc'}
        
        urls = set()
        for file in files:
            if file.suffix != '.asc' and (p := make_package(file, signatures)) is not None:
                urls.add(f'simple/{p.name}/{p.version}/')
        
        print('View new Packages at:')
        for url in urls:
            print(f'\t{url}')


def make_package(file: Path, signatures: dict[str, Path]) -> Optional[Package]:
    """Create and sign a package, based off of filename, signatures and settings."""
    package = Package(file, None)
    
    if (signed_name := package.signed_file.name) in signatures:
        package.add_gpg_signature(signatures[signed_name])
    
    print(f'Package created for file: \'{package.file.name}\' ({file_size_str(package.file.stat().st_size)})')
    if package.gpg_signature:
        print(f'\tSigned with {package.signed_file}')
    
    projects = Database.get(Project, where=Project.name == package.name)
    if len(projects) == 0:
        project = Project(
            name=package.name,
            created=_get_now(),
            documentation='',
            total_size=0,
        )
        Database.put(Project, project)
    elif len(projects) > 1:
        raise ValueError(f'Multiple Projects found with name \'{package.name}\'')
    else:
        project = projects[0]
    
    releases = Database.get(Release, where=(
            (Release.project_id == project.id) &
            (Release.version == package.version)
    ))
    if len(releases) == 0:
        release = Release(
            project_id=project.id,
            version=package.version,
            created=_get_now(),
            author=package.author,
            author_email=package.author_email,
            maintainer=package.maintainer,
            maintainer_email=package.maintainer_email,
            summary=package.summary,
            description={
                'raw':          package.description or '',
                'content_type': package.description_content_type
            },
            keywords=package.keywords,
            classifiers=package.classifiers,
            license=package.license,
            platform=package.platform,
            home_page=package.home_page,
            download_url=package.download_url,
            requires_python=package.requires_python,
            dependencies={
                'requires':          package.requires or [],
                'provides':          package.provides or [],
                'obsoletes':         package.obsoletes or [],
                'requires_dist':     package.requires_dist or [],
                'provides_dist':     package.provides_dist or [],
                'obsoletes_dist':    package.obsoletes_dist or [],
                'requires_external': package.requires_external or [],
                'project_urls':      package.project_urls or [],
            },
            # uploader=package.uploader,
            # uploaded_via=package.uploaded_via,
            # yanked=package.yanked,
            # yanked_reason=package.yanked_reason,
        )
        Database.put(Release, release)
    elif len(releases) > 1:
        raise ValueError(f'Multiple Releases found with name \'{package.name}\'')
    else:
        release = releases[0]
    
    # Update project information if release if greater version than project
    
    if package.file.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f'File too large. Limit for files is {file_size_str(MAX_FILE_SIZE)}')
    
    files = Database.get(File, where=File.name == package.file.name)
    if len(files) > 0:
        raise ValueError('File already exists')
    
    # TODO - Check for duplicates
    # TODO - Check for multiple sdist
    # TODO - Check for valid dist file
    # TODO - Check that if it's a binary wheel, it's on a supported platform
    
    if package.gpg_signature is not None:
        has_signature = True
        # with open(os.path.join(tmpdir, filename + '.asc'), 'wb') as fp:
        #     signature_size = 0
        #     for chunk in iter(lambda: package_data['gpg_signature'].file.read(8096), b''):
        #         signature_size += len(chunk)
        #         if signature_size > MAX_SIG_SIZE:
        #             raise _exc_with_message(HTTPBadRequest, 'Signature too large.')
        #         fp.write(chunk)
        #
        # # Check whether signature is ASCII armored
        # with open(os.path.join(tmpdir, filename + '.asc'), 'rb') as fp:
        #     if not fp.read().startswith(b'-----BEGIN PGP SIGNATURE-----'):
        #         raise _exc_with_message(HTTPBadRequest, 'PGP signature isn\'t ASCII armored.')
    else:
        has_signature = False
    
    # file = File.get(release, package_data['file'])
    file = File(
        release_id=release.id,
        name=package.file.name,
        path=f'files/{package.file.name}',
        python_version=package.pyversion,
        package_type=package.filetype,
        comment_text=package.comment,
        size=package.file.stat().st_size,
        has_signature=has_signature,
        md5_digest=package.md5_digest,
        sha256_digest=package.sha256_digest,
        blake2_256_digest=package.blake2_256_digest,
        upload_time=_get_now(),
        # uploaded_via=,
    )
    Database.put(File, file)
    
    shutil.copy(package.file, file.path)
    
    # TODO - Move to files
    
    project.total_size += file.size
    if project.total_size > MAX_PROJECT_SIZE:
        raise ValueError('Project is now too large')
    
    # Database.commit()
    
    return package


def _get_now() -> str:
    return datetime.now().isoformat()
