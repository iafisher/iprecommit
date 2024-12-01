"""Python module which parses and emits TOML.

Released under the MIT license.
"""

from . import decoder

__version__ = "0.10.2"
_spec_ = "0.5.0"

load = decoder.load
loads = decoder.loads
TomlDecoder = decoder.TomlDecoder
TomlDecodeError = decoder.TomlDecodeError
TomlPreserveCommentDecoder = decoder.TomlPreserveCommentDecoder
