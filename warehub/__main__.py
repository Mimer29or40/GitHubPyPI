import argparse

import warehub
from warehub.secrets import Secrets

secrets = Secrets()


def github(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub github',
        description='Parses the args provided the github environment variable'
    )
    
    args = parser.parse_args(argv)
    print(args)


def upload(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog='warehub upload'
    )
    
    parser.add_argument(
        'repository',
        help='The path of the github repository. {user}/{repo_name}',
    )
    
    default_domain = 'https://api.github.com'
    parser.add_argument(
        '-d', '--domain',
        default=default_domain,
        help=f'The domain of the github api. '
             f'[Default: {default_domain}]'
    )
    
    default_username = secrets.get_name('USERNAME')
    parser.add_argument(
        '-u', '--username',
        default=default_username,
        help=f'The username to use to login to github. '
             f'Surround with {secrets.token} to get from environment (case sensitive). '
             f'[Default: {default_username}]'
    )

    default_password = secrets.get_name('PASSWORD')
    parser.add_argument(
        '-p', '--password',
        default=default_password,
        help=f'The password to use to login to github. '
             f'Surround with {secrets.token} to get from environment (case sensitive). '
             f'[Default: {default_password}]'
    )
    
    args = parser.parse_args(argv)
    print(args)


commands = {c.__name__: c for c in {
    github,
    upload
}}


def main():
    parser = argparse.ArgumentParser(
        prog='warehub',
        description='Upload a package to github pypi'
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'%(prog)s version {warehub.__version__}',
    )
    parser.add_argument(
        'command',
        choices=commands,
    )
    parser.add_argument(
        'args',
        help=argparse.SUPPRESS,
        nargs=argparse.REMAINDER,
    )
    
    args = parser.parse_args()
    print(args)
    
    commands[args.command](args.args)


if __name__ == '__main__':
    main()
