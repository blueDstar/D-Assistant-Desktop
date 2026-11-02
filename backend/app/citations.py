"""Validate source identifiers, including model-produced Unicode lookalikes."""
import re

SOURCE_MARK = re.compile(r'\[([SsＳЅѕСс]\d+)\]')


def validate_marks(content, known):
    invalid = set()
    def replace(match):
        raw = match.group(1)
        label = 'S' + str(int(raw[1:]))
        if label in known:
            return '[' + label + ']'
        invalid.add(label)
        return '[nguồn chưa xác minh: ' + label + ']'
    return SOURCE_MARK.sub(replace, content), sorted(invalid)
