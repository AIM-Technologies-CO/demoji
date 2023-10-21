"""Find and replace emojis within text strings.

The set of emojis is refreshable from its canonical source at
http://www.unicode.org/emoji/charts/full-emoji-list.html.
"""

__all__ = (
    "findall",
    "findall_list",
    "last_downloaded_timestamp",
    "replace",
    "replace_with_desc",
)
__version__ = "1.1.0"

import datetime
import functools
import logging
import os.path
import re
import sys
import warnings
import json
import pathlib
import re
import time
import colorama
import requests

try:
    # Enable faster loads with ujson if installed
    import ujson as json
except ImportError:
    import json

logging.getLogger(__name__).addHandler(logging.NullHandler())

if sys.version_info >= (3, 7):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

# Download endpoint
EMOJI_VERSION = "latest"
URL = "https://unicode.org/Public/emoji/%s/emoji-test.txt" % EMOJI_VERSION


_depr_msg = (
    "The %s attribute is deprecated"
    " and will be removed from demoji in a future version."
    " It is an unused attribute as emoji codes are now distributed"
    " directly with the demoji package."
)


def __getattr__(name):
    # Warn about deprecated attributes that are no longer used
    if name == "DIRECTORY":
        warnings.warn(
            _depr_msg % "demoji.DIRECTORY",
            FutureWarning,
            stacklevel=2,
        )
        return os.path.join(os.path.expanduser("~"), ".demoji")
    if name == "CACHEPATH":
        warnings.warn(
            _depr_msg % "demoji.CACHEPATH",
            FutureWarning,
            stacklevel=2,
        )
        return os.path.join(
            os.path.join(os.path.expanduser("~"), ".demoji"), "codes.json"
        )
    raise AttributeError("module 'demoji' has no attribute '%s'" % name)


def cache_setter(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        set_emoji_pattern()
        return func(*args, **kwargs)

    return wrapper


@cache_setter
def findall(string):
    """Find emojis within ``string``.

    :param string: The input text to search
    :type string: str
    :return: A dictionary of ``{emoji: description}``
    :rtype: dict
    """

    return {f: _CODE_TO_DESC[f] for f in set(_EMOJI_PAT.findall(string))}


@cache_setter
def findall_list(string, desc=True):
    """Find emojis within ``string``; return a list with possible duplicates.

    :param string: The input text to search
    :type string: str
    :param desc: Whether to return the description rather than emoji
    :type desc: bool
    :return: A list of ``[description, ...]`` in the order in which they
      are found.
    :rtype: list
    """

    if desc:
        return [_CODE_TO_DESC[k] for k in _EMOJI_PAT.findall(string)]
    else:
        return _EMOJI_PAT.findall(string)


@cache_setter
def replace(string, repl=""):
    """Replace emojis in ``string`` with ``repl``.

    :param string: The input text to search
    :type string: str
    :return: Modified ``str`` with replacements made
    :rtype: str
    """
    return _EMOJI_PAT.sub(repl, string)


@cache_setter
def replace_with_desc(string, sep=":"):
    """Replace emojis in ``string`` with their description.

    Add a ``sep`` immediately before and after ``string``.

    :param string: The input text to search
    :type string: str
    :param sep: String to put before and after the emoji description
    :type sep: str
    :return: New copy of ``string`` with replacements made and ``sep``
      immediately before and after each code
    :rtype: str
    """

    found = findall(string)
    result = string
    for emoji, desc in found.items():
        result = result.replace(emoji, sep + desc + sep)
    return result


# This variable is updated automatically from scripts/download_codes.py
_LDT = datetime.datetime(
    2021, 7, 18, 19, 57, 25, 20304, tzinfo=datetime.timezone.utc
)  # noqa: E501


def last_downloaded_timestamp():
    # This is retained as a callable rather than plain module attribute
    # for backwards compatibility.
    return _LDT


def _compile_codes(codes):
    escp = (re.escape(c) for c in sorted(codes, key=len, reverse=True))
    return re.compile(r"|".join(escp))


_EMOJI_PAT = None
_CODE_TO_DESC = {}


def _load_codes_from_file():
    with importlib_resources.open_text("demoji", "codes.json") as f:
        return json.load(f)


def set_emoji_pattern():
    global _EMOJI_PAT
    global _CODE_TO_DESC
    if _EMOJI_PAT is None:
        codes = _load_codes_from_file()
        _EMOJI_PAT = _compile_codes(codes)
        _CODE_TO_DESC.update(codes)


parent = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
CACHEPATH = parent / "codes.json"
MODULEPATH = parent / "__init__.py"


def download_codes(dest=CACHEPATH):
    # Ensure the target directory exists
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    codes = dict(stream_unicodeorg_emojifile(URL))
    _write_codes(codes, dest)


def _write_codes(codes, dest):
    print(
        colorama.Fore.YELLOW
        + "Writing emoji data to %s ..." % CACHEPATH
        + colorama.Style.RESET_ALL
    )
    with open(CACHEPATH, "w") as f:
        json.dump(codes, f, separators=(",", ":"))
    print(colorama.Fore.GREEN + "... OK" + colorama.Style.RESET_ALL)


def stream_unicodeorg_emojifile(url=URL):
    for codes, desc in _raw_stream_unicodeorg_emojifile(url):
        if ".." in codes:
            for cp in parse_unicode_range(codes):
                yield cp, desc
        else:
            yield parse_unicode_sequence(codes), desc


def parse_unicode_sequence(string):
    return "".join((chr(int(i.zfill(8), 16)) for i in string.split()))


def parse_unicode_range(string):
    start, _, end = string.partition("..")
    start, end = map(lambda i: int(i.zfill(8), 16), (start, end))
    return (chr(i) for i in range(start, end + 1))


def _raw_stream_unicodeorg_emojifile(url):
    colorama.init()
    print(
        colorama.Fore.YELLOW
        + "Downloading emoji data from %s ..." % URL
        + colorama.Style.RESET_ALL
    )
    resp = requests.request("GET", url, stream=True)
    print(
        colorama.Fore.GREEN
        + "... OK"
        + colorama.Style.RESET_ALL
        + " (Got response in %0.2f seconds)" % resp.elapsed.total_seconds()
    )

    POUNDSIGN = "#"
    POUNDSIGN_B = b"#"
    SEMICOLON = ";"
    SPACE = " "
    for line in resp.iter_lines():
        if not line or line.startswith(POUNDSIGN_B):
            continue
        line = line.decode("utf-8")
        codes, desc = line.split(SEMICOLON, 1)
        _, desc = desc.split(POUNDSIGN, 1)
        desc = desc.split(SPACE, 3)[-1]
        yield (codes.strip(), desc.strip())


def replace_lastdownloaded_timestamp():
    with open(MODULEPATH) as f:
        text = f.read()
    now = datetime.datetime.fromtimestamp(
        time.time(), tz=datetime.timezone.utc
    )
    ldt_re = re.compile(r"^_LDT = .*$", re.M)
    with open(MODULEPATH, "w") as f:
        f.write(ldt_re.sub("_LDT = %r  # noqa: E501" % now, text))
    print(
        colorama.Fore.GREEN
        + "Replaced timestamp with %r in %s" % (now, MODULEPATH)
        + colorama.Style.RESET_ALL
    )


if __name__ == "__main__":
    download_codes()
    replace_lastdownloaded_timestamp()