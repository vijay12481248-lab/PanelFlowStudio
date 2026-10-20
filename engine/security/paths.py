"""Path containment helpers for project-scoped filesystem access."""

import os
import stat
import json
from contextlib import contextmanager
from pathlib import Path

from fastapi.responses import StreamingResponse


def resolve_contained_path(root: Path | str, candidate: Path | str, *, must_be_file: bool = False) -> Path:
    """Resolve a candidate below a non-symlinked root without following links."""
    root_input = Path(root).expanduser()
    root_absolute = root_input.absolute()
    root_cursor = Path(root_absolute.anchor) if root_absolute.anchor else Path()
    for part in root_absolute.parts:
        if part == root_absolute.anchor:
            continue
        root_cursor /= part
        if root_cursor.is_symlink() or root_cursor.is_junction():
            raise ValueError("allowed root cannot contain symlinks")
    root_path = root_absolute.resolve()
    candidate_path = Path(candidate)
    lexical_candidate = candidate_path if candidate_path.is_absolute() else root_absolute / candidate_path
    lexical_cursor = Path(lexical_candidate.anchor) if lexical_candidate.anchor else Path()
    for part in lexical_candidate.parts:
        if part == lexical_candidate.anchor:
            continue
        lexical_cursor /= part
        if lexical_cursor.is_symlink() or lexical_cursor.is_junction():
            raise ValueError("path contains a symlink")
    if candidate_path.is_absolute():
        resolved = candidate_path.resolve()
    else:
        resolved = (root_path / candidate_path).resolve()
    if resolved == root_path or root_path not in resolved.parents:
        raise ValueError("path escapes its allowed workspace")
    relative_parts = resolved.relative_to(root_path).parts
    current = root_path
    for part in relative_parts:
        current /= part
        if current.is_symlink() or current.is_junction():
            raise ValueError("path contains a symlink")
    if must_be_file and not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return resolved


def project_path(workspace: Path | str, directory: str, filename: str | Path, *, must_be_file: bool = False) -> Path:
    """Resolve a project artifact against the actual persisted project root.

    Never promote the artifact directory to a trusted root: it may itself be a link.
    """
    base = resolve_contained_path(workspace, directory)
    target = resolve_contained_path(workspace, Path(directory) / filename, must_be_file=must_be_file)
    if not target.is_relative_to(base) or target == base:
        raise ValueError("artifact escapes its project directory")
    return target


def write_contained_image(root: Path | str, candidate: Path | str, image, format: str, **options) -> None:
    """Give Pillow a held, validated stream rather than a pathname to reopen."""
    with open_contained_output(root, candidate) as output:
        image.save(output, format=format, **options)


def read_contained_bytes(root: Path | str, candidate: Path | str, *, max_bytes: int | None = None) -> bytes:
    with _open_contained_file(root, candidate) as source:
        if max_bytes is None:
            return source.read()
        data = source.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise OverflowError("contained file exceeds size limit")
        return data


def write_contained_bytes(root: Path | str, candidate: Path | str, data: bytes, *, exclusive: bool = False) -> None:
    """Write bytes through a checked, held file handle."""
    with open_contained_output(root, candidate, exclusive=exclusive) as output:
        output.write(data)


def write_contained_json(root: Path | str, candidate: Path | str, value, **json_options) -> None:
    options = {"indent": 2, **json_options}
    write_contained_bytes(root, candidate, json.dumps(value, **options).encode("utf-8"))


def promote_contained_file(root: Path | str, staged: Path | str, destination: Path | str) -> None:
    """Copy a staged file into a held output, then unlink it.

    This avoids pathname replace. It is containment-safe but not crash-atomic:
    interruption can leave a partial destination.
    """
    with _open_contained_file(root, staged) as source, open_contained_output(root, destination) as output:
        while chunk := source.read(1024 * 1024):
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    unlink_contained_file(root, staged)


def ensure_contained_directory(root: Path | str, candidate: Path | str) -> Path:
    """Create descendant directories while pinning each immediate parent."""
    root_path = Path(root).expanduser().absolute()
    target = resolve_contained_path(root_path, candidate)
    current = root_path
    for part in target.relative_to(root_path).parts:
        child = current / part
        if child.exists():
            if not resolve_contained_path(root_path, child).is_dir():
                raise NotADirectoryError(str(child))
            current = child
            continue
        if os.name == "nt":
            with _windows_held_directory(current):
                os.mkdir(child)
        elif os.name == "posix":
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent_fd = os.open(current, flags)
            try:
                os.mkdir(part, mode=0o700, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        else:
            raise NotImplementedError("handle-bound directory creation is unsupported")
        resolve_contained_path(root_path, child)
        current = child
    return target


@contextmanager
def _windows_held_directory(path: Path):
    import ctypes
    from ctypes import wintypes

    expected = path.stat(follow_symlinks=False)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    class FileInfo(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                    ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    invalid = ctypes.c_void_p(-1).value
    handle = kernel.CreateFileW(str(path), 0x80, 0x1 | 0x2, None, 3, 0x02000000 | 0x00200000, None)
    if handle == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = FileInfo()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & 0x400:
            raise ValueError("directory is a reparse point")
        opened_ino = (int(info.index_high) << 32) | int(info.index_low)
        if expected.st_ino and opened_ino != expected.st_ino:
            raise ValueError("directory changed during validation")
        yield handle
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def open_contained_output(root: Path | str, candidate: Path | str, *, exclusive: bool = False):
    """Open a regular file relative to a held directory, without following a final link.

    The returned binary stream is truncated only after the opened handle is checked.
    The containing directory must already exist. This does not protect against
    malicious hardlinks or writes performed by other pathname-based libraries.
    """
    target = resolve_contained_path(root, candidate)
    root_path = Path(root).expanduser().absolute()
    parts = target.relative_to(root_path).parts
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("invalid output filename")
    if os.name != "nt":
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(root_path.anchor, flags)
        try:
            for part in (*root_path.parts[1:], *parts[:-1]):
                next_dir = os.open(part, flags, dir_fd=directory)
                os.close(directory)
                directory = next_dir
            fd = os.open(parts[-1], os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT |
                         (os.O_EXCL if exclusive else 0), 0o600, dir_fd=directory)
        finally:
            os.close(directory)
    else:
        fd = _windows_open_output(root_path, target, exclusive=exclusive)
        assert fd is not None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("output is not a regular file")
        if not exclusive:
            os.ftruncate(fd, 0)
        with os.fdopen(fd, "wb") as output:
            fd = -1
            yield output
    finally:
        if fd >= 0:
            os.close(fd)


def unlink_contained_file(root: Path | str, candidate: Path | str) -> None:
    """Delete a regular file without reopening a checked filename through a swapped parent."""
    target = resolve_contained_path(root, candidate, must_be_file=True)
    root_path = Path(root).expanduser().absolute()
    if os.name == "nt":
        _windows_open_output(root_path, target, exclusive=False, delete=True)
        return
    parts = target.relative_to(root_path).parts
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root_path.anchor, flags)
    try:
        for part in (*root_path.parts[1:], *parts[:-1]):
            next_dir = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = next_dir
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError("target is not a regular file")
            # POSIX unlinkat removes the named entry, never follows its final link.
            # Concurrent replacement can remove a different entry inside this parent.
            os.unlink(parts[-1], dir_fd=directory)
        finally:
            os.close(file_fd)
    finally:
        os.close(directory)


def _windows_open_output(root: Path, target: Path, *, exclusive: bool, delete: bool = False) -> int | None:
    """Open a target relative to a checked, held parent directory on Windows.

    NtCreateFile RootDirectory binds the filename to that handle rather than
    re-resolving its pathname. Both directory and file opens reject reparse points.
    """
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    INVALID = ctypes.c_void_p(-1).value
    OPEN_REPARSE = 0x00200000
    BACKUP = 0x02000000
    REPARSE_ATTRIBUTE = 0x400
    share = 0x1 | 0x2  # no FILE_SHARE_DELETE: pin the directory until opened
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    class FileInfo(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                    ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    class UnicodeString(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                    ("Buffer", wintypes.LPWSTR)]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [("Length", wintypes.ULONG), ("RootDirectory", wintypes.HANDLE),
                    ("ObjectName", ctypes.POINTER(UnicodeString)), ("Attributes", wintypes.ULONG),
                    ("SecurityDescriptor", ctypes.c_void_p), ("SecurityQualityOfService", ctypes.c_void_p)]

    class IoStatus(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    parent = target.parent
    directory = kernel.CreateFileW(str(parent), 0x80, share, None, 3, BACKUP | OPEN_REPARSE, None)
    if directory == INVALID:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = wintypes.HANDLE()
    try:
        info = FileInfo()
        if not kernel.GetFileInformationByHandle(directory, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & REPARSE_ATTRIBUTE:
            raise ValueError("output parent is a reparse point")
        buf = ctypes.create_unicode_buffer(32768)
        length = kernel.GetFinalPathNameByHandleW(directory, buf, len(buf), 0)
        if not length or length >= len(buf):
            raise OSError("Cannot verify output parent")
        final_name = buf.value
        if final_name.startswith("\\\\?\\UNC\\"):
            final_name = "\\\\" + final_name[8:]
        else:
            final_name = final_name.removeprefix("\\\\?\\")
        final = Path(final_name)
        if os.path.normcase(str(final)) != os.path.normcase(str(parent)):
            raise ValueError("output parent changed during validation")
        name = target.name
        text = ctypes.create_unicode_buffer(name)
        unicode = UnicodeString(len(name) * 2, (len(name) + 1) * 2, ctypes.cast(text, wintypes.LPWSTR))
        attrs = ObjectAttributes(ctypes.sizeof(ObjectAttributes), directory, ctypes.pointer(unicode),
                                 0x40, None, None)  # OBJ_CASE_INSENSITIVE
        ios = IoStatus()
        ntdll.NtCreateFile.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                       ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IoStatus),
                                       ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG,
                                       wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG]
        ntdll.NtCreateFile.restype = ctypes.c_long
        status = ntdll.NtCreateFile(ctypes.byref(handle),
                                   (0x10000 if delete else 0x40000000) | 0x80 | 0x100000,
                                   ctypes.byref(attrs), ctypes.byref(ios), None, 0,
                                   share, 1 if delete else (2 if exclusive else 3),  # FILE_OPEN / CREATE / OPEN_IF
                                   0x40 | 0x20 | OPEN_REPARSE, None, 0)  # NON_DIRECTORY_FILE | SYNCHRONOUS_IO_NONALERT
        if status < 0:
            if status & 0xffffffff == 0xC0000035:
                raise FileExistsError(str(target))
            raise OSError(f"NtCreateFile failed: NTSTATUS 0x{status & 0xffffffff:08x}")
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & REPARSE_ATTRIBUTE:
            raise ValueError("output target is a reparse point")
        if delete:
            kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.SetFileInformationByHandle.restype = wintypes.BOOL
            disposition = wintypes.BOOLEAN(1)
            if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                raise ctypes.WinError(ctypes.get_last_error())
            return None
        fd = msvcrt.open_osfhandle(int(handle.value), os.O_WRONLY | os.O_BINARY)
        handle = wintypes.HANDLE()
        return fd
    finally:
        if handle.value:
            kernel.CloseHandle(handle)
        kernel.CloseHandle(directory)


def _open_contained_file(root: Path | str, candidate: Path | str):
    """Open one checked file without a pathname re-open during response delivery.

    POSIX walks each directory with openat/O_NOFOLLOW; on Windows check the
    opened handle's *final* path, since Python lacks openat and O_NOFOLLOW there.
    """
    path = resolve_contained_path(root, candidate, must_be_file=True)
    root_path = Path(root).expanduser().absolute()
    parts = path.relative_to(root_path).parts
    if os.name != "nt":
        flags = os.O_RDONLY | os.O_NOFOLLOW
        directory = os.open(root_path.anchor, flags | os.O_DIRECTORY)
        try:
            for part in root_path.parts[1:]:
                next_directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                os.close(directory)
                directory = next_directory
            for part in parts[:-1]:
                next_directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                os.close(directory)
                directory = next_directory
            fd = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        import stat
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("artifact is not a regular file")
    else:
        import ctypes
        from ctypes import wintypes
        import msvcrt
        expected_root = root_path
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            handle = msvcrt.get_osfhandle(fd)
            buf = ctypes.create_unicode_buffer(32768)
            final_name = ctypes.windll.kernel32.GetFinalPathNameByHandleW
            final_name.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            final_name.restype = wintypes.DWORD
            size = final_name(handle, buf, len(buf), 0)
            if not size or size >= len(buf):
                raise OSError("Cannot inspect opened file path")
            final = buf.value.removeprefix("\\\\?\\")
            if not Path(final).is_relative_to(expected_root):
                raise ValueError("opened artifact escaped project root")
        except BaseException:
            os.close(fd)
            raise
    return os.fdopen(fd, "rb")


def contained_file_response(root: Path | str, candidate: Path | str, *, media_type: str, filename: str | None = None):
    """Stream from the checked open handle, not a later FileResponse path open."""
    handle = _open_contained_file(root, candidate)

    def chunks():
        with handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    headers = {}
    if filename:
        from urllib.parse import quote
        headers["Content-Disposition"] = f"attachment; filename*=utf-8''{quote(filename)}"
    return StreamingResponse(chunks(), media_type=media_type, headers=headers)
