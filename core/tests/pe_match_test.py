# Regression tests for the photo-matching Must fixes (audit findings 5, 6, 7).
#
# These tests use fake pictures and a real on-disk SqliteCache so they run
# without Qt or real image files: the block decoding itself is covered by
# block_test.py.

from pathlib import Path

from hscommon.jobprogress import job as jobmod
from hscommon.testutil import eq_

from core.pe.cache_sqlite import SqliteCache
from core.pe.matchblock import async_compare, prepare_pictures
from core.pe.matchexif import getmatches as exif_getmatches

BLACK_BLOCKS = [(0, 0, 0)] * 225


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


def test_oriented_photos_match_in_default_scan(tmpdir):
    # Two identical photos with EXIF orientation 6 (the usual phone value)
    # must match in the default (non-rotated) scan. The old code stored
    # their blocks in slot 5 and compared slot 0, which was empty, so the
    # pair scored 0% and never matched.
    dbpath = str(tmpdir.join("piccache.db"))
    pics = []
    for name in ("p1.jpg", "p2.jpg"):
        p = tmpdir.join(name)
        p.write_binary(b"x")
        pics.append(FakePhoto(str(p), orientation=6))
    prepared = prepare_pictures(pics, dbpath, with_dimensions=False, match_rotated=False, j=jobmod.nulljob)
    eq_(2, len(prepared))
    cache = SqliteCache(dbpath)
    ids = [cache.get_id(p.unicode_path) for p in pics]
    # The orientation-corrected blocks must be in slot 0, the slot the
    # comparison reads.
    eq_(list(BLACK_BLOCKS), cache[pics[0].unicode_path][0])
    cache.close()
    picinfo = {i: ((100, 100), False) for i in ids}
    matches = async_compare(ids, None, dbpath, 90, picinfo)
    eq_(1, len(matches))
    eq_(100, matches[0][2])


class FakeExifPic:
    def __init__(self, name, timestamp, digest, dimensions=(100, 100)):
        self.name = name
        self.exif_timestamp = timestamp
        self.digest = digest
        self.dimensions = dimensions


def test_exif_same_timestamp_different_content_is_not_100_percent():
    # Two different photos taken in the same second (burst mode) are not
    # duplicates, even though they share a timestamp.
    pics = [
        FakeExifPic("a.jpg", "2024:01:01 12:00:00", b"digest-a"),
        FakeExifPic("b.jpg", "2024:01:01 12:00:00", b"digest-b"),
    ]
    matches = exif_getmatches(pics, False, jobmod.nulljob)
    eq_(1, len(matches))
    assert matches[0].percentage < 100


def test_exif_same_timestamp_same_content_is_100_percent():
    pics = [
        FakeExifPic("a.jpg", "2024:01:01 12:00:00", b"digest-a"),
        FakeExifPic("b.jpg", "2024:01:01 12:00:00", b"digest-a"),
    ]
    matches = exif_getmatches(pics, False, jobmod.nulljob)
    eq_(1, len(matches))
    eq_(100, matches[0].percentage)


def test_exif_unreadable_content_is_not_100_percent():
    # If a digest could not be read (None), identity cannot be confirmed.
    pics = [
        FakeExifPic("a.jpg", "2024:01:01 12:00:00", None),
        FakeExifPic("b.jpg", "2024:01:01 12:00:00", b"digest-b"),
    ]
    matches = exif_getmatches(pics, False, jobmod.nulljob)
    eq_(1, len(matches))
    assert matches[0].percentage < 100
