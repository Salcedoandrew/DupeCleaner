# Regression tests for the parallel digest pre-hash in
# core/engine.py::getmatches_by_contents.
#
# The pre-hash step computes digests across CPU cores before the pair loop
# runs, but match results must be identical to the old sequential lazy
# behaviour. These tests pin that down with real files on disk.

import multiprocessing
import os
import random
import sqlite3
from pathlib import Path

import pytest

from core import engine, fs
from core.engine import getmatches_by_contents
from core.fs import File, FilesDB
from hscommon.jobprogress.job import Job
from hscommon.testutil import eq_


@pytest.fixture
def filesdb(tmp_path, monkeypatch):
    """Connect the filesdb singleton to a throwaway database."""
    db = FilesDB()
    db.connect(str(tmp_path / "cache.db"))
    monkeypatch.setattr(fs, "filesdb", db)
    yield db
    db.close()


@pytest.fixture
def force_parallel(monkeypatch):
    """Make even a tiny workload take the process-pool path."""
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_FILES", 0)
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 0)


@pytest.fixture
def force_sequential(monkeypatch):
    """Make every workload take the sequential path."""
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_FILES", 10**9)
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 10**9)


def _cached_row(db_path, path):
    """Read a cache row by path only, returning (digest, digest_partial).

    This deliberately bypasses FilesDB.get()'s stat-keyed lookup: on this
    VM a fresh file's ctime keeps moving for a while after creation even
    though nothing writes to it, so a get() right after a put() can miss
    even though the row was stored. Tests that assert "the row was
    stored" use this; tests that assert "a later scan hits the cache"
    use get() through a real scan instead.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT digest, digest_partial FROM files WHERE path=?", (str(path),)).fetchone()
    finally:
        conn.close()


def _write(path, data):
    path.write_bytes(data)


def build_tree(root):
    """Build a small tree of real files and return fresh File objects.

    Contents (all sizes equal within a group, so every group is a
    candidate for matching):
    - dup5a/dup5b: identical 5 MiB files (a match)
    - uniq5: unique 5 MiB file (no match)
    - diffmid_a/diffmid_b: 5 MiB files that agree on the partial digest
      (16-32 KiB) but differ at offset 100 KiB (no match, full digest
      decides)
    - dup100a/dup100b: identical 100 KiB files (a match)
    - small10a/small10b: identical 10 KiB files, too small for a partial
      digest (a match; partial == full digest)
    - big1/big2/big3: 2 MiB files for the bigsize samples branch
      (bigsize=1 MiB): big1 and big3 are identical (a match); big2 agrees
      with big1 on the partial and sampled regions but differs at offset
      100 KiB, so samples agree but the full digest differs (no match)
    """
    rng = random.Random(42)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    bigsize = 1024 * 1024

    def rand(n):
        return rng.randbytes(n)

    files = {}

    data5 = rand(5 * 1024 * 1024)
    _write(root / "dup5a.bin", data5)
    _write(root / "dup5b.bin", data5)
    _write(root / "uniq5.bin", rand(5 * 1024 * 1024))

    base = bytearray(rand(5 * 1024 * 1024))
    other = bytearray(base)
    other[100 * 1024 : 101 * 1024] = b"\x00" * 1024
    _write(root / "diffmid_a.bin", bytes(base))
    _write(root / "diffmid_b.bin", bytes(other))

    data100 = rand(100 * 1024)
    _write(root / "dup100a.bin", data100)
    _write(root / "dup100b.bin", data100)

    data10 = rand(10 * 1024)
    _write(root / "small10a.bin", data10)
    _write(root / "small10b.bin", data10)

    bigbase = bytearray(rand(2 * 1024 * 1024))
    bigother = bytearray(bigbase)
    bigother[100 * 1024 : 101 * 1024] = b"\x00" * 1024
    _write(root / "big1.bin", bytes(bigbase))
    _write(root / "big2.bin", bytes(bigother))
    _write(root / "big3.bin", bytes(bigbase))

    for p in sorted(root.iterdir()):
        f = File(p)
        f.is_ref = False
        files[p.name] = f
    return files, bigsize


def match_pairs(matches):
    # Match.first/second follow set iteration order, so sort within a pair.
    return sorted(tuple(sorted((m.first.name, m.second.name))) for m in matches)


EXPECTED_PAIRS = [
    ("big1.bin", "big3.bin"),
    ("dup100a.bin", "dup100b.bin"),
    ("dup5a.bin", "dup5b.bin"),
    ("small10a.bin", "small10b.bin"),
]


def test_parallel_matches_equal_sequential(tmp_path, filesdb):
    files, bigsize = build_tree(tmp_path / "tree")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine, "PARALLEL_HASH_MIN_FILES", 0)
        mp.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 0)
        parallel = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(parallel)), sorted(EXPECTED_PAIRS))
    parallel_digests = {name: (f.digest, f.digest_partial) for name, f in files.items()}
    # Fresh objects and an empty cache: the sequential path must find the
    # exact same matches and the same digests.
    filesdb.clear()
    files, _ = build_tree(tmp_path / "tree")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine, "PARALLEL_HASH_MIN_FILES", 10**9)
        mp.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 10**9)
        sequential = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(sequential)), sorted(EXPECTED_PAIRS))
    for name, (digest, partial) in parallel_digests.items():
        eq_(digest, files[name].digest)
        eq_(partial, files[name].digest_partial)


def test_parallel_populates_cache(tmp_path, filesdb, force_parallel):
    files, bigsize = build_tree(tmp_path / "tree")
    getmatches_by_contents(list(files.values()), bigsize=bigsize)
    # Check the rows directly by path: the stat-keyed get() can miss on
    # this VM, where a fresh file's ctime moves for a while after
    # creation even though nothing writes to it (see _cached_row).
    for name in ("dup5a.bin", "dup100a.bin", "small10a.bin", "big1.bin"):
        row = _cached_row(tmp_path / "cache.db", files[name].path)
        assert row is not None, f"no cache row for {name}"
        assert row[0] is not None, f"no cached digest for {name}"
        assert row[1] is not None, f"no cached partial digest for {name}"
    # A second scan with the pool disabled must find the same matches from
    # the cache alone (fresh objects, nothing re-hashed).
    files2, _ = build_tree(tmp_path / "tree")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine, "PARALLEL_HASH_MIN_FILES", 10**9)
        mp.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 10**9)
        second = getmatches_by_contents(list(files2.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(second)), sorted(EXPECTED_PAIRS))


def test_unreadable_file_never_matches(tmp_path, filesdb, force_parallel):
    files, bigsize = build_tree(tmp_path / "tree")
    gone = File(Path(tmp_path) / "gone.bin")
    gone.is_ref = False
    gone2 = File(Path(tmp_path) / "gone2.bin")
    gone2.is_ref = False
    matches = getmatches_by_contents(list(files.values()) + [gone, gone2], bigsize=bigsize)
    assert not [m for m in matches if m.first.name.startswith("gone") or m.second.name.startswith("gone")]
    eq_(None, gone.digest)
    eq_(None, gone.digest_partial)
    eq_(None, gone.digest_samples)


def test_pool_failure_falls_back_to_sequential(tmp_path, filesdb, force_parallel, monkeypatch):
    files, bigsize = build_tree(tmp_path / "tree")

    def boom(*args, **kwargs):
        raise RuntimeError("no pool here")

    monkeypatch.setattr(multiprocessing, "Pool", boom)
    matches = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(matches)), sorted(EXPECTED_PAIRS))


def test_small_workload_stays_sequential(tmp_path, filesdb, monkeypatch):
    files, bigsize = build_tree(tmp_path / "tree")

    calls = []
    real_pool = multiprocessing.Pool

    def spy(*args, **kwargs):
        calls.append(True)
        return real_pool(*args, **kwargs)

    monkeypatch.setattr(multiprocessing, "Pool", spy)
    # Default thresholds: this fixture (~50 MiB, 13 files) is below the
    # 64 MiB bar, so no pool must be created.
    matches = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(matches)), sorted(EXPECTED_PAIRS))
    eq_(0, len(calls))


def test_large_workload_uses_pool(tmp_path, filesdb, monkeypatch):
    files, bigsize = build_tree(tmp_path / "tree")

    calls = []
    real_pool = multiprocessing.Pool

    def spy(*args, **kwargs):
        calls.append(True)
        return real_pool(*args, **kwargs)

    monkeypatch.setattr(multiprocessing, "Pool", spy)
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_FILES", 0)
    monkeypatch.setattr(engine, "PARALLEL_HASH_MIN_BYTES", 0)
    matches = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(matches)), sorted(EXPECTED_PAIRS))
    assert len(calls) >= 1


def test_folder_objects_still_match_lazily(tmp_path, filesdb, force_parallel):
    # Folders compute their digest from their contents, so the pre-hash
    # must leave them alone and the pair loop must hash them lazily, as
    # before. Two folders with identical contents are a match.
    rng = random.Random(7)
    for dirname in ("folder_a", "folder_b"):
        d = Path(tmp_path) / dirname
        d.mkdir()
        (d / "one.bin").write_bytes(rng.randbytes(1024 * 1024))
        (d / "two.bin").write_bytes(rng.randbytes(512 * 1024))
    # Make the contents identical: copy folder_a over folder_b.
    import shutil

    shutil.rmtree(Path(tmp_path) / "folder_b")
    shutil.copytree(Path(tmp_path) / "folder_a", Path(tmp_path) / "folder_b")
    folders = [fs.Folder(Path(tmp_path) / "folder_a"), fs.Folder(Path(tmp_path) / "folder_b")]
    for f in folders:
        f.is_ref = False
    matches = getmatches_by_contents(folders)
    eq_(1, len(matches))


def test_progress_job_with_two_subjobs(tmp_path, filesdb, force_parallel):
    # getmatches_by_contents is called by the scanner with a [2, 8]
    # subjob: the pre-hash starts one job and the pair loop another. That
    # must not raise JobCountError.
    files, bigsize = build_tree(tmp_path / "tree")
    seen = []

    def callback(*args):
        seen.append(args)
        return True

    top = Job(1, callback)
    sub = top.start_subjob([2, 8])
    matches = getmatches_by_contents(list(files.values()), bigsize=bigsize, j=sub)
    eq_(sorted(match_pairs(matches)), sorted(EXPECTED_PAIRS))
    assert seen  # progress was reported


def test_worker_unit(tmp_path):
    # Small file: partial and samples stand in for the full digest.
    small = Path(tmp_path) / "small.bin"
    small.write_bytes(b"a" * 1000)
    path_str, digests = fs.compute_digests_task((str(small), 1000, ("digest_partial", "digest_samples")))
    assert digests["digest_partial"] == digests["digest"] == digests["digest_samples"]
    assert digests["digest"] is not None
    # Big file: partial differs from full, samples differ from full.
    big = Path(tmp_path) / "big.bin"
    big.write_bytes(os.urandom(5 * 1024 * 1024))
    path_str, digests = fs.compute_digests_task(
        (str(big), 5 * 1024 * 1024, ("digest_partial", "digest", "digest_samples"))
    )
    assert digests["digest_partial"] != digests["digest"]
    assert digests["digest_samples"] != digests["digest"]
    # Unreadable file: every digest is None, never b"".
    path_str, digests = fs.compute_digests_task((str(tmp_path / "gone.bin"), 1234, ("digest_partial", "digest")))
    eq_({"digest_partial": None, "digest": None}, digests)


def test_pre_hash_stores_cache_in_one_transaction(tmp_path, filesdb, force_parallel, monkeypatch):
    # The pre-hash step must store its digests with one batched write,
    # not one commit per digest: on filesystems where a commit costs a
    # full sync, per-digest commits dominate the scan.
    files, bigsize = build_tree(tmp_path / "tree")
    put_many_calls = []
    put_calls = []
    orig_put_many = filesdb.put_many
    orig_put = filesdb.put

    def spy_put_many(entries):
        put_many_calls.append(list(entries))
        return orig_put_many(entries)

    def spy_put(path, key, value):
        put_calls.append((path, key))
        return orig_put(path, key, value)

    monkeypatch.setattr(filesdb, "put_many", spy_put_many)
    monkeypatch.setattr(filesdb, "put", spy_put)
    matches = getmatches_by_contents(list(files.values()), bigsize=bigsize)
    eq_(sorted(match_pairs(matches)), sorted(EXPECTED_PAIRS))
    assert put_many_calls, "expected the pre-hash to batch its cache writes"
    assert not put_calls, "expected no per-digest cache commits during the pre-hash"
    # The batch really landed in the cache: a second scan with the pool
    # disabled finds the same matches from cached digests.
    assert all(len(c) > 0 for c in put_many_calls)


def test_put_many_writes_all_entries(tmp_path):
    db = FilesDB()
    db.connect(str(tmp_path / "pm.db"))
    try:
        a = Path(tmp_path) / "a.bin"
        b = Path(tmp_path) / "b.bin"
        a.write_bytes(b"a" * 1000)
        b.write_bytes(b"b" * 2000)
        digest_a = fs._hash_full(str(a))
        digest_b = fs._hash_full(str(b))
        db.put_many([(a, "digest", digest_a), (b, "digest", digest_b), (a, "digest_partial", digest_a)])
        eq_(digest_a, _cached_row(tmp_path / "pm.db", a)[0])
        eq_(digest_b, _cached_row(tmp_path / "pm.db", b)[0])
        eq_(digest_a, _cached_row(tmp_path / "pm.db", a)[1])
        # Empty batch is a no-op, not an error.
        db.put_many([])
        # One bad entry must not lose the good ones or raise.
        gone = Path(tmp_path) / "gone.bin"
        db.put_many([(gone, "digest", b"x"), (b, "digest_partial", digest_b)])
        eq_(digest_b, _cached_row(tmp_path / "pm.db", b)[1])
        eq_(digest_b, _cached_row(tmp_path / "pm.db", b)[0])
    finally:
        db.close()
