from core.captions import build_ass
from core.highlights import find_highlights
from core.models import JobSettings, Word
from core.renderer import crop_box


def test_crop_box_landscape_centres_on_focus():
    cw, ch, cx, cy = crop_box(1920, 1080, 0.5)
    assert ch == 1080
    assert cw % 2 == 0
    assert abs(cx + cw / 2 - 960) <= 2
    assert cy == 0


def test_crop_box_clamps_to_frame_edges():
    cw, _, cx, _ = crop_box(1920, 1080, 0.0)
    assert cx == 0
    assert cx + cw <= 1920


def test_highlights_respect_duration_bounds():
    words = [Word(i * 0.4, i * 0.4 + 0.35, f"word{i}.") for i in range(400)]
    settings = JobSettings(min_duration=30, max_duration=60, num_clips=3)
    picks = find_highlights(words, settings)
    assert picks
    assert all(30 <= h.end - h.start <= 60 for h in picks)


def test_highlights_do_not_overlap():
    words = [Word(i * 0.4, i * 0.4 + 0.35, f"word{i}.") for i in range(1000)]
    picks = find_highlights(words, JobSettings(num_clips=4))
    for a, b in zip(picks, picks[1:]):
        assert b.start >= a.end


def test_ass_contains_dialogue_lines():
    words = [Word(0.0, 0.5, "hi"), Word(0.5, 1.0, "there")]
    ass = build_ass(words, 0.0, 1.0, "bold_pop")
    assert "Dialogue:" in ass
    assert "[V4+ Styles]" in ass
