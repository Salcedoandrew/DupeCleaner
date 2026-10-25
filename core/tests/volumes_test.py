# Tests for core/volumes.py: network-volume detection on each platform
# (driven through mocks, since the suite runs on Linux only) and the
# worker-pool cap that follows from it.
#
# Volume detection is a performance hint, never a correctness gate, so
# the module must never raise: several tests pin that down too.

import sys

import pytest

from core import volumes
from core.volumes import (
    NETWORK_VOLUME_MAX_WORKERS,
    _LinuxMountTable,
    _unescape_mount_path,
    is_network_path,
    pool_size_for_paths,
)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


@pytest.fixture
def darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")


def test_unescape_mount_path():
    # /proc/mounts escapes spaces, tabs, newlines and backslashes in
    # mount points as octal.
    assert _unescape_mount_path("/mnt/my\\040share") == "/mnt/my share"
    assert _unescape_mount_path("/mnt/a\\011b\\012c\\134d") == "/mnt/a\tb\nc\\d"
    assert _unescape_mount_path("/plain/path") == "/plain/path"


def test_mount_table_longest_prefix_wins():
    table = _LinuxMountTable(
        [
            ("/", "ext4"),
            ("/mnt", "ext4"),
            ("/mnt/nas", "nfs"),
            ("/mnt/nas/photos", "cifs"),
        ]
    )
    assert table.fstype_for("/mnt/nas/photos/wedding.jpg") == "cifs"
    assert table.fstype_for("/mnt/nas/other.txt") == "nfs"
    assert table.fstype_for("/mnt/local.txt") == "ext4"
    assert table.fstype_for("/etc/hosts") == "ext4"
    # A mount point must match on a path boundary, not a string prefix:
    # /mnt/nas2 is under /mnt, not under /mnt/nas.
    assert table.fstype_for("/mnt/nas2/file.txt") == "ext4"
    # With no "/" entry, a path on no listed mount has no fstype.
    assert _LinuxMountTable([("/mnt/nas", "nfs")]).fstype_for("/home/a.jpg") is None


def test_linux_network_fstype(linux, monkeypatch):
    monkeypatch.setattr(
        volumes,
        "_read_proc_mounts",
        lambda: [("/", "ext4"), ("/mnt/nas", "nfs"), ("/mnt/smb", "cifs"), ("/mnt/ssh", "fuse.sshfs")],
    )
    assert is_network_path("/mnt/nas/photos/a.jpg")
    assert is_network_path("/mnt/smb/a.jpg")
    assert is_network_path("/mnt/ssh/a.jpg")
    assert not is_network_path("/home/andrew/a.jpg")
    # The mount point itself is on the share too.
    assert is_network_path("/mnt/nas")


def test_linux_unreadable_mounts_is_local(linux, monkeypatch):
    # /proc/mounts unreadable: detection fails safe to "local".
    monkeypatch.setattr(volumes, "_read_proc_mounts", lambda: [])
    assert not is_network_path("/mnt/nas/a.jpg")


def test_linux_local_fstypes_are_not_network(linux, monkeypatch):
    monkeypatch.setattr(
        volumes,
        "_read_proc_mounts",
        lambda: [("/", "ext4"), ("/mnt/usb", "vfat"), ("/mnt/overlay", "overlay")],
    )
    assert not is_network_path("/mnt/usb/a.jpg")
    assert not is_network_path("/mnt/overlay/a.jpg")


def test_darwin_statfs_flag(darwin, monkeypatch):
    # MNT_LOCAL set -> local disk; clear -> network volume; statfs
    # failing (None) -> fail safe to local.
    monkeypatch.setattr(volumes, "_statfs_flags", lambda path: 0x00001000)
    assert not is_network_path("/Volumes/Macintosh HD/a.jpg")
    monkeypatch.setattr(volumes, "_statfs_flags", lambda path: 0x00000000)
    assert is_network_path("/Volumes/NAS/a.jpg")
    monkeypatch.setattr(volumes, "_statfs_flags", lambda path: None)
    assert not is_network_path("/Volumes/NAS/a.jpg")


def test_statfs_buffer_fits_whole_struct():
    # Regression test for the macOS segfault: statfs() writes the whole
    # struct statfs (~2 KB on macOS), so the buffer it writes into must
    # be comfortably bigger than that. A hand-defined struct ending at
    # f_flags is only 72 bytes and overflows the heap.
    assert volumes._STATFS_BUFFER_SIZE >= 4096
    assert volumes._F_FLAGS_OFFSET == 64


def test_windows_drive_type(windows, monkeypatch):
    monkeypatch.setattr(volumes, "_windows_drive_type", lambda path: 4)  # DRIVE_REMOTE
    assert is_network_path("Z:\\photos\\a.jpg")
    monkeypatch.setattr(volumes, "_windows_drive_type", lambda path: 3)  # DRIVE_FIXED
    assert not is_network_path("C:\\Users\\a.jpg")
    monkeypatch.setattr(volumes, "_windows_drive_type", lambda path: None)
    assert not is_network_path("Z:\\photos\\a.jpg")


def test_unknown_platform_is_local(monkeypatch):
    monkeypatch.setattr(sys, "platform", "haiku")
    assert not is_network_path("/some/path/a.jpg")


def test_is_network_path_never_raises(monkeypatch):
    # Bad inputs and exploding helpers must return False, not raise.
    assert not is_network_path(None)
    assert not is_network_path(12345)

    class BadPath:
        def __fspath__(self):
            raise RuntimeError("nope")

    assert not is_network_path(BadPath())
    monkeypatch.setattr(volumes, "_read_proc_mounts", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert not is_network_path("/mnt/nas/a.jpg")


def test_pool_size_caps_at_six_on_network(monkeypatch):
    monkeypatch.setattr(volumes, "is_network_path", lambda path, _mount_table=None: True)
    assert pool_size_for_paths(["/mnt/nas/a.jpg"], 16) == NETWORK_VOLUME_MAX_WORKERS
    assert pool_size_for_paths(["/mnt/nas/a.jpg"], 8) == NETWORK_VOLUME_MAX_WORKERS
    # A machine with 6 or fewer CPUs is already at/below the cap.
    assert pool_size_for_paths(["/mnt/nas/a.jpg"], 6) == 6
    assert pool_size_for_paths(["/mnt/nas/a.jpg"], 2) == 2


def test_pool_size_unchanged_on_local(monkeypatch):
    monkeypatch.setattr(volumes, "is_network_path", lambda path, _mount_table=None: False)
    assert pool_size_for_paths(["/home/andrew/a.jpg"], 16) == 16
    assert pool_size_for_paths(["/home/andrew/a.jpg"], 8) == 8


def test_pool_size_mixed_paths_cap_when_any_is_network(monkeypatch):
    seen = []

    def fake_is_network(path, _mount_table=None):
        seen.append(path)
        return "nas" in path

    monkeypatch.setattr(volumes, "is_network_path", fake_is_network)
    assert pool_size_for_paths(["/home/a.jpg", "/mnt/nas/b.jpg", "/home/c.jpg"], 16) == 6
    assert seen == ["/home/a.jpg", "/mnt/nas/b.jpg"]  # stops at the first network path
    assert pool_size_for_paths(["/home/a.jpg", "/home/c.jpg"], 16) == 16


def test_pool_size_empty_paths_is_default(monkeypatch):
    assert pool_size_for_paths([], 16) == 16
    assert pool_size_for_paths([], None) >= 1


def test_pool_size_reads_mount_table_once(linux, monkeypatch):
    # Thousands of files must not mean thousands of /proc/mounts reads.
    calls = []
    real_read = volumes._read_proc_mounts

    def counting_read():
        calls.append(1)
        return real_read()

    monkeypatch.setattr(volumes, "_read_proc_mounts", counting_read)
    paths = ["/home/andrew/file%d.jpg" % i for i in range(50)]
    assert pool_size_for_paths(paths, 16) == 16
    assert len(calls) == 1


def test_real_local_paths_are_local(tmp_path):
    # On this Linux VM, a real local directory is not a network volume,
    # and the pool size is a no-op for it.
    local_file = tmp_path / "a.jpg"
    local_file.write_bytes(b"x")
    assert not is_network_path(str(local_file))
    assert not is_network_path(tmp_path)
    assert pool_size_for_paths([str(local_file)], 16) == 16
