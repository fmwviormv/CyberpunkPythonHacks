from pathlib import Path
from typing import NamedTuple
from cp2077chunk import (
    HeaderChunk,
    ChunkTableChunk,
    DataChunk,
    NodeTableChunk,
    EndChunk,
)


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

    def __init__(self, path):
        path = Path(path)
        if path.is_file() and path.name == self.NAME:
            path = path.parent
        if not path.is_dir():
            raise Exception
        self.path = path
        with (path / self.NAME).open("rb") as f:
            self.header = HeaderChunk.read(f)
            self.data_chunks = []
            for chunk_info in ChunkTableChunk.read(f).info:
                self.data_chunks.append(DataChunk.read(f))
            self.node_info = NodeTableChunk.read(f).info
            EndChunk.read(f)
            if f.read(1):
                raise Exception
        self.data = bytearray()
        for data_chunk in self.data_chunks:
            self.data.extend(data_chunk.data)


    @classmethod
    def summary(cls, path):
        path = Path(path)
        if path.is_file() and path.name == cls.NAME:
            path = path.parent
        if not path.is_dir():
            raise Exception
        with (path / cls.NAME).open("rb") as f:
            header = HeaderChunk.read(f)
        return SaveFileSummary(
            name=path.name,
            path=path,
            version=header.game_ver,
            date=header.date,
            time=header.time,
        )
