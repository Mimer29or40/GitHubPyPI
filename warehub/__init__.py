from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass, field, fields, asdict, MISSING
from pathlib import Path
from pprint import pprint

import requests

from .database import *
from .generate import *
from .model import *
from .package import *
from .utils import *

__version__ = '1.0.0'

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
    
    Database.file(DATABASE_FILE)
    
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
    
    print('Generating File Structure')
    generate_file_structure()
