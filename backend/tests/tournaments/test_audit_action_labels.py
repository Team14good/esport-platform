"""Story 2.8：S34 動作對照表涵蓋所有帶賽事的 audit 動作。

前端 `frontend/src/features/tournaments/audit-log.ts` 的 `AUDIT_ACTION_LABELS` 把動作代碼
換成繁中名稱；漏掉的代碼會在 S34 直接顯示英文。前後端容器看不到彼此的原始碼，所以這裡
靜態掃描 `app/` 底下所有 `audit.record(...)` 呼叫，跟下方 `LABELED_ACTIONS`（前端對照表
鍵值的副本）比對：新增動作卻沒同步時這個測試會失敗，提醒兩邊一起改。
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# 與前端 AUDIT_ACTION_LABELS 的鍵一致；改這裡時要同步改 audit-log.ts
LABELED_ACTIONS = {
    "tournament.created",
    "tournament.status_changed",
    "tournament.podium",
    "tournament.capacity_changed",
    "referee_invitation.created",
    "referee.accepted",
    "team.created",
    "team.member_joined",
    "team.member_removed",
    "team.captain_transferred",
    "team.member_left",
    "team.disbanded",
    "team_member.profile_updated",
    "registration.submitted",
    "registration.status_changed",
    "registration.priority_window_settled",
    "registration.rejected",
    "bracket.drawn",
    "bracket.auto_draw_skipped",
    "match.referee_assigned",
    "match.referee_unassigned",
    "match.checked_in",
    "match.forfeited",
    "match.game_recorded",
    "match.game_deleted",
    "match.result_submitted",
    "match.result_screenshot_uploaded",
    "match.confirmed",
    "match.rescheduled",
    "match.replay_scheduled",
    "match.teams_changed",
    "match.voided",
    "report.filed",
    "report.resolved",
    "appeal.filed",
    "appeal.resolved",
}


def _is_audit_record(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "record"
        and isinstance(func.value, ast.Name)
        and func.value.id == "audit"
    )


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """模組層級 `NAME = "字串"` 的對照，用來解析 `action=AUDIT_ACTION` 這種寫法。"""
    constants: dict[str, str] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = stmt.value.value
    return constants


def _action_strings(expr: ast.expr, constants: dict[str, str], where: str) -> set[str]:
    """`action=` 可能用到的字串：字串常數、條件運算式的各分支、模組常數。"""
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    if isinstance(expr, ast.IfExp):
        return _action_strings(expr.body, constants, where) | _action_strings(
            expr.orelse, constants, where
        )
    if isinstance(expr, ast.Name) and expr.id in constants:
        return {constants[expr.id]}
    raise AssertionError(
        f"{where} 的 action 無法靜態解析（{ast.unparse(expr)}）；"
        "請改用字串常數，或擴充這個測試的解析方式"
    )


def _tournament_actions() -> dict[str, str]:
    """帶賽事（`tournament_id` 不是 None）的動作代碼 → 第一次出現的位置。"""
    found: dict[str, str] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_audit_record(node)):
                continue
            where = f"{path.relative_to(APP_DIR.parent)}:{node.lineno}"
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            assert "action" in kwargs and "tournament_id" in kwargs, (
                f"{where} 的 audit.record 要用關鍵字傳 action 與 tournament_id"
            )
            tournament_id = kwargs["tournament_id"]
            if isinstance(tournament_id, ast.Constant) and tournament_id.value is None:
                continue  # 帳號類動作，不會出現在 S34
            for action in _action_strings(kwargs["action"], constants, where):
                found.setdefault(action, where)
    return found


def test_scanner_finds_audit_record_calls() -> None:
    # 防止掃描方式失效時（例如改了 import 名稱）測試變成永遠通過
    assert len(_tournament_actions()) >= 20


def test_every_tournament_action_has_a_label() -> None:
    actions = _tournament_actions()

    missing = sorted(set(actions) - LABELED_ACTIONS)

    assert not missing, (
        "以下帶賽事的 audit 動作沒有繁中名稱，S34 會直接顯示代碼；請在 "
        "frontend/src/features/tournaments/audit-log.ts 的 AUDIT_ACTION_LABELS "
        "與本測試的 LABELED_ACTIONS 一起補上：\n"
        + "\n".join(f"- {action}（{actions[action]}）" for action in missing)
    )


def test_labels_have_no_stale_actions() -> None:
    stale = sorted(LABELED_ACTIONS - set(_tournament_actions()))

    assert not stale, (
        "以下動作已不在後端的 audit.record 裡，請從 AUDIT_ACTION_LABELS 與 "
        f"LABELED_ACTIONS 一起移除：{stale}"
    )
