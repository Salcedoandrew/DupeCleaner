# Regression tests for parallel picture preparation.
#
# prepare_pictures() computes image blocks in a process pool (spawn
# context) and writes them to the SqliteCache from the parent process.
# These tests pin down the contract: parallel results are identical to
# sequential ones, cached pictures are never recomputed, bad pictures are
# skipped instead of crashing the scan, a broken pool falls back to the
# sequential loop, and QImage decoding works in a spawned worker.

import multiprocessing
import os
from pathlib import Path

from PyQt5.QtGui import QImage

from hscommon.jobprogress import job as jobmod
from hscommon.jobprogress.job import Job
from hscommon.testutil import eq_

from core.pe import matchblock
from core.pe.cache_sqlite import SqliteCache
from core.pe.matchblock import _prepare_picture_task, prepare_pictures
from qt.pe.photo import File as QtPhoto

BLACK_BLOCKS = [(0, 0, 0)] * 225


def make_image(path, width, height, rgb):
    """Write a solid-colour PNG with QImage."""
    img = QImage(width, height, QImage.Format_RGB888)
    img.fill(rgb)
    assert img.save(str(path), "PNG")


def make_photos(tmpdir, count, prefix="p"):
    """Create ``count`` varied real photos and return QtPhoto objects."""
    sizes = [(64, 64), (100, 80), (200, 150), (320, 240), (128, 128)]
    pics = []
    for i in range(count):
        width, height = sizes[i % len(sizes)]
        rgb = ((i * 37) % 256 << 16) | ((i * 91) % 256 << 8) | (i * 53) % 256
        path = Path(str(tmpdir.join("%s%d.png" % (prefix, i))))
        make_image(path, width, height, rgb)
        pics.append(QtPhoto(path))
    return pics


def cache_contents(dbpath):
    cache = SqliteCache(dbpath)
    result = {path: cache[path] for path in list(cache)}
    cache.close()
    return result


def test_parallel_prep_matches_sequential(tmpdir, monkeypatch):
    # 40 pictures: enough to trigger the pool (>= 32). The parallel run
    # and the forced-sequential run must produce the same prepared list
    # (in input order), the same dimensions, and identical cache contents.
    pics_parallel = make_photos(tmpdir, 40)
    db_parallel = str(tmpdir.join("parallel.db"))
    prepared_parallel = prepare_pictures(
        pics_parallel, db_parallel, with_dimensions=True, match_rotated=False, j=jobmod.nulljob
    )
    eq_(40, len(prepared_parallel))
    eq_(
        [p.unicode_path for p in pics_parallel],
        [p.unicode_path for p in prepared_parallel],
    )
    dims_parallel = [p.dimensions for p in pics_parallel]

    pics_seq = make_photos(tmpdir, 40)
    db_seq = str(tmpdir.join("sequential.db"))
    monkeypatch.setattr(matchblock, "MIN_PICTURES_FOR_PARALLEL_PREP", 10**9)
    prepared_seq = prepare_pictures(pics_seq, db_seq, with_dimensions=True, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared_seq))
    eq_([p.unicode_path for p in pics_seq], [p.unicode_path for p in prepared_seq])
    eq_(dims_parallel, [p.dimensions for p in pics_seq])
    eq_(cache_contents(db_parallel), cache_contents(db_seq))


def test_rotated_parallel_matches_sequential(tmpdir, monkeypatch):
    # Rotated scans compute 8 block lists per picture; they must agree too.
    pics_parallel = make_photos(tmpdir, 5)
    db_parallel = str(tmpdir.join("parallel.db"))
    monkeypatch.setattr(matchblock, "MIN_PICTURES_FOR_PARALLEL_PREP", 1)
    prepared_parallel = prepare_pictures(
        pics_parallel, db_parallel, with_dimensions=True, match_rotated=True, j=jobmod.nulljob
    )
    eq_(5, len(prepared_parallel))

    pics_seq = make_photos(tmpdir, 5)
    db_seq = str(tmpdir.join("sequential.db"))
    monkeypatch.setattr(matchblock, "MIN_PICTURES_FOR_PARALLEL_PREP", 10**9)
    prepared_seq = prepare_pictures(pics_seq, db_seq, with_dimensions=True, match_rotated=True, j=jobmod.nulljob)
    eq_(5, len(prepared_seq))
    eq_(cache_contents(db_parallel), cache_contents(db_seq))


class FakePhoto:
    """A picture whose blocks are fixed, whatever its file contains."""

    def __init__(self, path, orientation=6):
        self.path = Path(path)
        self.unicode_path = str(path)
        self._orientation = orientation
        self.dimensions = (100, 100)
        self.size = 10

    def get_orientation(self):
        return self._orientation

    def get_blocks(self, block_count_per_side, orientation=None):
        return list(BLACK_BLOCKS)


class CountingPhoto(FakePhoto):
    """Counts every get_blocks call by appending to a file.

    The path comes from an env var, not a class attribute: spawned
    workers re-import this module, so a value set on the class in the
    parent would not be visible to them, but the environment is inherited.
    """

    def get_blocks(self, block_count_per_side, orientation=None):
        counter = os.environ.get("DUPECLEANER_PREP_COUNT_FILE")
        if counter:
            with open(counter, "a") as f:
                # The pid proves the work really happened in pool workers
                # (several pids) rather than in the test process alone.
                f.write("%d:%s\n" % (os.getpid(), self.unicode_path))
        return super().get_blocks(block_count_per_side, orientation)


def test_cached_pictures_are_not_recomputed(tmpdir, monkeypatch):
    pics = []
    for i in range(40):
        path = tmpdir.join("p%d.jpg" % i)
        path.write_binary(b"x")
        pics.append(CountingPhoto(str(path)))
    counter = str(tmpdir.join("calls.txt"))
    monkeypatch.setenv("DUPECLEANER_PREP_COUNT_FILE", counter)
    dbpath = str(tmpdir.join("piccache.db"))
    prepared = prepare_pictures(pics, dbpath, with_dimensions=False, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared))
    with open(counter) as f:
        lines = f.readlines()
    eq_(40, len(lines))
    pids = {line.split(":", 1)[0] for line in lines}
    assert len(pids) > 1, "expected the pool workers (several pids), got %s" % (pids,)
    # Second run, same cache: everything is cached, so nothing is recomputed.
    prepared = prepare_pictures(pics, dbpath, with_dimensions=False, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared))
    with open(counter) as f:
        eq_(40, len(f.readlines()))


class UnreadablePhoto(FakePhoto):
    def get_blocks(self, block_count_per_side, orientation=None):
        raise OSError("cannot read %s" % self.unicode_path)


def test_unreadable_picture_is_skipped_in_parallel(tmpdir):
    # 39 good pictures + 1 unreadable one, enough to trigger the pool.
    # The bad picture is skipped; the rest are prepared and the scan
    # does not crash.
    pics = []
    for i in range(39):
        path = tmpdir.join("p%d.jpg" % i)
        path.write_binary(b"x")
        pics.append(FakePhoto(str(path)))
    bad_path = tmpdir.join("bad.jpg")
    bad_path.write_binary(b"x")
    pics.append(UnreadablePhoto(str(bad_path)))
    dbpath = str(tmpdir.join("piccache.db"))
    prepared = prepare_pictures(pics, dbpath, with_dimensions=False, match_rotated=False, j=jobmod.nulljob)
    eq_(39, len(prepared))
    assert str(bad_path) not in [p.unicode_path for p in prepared]
    cache = SqliteCache(dbpath)
    assert str(bad_path) not in cache
    cache.close()


def test_corrupt_image_does_not_crash_parallel_prep(tmpdir):
    # A real .jpg that is not an image at all, mixed into a pool-sized
    # batch. It must not crash the scan; it is prepared with empty blocks.
    pics = make_photos(tmpdir, 39)
    bad_path = Path(str(tmpdir.join("bad.jpg")))
    bad_path.write_bytes(b"this is not a jpeg at all" * 100)
    pics.append(QtPhoto(bad_path))
    dbpath = str(tmpdir.join("piccache.db"))
    prepared = prepare_pictures(pics, dbpath, with_dimensions=True, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared))
    assert cache_contents(dbpath)[str(bad_path)][0] == []


def test_spawn_worker_decodes_with_qimage(tmpdir):
    # The key risk for the frozen macOS app: QImage decoding must work in
    # a *spawned* worker (a fresh interpreter, as macOS uses), not just
    # in a forked one. Compare spawned results against in-process ones.
    pics = make_photos(tmpdir, 4)
    tasks = [(QtPhoto, p.unicode_path, False, True) for p in pics]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(2) as pool:
        results = pool.map(_prepare_picture_task, tasks)
    for pic, (dimensions, blocks, error) in zip(pics, results):
        eq_(None, error)
        eq_(pic.dimensions, dimensions)
        eq_(pic.get_blocks(matchblock.BLOCK_COUNT_PER_SIDE), blocks[0])
    # And with rotation: 8 block lists, one per orientation.
    tasks = [(QtPhoto, p.unicode_path, True, True) for p in pics[:2]]
    with ctx.Pool(2) as pool:
        results = pool.map(_prepare_picture_task, tasks)
    for pic, (dimensions, blocks, error) in zip(pics[:2], results):
        eq_(None, error)
        eq_(8, len(blocks))
        for orientation in range(1, 9):
            eq_(pic.get_blocks(matchblock.BLOCK_COUNT_PER_SIDE, orientation), blocks[orientation - 1])


def test_pool_failure_falls_back_to_sequential(tmpdir, monkeypatch):
    # If the pool cannot even start, preparation falls back to the
    # sequential loop and produces identical results.
    pics = make_photos(tmpdir, 40)
    db_parallel = str(tmpdir.join("parallel.db"))
    prepared_parallel = prepare_pictures(pics, db_parallel, with_dimensions=True, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared_parallel))

    def _boom(*args, **kwargs):
        raise RuntimeError("no pool for you")

    monkeypatch.setattr(matchblock.multiprocessing, "get_context", _boom)
    pics_seq = make_photos(tmpdir, 40)
    db_seq = str(tmpdir.join("sequential.db"))
    prepared_seq = prepare_pictures(pics_seq, db_seq, with_dimensions=True, match_rotated=False, j=jobmod.nulljob)
    eq_(40, len(prepared_seq))
    eq_([p.dimensions for p in pics], [p.dimensions for p in pics_seq])
    eq_(cache_contents(db_parallel), cache_contents(db_seq))


def test_prepare_reports_progress(tmpdir):
    pics = make_photos(tmpdir, 40)
    seen = []

    def callback(progress, desc=""):
        seen.append((progress, desc))
        return True

    j = Job([1], callback)
    dbpath = str(tmpdir.join("piccache.db"))
    prepared = prepare_pictures(pics, dbpath, with_dimensions=True, match_rotated=False, j=j)
    eq_(40, len(prepared))
    assert seen, "no progress was reported"
    eq_(100, seen[-1][0])
    eq_("Analyzed 40/40 pictures", seen[-1][1])
    assert all(0 <= progress <= 100 for progress, _ in seen)
