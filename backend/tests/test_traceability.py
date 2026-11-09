"""Story 7.3：tests/traceability.yaml 涵蓋每個後端測試檔，格式正確。

對應檔是分層（unit／integration）與 Story、FR 追溯的單一來源；新增測試檔卻沒寫進去時，
這裡會失敗並列出檔名，測試報告才不會出現沒有標註的案例。
"""

from tests.report_support import (
    LAYERS,
    REQUIREMENT_PATTERN,
    STORY_PATTERN,
    TESTS_DIR,
    load_traceability,
)


def _test_files() -> set[str]:
    return {
        path.relative_to(TESTS_DIR).as_posix() for path in TESTS_DIR.rglob("test_*.py")
    }


def test_every_test_file_is_listed() -> None:
    missing = sorted(_test_files() - set(load_traceability()))
    assert missing == [], (
        "以下測試檔沒有寫進 tests/traceability.yaml（請標 layer、stories、frs）：\n"
        + "\n".join(missing)
    )


def test_no_stale_rows() -> None:
    stale = sorted(set(load_traceability()) - _test_files())
    assert stale == [], (
        "tests/traceability.yaml 有不存在的測試檔，請刪除這些列：\n" + "\n".join(stale)
    )


def test_rows_are_well_formed() -> None:
    problems: list[str] = []
    for path, entry in sorted(load_traceability().items()):
        if not isinstance(entry, dict) or set(entry) != {"layer", "stories", "frs"}:
            problems.append(f"{path}：欄位必須剛好是 layer、stories、frs")
            continue
        if entry["layer"] not in LAYERS:
            problems.append(f"{path}：layer 必須是 unit 或 integration")
        stories = entry["stories"]
        if not isinstance(stories, list) or not stories:
            problems.append(f"{path}：stories 至少要有一個")
        else:
            problems += [
                f'{path}：Story 編號格式錯誤（應為 "3.4" 這種字串）：{story!r}'
                for story in stories
                if not isinstance(story, str) or not STORY_PATTERN.match(story)
            ]
        frs = entry["frs"]
        if not isinstance(frs, list) or not frs:
            problems.append(f"{path}：frs 至少要有一個")
        else:
            problems += [
                f"{path}：需求編號格式錯誤（應為 FR-n 或 NFR-n）：{fr!r}"
                for fr in frs
                if not isinstance(fr, str) or not REQUIREMENT_PATTERN.match(fr)
            ]
    assert problems == [], "\n".join(problems)
