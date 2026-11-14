import os
import re
import struct
import threading
import zlib
from typing import Any, Dict, List, Optional, Set, Union

VECTOR_ID = 0x1CB5C415
GZIP_ID = 0x3072CFA1
BOOL_TRUE = 0x997275B5
BOOL_FALSE = 0xBC799737

PRIMITIVES: Set[str] = {
    "int", "long", "double", "string", "bytes", "Bool", "true",
    "int128", "int256", "#",
}

_TL_LINE_REGEX = re.compile(r"^([\w.]+)#([0-9a-fA-F]+)\s*(.*?)\s*=\s*([\w.<>%]+)\s*;")

_runtime_lock = threading.RLock()
_is_schema_loaded = False
_combinators_by_id: Dict[int, Any] = {}
_combinators_by_name: Dict[str, Any] = {}
_functions_by_name: Dict[str, Any] = {}
_type_classes_by_name: Dict[str, type] = {}

_by_id = _combinators_by_id
_by_name = _combinators_by_name
_functions = _functions_by_name
_types = _type_classes_by_name
_loaded = False


class ArrayList(list):
    def add(self, *args: Any) -> bool:
        if len(args) == 1:
            self.append(args[0])
        else:
            self.insert(args[0], args[1])
        return True

    def size(self) -> int:
        return len(self)

    def get(self, index: int) -> Any:
        return self[index]

    def set(self, index: int, value: Any) -> Any:
        old_val = self[index]
        self[index] = value
        return old_val

    def isEmpty(self) -> bool:
        return len(self) == 0

    def contains(self, value: Any) -> bool:
        return value in self

    def clear(self) -> None:
        del self[:]

    def addAll(self, values: Any) -> bool:
        self.extend(values)
        return True

    def toArray(self) -> List[Any]:
        return list(self)


class _ClassInfo:
    def __init__(self, class_name: str):
        self._name = class_name

    def getSimpleName(self) -> str:
        return self._name

    def getName(self) -> str:
        return f"org.telegram.tgnet.TLRPC${self._name}"


_ClassDescriptor = _ClassInfo


class Param:
    __slots__ = ("name", "type", "flag_field", "flag_bit")

    def __init__(self, name: str, type_: str, flag_field: Optional[str] = None, flag_bit: Optional[int] = None):
        self.name = name
        self.type = type_
        self.flag_field = flag_field
        self.flag_bit = flag_bit


class Combinator:
    __slots__ = ("name", "id", "params", "result", "is_function", "cls")

    def __init__(self, name: str, id_: int, params: List[Param], result: str, is_function: bool):
        self.name = name
        self.id = id_
        self.params = params
        self.result = result
        self.is_function = is_function
        self.cls: Optional[type] = None


class TLObject:
    _tl: Optional[Combinator] = None

    def __init__(self, **kwargs: Any):
        comb = type(self)._tl
        if comb is not None:
            for p in comb.params:
                object.__setattr__(self, p.name, _get_param_default(p))
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def constructor(self) -> int:
        comb = type(self)._tl
        return comb.id if comb else 0

    def getClass(self) -> _ClassDescriptor:
        return _ClassDescriptor(type(self).__name__)

    def getObjectSize(self) -> int:
        return len(serialize(self))

    def serializeToStream(self, stream: Any = None) -> bytes:
        data = serialize(self)
        if stream is not None and hasattr(stream, "write"):
            stream.write(data)
        return data

    def to_dict(self) -> Dict[str, Any]:
        comb = type(self)._tl
        out: Dict[str, Any] = {"_": comb.name if comb else type(self).__name__}
        if comb:
            for p in comb.params:
                out[p.name] = _convert_to_plain(getattr(self, p.name, None))
        return out

    def __repr__(self) -> str:
        comb = type(self)._tl
        descriptor = comb.name if comb else ""
        return f"<{type(self).__name__} {descriptor}>".rstrip() + ">" if not descriptor else f"<{type(self).__name__} {descriptor}>"


class Vector(TLObject):
    def __init__(self, objects: Optional[Any] = None):
        super().__init__()
        self.objects = ArrayList(objects or [])


class TL_error(TLObject):
    def __init__(self, code: int = 0, text: str = ""):
        super().__init__()
        self.code = code
        self.text = text


def _convert_to_plain(val: Any) -> Any:
    if isinstance(val, TLObject):
        return val.to_dict()
    if isinstance(val, list):
        return [_convert_to_plain(v) for v in val]
    if isinstance(val, bytes):
        return val.hex()
    return val


def _get_param_default(param: Param) -> Any:
    t = param.type
    if param.flag_field is not None:
        return False if t == "true" else None
    if t == "#":
        return 0
    if t in ("int", "long"):
        return 0
    if t == "double":
        return 0.0
    if t == "string":
        return ""
    if t == "bytes":
        return b""
    if t == "Bool":
        return False
    if t in ("int128", "int256"):
        return b"\x00" * (16 if t == "int128" else 32)
    if t.startswith(("Vector<", "vector<")):
        return ArrayList()
    return None


def class_name(name: str) -> str:
    return "TL_" + name.replace(".", "_")


def type_class_name(name: str) -> str:
    return name.replace(".", "_")


def _parse_param_definition(token: str) -> Optional[Param]:
    if ":" not in token:
        return None
    name, type_str = token.split(":", 1)
    flag_field = None
    flag_bit = None
    match = re.match(r"^(\w+)\.(\d+)\?(.+)$", type_str)
    if match:
        flag_field, flag_bit, type_str = match.group(1), int(match.group(2)), match.group(3)
    clean_type = type_str.lstrip("!%")
    return Param(name, clean_type, flag_field, flag_bit)


def _get_or_create_type_class(name: str) -> type:
    target_name = type_class_name(name)
    cls = _type_classes_by_name.get(target_name)
    if cls is None:
        cls = type(target_name, (TLObject,), {"_tl": None})
        _type_classes_by_name[target_name] = cls
    return cls


def _parse_schema_definitions(text: str, start_as_functions: bool) -> None:
    is_function_mode = start_as_functions
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("---functions---"):
            is_function_mode = True
            continue
        if line.startswith("---types---"):
            is_function_mode = False
            continue
        if not line or line.startswith("//"):
            continue

        match = _TL_LINE_REGEX.match(line)
        if not match:
            continue

        def_name, hex_id_str, raw_params, result_type_name = match.groups()
        if def_name in ("vector", "true", "boolTrue", "boolFalse", "gzip_packed"):
            continue
        if "{" in raw_params:
            continue

        parsed_params: List[Param] = []
        for token in raw_params.split():
            param = _parse_param_definition(token)
            if param is not None:
                parsed_params.append(param)

        comb = Combinator(
            def_name,
            int(hex_id_str, 16),
            parsed_params,
            result_type_name,
            is_function_mode,
        )
        base_class = TLObject if is_function_mode else _get_or_create_type_class(result_type_name)
        new_class = type(class_name(def_name), (base_class,), {"_tl": comb})
        comb.cls = new_class

        _combinators_by_id[comb.id] = comb
        _combinators_by_name[new_class.__name__] = comb
        if is_function_mode:
            _functions_by_name[def_name] = comb


def _resolve_tl_paths() -> List[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [
        os.path.join(here, "tl"),
        os.path.normpath(os.path.join(here, "..", "..", "mtproto", "scheme")),
    ]
    for folder in search_dirs:
        api_path = os.path.join(folder, "api.tl")
        if os.path.exists(api_path):
            return [api_path]
    return []


def ensure_loaded() -> None:
    global _is_schema_loaded
    with _runtime_lock:
        if _is_schema_loaded:
            return
        for file_path in _resolve_tl_paths():
            try:
                with open(file_path, encoding="utf-8") as handle:
                    _parse_schema_definitions(handle.read(), False)
            except Exception:
                pass
        _is_schema_loaded = True


def lookup(name: str) -> Optional[type]:
    ensure_loaded()
    comb = _combinators_by_name.get(name)
    if comb is not None:
        return comb.cls
    if name in _type_classes_by_name:
        return _type_classes_by_name[name]
    if name == "Vector":
        return Vector
    if name == "TL_error":
        return TL_error
    return None


class _BinaryWriter:
    def __init__(self):
        self._buffers: List[bytes] = []

    def int(self, val: Any) -> None:
        self._buffers.append(struct.pack("<i", _normalize_int32(val)))

    def uint(self, val: Any) -> None:
        self._buffers.append(struct.pack("<I", int(val) & 0xFFFFFFFF))

    def long(self, val: Any) -> None:
        self._buffers.append(struct.pack("<q", _normalize_int64(val)))

    def double(self, val: Any) -> None:
        self._buffers.append(struct.pack("<d", float(val or 0)))

    def bytes(self, val: Any) -> None:
        if isinstance(val, str):
            val = val.encode("utf-8")
        payload = bytes(val or b"")
        size = len(payload)
        if size < 254:
            prefix = bytes([size])
        else:
            prefix = bytes([254]) + struct.pack("<I", size)[:3]
        total_len = len(prefix) + size
        padding_len = (-total_len) % 4
        self._buffers.append(prefix + payload + (b"\x00" * padding_len))

    def raw(self, val: Any) -> None:
        self._buffers.append(bytes(val))

    def build(self) -> bytes:
        return b"".join(self._buffers)


def _normalize_int32(v: Any) -> int:
    val = int(v or 0) & 0xFFFFFFFF
    return val - 0x100000000 if val >= 0x80000000 else val


def _normalize_int64(v: Any) -> int:
    val = int(v or 0) & 0xFFFFFFFFFFFFFFFF
    return val - 0x10000000000000000 if val >= 0x8000000000000000 else val


def _extract_vector_inner_type(type_name: str) -> Optional[str]:
    match = re.match(r"^[Vv]ector<(.+)>$", type_name)
    return match.group(1) if match else None


def _write_typed_value(writer: _BinaryWriter, type_str: str, val: Any) -> None:
    inner_t = _extract_vector_inner_type(type_str)
    if inner_t is not None:
        if type_str.startswith("Vector"):
            writer.uint(VECTOR_ID)
        items = list(val or [])
        writer.int(len(items))
        for it in items:
            _write_typed_value(writer, inner_t, it)
        return

    if type_str == "int":
        writer.int(val)
    elif type_str == "long":
        writer.long(val)
    elif type_str == "double":
        writer.double(val)
    elif type_str in ("string", "bytes"):
        writer.bytes(val)
    elif type_str == "Bool":
        writer.uint(BOOL_TRUE if val else BOOL_FALSE)
    elif type_str == "int128":
        writer.raw((bytes(val or b"") + b"\x00" * 16)[:16])
    elif type_str == "int256":
        writer.raw((bytes(val or b"") + b"\x00" * 32)[:32])
    elif type_str == "true":
        return
    else:
        if val is None:
            raise ValueError(f"missing value of type {type_str}")
        _write_tl_object(writer, val)


def _write_tl_object(writer: _BinaryWriter, obj: Any) -> None:
    if isinstance(obj, bool):
        writer.uint(BOOL_TRUE if obj else BOOL_FALSE)
        return

    comb = type(obj)._tl
    if comb is None:
        raise ValueError(f"cannot serialize {type(obj).__name__}")

    writer.uint(comb.id)
    bitmask_map: Dict[str, int] = {}

    for p in comb.params:
        if p.type == "#":
            bitmask_map[p.name] = int(getattr(obj, p.name, 0) or 0)

    for p in comb.params:
        if p.flag_field is None:
            continue
        attr_val = getattr(obj, p.name, None)
        bit = 1 << p.flag_bit
        curr_mask = bitmask_map.get(p.flag_field, 0)

        if p.type == "true":
            is_present = bool(attr_val) or bool(curr_mask & bit)
        else:
            is_present = attr_val is not None and not (
                isinstance(attr_val, list) and not attr_val and not (curr_mask & bit)
            )

        if is_present:
            bitmask_map[p.flag_field] = curr_mask | bit
        else:
            bitmask_map[p.flag_field] = curr_mask & ~bit

    for p in comb.params:
        if p.type == "#":
            writer.uint(bitmask_map.get(p.name, 0))
            continue
        if p.flag_field is not None:
            if not (bitmask_map.get(p.flag_field, 0) & (1 << p.flag_bit)):
                continue
            if p.type == "true":
                continue
        _write_typed_value(writer, p.type, getattr(obj, p.name, None))


def serialize(obj: Any) -> bytes:
    ensure_loaded()
    w = _BinaryWriter()
    _write_tl_object(w, obj)
    return w.build()


class _BinaryReader:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    def consume(self, count: int) -> bytes:
        if self._offset + count > len(self._data):
            raise ValueError("unexpected end of data")
        chunk = self._data[self._offset:self._offset + count]
        self._offset += count
        return chunk

    def int(self) -> int:
        return struct.unpack("<i", self.consume(4))[0]

    def uint(self) -> int:
        return struct.unpack("<I", self.consume(4))[0]

    def long(self) -> int:
        return struct.unpack("<q", self.consume(8))[0]

    def double(self) -> float:
        return struct.unpack("<d", self.consume(8))[0]

    def bytes(self) -> bytes:
        first = self.consume(1)[0]
        if first == 254:
            size = int.from_bytes(self.consume(3), "little")
            header_len = 4
        else:
            size = first
            header_len = 1
        content = self.consume(size)
        padding = (-(header_len + size)) % 4
        self.consume(padding)
        return content


def _read_typed_value(reader: _BinaryReader, type_str: str, is_top: bool = False) -> Any:
    inner = _extract_vector_inner_type(type_str)
    if inner is not None:
        if type_str.startswith("Vector"):
            ctor = reader.uint()
            if ctor != VECTOR_ID:
                raise ValueError(f"expected vector, got {ctor:#x}")
        length = reader.int()
        elements = ArrayList(_read_typed_value(reader, inner) for _ in range(length))
        return Vector(elements) if is_top else elements

    if type_str == "int":
        return reader.int()
    if type_str == "long":
        return reader.long()
    if type_str == "double":
        return reader.double()
    if type_str == "string":
        return reader.bytes().decode("utf-8", "replace")
    if type_str == "bytes":
        return reader.bytes()
    if type_str == "int128":
        return reader.consume(16)
    if type_str == "int256":
        return reader.consume(32)
    if type_str == "Bool":
        flag = reader.uint() == BOOL_TRUE
        if is_top:
            bool_cls = lookup("TL_boolTrue" if flag else "TL_boolFalse")
            return bool_cls() if bool_cls else flag
        return flag
    if type_str == "true":
        return True
    return _read_tl_object(reader)


def _read_tl_object(reader: _BinaryReader) -> Any:
    constructor_id = reader.uint()
    if constructor_id == GZIP_ID:
        packed_bytes = reader.bytes()
        decompressed = zlib.decompress(packed_bytes, 16 + zlib.MAX_WBITS)
        return _read_tl_object(_BinaryReader(decompressed))
    if constructor_id == BOOL_TRUE:
        return True
    if constructor_id == BOOL_FALSE:
        return False
    if constructor_id == VECTOR_ID:
        count = reader.int()
        return ArrayList(_read_tl_object(reader) for _ in range(count))

    comb = _combinators_by_id.get(constructor_id)
    if comb is None:
        raise ValueError(f"unknown constructor {constructor_id:#x}")

    instance = comb.cls.__new__(comb.cls)
    bitmask_fields: Dict[str, int] = {}

    for p in comb.params:
        if p.type == "#":
            mask_val = reader.uint()
            bitmask_fields[p.name] = mask_val
            object.__setattr__(instance, p.name, mask_val)
            continue
        if p.flag_field is not None:
            if not (bitmask_fields.get(p.flag_field, 0) & (1 << p.flag_bit)):
                object.__setattr__(instance, p.name, False if p.type == "true" else None)
                continue
        object.__setattr__(instance, p.name, _read_typed_value(reader, p.type))

    return instance


def deserialize(data: bytes, result_type: Optional[str] = None) -> Any:
    ensure_loaded()
    reader = _BinaryReader(data)
    if result_type:
        return _read_typed_value(reader, result_type, is_top=True)
    return _read_tl_object(reader)


def result_type(request: Any) -> Optional[str]:
    comb = getattr(type(request), "_tl", None)
    return comb.result if comb else None


def is_request(obj: Any) -> bool:
    comb = getattr(type(obj), "_tl", None)
    return comb is not None and comb.is_function


class _Namespace:
    def __init__(self, namespace_name: str):
        self._name = namespace_name

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__"):
            raise AttributeError(item)
        target_cls = lookup(item)
        if target_cls is None and not item.startswith("TL_"):
            target_cls = lookup("TL_" + item[0].lower() + item[1:]) if item else None
        if target_cls is None:
            import _compat
            return _compat.Stub(f"{self._name}.{item}")
        return target_cls


_TLRPCNamespace = _Namespace
TLRPC = _Namespace("TLRPC")
