# Copyright 2026 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os
from pathlib import Path

from hscommon.testutil import eq_
from hscommon.util import get_file_ext

from core import fs
from core.directories import Directories, DirectoryState

BASE_MTIME_NS = 1_700_000_000_000_000_000


def make_package(root, name="Foo.app", contents=None, root_mtime_ns=BASE_MTIME_NS):
    """Create a fake macOS package: a dir with a Contents tree.

    ``contents`` maps relative paths inside the package to bytes. Every
    file and directory gets an explicit mtime, so two packages built with
    the same arguments are identical, and a test can change exactly one
    thing and see the digest move.
    """
    pkg = Path(root) / name
    (pkg / "Contents" / "MacOS").mkdir(parents=True)
    (pkg / "Contents" / "Resources").mkdir(parents=True)
    if contents is None:
        contents = {
            "Contents/Info.plist": b"plist-data",
            "Contents/MacOS/Foo": b"binary-data",
            "Contents/Resources/icon.icns": b"icon-data",
        }
    for i, (relpath, data) in enumerate(sorted(contents.items())):
        p = pkg / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        mtime_ns = BASE_MTIME_NS + i * 1_000_000_000
        os.utime(p, ns=(mtime_ns, mtime_ns))
    # Directory mtimes last, bottom-up, so creating files doesn't move them.
    for dirpath, _, _ in os.walk(pkg, topdown=False):
        os.utime(dirpath, ns=(root_mtime_ns, root_mtime_ns))
    return pkg


def collect(rootpath):
    """Scan ``rootpath`` with Directories and return the collected items."""
    d = Directories()
    d.add_path(Path(rootpath))
    return list(d.get_files())


class FakeKindFile(fs.File):
    """A fileclass that only handles one extension, like Photo/MusicFile."""

    @classmethod
    def can_handle(cls, path):
        return fs.File.can_handle(path) and get_file_ext(path.name) == "jpg"


# --- Detection ------------------------------------------------------------


def test_is_package_dir_by_extension(tmp_path):
    for ext in (
        ".app",
        ".appex",
        ".pkg",
        ".mpkg",
        ".bundle",
        ".framework",
        ".kext",
        ".plugin",
        ".component",
        ".saver",
        ".qlgenerator",
        ".mdimporter",
        ".action",
        ".prefPane",
        ".wdgt",
        ".xpc",
        ".service",
        ".docset",
    ):
        p = tmp_path / f"Thing{ext}"
        p.mkdir()
        assert fs.is_package_dir(p), ext
        # Detection is case-insensitive: Finder treats .APP like .app.
        q = tmp_path / f"Other{ext.upper()}"
        q.mkdir()
        assert fs.is_package_dir(q), ext.upper()


def test_is_package_dir_rejects_non_packages(tmp_path):
    regular = tmp_path / "regular"
    regular.mkdir()
    assert not fs.is_package_dir(regular)
    # A plain file is never a package, even with a bundle extension.
    plain = tmp_path / "Foo.app"
    plain.write_bytes(b"not a bundle")
    assert not fs.is_package_dir(plain)
    # Symlinks are never packages: scans exclude symlinks everywhere.
    target = make_package(tmp_path, "Real.app")
    link = tmp_path / "Link.app"
    os.symlink(target, link)
    assert not fs.is_package_dir(link)
    # A missing path is not a package (and does not raise).
    assert not fs.is_package_dir(tmp_path / "Nope.app")


def test_is_package_dir_accepts_dir_entry(tmp_path):
    make_package(tmp_path, "Foo.app")
    with os.scandir(tmp_path) as entries:
        for entry in entries:
            assert fs.is_package_dir(entry)


# --- The walk -------------------------------------------------------------


def test_package_not_descended(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    (tmp_path / "loose.txt").write_bytes(b"loose")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_bytes(b"inner")
    items = collect(tmp_path)
    paths = {item.path for item in items}
    # The package itself is there, but nothing inside it is.
    assert pkg in paths
    assert not any(pkg in p.parents for p in paths if p != pkg)
    assert tmp_path / "loose.txt" in paths
    assert sub / "inner.txt" in paths


def test_package_appears_once_as_folder(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    items = collect(tmp_path)
    packages = [item for item in items if item.path == pkg]
    eq_(len(packages), 1)
    assert isinstance(packages[0], fs.Folder)
    assert packages[0].is_package


def test_regular_dirs_still_descended(tmp_path):
    sub = tmp_path / "sub" / "deeper"
    sub.mkdir(parents=True)
    (sub / "a.txt").write_bytes(b"a")
    (sub / "b.txt").write_bytes(b"b")
    items = collect(tmp_path)
    paths = {item.path for item in items}
    assert sub / "a.txt" in paths
    assert sub / "b.txt" in paths


def test_nested_package_outer_wins(tmp_path):
    outer = make_package(tmp_path, "Outer.app")
    inner = make_package(outer, "Inner.app")
    items = collect(tmp_path)
    eq_(len(items), 1)
    eq_(items[0].path, outer)
    # The nested package is part of the outer package's fingerprint: change
    # a file inside it and the outer package's digest moves.
    before = fs.Folder(outer).digest
    target = inner / "Contents" / "MacOS" / "Foo"
    target.write_bytes(b"changed-binary")
    os.utime(target, ns=(BASE_MTIME_NS + 999_000_000_000, BASE_MTIME_NS + 999_000_000_000))
    assert fs.Folder(outer).digest != before


def test_package_as_scan_root(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    d = Directories()
    d.add_path(pkg)
    items = list(d.get_files())
    eq_(len(items), 1)
    assert isinstance(items[0], fs.Folder)
    eq_(items[0].path, pkg)


def test_empty_package(tmp_path):
    pkg = tmp_path / "Empty.app"
    pkg.mkdir()
    folder = fs.Folder(pkg)
    eq_(folder.size, 0)
    assert folder.digest is not None
    items = collect(tmp_path)
    eq_(len(items), 1)
    eq_(items[0].path, pkg)


def test_package_skipped_in_kind_scan(tmp_path):
    # In a Photo/Music-style scan a package is neither a photo nor a track:
    # it is skipped entirely, not descended into (even though it contains a
    # .jpg that the kind fileclass would otherwise accept).
    make_package(
        tmp_path,
        "Foo.app",
        contents={"Contents/Resources/photo.jpg": b"fake-jpeg"},
    )
    d = Directories()
    d.add_path(tmp_path)
    eq_(list(d.get_files(fileclasses=[FakeKindFile])), [])
    # The same holds when the package itself is the scan root.
    d = Directories()
    d.add_path(tmp_path / "Foo.app")
    eq_(list(d.get_files(fileclasses=[FakeKindFile])), [])


def test_package_reference_and_excluded_states(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    (tmp_path / "loose.txt").write_bytes(b"loose")
    d = Directories()
    d.add_path(tmp_path)
    d.states[pkg] = DirectoryState.REFERENCE
    items = list(d.get_files())
    packages = [item for item in items if item.path == pkg]
    eq_(len(packages), 1)
    assert packages[0].is_ref
    d = Directories()
    d.add_path(tmp_path)
    d.states[pkg] = DirectoryState.EXCLUDED
    items = list(d.get_files())
    assert pkg not in {item.path for item in items}
    # Excluding the package does not exclude the loose file next to it.
    assert tmp_path / "loose.txt" in {item.path for item in items}


# --- Fingerprint ----------------------------------------------------------


def test_identical_packages_have_same_digest(tmp_path):
    first = make_package(tmp_path / "one", "Foo.app")
    second = make_package(tmp_path / "two", "Bar.app")
    # Different names and different parents, same interior and mtimes: the
    # fingerprint covers the tree, not the package's own name or location.
    eq_(fs.Folder(first).digest, fs.Folder(second).digest)
    eq_(fs.Folder(first).size, fs.Folder(second).size)


def test_package_digest_changes_with_interior_content(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    before = fs.Folder(pkg).digest
    target = pkg / "Contents" / "MacOS" / "Foo"
    target.write_bytes(b"different-binary-of-the-same-length")
    os.utime(target, ns=(BASE_MTIME_NS + 999_000_000_000, BASE_MTIME_NS + 999_000_000_000))
    # A fresh Folder: the digest is recomputed, never read from a cache.
    assert fs.Folder(pkg).digest != before


def test_package_digest_changes_with_interior_mtime(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    before = fs.Folder(pkg).digest
    target = pkg / "Contents" / "Resources" / "icon.icns"
    os.utime(target, ns=(BASE_MTIME_NS + 999_000_000_000, BASE_MTIME_NS + 999_000_000_000))
    assert fs.Folder(pkg).digest != before


def test_package_digest_changes_with_root_mtime(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    before = fs.Folder(pkg).digest
    os.utime(pkg, ns=(BASE_MTIME_NS + 999_000_000_000, BASE_MTIME_NS + 999_000_000_000))
    assert fs.Folder(pkg).digest != before


def test_package_digest_changes_when_interior_file_renamed(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    before = fs.Folder(pkg).digest
    (pkg / "Contents" / "Resources" / "icon.icns").rename(pkg / "Contents" / "Resources" / "other.icns")
    assert fs.Folder(pkg).digest != before


def test_package_digest_changes_when_interior_file_added_or_removed(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    before = fs.Folder(pkg).digest
    added = pkg / "Contents" / "Resources" / "extra.txt"
    added.write_bytes(b"extra")
    assert fs.Folder(pkg).digest != before
    added.unlink()
    eq_(fs.Folder(pkg).digest, before)


def test_package_size_is_sum_of_contents(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    expected = sum(
        len(data)
        for data in (
            b"plist-data",
            b"binary-data",
            b"icon-data",
        )
    )
    eq_(fs.Folder(pkg).size, expected)


def test_package_digest_same_for_all_fields(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    folder = fs.Folder(pkg)
    # One fingerprint serves all three digest kinds.
    eq_(folder.digest, folder.digest_partial)
    eq_(folder.digest, folder.digest_samples)


def test_parent_folder_counts_package_once(tmp_path):
    # Guards the double-count: a package inside a regular folder must
    # count once in the parent's size and digest, not once as a subfolder
    # and once as a file.
    pkg = make_package(tmp_path, "Foo.app")
    (tmp_path / "loose.txt").write_bytes(b"loose")
    parent = fs.Folder(tmp_path)
    eq_(parent.size, fs.Folder(pkg).size + 5)
    before = parent.digest
    target = pkg / "Contents" / "MacOS" / "Foo"
    target.write_bytes(b"changed")
    os.utime(target, ns=(BASE_MTIME_NS + 999_000_000_000, BASE_MTIME_NS + 999_000_000_000))
    assert fs.Folder(tmp_path).digest != before


# --- Folder-mode scan -----------------------------------------------------


def test_package_in_folder_scan(tmp_path):
    pkg = make_package(tmp_path, "Foo.app")
    sub = tmp_path / "sub"
    sub.mkdir()
    d = Directories()
    d.add_path(tmp_path)
    folders = list(d.get_folders())
    paths = {folder.path for folder in folders}
    assert pkg in paths
    # No folder inside the package is yielded, but the regular subfolder is.
    assert not any(pkg in p.parents for p in paths if p != pkg)
    assert sub in paths
