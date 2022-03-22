"""Classes for extracting and changing nodes data.


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

from collections import namedtuple
from itertools import chain, repeat
from struct import Struct
from cp2077type import Type

pack16 = Struct("<H").pack
unpack16 = Struct("<H").unpack


class StructData(bytearray):
    __slots__ = "_name", "_strings"

    def __init__(self, strings, name, data):
        self._name = strings[name]
        self._strings = strings
        bytearray.__init__(self, data)

    def __len__(self):
        return unpack16(super().__getitem__(slice(0, 2)))[0]

    def __getitem__(self, key):
        name, t, slc = self._field_info(key)
        return t.from_bytes(bytes(super().__getitem__(slc)))

    def __setitem__(self, key, value):
        if isinstance(key, (bytes, str)):
            key = self._field_index(key)
        name, t, slc = self._field_info(key)
        value = t.to_bytes(value)
        sup = super()
        setitem = sup.__setitem__
        setitem(slc, value)
        if slc.stop is not None and slc.start + len(value) != slc.stop:
            change = slc.start + len(value) - slc.stop
            get = sup.__getitem__
            offset = Struct("<I")
            pack = offset.pack
            unpack = offset.unpack
            for i in range(key + 1, len(self)):
                slc = 6 + 8 * i
                slc = slice(slc, slc + 4)
                setitem(slc, pack(unpack(get(slc))[0] + change))

    def __repr__(self):
        return "%s(...%d fields...)" % (self._name, len(self))

    def __dir__(self):
        res = []
        strings = self._strings
        get = super().__getitem__
        for i in range(len(self)):
            start = 2 + 8 * i
            name = strings[unpack16(get(slice(start, start + 2)))[0]]
            if isinstance(name, str) and name.isidentifier():
                res.append(name)
        return res

    def __getattr__(self, name):
        try:
            return self[name]
        except LookupError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in type(self).__slots__:
            return super().__setattr__(name, value)
        try:
            self[name] = value
        except LookupError:
            raise AttributeError(name)

    def _field_index(self, name):
        if isinstance(name, bytes):
            try:
                name = name.decode()
            except Exception:
                pass
        strings = self._strings
        get = super().__getitem__
        for i in range(len(self)):
            start = 2 + 8 * i
            name_id = unpack16(get(slice(start, start + 2)))[0]
            if name == strings[name_id]:
                return i
        raise KeyError

    def _field_name(self, index):
        if not isinstance(index, int):
            raise TypeError
        get = super().__getitem__
        if index < 0 or index >= len(self):
            raise IndexError
        index *= 8
        name = unpack16(get(slice(index + 2, index + 4)))[0]
        return self._strings[name]

    def _field_info(self, index):
        if isinstance(index, (bytes, str)):
            index = self._field_index(index)
        if not isinstance(index, int):
            raise TypeError
        get = super().__getitem__
        n = len(self)
        if index < 0 or index >= n:
            raise IndexError
        unpack = Struct("<HHI").unpack
        start = 2 + 8 * index
        name, t, off = unpack(get(slice(start, start + 8)))
        end = None
        if index < n - 1:
            end = unpack(get(slice(start + 8, start + 16)))[2]
        strings = self._strings
        return strings[name], Type(strings[t]), slice(off, end)


class StructListNode(list):
    def __init__(self, data):
        unpack1 = Struct("<I").unpack
        unpack2 = Struct("<II").unpack
        if len(data) < 32 or unpack2(data[:8])[1] != len(data) - 8:
            raise Exception
        self._node_id = unpack1(data[:4])[0]
        self._unknown1 = bytes(data[8:16])
        string_ind = unpack2(data[16:24])
        data_ind = unpack2(data[24:32])
        if string_ind[0] >= string_ind[1] or data_ind[0] >= data_ind[1]:
            raise Exception
        base = 32
        if unpack2(self._unknown1)[1] >= 2:
            base += 4 + 8 * unpack1(data[base : base + 4])[0]
        self._unknown2 = bytes(data[32:base])
        data = bytes(data[base:])
        p = 0
        if string_ind[0] != p or (string_ind[1] - p) % 4:
            raise Exception
        self._strings = []
        p = string_ind[1]
        for i in range(string_ind[0], p, 4):
            ind = unpack1(data[i : i + 4])[0]
            if (ind & ((1 << 24) - 1)) != p:
                raise Exception
            ind >>= 24
            if ind < 1 or data[p + ind - 1]:
                raise Exception
            string = bytes(data[p : p + ind - 1])
            if 0 in string:
                raise Exception
            try:
                if string.decode().encode() == string:
                    string = string.decode()
            except Exception:
                pass
            self._strings.append(string)
            p += ind
        if len(set(self._strings)) != len(self._strings):
            raise Exception
        if data_ind[0] != p or (data_ind[1] - p) % 8:
            raise Exception
        p = data_ind[1]
        value = [
            unpack2(data[i : i + 8]) for i in range(data_ind[0], p, 8)
        ]
        if value:
            if value[0][1] != p:
                raise Exception
        else:
            if len(data) != p:
                raise Exception
        for i, (ind, p) in enumerate(value):
            end = None
            if i + 1 < len(value):
                end = value[i + 1][1]
                if end < p:
                    raise Exception
            value[i] = StructData(self._strings, ind, data[p:end])
        super().__init__(value)

    def __dir__(self):
        res = {}
        for item in self:
            name = item._name
            if isinstance(name, str) and name.isidentifier():
                res[name] = name not in res
        return list(res)

    def __getattr__(self, name):
        res = []
        for item in self:
            if item._name == name:
                res.append(item)
        if len(res) != 1:
            raise AttributeError(name)
        return res[0]

    def __bytes__(self):
        pack1 = Struct("<I").pack
        pack2 = Struct("<II").pack
        data = bytearray(4 * len(self._strings))
        string_ind = 0, len(data)
        for i, string in enumerate(self._strings):
            if isinstance(string, str):
                string = string.encode()
            if 0 in string:
                raise Exception
            string += b"\x00"
            n = len(string)
            if n > 255:
                raise Exception
            offset = string_ind[0] + 4 * i
            data[offset : offset + 4] = pack1(n << 24 | len(data))
            data.extend(string)
        data_ind = len(data)
        data.extend(bytes(8 * len(self)))
        data_ind = data_ind, len(data)
        si = {s: i for i, s in enumerate(self._strings)}
        for i, item in enumerate(self):
            name = si[item._name]
            offset = data_ind[0] + 8 * i
            data[offset : offset + 8] = pack2(name, len(data))
            data.extend(bytes(item))
        del si
        string_ind = pack2(*string_ind)
        data_ind = pack2(*data_ind)
        h = self._unknown1 + string_ind + data_ind + self._unknown2
        return pack2(self._node_id, len(h) + len(data)) + h + data


def parse_node(data, path):
    try:
        return StructListNode(data)
    except Exception:
        pass
    return bytearray(data)
