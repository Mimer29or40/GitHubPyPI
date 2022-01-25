from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pprint import pprint

from warehub.database import Database, Table


@dataclass
class Entry(Table):
    name: str


def main():
    Database.file(Path('test.json'))
    
    entry = Entry('test')
    print(entry)
    entry.__data__ = {
        'name': 'Renamed',
    }
    print(entry)
    
    # entry1 = Entry(1, 'Test')
    # print(entry1.name)
    
    # print(Database.get(Entry, where=(Entry.name == 'thing')))
    # Database.put(Entry, entry)
    # Database.put(Entry, entry1)
    
    # pprint(Database.get(Entry))
    # pprint(Database.get(Entry, where={'name': r'Test'}))
    
    entry = Entry('Added Entry')
    print(entry)
    Database.put(Entry, entry)
    pprint(Database.get(Entry))
    
    popped = Database.pop(Entry, where=Entry.name != 'Added Entry')
    pprint(popped)
    
    entries = Database.get(Entry)
    pprint(entries)
    for entry in entries:
        entry.name = 'RENAMED'
    pprint(Database.get(Entry))


if __name__ == '__main__':
    main()
