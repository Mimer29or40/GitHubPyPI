import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import warehub.command


@dataclass(frozen=True)
class Arguments:
    repository: str
    domain: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def args(self) -> list[str]:
        args: list[str] = []
        if self.domain is not None:
            args.extend([f'--domain', self.domain])
        if self.username is not None:
            args.extend([f'--username', self.username])
        if self.password is not None:
            args.extend([f'--password', self.password])
        args.append(self.repository)
        return args


def main():
    context = json.loads(os.environ['GITHUB_CONTEXT'])

    args: dict[str, str] = {}
    for line in context['event']['issue']['body'].replace('\r', '').split('\n'):
        if (match := re.match(r'- \*\*(\w+):\*\*\s*(.*)', line)) is not None:
            name = match.group(1).lower().strip()
            if (value := match.group(2).strip()) != '':
                args[name] = value

    arguments: Arguments = Arguments(**args)

    warehub.command.add(['--verbose'] + arguments.args())


if __name__ == '__main__':
    main()
