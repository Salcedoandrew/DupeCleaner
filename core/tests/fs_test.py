# Created By: Virgil Dupras
# Created On: 2009-10-23
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import sys
import typing
from os import urandom

import pytest
from pathlib import Path
from hscommon.testutil import eq_
from core.tests.directories_test import create_fake_fs

from core import fs

hasher: typing.Callable
try:
    import xxhash

    hasher = xxhash.xxh128
except ImportError:
    import hashlib

    hasher = hashlib.md5


def create_fake_fs_with_random_data(rootpath):
    rootpath = rootpath.joinpath("fs")
    rootpath.mkdir()
    rootpath.joinpath("dir1").mkdir()
    rootpath.joinpath("dir2").mkdir()
    rootpath.joinpath("dir3").mkdir()
    data1 = urandom(200 * 1024)  # 200KiB
    data2 = urandom(1024 * 1024)  # 1MiB
    data3 = urandom(10 * 1024 * 1024)  # 10MiB
    with rootpath.joinpath("file1.test").open("wb") as fp:
        fp.write(data1)
    with rootpath.joinpath("file2.test").open("wb") as fp:
        fp.write(data2)
    with rootpath.joinpath("file3.test").open("wb") as fp:
        fp.write(data3)
    with rootpath.joinpath("dir1", "file1.test").open("wb") as fp:
        fp.write(data1)
    with rootpath.joinpath("dir2", "file2.test").open("wb") as fp:
        fp.write(data2)
    with rootpath.joinpath("dir3", "file3.test").open("wb") as fp:
        fp.write(data3)
    return rootpath


def test_size_aggregates_subfiles(tmpdir):
    p = create_fake_fs(Path(str(tmpdir)))
    b = fs.Folder(p)
    eq_(b.size, 12)


def test_digest_aggregate_subfiles_sorted(tmpdir):
    # dir.allfiles can return child in any order. Thus, bundle.digest must aggregate
    # all files' digests it contains, but it must make sure that it does so in the
    # same order everytime.
    p = create_fake_fs_with_random_data(Path(str(tmpdir)))
    b = fs.Folder(p)
    digest1 = fs.File(p.joinpath("dir1", "file1.test")).digest
    digest2 = fs.File(p.joinpath("dir2", "file2.test")).digest
    digest3 = fs.File(p.joinpath("dir3", "file3.test")).digest
    digest4 = fs.File(p.joinpath("file1.test")).digest
    digest5 = fs.File(p.joinpath("file2.test")).digest
    digest6 = fs.File(p.joinpath("file3.test")).digest
    # The expected digest is the hash of digests for folders and the direct digest for files
    folder_digest1 = hasher(digest1).digest()
    folder_digest2 = hasher(digest2).digest()
    folder_digest3 = hasher(digest3).digest()
    digest = hasher(folder_digest1 + folder_digest2 + folder_digest3 + digest4 + digest5 + digest6).digest()
    eq_(b.digest, digest)


def test_partial_digest_aggregate_subfile_sorted(tmpdir):
    p = create_fake_fs_with_random_data(Path(str(tmpdir)))
    b = fs.Folder(p)
    digest1 = fs.File(p.joinpath("dir1", "file1.test")).digest_partial
    digest2 = fs.File(p.joinpath("dir2", "file2.test")).digest_partial
    digest3 = fs.File(p.joinpath("dir3", "file3.test")).digest_partial
    digest4 = fs.File(p.joinpath("file1.test")).digest_partial
    digest5 = fs.File(p.joinpath("file2.test")).digest_partial
    digest6 = fs.File(p.joinpath("file3.test")).digest_partial
    # The expected digest is the hash of digests for folders and the direct digest for files
    folder_digest1 = hasher(digest1).digest()
    folder_digest2 = hasher(digest2).digest()
    folder_digest3 = hasher(digest3).digest()
    digest = hasher(folder_digest1 + folder_digest2 + folder_digest3 + digest4 + digest5 + digest6).digest()
    eq_(b.digest_partial, digest)

    digest1 = fs.File(p.joinpath("dir1", "file1.test")).digest_samples
    digest2 = fs.File(p.joinpath("dir2", "file2.test")).digest_samples
    digest3 = fs.File(p.joinpath("dir3", "file3.test")).digest_samples
    digest4 = fs.File(p.joinpath("file1.test")).digest_samples
    digest5 = fs.File(p.joinpath("file2.test")).digest_samples
    digest6 = fs.File(p.joinpath("file3.test")).digest_samples
    # The expected digest is the digest of digests for folders and the direct digest for files
    folder_digest1 = hasher(digest1).digest()
    folder_digest2 = hasher(digest2).digest()
    folder_digest3 = hasher(digest3).digest()
    digest = hasher(folder_digest1 + folder_digest2 + folder_digest3 + digest4 + digest5 + digest6).digest()
    eq_(b.digest_samples, digest)


def test_has_file_attrs(tmpdir):
    # a Folder must behave like a file, so it must have mtime attributes
    b = fs.Folder(Path(str(tmpdir)))
    assert b.mtime > 0
    eq_(b.extension, "")


def test_unreadable_file_digest_is_none(tmpdir):
    # A digest that could not be read must be None, not b"": two files
    # hashing to b"" would be reported as exact duplicates of each other.
    p = Path(str(tmpdir)).joinpath("gone.test")
    f = fs.File(p)
    eq_(None, f.digest)
    eq_(None, f.digest_partial)
    eq_(None, f.digest_samples)


def test_filesdb_cache_key_includes_ctime(tmpdir):
    # Restoring a file (cp -p, rsync -a) with different content of the same
    # size while preserving its mtime must not reuse the old file's cached
    # digest. A restore writes a new file, so ctime changes even though
    # mtime does not.
    import os

    from core.fs import FilesDB

    db = FilesDB()
    db.connect(str(Path(str(tmpdir)).joinpath("cache.db")))
    try:
        p = Path(str(tmpdir)).joinpath("f.test")
        p.write_bytes(b"aaaaaaaaaa")
        db.put(p, "digest", b"digest-v1")
        eq_(b"digest-v1", db.get(p, "digest"))
        st = p.stat()
        p.unlink()
        p.write_bytes(b"bbbbbbbbbb")  # same size, different content, new file
        os.utime(p, (st.st_atime, st.st_mtime))  # restore mtime; ctime moved on
        eq_(None, db.get(p, "digest"))
    finally:
        db.close()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="On Windows st_ctime is the creation time, which an in-place rewrite does not change",
)
def test_filesdb_cache_key_includes_ctime_inplace(tmpdir):
    # Same as above, but the file is rewritten in place instead of
    # replaced. On POSIX ctime moves on any write, so the stale digest is
    # still caught. Windows cannot see this case (see the skip above).
    import os

    from core.fs import FilesDB

    db = FilesDB()
    db.connect(str(Path(str(tmpdir)).joinpath("cache.db")))
    try:
        p = Path(str(tmpdir)).joinpath("f.test")
        p.write_bytes(b"aaaaaaaaaa")
        db.put(p, "digest", b"digest-v1")
        eq_(b"digest-v1", db.get(p, "digest"))
        st = p.stat()
        p.write_bytes(b"bbbbbbbbbb")  # same size, different content
        os.utime(p, (st.st_atime, st.st_mtime))  # restore mtime; ctime moved on
        eq_(None, db.get(p, "digest"))
    finally:
        db.close()
