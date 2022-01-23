from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from .metadata import MetadataForm
from .model import DATA_FILE, Project
from .package import Package

__version__ = '1.0.0'

from .secrets import Secrets

secrets = Secrets()


@dataclass(frozen=True)
class Argument:
    long_name: Optional[str]
    short_name: Optional[str]
    default: Optional[str] = field(default=None)
    help: str = field(default='')


default_domain = 'https://api.github.com'
default_username = secrets.get_name('USERNAME')
default_password = secrets.get_name('PASSWORD')

arguments: dict[str, Argument] = {
    'repository': Argument(long_name='repository',
                           short_name=None,
                           help='The path of the github repository. {user}/{repo_name}'
                           ),
    'domain':     Argument(long_name='--domain',
                           short_name='-d',
                           default=default_domain,
                           help=f'The domain of the github api. '
                                f'[Default: {default_domain}]'
                           ),
    'username':   Argument(long_name='--username',
                           short_name='-u',
                           default=default_username,
                           help=f'The username to use to login to github. '
                                f'Surround with {secrets.token} to get from environment (case sensitive). '
                                f'[Default: {default_username}]'
                           ),
    'password':   Argument(long_name='--password',
                           short_name='-p',
                           default=default_password,
                           help=f'The password to use to login to github. '
                                f'Surround with {secrets.token} to get from environment (case sensitive). '
                                f'[Default: {default_password}]'
                           ),
}


def github(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub github',
        description='Parses the args provided the github environment variable'
    )

    parser.parse_args(argv)
    
    if 'GITHUB_CONTEXT' not in os.environ:
        raise KeyError(f'\'GITHUB_CONTEXT\' is not in environment. Did you mean to run \'upload\'')
    
    # Get the context from the environment variable
    context = json.loads(os.environ['GITHUB_CONTEXT'])
    
    args = []
    for line in context['event']['issue']['body'].replace('\r', '').split('\n'):
        if (match := re.match(r'- \*\*(\w+):\*\*\s*(.*)', line)) is not None:
            if (name := match.group(1).lower()) in arguments:
                if (argument := arguments[name]).default is None:
                    args.append(match.group(2))
                else:
                    args.extend([argument.long_name, match.group(2)])
    upload(args)


def upload(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub upload',
    )
    
    for name, arg in arguments.items():
        names = (arg.long_name,) + (() if arg.short_name is None else (arg.short_name,))
        parser.add_argument(
            *names,
            metavar=name,
            default=arg.default,
            help=arg.help,
        )
    args = vars(parser.parse_args(argv))
    
    for name in arguments:
        if secrets.is_name(args[name]):
            args[name] = secrets.get(args[name])
    
    handle_arguments(**args)


commands = {c.__name__: c for c in {
    github,
    upload
}}


def handle_arguments(**args):
    print('--- Arguments Provided ---')
    for name, value in args.items():
        print(f'\t{name}: \'{value}\'')
    print()
    
    files = download_files(**args)
    
    # Determine if the user has passed in pre-signed distributions
    signatures: dict[str, Path] = {d.name: d for d in files if d.suffix == '.asc'}
    uploads = [i for i in files if i.suffix != '.asc']
    
    packages = [make_package(file, signatures) for file in uploads]
    
    data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
    
    added_packages = [p for p in packages if process_package(p, data)]
    
    urls = {f'simple/{package.safe_name}/{package.metadata.version}/' for package in added_packages}
    print('View at:')
    for url in urls:
        print(url)


def download_files(domain: str, repository: str, username: str, password: str) -> list[Path]:
    repository_url = f'{domain}/repos/{repository}'
    print(f'Downloading Releases from: {repository_url}')
    
    auth = (username or "", password or "") if username or password else None
    
    response = requests.get(f'{repository_url}/releases', auth=auth)
    releases_obj = response.json()
    if response.status_code != requests.codes.ok:
        raise LookupError(f'Could not get releases for \'{repository}\':\n\t{releases_obj["message"]}')
    
    files_to_download = []
    for release_info in releases_obj:
        for asset in release_info['assets']:
            files_to_download.append(asset['browser_download_url'])
    
    files_dir = Path('files')
    files_dir.mkdir(parents=True, exist_ok=True)
    
    files: list[Path] = []
    for file_url in files_to_download:
        download = requests.get(file_url, auth=auth)
        if download.status_code != requests.codes.ok:
            raise LookupError(f'Could not download \'{file_url}\': {download.status_code}')
        
        downloaded_file = files_dir / Path(file_url).name
        downloaded_file.write_bytes(download.content)
        
        files.append(downloaded_file)
    return files


def make_package(filename: Path, signatures: dict[str, Path]) -> Package:
    """Create and sign a package, based off of filename, signatures and settings."""
    package = Package(filename, None)
    
    if (signed_name := package.signed_file.name) in signatures:
        package.add_gpg_signature(signatures[signed_name])
    
    print(f'Package created for file: \'{package.file}\' ({package.file.stat().st_size})')
    if package.gpg_signature:
        print(f'\tSigned with {package.signed_file}')
    
    return package


def process_package(package: Package, data: dict[str, Any]) -> bool:
    package_data = package.metadata_dictionary()
    package_data.update(
        {
            # action
            ":action":          "file_upload",
            "protocol_version": "1",
        }
    )
    
    with package.file.open('rb') as fp:
        package_data.update(
            {'content': [package.file.name, fp, 'application/octet-stream']}
        )
    
    metadata = MetadataForm.from_kwargs(**package_data)
    
    project_name = package_data['name']
    
    project = Project.get(project_name, data)
    
    print(f'Uploading {package.file}')
    
    return True
