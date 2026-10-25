# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

"""Detect whether a path lives on a network volume, and size worker pools
accordingly.

Why this exists: a scan's worker pools read every file they hash or decode,
so on a network volume the pool turns into many simultaneous readers
hammering one remote share. kDolphin/Fast_Duplicate_Finder (a Swift
duplicate finder) hit the same wall and benched it: on SMB, 6 hash workers
ran 2-3x faster than 3, while throwing the full core count at the share
was slower than either. So when any scanned path is on a network volume,
pools are capped at NETWORK_VOLUME_MAX_WORKERS (6); local disks keep the
full CPU count.

Every function here must never raise: volume detection is a performance
hint, and a scan must never fail because a mount table was unreadable or
a platform call was unavailable. On any error or unknown platform,
``is_network_path`` returns False (treat the volume as local).
"""

import ctypes
import multiprocessing
import os
import posixpath
import sys

# kDolphin/Fast_Duplicate_Finder benched 6 hash workers as the sweet spot
# on SMB (2-3x faster than 3 workers); more workers than that slowed the
# scan down again as the share saturated.
NETWORK_VOLUME_MAX_WORKERS = 6

# Filesystem types that live on the other end of a network connection
# (Linux /proc/mounts names).
NETWORK_FSTYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smbfs",
        "smb3",
        "sshfs",
        "fuse.sshfs",
        "davfs",
        "davfs2",
        "afp",
        "afpfs",
        "ncpfs",
        "glusterfs",
        "fuse.glusterfs",
        "ceph",
        "fuse.ceph",
        "9p",
    }
)

# macOS statfs(2) flag: set when the filesystem is local. Network mounts
# (SMB, NFS, AFP, ...) do not have it.
_MNT_LOCAL = 0x00001000

# Offset of f_flags in macOS struct statfs: 4 + 4 + 5*8 + 8 + 4 + 4 = 64.
# The buffer statfs writes into must hold the whole struct (~2 KB on
# macOS), so it is allocated generously -- see _statfs_flags.
_F_FLAGS_OFFSET = 64
_STATFS_BUFFER_SIZE = 4096

# Windows GetDriveTypeW() return value for a network drive.
_DRIVE_REMOTE = 4


# ---------------------------------------------------------------------------
# Platform helpers (small and separately mockable, so tests can drive each
# platform without running on it)
# ---------------------------------------------------------------------------


def _statfs_flags(path):
    """Return the statfs f_flags for ``path`` on macOS, or None on failure.

    The flags live at a fixed offset (64) in struct statfs, but the whole
    struct is ~2 KB -- so the call writes into a generously sized raw
    buffer instead of a hand-defined struct. (A struct defined only up
    to f_flags is 72 bytes; statfs would write past it and corrupt the
    heap, which crashed the macOS CI job -- and would have crashed the
    shipped app on any scan.)
    """
    try:
        libc = ctypes.CDLL("libc.dylib", use_errno=True)
        buf = ctypes.create_string_buffer(_STATFS_BUFFER_SIZE)
        if libc.statfs(os.fsencode(path), buf) != 0:
            return None
        return ctypes.c_uint32.from_buffer(buf, _F_FLAGS_OFFSET).value
    except Exception:
        return None


def _windows_drive_type(path):
    """Return the GetDriveTypeW() value for ``path``'s drive, or None."""
    try:
        drive, _tail = os.path.splitdrive(os.path.abspath(path))
        if not drive:
            return None
        root = drive + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(root)
    except Exception:
        return None


def _unescape_mount_path(text):
    """Undo the octal escapes /proc/mounts uses in mount points."""
    return text.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def _read_proc_mounts():
    """Parse /proc/mounts into a [(mountpoint, fstype)] list.

    Returns [] when the file cannot be read or parsed.
    """
    entries = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                entries.append((_unescape_mount_path(parts[1]), parts[2]))
    except Exception:
        return []
    return entries


class _LinuxMountTable:
    """A parsed /proc/mounts, answering "which fstype is this path on?".

    Built once per call and reused for every path in it, so a scan of
    thousands of files reads /proc/mounts once instead of once per file.
    """

    def __init__(self, entries):
        # Longest mount point first, so a nested mount wins over its
        # parent (and "/" sorts last as the catch-all).
        self._entries = sorted(entries, key=lambda entry: len(entry[0]), reverse=True)

    def fstype_for(self, path):
        # POSIX rules, not os.path: the table and the paths are Linux
        # /proc/mounts data, and os.path.abspath on Windows would turn
        # "/mnt/nas/..." into "C:\\mnt\\nas\\..." so nothing matched.
        path = posixpath.normpath(os.fspath(path))
        for mountpoint, fstype in self._entries:
            if mountpoint == "/":
                return fstype
            if path == mountpoint or path.startswith(mountpoint.rstrip("/") + "/"):
                return fstype
        return None


def _linux_mount_table():
    return _LinuxMountTable(_read_proc_mounts())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_network_path(path, _mount_table=None):
    """True when ``path`` is on a network volume. Never raises.

    ``_mount_table`` is an internal hook for sharing one parsed
    /proc/mounts across many paths (see pool_size_for_paths); callers
    should not pass it.
    """
    try:
        path = os.fspath(path)
    except Exception:
        return False
    try:
        if sys.platform == "darwin":
            flags = _statfs_flags(path)
            return flags is not None and not (flags & _MNT_LOCAL)
        if sys.platform.startswith("linux"):
            table = _mount_table if _mount_table is not None else _linux_mount_table()
            return table.fstype_for(path) in NETWORK_FSTYPES
        if sys.platform == "win32":
            return _windows_drive_type(path) == _DRIVE_REMOTE
        return False
    except Exception:
        return False


def pool_size_for_paths(paths, default=None):
    """How many pool workers to use for files under ``paths``.

    Returns ``default`` (or the CPU count when ``default`` is None) for
    local volumes, and min(default, NETWORK_VOLUME_MAX_WORKERS) when any
    path is on a network volume. The mount table is read once and shared
    across all paths, so this stays cheap for thousands of files. Never
    raises; on any error it returns the default.
    """
    try:
        if default is None:
            default = multiprocessing.cpu_count()
        default = max(1, int(default))
        if default <= NETWORK_VOLUME_MAX_WORKERS:
            return default
        table = _linux_mount_table() if sys.platform.startswith("linux") else None
        for path in paths:
            if is_network_path(path, _mount_table=table):
                return NETWORK_VOLUME_MAX_WORKERS
        return default
    except Exception:
        try:
            return max(1, int(default))
        except Exception:
            return NETWORK_VOLUME_MAX_WORKERS
