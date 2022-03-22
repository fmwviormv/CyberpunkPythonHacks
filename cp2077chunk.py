from collections import namedtuple
from io import BytesIO
from struct import Struct

uint32 = Struct("<I")
pack32 = uint32.pack
unpack32 = uint32.unpack


class ChunkMeta(type):
    def __new__(mcls, name, bases, ns, **kwargs):
        empty = ns.get("EMPTY")
        if empty is None:
            return super().__new__(mcls, name, bases, ns, **kwargs)
        empty = bytes(empty)
        ns["EMPTY"] = empty
        magic = empty[:4]
        if len(magic) != 4:
            raise TypeError
        ns["MAGIC"] = magic
        ns["__slots__"] = ()
        cls = super().__new__(mcls, name, bases, ns, **kwargs)
        Chunk._BY_MAGIC[magic] = cls
        return cls

    def __call__(cls, *args, **kwargs):
        if (
            len(args) == 1
            and not kwargs
            and isinstance(args[0], (cls, bytes, bytearray))
        ):
            res = args[0]
            if not isinstance(res, cls):
                stream = BytesIO(res)
                res = cls.read(stream)
                if stream.read(1):
                    raise ValueError
            return res
        return cls.__new__(cls, *args, **kwargs)


class Chunk(bytearray, metaclass=ChunkMeta):
    _BY_MAGIC = {}

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __new__(cls, *args, **kwargs):
        res = bytearray.__new__(cls)
        bytearray.__init__(res, cls.EMPTY)
        res.__init__(*args, **kwargs)
        return res

    @property
    def is_ok(self):
        try:
            magic = type(self).MAGIC
            if not self.startswith(magic):
                return False
            return bool(self.check_data(len(magic)))
        except Exception:
            return False

    @classmethod
    def read(cls, stream):
        magic = stream.read(4)
        match = __class__._BY_MAGIC.get(magic)
        if match is None or not issubclass(match, cls):
            raise TypeError("Invalid magic")
        res = match()
        res.read_data(stream, len(magic))
        return res


class StructIndex(int):
    __slots__ = ()

    def __get__(self, obj, objtype=None):
        return obj.STRUCT.unpack(obj)[self]

    def __set__(self, obj, value):
        struct = obj.STRUCT
        res = list(struct.unpack(obj))
        res[self] = value
        obj[:] = struct.pack(*res)


class DateProperty(StructIndex):
    def __get__(self, obj, objtype=None):
        value = super().__get__(obj, objtype)
        if value & 1023:
            raise Exception
        value = value >> 20, value >> 15 & 31, value >> 10 & 31
        return "%04d-%02d-%02d" % (value[0], value[1] + 1, value[2] + 1)

    def __set__(self, obj, value):
        year, month, day = [int(item) - 1 for item in value.split("-")]
        year += 1
        if year >> 12 or month not in range(12) or day not in range(31):
            raise ValueError
        super().__set__(obj, year << 20 | month << 15 | day << 10)


class TimeProperty(StructIndex):
    def __get__(self, obj, objtype=None):
        val = super().__get__(obj, objtype)
        val = val >> 22, val >> 16 & 63, val >> 10 & 63, val & 1023
        return "%02d:%02d:%02d.%03d" % val

    def __set__(self, obj, value):
        value = (value.split(".", 1) + [0])[:2]
        value = list(map(int, [*value[0].split(":"), value[1]]))
        if all(0 <= i < n for i, n in zip(value, [24, 60, 60, 1000])):
            value = sum(i << n for i, n in zip(value, [22, 16, 10, 0]))
            super().__set__(obj, value)
        else:
            raise ValueError


class HeaderChunk(Chunk):
    EMPTY = b"VASC" + bytes(21)
    STRUCT = Struct("<4sIIBIII")

    def __repr__(self):
        val = "save_ver game_ver arch_ver date time".split()
        val = ", ".join(f"{n}={getattr(self, n)!r}" for n in val)
        return f"{type(self).__name__}({val})"

    save_ver = StructIndex(1)
    game_ver = StructIndex(2)
    arch_ver = StructIndex(6)
    date = DateProperty(5)
    time = TimeProperty(4)

    def check_data(self, mlen):
        return self.date and self.time and self[mlen + 8] == 0

    def read_data(self, stream, mlen):
        size = len(self.EMPTY) - mlen
        data = stream.read(size)
        if len(data) != size or data[8]:
            raise ValueError
        self[mlen:] = data


ChunkInfo = namedtuple(
    "ChunkInfo", ["offset", "comp_len", "uncomp_len"]
)


class DataChunkTableChunk(Chunk):
    EMPTY = b"FZLC" + bytes(4)
    STRUCT = Struct("<III")
    VALID_CAPACITY = 0x100, 0x400

    def __repr__(self):
        val = type(self).__name__, self.capacity, self.count
        return "%s(capacity=%d, info=...%d chunk info(s)...)" % val

    @property
    def capacity(self):
        size = self.STRUCT.size
        res = len(self) - len(self.MAGIC) - 4
        if res % size:
            raise Exception
        return res // size

    @capacity.setter
    def capacity(self, value):
        if value < self.count or value not in self.VALID_CAPACITY:
            raise Exception
        size = len(self.MAGIC) + 4 + self.STRUCT.size * value
        if len(self) < size:
            self.extend(bytes(size - len(self)))
        else:
            self[size:] = b""

    @property
    def count(self):
        magiclen = len(self.MAGIC)
        return unpack32(self[magiclen : magiclen + 4])[0]

    @property
    def info(self):
        struct = self.STRUCT
        unpack = struct.unpack
        struct = struct.size
        return tuple(
            ChunkInfo(*unpack(self[i : i + struct]))
            for i in range(len(self.EMPTY), self.count * struct, struct)
        )

    @info.setter
    def info(self, value):
        pack = self.STRUCT.pack
        value = tuple(pack(*item) for item in value)
        if len(value) > self.capacity:
            raise ValueError
        value = pack32(len(value)) + b"".join(value)
        mlen = len(self.MAGIC)
        self[mlen : mlen + len(value)] = value

    def check_data(self, mlen):
        return self.capacity in self.VALID_CAPACITY

    def read_data(self, stream, mlen):
        read = stream.read
        prefix = read(8)
        size = unpack32(prefix[4:])[0]
        size -= len(HeaderChunk.EMPTY) + mlen + 4
        item_size = self.STRUCT.size
        if size % item_size != 0:
            raise TypeError
        if size // item_size not in self.VALID_CAPACITY:
            raise ValueError
        size -= len(prefix) - 4
        data = read(size)
        if len(data) != size:
            raise Exception
        self[mlen:] = prefix + data


class DataChunk(Chunk):
    def __repr__(self):
        name = type(self).__name__
        return "%s(data=...%d byte(s)...)" % (name, self.uncomp_len)

    def __new__(cls, *args, **kwargs):
        if cls is __class__:
            return LZ4DataChunk(*args, **kwargs)
        return super().__new__(cls, *args, **kwargs)

    @classmethod
    def read(cls, stream, size=None):
        if size is None:
            return super().read(stream)
        read = stream.read
        magic = read(4)
        match = __class__._BY_MAGIC.get(magic)
        if match is None or not issubclass(match, cls):
            raise TypeError("Invalid magic")
        res = match()
        res[len(magic) :] = read(size - 4)
        if len(res) != size:
            raise Exception
        return res


class LZ4DataChunk(DataChunk):
    EMPTY = b"4ZLX" + bytes(4)

    @property
    def comp_len(self):
        return len(self)

    @property
    def uncomp_len(self):
        magiclen = len(self.MAGIC)
        return unpack32(self[magiclen : magiclen + 4])[0]

    @property
    def data(self):
        res = bytearray()
        extend = res.extend
        read = BytesIO(self).read
        read(len(self.MAGIC) + 4)
        while token := read(1):
            last = (length := token[0] >> 4) + 240
            while last == 255:
                length += (last := read(1)[0])
            extend(read(length))
            if not (off := read(2)):
                break
            off = off[0] + (off[1] << 8)
            if off <= 0 or (off := len(res) - off) < 0:
                raise Exception
            last = (length := (token[0] & 15) + 4) + 236
            while last == 255:
                length += (last := read(1)[0])
            while length > 0:
                extend(match := res[off : off + length])
                off += (match := len(match))
                length -= match
        return bytes(res)

    @data.setter
    def data(self, value):
        length = len(value)
        res = bytearray(pack32(length))
        if length >= 15:
            length -= 15
            res.append(0xF0)
            res.extend((length // 255) * b"\xff")
            res.append(length % 255)
        elif length:
            res.append(length << 4)
        self[len(self.MAGIC) :] = bytes(res) + value

    def read_data(self, stream, mlen):
        block = bytearray()
        append = block.append
        extend = block.extend
        read = stream.read
        prefix = read(4)
        size = unpack32(prefix)[0]
        while size > 0:
            extend(token := read(1))
            last = (length := token[0] >> 4) + 240
            while last == 255:
                append(last := read(1)[0])
                length += last
            if len(off := read(length)) != length:
                raise Exception
            extend(off)
            size -= length
            if size <= 0:
                break
            if len(off := read(2)) != 2:
                raise Exception
            extend(off)
            last = (length := (token[0] & 15) + 4) + 236
            while last == 255:
                append(last := read(1)[0])
                length += last
            size -= length
        if size != 0:
            raise Exception
        self[mlen:] = prefix + block


NodeInfo = namedtuple("NodeInfo", "name next child offset size".split())


class NodeTableChunk(Chunk):
    EMPTY = b"EDON" + bytes(8)
    STRUCT_FMT = "<%dsIIII"

    def __repr__(self):
        val = type(self).__name__, self.count, self.offset
        return "%s(info=...%d node info(s)..., offset=%r)" % val

    @staticmethod
    def read_packed_int(read):
        res = bytearray(read(1))
        if not res[0] >> 6 & 1:
            return bytes(res)
        res.append(read(1)[0])
        while res[-1] >> 7:
            res.append(read(1)[0])
        return bytes(res)

    @staticmethod
    def pack_int(value):
        data = abs(value) << 1
        size = max(1, data.bit_length())
        data = [data >> i & 127 | 128 for i in range(0, size, 7)]
        data[-1] &= 127
        data[0] = data[0] >> 1 | (128 if value < 0 else 0)
        return bytes(data)

    @staticmethod
    def unpack_int(value):
        value = iter(value)
        byte = next(value)
        res = byte & 63
        reslen = 6
        is_neg = byte >> 7
        for byte in value:
            res |= (byte & 127) << reslen
            reslen += 7
        return -res if is_neg else res

    @property
    def reader(self):
        read = BytesIO(self).read
        read(len(self.MAGIC))
        return read

    @property
    def count(self):
        return self.unpack_int(self.read_packed_int(self.reader))

    @property
    def info(self):
        read = self.reader
        read_packed_int = self.read_packed_int
        unpack_int = self.unpack_int
        struct_fmt = self.STRUCT_FMT
        res = []
        n = (1 << 32) - 1
        for _ in range(unpack_int(read_packed_int(read))):
            s = Struct(struct_fmt % -unpack_int(read_packed_int(read)))
            s = [None if i == n else i for i in s.unpack(read(s.size))]
            res.append(NodeInfo(*s))
        return tuple(res)

    @info.setter
    def info(self, value):
        magiclen = len(self.MAGIC)
        struct_fmt = self.STRUCT_FMT
        pack_int = self.pack_int
        res = []
        n = (1 << 32) - 1
        for item in value:
            namlen = len(item.name)
            struct = Struct(struct_fmt % namlen)
            item = [n if i is None else i for i in item]
            res.append(pack_int(-namlen) + struct.pack(*item))
        count = self.read_packed_int(self.reader)
        if self.unpack_int(count) != len(res):
            count = pack_int(len(res))
        self[magiclen:-4] = count + b"".join(res)

    @property
    def offset(self):
        return unpack32(self[-4:])[0]

    @offset.setter
    def offset(self, value):
        self[-4:] = pack32(value)

    def check_data(self, mlen):
        read = self.reader
        read_packed_int = self.read_packed_int
        unpack_int = self.unpack_int
        struct_fmt = self.STRUCT_FMT
        for _ in range(unpack_int(read_packed_int(read))):
            s = Struct(struct_fmt % -unpack_int(read_packed_int(read)))
            if len(read(s.size)) != s.size:
                return False
        return len(read(5)) == 4

    def read_data(self, stream, mlen):
        read = stream.read
        read_packed_int = self.read_packed_int
        unpack_int = self.unpack_int
        struct_fmt = self.STRUCT_FMT
        data = [read_packed_int(read)]
        for _ in range(unpack_int(data[-1])):
            data.append(read_packed_int(read))
            s = Struct(struct_fmt % -unpack_int(data[-1]))
            data.append(read(s.size))
            if len(data[-1]) != s.size:
                raise Exception
        data.append(read(4))
        if len(data[-1]) != 4:
            raise Exception
        data = b"".join(data)
        self[mlen:] = data


class EndChunk(Chunk):
    EMPTY = b"ENOD"

    def __repr__(self):
        return type(self).__name__ + "()"

    def check_data(self, mlen):
        return True

    def read_data(self, stream, mlen):
        pass
