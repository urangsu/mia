"""Exact Excel extensions; ECM cache suffixes require an observed fresh open."""
from pathlib import PureWindowsPath
import re


def split_name(value):
    name=PureWindowsPath(str(value)).name
    suffix=PureWindowsPath(name).suffix.casefold()
    return (' '.join(name[:-len(suffix)].split()),suffix) if suffix in ('.xlsx','.xlsm') else (' '.join(name.split()),'')


def file_matches(actual,expected,*,allow_generated=False,allow_stem=False):
    stem,extension=split_name(expected)
    extension=extension or '.xlsx'
    candidate,actual_extension=split_name(actual)
    if allow_stem and not actual_extension and candidate.casefold()==stem.casefold():return True
    if actual_extension!=extension:return False
    if candidate.casefold()==stem.casefold():return True
    return bool(allow_generated and re.fullmatch(re.escape(stem)+r'_[0-9a-f]{16}_(?:usr)?[a-z0-9_-]{6,80}',candidate,re.I))
