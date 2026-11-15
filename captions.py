"""Build ASS subtitle files with word-by-word highlighting for burned-in captions."""
from __future__ import annotations

from dataclasses import dataclass

from core.models import Word


@dataclass(frozen=True)
class CaptionStyle:
    label: str
    font: str
    size: int
    primary: str        # ASS colour format &HAABBGGRR
    highlight: str      # colour of the word currently being spoken
    outline: str
    back: str
    border_style: int   # 1 = outline + shadow, 3 = opaque box
    outline_width: float
    bold: bool
    uppercase: bool
    words_per_line: int
    margin_v: int


CAPTION_STYLES: dict[str, CaptionStyle] = {
    "bold_pop": CaptionStyle(
        "Bold pop (yellow highlight)", "DejaVu Sans", 92,
        "&H00FFFFFF", "&H0000FFFF", "&H00000000", "&H00000000",
        1, 7, True, True, 3, 520,
    ),
    "clean": CaptionStyle(
        "Clean (cyan highlight)", "DejaVu Sans", 74,
        "&H00FFFFFF", "&H00FFFF00", "&H00000000", "&H00000000",
        1, 4, True, False, 5, 520,
    ),
    "boxed": CaptionStyle(
        "Boxed (gold on black)", "DejaVu Sans", 70,
        "&H00FFFFFF", "&H0000D7FF", "&H00000000", "&H99000000",
        3, 6, True, False, 4, 520,
    ),
}

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"""

EVENTS_HEADER = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def _style_line(s: CaptionStyle) -> str:
    bold = -1 if s.bold else 0
    return (
        f"Style: Default,{s.font},{s.size},{s.primary},{s.highlight},{s.outline},{s.back},"
        f"{bold},0,0,0,100,100,0,0,{s.border_style},{s.outline_width},0,2,60,60,{s.margin_v},1"
    )


def _ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    hours, rem = divmod(centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _clean(text: str, uppercase: bool) -> str:
    # Strip characters that would be interpreted as ASS override tags.
    t = text.strip().replace("{", "(").replace("}", ")").replace("\\", "").replace("\n", " ")
    return t.upper() if uppercase else t


def _group(words: list[Word], per_line: int) -> list[list[Word]]:
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        breaks_on_pause = bool(current) and word.start - current[-1].end > 0.8
        if current and (len(current) >= per_line or breaks_on_pause):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def build_ass(words: list[Word], clip_start: float, clip_end: float, style_key: str = "bold_pop") -> str:
    style = CAPTION_STYLES.get(style_key, CAPTION_STYLES["bold_pop"])
    duration = max(clip_end - clip_start, 0.1)
    lines = [ASS_HEADER, _style_line(style), "", EVENTS_HEADER]

    for group in _group(words, style.words_per_line):
        for k, active in enumerate(group):
            t0 = max(active.start - clip_start, 0.0)
            if t0 >= duration:
                continue
            next_start = group[k + 1].start if k + 1 < len(group) else active.end
            t1 = min(max(next_start - clip_start, t0 + 0.08), duration)

            parts = []
            for j, word in enumerate(group):
                text = _clean(word.text, style.uppercase)
                if j == k:
                    parts.append(f"{{\\c{style.highlight}&}}{text}{{\\c{style.primary}&}}")
                else:
                    parts.append(text)
            lines.append(
                f"Dialogue: 0,{_ass_time(t0)},{_ass_time(t1)},Default,,0,0,0,,{' '.join(parts)}"
            )
    return "\n".join(lines) + "\n"
