"""Save file field value conversion utils.


Copyright (c) 2022 Ali Farzanrad <ali_farzanrad@riseup.net>

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

from struct import Struct, unpack


class Type:
    BY_NAME = {}

    def __init__(self, name=None):
        if name != getattr(self, "name", None):
            self.name = name

    def __new__(cls, name=None):
        if name:
            name = name.split(":", 1)[0]
        cls = __class__.BY_NAME.get(name, cls)
        return super().__new__(cls)

    def __repr__(self):
        return getattr(self, "name", None) or "GenericType"

    def __init_subclass__(cls, name=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if name:
            __class__.BY_NAME[name] = cls

    from_bytes = to_bytes = bytes


class Array(Type, name="array"):
    def __init__(self, name):
        super().__init__(name)
        self.item = Type(name.split(":", 1)[1])

    def from_bytes(self, value):
        if len(value) < 4:
            raise ValueError("too small")
        res = []
        item = self.item
        item_size = item.size
        item = item.from_bytes
        for i in range(4, len(value), item_size):
            res.append(item(value[i : i + item_size]))
        if len(res) != unpack("<I", value[:4])[0]:
            raise ValueError("array size mismatch: %r" % value)
        return tuple(res)

    def to_bytes(self, value):
        return b"".join(map(self.item.to_bytes, value))


class Bool(Type, name="Bool"):
    size = 1

    @staticmethod
    def from_bytes(value):
        if len(value) != 1:
            raise ValueError("bad boolean size: %d" % len(value))
        if value[0] > 1:
            raise ValueError("bad boolean value: %d" % value[0])
        return bool(value[0])

    @staticmethod
    def to_bytes(value):
        return bytes([bool(value)])


class Int32(Type, name="Int32"):
    size = 4

    @staticmethod
    def from_bytes(value):
        return unpack("<i", value)[0]

    to_bytes = Struct("<i").pack


class Float(Type, name="Float"):
    size = 4

    @staticmethod
    def from_bytes(value):
        return unpack("<f", value)[0]

    to_bytes = Struct("<f").pack
