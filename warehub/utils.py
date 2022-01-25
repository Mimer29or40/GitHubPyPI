def file_size_str(size: int) -> str:
    suffix = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    i = 0
    while size > 1024 and i < len(suffix) - 1:
        size = size // 1024
        i += 1
    return f'{size} {suffix[i]}'
