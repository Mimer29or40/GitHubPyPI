from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union, Any

import requests

from .metadata import MetadataForm
from .model import DATA_FILE, Project
from .package import Package


__version__ = '1.0.0'


def parse_issue(issue_ctx, *arguments: Union[tuple[str, str], tuple[str, str, str]]) -> dict[str, str]:
    secrets = json.loads(os.environ['SECRETS']) if 'SECRETS' in os.environ else {}
    
    args = {}
    for line in issue_ctx['body'].replace('\r', '').split('\n'):
        if (match := re.match(r'- \*\*(\w+):\*\*\s*(.*)', line)) is not None:
            name = match.group(1).lower()
            value = match.group(2)
            
            if (match := re.match(r'##(\w+)##', value)) is not None:
                if match.group(1) not in secrets:
                    raise KeyError(f'Requested secret not present: %%{match.group(1)}%%')
                value = secrets[match.group(1)]
            
            args[name] = value
    
    @dataclass(frozen=True)
    class Argument:
        name: str
        string: str
        default: str = None
    
    for argument in map(lambda a: Argument(*a), arguments):
        if argument.name not in args:
            if argument.default is None:
                raise ValueError(f'Missing required argument: {argument.name}\n\t{argument.string}')
            args[argument.name] = argument.default
        if args[argument.name].strip() == '':
            if argument.default is None:
                raise ValueError(f'Argument is empty: {argument.name}\n\t{argument.string}')
            args[argument.name] = argument.default
    
    print('--- Arguments Provided ---')
    for name, value in args.items():
        print(f'\t{name}: \'{value}\'')
    print()
    
    return args


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


def main():
    # Get the context from the environment variable
    context = json.loads(os.environ['GITHUB_CONTEXT'])
    issue_ctx = context['event']['issue']
    
    args = parse_issue(issue_ctx,
                       ('domain', 'The domain of the github api', 'https://api.github.com'),
                       ('repository', 'The path of the github repository'),
                       ('username', 'The username to use to access the repository', ''),
                       ('password', 'The password to use to access the repository', ''))
    
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
