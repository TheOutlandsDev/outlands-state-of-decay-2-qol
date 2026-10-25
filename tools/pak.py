"""Small, dependency-free reader/writer for the v3 PAKs used by this profile."""
from pathlib import Path, PurePosixPath
import hashlib
import struct
import zlib


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError('Truncated PAK data')
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def unpack(self, fmt):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))

    def string(self):
        count, = self.unpack('<i')
        if not count or abs(count) > 100000:
            raise ValueError('Invalid PAK string length')
        raw = self.read(abs(count) * (2 if count < 0 else 1))
        return raw.decode('utf-16-le' if count < 0 else 'utf-8').rstrip('\0')


def index(path):
    path = Path(path)
    with path.open('rb') as stream:
        length = path.stat().st_size
        stream.seek(-min(length, 4096), 2)
        tail = stream.read()
        magic = tail.rfind(struct.pack('<I', 0x5A6F12E1))
        if magic < 0 or magic + 44 > len(tail):
            raise ValueError('PAK footer missing')
        version, offset, size = struct.unpack_from('<iqq', tail, magic + 4)
        if version & 0xffff != 3 or not 0 <= offset <= offset + size <= length:
            raise ValueError('Unsupported PAK version or index bounds')
        stream.seek(offset)
        raw = stream.read(size)
    if hashlib.sha1(raw).digest() != tail[magic + 24:magic + 44]:
        raise ValueError('PAK index checksum mismatch')
    reader = Reader(raw)
    mount = reader.string()
    count, = reader.unpack('<i')
    if not 0 <= count <= 1000000:
        raise ValueError('Invalid PAK entry count')
    entries = []
    names = set()
    for _ in range(count):
        name = reader.string()
        parts = PurePosixPath(name).parts
        if not parts or '..' in parts or name.startswith(('/', '\\')) or ':' in name or '\\' in name:
            raise ValueError('Unsafe asset path')
        if name.lower() in names:
            raise ValueError('Duplicate asset inside PAK')
        names.add(name.lower())
        position, packed, size, compression = reader.unpack('<qqqI')
        checksum = reader.read(20)
        blocks = []
        if compression:
            blocks_count, = reader.unpack('<i')
            if not 0 <= blocks_count <= 1000000:
                raise ValueError('Invalid compression block count')
            blocks = [reader.unpack('<qq') for _ in range(blocks_count)]
        encrypted, block_size = reader.unpack('<BI')
        if min(position, packed, size) < 0 or encrypted:
            raise ValueError('Invalid or encrypted PAK entry')
        entries.append(dict(name=name, offset=position, packed=packed, size=size,
                            compression=compression, checksum=checksum,
                            blocks=blocks, block_size=block_size))
    if reader.pos != len(raw):
        raise ValueError('Unexpected index trailer')
    return dict(mount=mount, entries=entries)


def lz4_block(raw, maximum=65536):
    """Decode a bounded raw LZ4 block (not an LZ4 frame)."""
    cursor = 0
    out = bytearray()

    def extended(length):
        nonlocal cursor
        if length == 15:
            while True:
                if cursor >= len(raw):
                    raise ValueError('Truncated LZ4 length')
                value = raw[cursor]
                cursor += 1
                length += value
                if value != 255:
                    break
        return length

    while cursor < len(raw):
        token = raw[cursor]
        cursor += 1
        literal = extended(token >> 4)
        if cursor + literal > len(raw) or len(out) + literal > maximum:
            raise ValueError('Invalid LZ4 literal bounds')
        out.extend(raw[cursor:cursor + literal])
        cursor += literal
        if cursor == len(raw):
            break
        if cursor + 2 > len(raw):
            raise ValueError('Truncated LZ4 offset')
        distance = raw[cursor] | raw[cursor + 1] << 8
        cursor += 2
        if not 0 < distance <= len(out):
            raise ValueError('Invalid LZ4 match distance')
        match = extended(token & 15) + 4
        if len(out) + match > maximum:
            raise ValueError('LZ4 output exceeds block bound')
        for _ in range(match):
            out.append(out[-distance])
    return bytes(out)


def payload(path, entry, verify=True):
    with Path(path).open('rb') as stream:
        if entry['compression']:
            chunks = []
            decoded = []
            for start, end in entry['blocks']:
                if not 0 <= start < end <= Path(path).stat().st_size:
                    raise ValueError('Invalid PAK block bounds')
                stream.seek(start)
                raw = stream.read(end - start)
                chunks.append(raw)
                if entry['compression'] == 1:
                    decoded.append(zlib.decompress(raw))
                elif entry['compression'] in (3, 259):
                    decoded.append(lz4_block(raw, entry['block_size'] or 65536))
                else:
                    raise ValueError('Unsupported compression')
            stored, result = b''.join(chunks), b''.join(decoded)
        else:
            stream.seek(entry['offset'] + 53)
            stored = result = stream.read(entry['packed'])
    if len(result) != entry['size']:
        raise ValueError('PAK payload size mismatch')
    if verify and hashlib.sha1(stored).digest() != entry['checksum']:
        raise ValueError('PAK payload checksum mismatch')
    return result


def _string(value):
    raw = value.encode('utf-8') + b'\0'
    return struct.pack('<i', len(raw)) + raw


def write_pak(path, assets):
    entries = []
    with Path(path).open('wb') as stream:
        for name, data in assets:
            position = stream.tell()
            checksum = hashlib.sha1(data).digest()
            common = struct.pack('<qqI', len(data), len(data), 0) + checksum + struct.pack('<BI', 0, 0)
            stream.write(struct.pack('<q', 0) + common)
            stream.write(data)
            entries.append(_string(name) + struct.pack('<q', position) + common)
        raw = _string('../../../') + struct.pack('<i', len(entries)) + b''.join(entries)
        offset = stream.tell()
        stream.write(raw)
        stream.write(struct.pack('<Iiqq', 0x5A6F12E1, 3, offset, len(raw)) + hashlib.sha1(raw).digest())
    index(path)
