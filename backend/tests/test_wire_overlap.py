"""Tests for collinear wire merging."""
from services.wire_router import _merge_collinear_wires


def test_exact_duplicate_collapses_to_one():
    wires = [(0, 0, 100, 0), (0, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_reversed_duplicate_collapses_to_one():
    wires = [(0, 0, 100, 0), (100, 0, 0, 0)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 1
    assert result[0] == (0, 0, 100, 0)


def test_containment_keeps_outer():
    wires = [(0, 0, 100, 0), (20, 0, 80, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_partial_overlap_merges_to_union():
    wires = [(0, 0, 60, 0), (40, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_abutting_segments_merge():
    wires = [(0, 0, 50, 0), (50, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_collinear_disjoint_stays_separate():
    wires = [(0, 0, 40, 0), (60, 0, 100, 0)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 40, 0) in result
    assert (60, 0, 100, 0) in result


def test_perpendicular_crossing_stays_separate():
    wires = [(0, 0, 100, 0), (50, -50, 50, 50)]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 100, 0) in result
    assert (50, -50, 50, 50) in result


def test_different_y_horizontals_stay_separate():
    wires = [(0, 0, 100, 0), (0, 16, 100, 16)]
    assert len(_merge_collinear_wires(wires)) == 2


def test_vertical_overlap_merges():
    wires = [(32, 0, 32, 80), (32, 40, 32, 120)]
    assert _merge_collinear_wires(wires) == [(32, 0, 32, 120)]


def test_empty_input_returns_empty():
    assert _merge_collinear_wires([]) == []


def test_zero_length_wire_dropped():
    wires = [(50, 50, 50, 50)]
    assert _merge_collinear_wires(wires) == []


def test_triple_partial_overlap():
    wires = [(0, 0, 40, 0), (30, 0, 70, 0), (60, 0, 100, 0)]
    assert _merge_collinear_wires(wires) == [(0, 0, 100, 0)]


def test_mixed_horizontal_and_vertical():
    wires = [
        (0, 0, 100, 0),
        (0, 0, 100, 0),
        (0, 0, 0, 100),
        (0, 50, 0, 150),
    ]
    result = _merge_collinear_wires(wires)
    assert len(result) == 2
    assert (0, 0, 100, 0) in result
    assert (0, 0, 0, 150) in result
