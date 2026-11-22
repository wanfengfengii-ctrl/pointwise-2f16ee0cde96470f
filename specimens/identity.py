from archive_core import text_key


def specimen_key(value):
    return text_key(value, 'specimen ID')


def source_reference(value):
    return text_key(value, 'measurement slip reference')
