import argparse

import warehub


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
        choices=warehub.commands,
    )
    parser.add_argument(
        'args',
        help=argparse.SUPPRESS,
        nargs=argparse.REMAINDER,
    )
    
    args = parser.parse_args()
    
    warehub.commands[args.command](args.args)


if __name__ == '__main__':
    main()
