import re

from .config import CITIES, SUBJECTS

DIM_KEYS = ("year", "subject", "city", "exam")

_YEAR_RANGE_4 = re.compile(r"(20\d{2})\s*[-~—－至到]\s*(20\d{2})")
_YEAR_SUFFIX_2 = re.compile(r"(?<!\d)(\d{2})年")
_YEAR_PLAIN_4 = re.compile(r"20\d{2}")
_YEAR_RANGE_2 = re.compile(r"(?<!\d)(\d{2})\s*[-~]\s*\d{2}(?!\d)")
_YEAR_PLAIN_2 = re.compile(r"(?<![\d.])(\d{2})(?!\d)")

_EXAMOrdinal = re.compile(r"第([一二三])次质量(?:监测|检测)")
_EXAM_JIAN = re.compile(r"[一二三]检")
_EXAM_ZHIJIAN = re.compile(r"质检|质量监测|质量检测")
_EXAM_ZHONGKAO = re.compile(r"中考")
_EXAM_TERM = re.compile(r"([七八九][上下])?(期中|期末)考?")
_EXAM_MOCK = re.compile(r"模拟考?")

_PAPER_RE = re.compile(r"试卷|试题|卷面|卷子")
_ANSWER_RE = re.compile(r"答案|解析|评分标准")

_ORDINAL_MAP = {"一": "一检", "二": "二检", "三": "三检"}


def _paper_type_from(text: str) -> str | None:
    if not text:
        return None
    has_answer = bool(_ANSWER_RE.search(text))
    has_paper = bool(_PAPER_RE.search(text))
    if has_answer and has_paper:
        return "试卷+答案"
    if has_answer:
        return "答案"
    if has_paper:
        return "试卷"
    return None


def _extract_year(text: str) -> str | None:
    m = _YEAR_RANGE_4.search(text)
    if m:
        return m.group(2)
    m = _YEAR_SUFFIX_2.search(text)
    if m:
        return "20" + m.group(1)
    m = _YEAR_PLAIN_4.search(text)
    if m:
        return m.group(0)
    m = _YEAR_RANGE_2.search(text)
    if m:
        return "20" + m.group(1)
    m = _YEAR_PLAIN_2.search(text)
    if m:
        return "20" + m.group(1)
    return None


_SUBJECT_ALIASES = {"道德与法治": "道法", "德与法治": "道法", "政治": "道法", "体育与健康": "体育"}


def _extract_subject(text: str) -> str | None:
    for subject in SUBJECTS:
        if subject in text:
            return _SUBJECT_ALIASES.get(subject, subject)
    return None


def _extract_city(text: str) -> str | None:
    for city in CITIES:
        if city in text or (len(city) > 1 and city[:-1] in text):
            return city
    return None


def _extract_exam(text: str) -> str | None:
    m = _EXAMOrdinal.search(text)
    if m:
        return _ORDINAL_MAP[m.group(1)]
    m = _EXAM_JIAN.search(text)
    if m:
        return m.group(0)
    if _EXAM_ZHIJIAN.search(text):
        return "质检"
    if _EXAM_ZHONGKAO.search(text):
        return "中考"
    m = _EXAM_TERM.search(text)
    if m:
        return m.group(0) if m.group(1) else m.group(2)
    if _EXAM_MOCK.search(text):
        return "模拟"
    return None


_EXTRACTORS = {
    "year": _extract_year,
    "subject": _extract_subject,
    "city": _extract_city,
    "exam": _extract_exam,
}


def classify(rel_segments: list[str], file_stem: str) -> tuple[dict[str, str | None], list[str]]:
    result: dict[str, str | None] = {k: None for k in DIM_KEYS}
    for text in [*reversed(rel_segments), file_stem]:
        if not text:
            continue
        if all(result[k] for k in DIM_KEYS):
            break
        for key in DIM_KEYS:
            if result[key] is None:
                value = _EXTRACTORS[key](text)
                if value:
                    result[key] = value
    paper_type = _paper_type_from(file_stem)
    if paper_type is None:
        for seg in reversed(rel_segments):
            paper_type = _paper_type_from(seg)
            if paper_type:
                break
    result["paper_type"] = paper_type or "试卷"
    missing = [k for k in DIM_KEYS if result[k] is None]
    return result, missing
