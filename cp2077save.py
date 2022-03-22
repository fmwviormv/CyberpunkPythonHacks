"""Save file management utils.


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

from pathlib import Path
from typing import NamedTuple
from cp2077chunk import (
    ChunkInfo,
    DataChunk,
    DataChunkTableChunk,
    EndChunk,
    HeaderChunk,
    NodeTableChunk,
)
from cp2077node import parse_node


class Data:
    def __init__(self, save):
        self._save = save

    def __len__(self):
        save = self._save
        offset = len(save.header) + len(save._data_chunks)
        return offset + sum(x.uncomp_len for x in save.data_chunks)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self[key : key + 1][0]
        if not isinstance(key, slice) or key.step not in (None, 1):
            raise TypeError(key)
        save = self._save
        header = save.header
        info = save._data_chunks
        data = save.data_chunks
        size = len(header) + len(info) + sum(x.uncomp_len for x in data)
        start, size = key.indices(size)[:2]
        size -= start
        res = []
        if size > 0 and start < len(header):
            res.append(header[start : start + size])
            size -= len(res[-1])
        start -= min(start, len(header))
        if size > 0 and start < len(info):
            res.append(info[start : start + size])
            size -= len(res[-1])
        start -= min(start, len(info))
        for chunk in data:
            if size > 0 and start < chunk.uncomp_len:
                res.append(chunk.data[start : start + size])
                size -= len(res[-1])
            start -= min(start, chunk.uncomp_len)
        return b"".join(res)

    def __setitem__(self, key, value):
        if isinstance(key, int):
            self[key : key + 1] = bytes([value])
            return
        if not isinstance(key, slice) or key.step not in (None, 1):
            raise TypeError(key)
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("expected bytes or bytearray")
        save = self._save
        header = save.header
        info = save._data_chunks
        data = save.data_chunks
        size = len(header) + len(info) + sum(x.uncomp_len for x in data)
        start, size = key.indices(size)[:2]
        size -= start
        chunk_size = data[0].uncomp_len
        if size != len(value):
            value = bytes(value) + self[start + size :]
            n = start + len(value)
            if n < len(header) + len(info) + chunk_size:
                raise ValueError("new size is too short")
            n = min(len(self) - start, len(value))
            self[start : start + n] = value[:n]
            start += n
            value = value[n:]
            if value:
                n = chunk_size - data[-1].uncomp_len
                if n > 0:
                    data[-1].data += value[:n]
                    value = value[n:]
                while value:
                    data.append(DataChunk(data=value[:chunk_size]))
                    value = value[chunk_size:]
            else:
                start -= len(header) + len(info)
                n = (start + chunk_size - 1) // chunk_size
                while len(data) > n:
                    data.pop()
                start %= chunk_size
                if data[-1].uncomp_len > start:
                    data[-1].data = data[-1].data[:start]
            return
        n = len(value)
        if size > 0 and start < len(header):
            n = min(len(header) - start, size)
            header[start : start + n] = value[:n]
            value = value[n:]
            size -= n
        start -= min(start, len(header))
        if size > 0 and start < len(info):
            n = min(len(info) - start, size)
            info[start : start + n] = value[:n]
            value = value[n:]
            size -= n
        start -= min(start, len(info))
        for chunk in data:
            if size > 0 and start < chunk_size:
                org = chunk.data
                if start > len(org):
                    raise IndexError
                new = bytearray(org)
                n = min(chunk_size - start, size)
                new[start : start + n] = value[:n]
                value = value[n:]
                size -= n
                if new != org:
                    chunk.data = new
                del org, new
            start -= min(start, chunk.uncomp_len)
        if start > 0:
            raise IndexError


class NodeDirectory:
    def __init__(self, save, node_id=None):
        self._save = save
        self._node_id = node_id
        self._ctx = []

    def __dir__(self):
        res = {}
        for _, item in self._items():
            name = item.name
            try:
                name = name.decode()
                if name.isidentifier():
                    res[name] = name not in res
            except Exception:
                pass
        return [item[0] for item in res.items() if item[1]]

    def __iter__(self):
        nodes_info = self._save.nodes_info
        next_id = self._node_id
        next_id = 0 if next_id is None else nodes_info[next_id].child
        while next_id is not None:
            yield next_id
            next_id = nodes_info[next_id].next

    def __len__(self):
        return len([*self])

    def __getattr__(self, name):
        res = None
        name = name.encode()
        for i, item in self._items():
            if name == item.name:
                if res is not None:
                    raise AttributeError(name)
                res = i
        if res is None:
            raise AttributeError(name)
        return NodeDirectory(self._save, res)

    def __getitem__(self, key):
        if isinstance(key, str):
            key = key.encode()
        if isinstance(key, int):
            res = key
        elif not isinstance(key, bytes):
            raise TypeError
        else:
            res = None
            for i, item in self._items():
                if key == item.name:
                    if res is not None:
                        raise AttributeError(name)
                    res = i
        if res is None:
            raise KeyError(key)
        return NodeDirectory(self._save, res)

    def __enter__(self):
        save = self._save
        nodes_info = save.nodes_info
        myinfo = [nodes_info[i] for i in self._address]
        path = tuple(i.name for i in myinfo)
        if myinfo:
            myinfo = myinfo[-1]
            offset = myinfo.offset
            data = save.data[offset : offset + myinfo.size]
        else:
            data = save.data[save.nodes_data_offset :]
        ctx = parse_node(data, path)
        self._ctx.append(ctx)
        return ctx

    def __exit__(self, *excinfo):
        ctx = self._ctx.pop()
        if excinfo[0] is not None:
            return
        save = self._save
        myinfo = self._address
        nodes_info = list(save.nodes_info)
        if myinfo:
            myinfo = nodes_info[myinfo[-1]]
            offset = myinfo.offset
            size = myinfo.size
        else:
            offset = save.nodes_data_offset
            size = len(save.data) - offset
        ctx = bytes(ctx)
        if len(ctx) != size:
            r = range(offset + 1, offset + size)
            for i, info in enumerate(nodes_info):
                if offset in r or (info.offset + info.size) in r:
                    raise Exception("could not resize this node")
                elif offset >= offset + size:
                    nodes_info[i] = info._replace(
                        offset=info.offset + len(ctx) - size
                    )
                elif info.offset + info.size >= offset + size:
                    nodes_info[i] = info._replace(
                        size=info.size + len(ctx) - size
                    )
        save.data[offset : offset + size] = ctx
        if len(ctx) != size:
            save.nodes_info = tuple(nodes_info)

    def _items(self):
        nodes_info = self._save.nodes_info
        next_id = self._node_id
        next_id = 0 if next_id is None else nodes_info[next_id].child
        while next_id is not None:
            info = nodes_info[next_id]
            yield next_id, info
            next_id = info.next

    @property
    def _address(self):
        child = self._node_id
        if child is None:
            return ()
        res = [child]
        nodes_info = self._save.nodes_info
        for i in range(child - 1, -1, -1):
            node_info = nodes_info[i]
            if node_info.next == child:
                child = i
            elif node_info.child == child:
                res.append(i)
                child = i
        return tuple(reversed(res))


class SaveFileSummary(NamedTuple):
    name: str
    path: Path
    version: int
    date: str
    time: str

    def __str__(self):
        return "%s (version: %g)" % (self.name, self.version / 1000)


class SaveFile:
    NAME = "sav.dat"
    TMP_NAME = "tmp.dat"
    BACKUP_NAME = "backup_{}.dat".format

    @classmethod
    def resolve_path(cls, path):
        path = Path(path)
        if path.is_file() and path.name == cls.NAME:
            path = path.parent
        if not path.is_dir():
            raise Exception
        return path

    def __init__(self, path):
        self.path = self.resolve_path(path)
        with (self.path / self.NAME).open("rb") as f:
            self.header = HeaderChunk.read(f)
            self._data_chunks = DataChunkTableChunk.read(f)
            self.data_chunks = []
            append = self.data_chunks.append
            for info in self._data_chunks.info:
                append(DataChunk.read(f, info.comp_len))
            self._nodes_info = NodeTableChunk.read(f)
            self.nodes_info = self._nodes_info.info
            EndChunk.read(f)
            if f.read(1):
                raise Exception

    @property
    def nodes_data_offset(self):
        return len(self.header) + len(self._data_chunks)

    @property
    def data(self):
        return Data(self)

    @property
    def nodes(self):
        return NodeDirectory(self)

    @classmethod
    def summary(cls, path):
        path = cls.resolve_path(path)
        with (path / cls.NAME).open("rb") as f:
            header = HeaderChunk.read(f)
        return SaveFileSummary(
            name=path.name,
            path=path,
            version=header.game_ver,
            date=header.date,
            time=header.time,
        )

    def save(self, path=None):
        if path is not None:
            self.path = self.resolve_path(path)
        path = self.path
        offset = self.nodes_data_offset
        info = []
        for chunk in self.data_chunks:
            item = ChunkInfo(
                offset=offset,
                comp_len=len(chunk),
                uncomp_len=chunk.uncomp_len,
            )
            info.append(item)
            offset += item.comp_len
        self._data_chunks.info = info
        self._nodes_info.info = self.nodes_info
        self._nodes_info.offset = offset
        with (path / self.TMP_NAME).open("wb") as f:
            f.write(self.header)
            f.write(self._data_chunks)
            for chunk in self.data_chunks:
                f.write(chunk)
            f.write(self._nodes_info)
            f.write(EndChunk())
        backup = 0
        while (path / self.BACKUP_NAME(backup + 1)).exists():
            backup += 1
        for backup in range(backup, -1, -1):
            if backup:
                old = path / self.BACKUP_NAME(backup)
            else:
                old = path / self.NAME
            old.rename(path / self.BACKUP_NAME(backup + 1))
        (path / self.TMP_NAME).rename(path / self.NAME)
