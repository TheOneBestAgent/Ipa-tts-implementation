from core.chunking import merge_small_segments


def test_merge_small_segments_merges_with_next():
    segments = ["tiny", "this is a longer segment"]
    merged = merge_small_segments(segments, min_chars=10)
    assert len(merged) == 1
    assert "tiny" in merged[0]


def test_merge_small_segments_merges_with_previous():
    segments = ["this is a longer segment", "tiny"]
    merged = merge_small_segments(segments, min_chars=10)
    assert len(merged) == 1
    assert merged[0].startswith("this is a longer segment")


def test_merge_small_segments_keeps_single_segment():
    segments = ["short"]
    merged = merge_small_segments(segments, min_chars=10)
    assert merged == segments
