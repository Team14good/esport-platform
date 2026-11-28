"""FLOW 壓力與負載測試（Locust）。僅供本機測試，只打 run.sh 指定的本機 compose。

五個情境各有自己的 User class（用 `SCENARIO` 環境變數選擇，run.sh 會一併設好）：

| SCENARIO     | User class                                  | 加壓方式                                   |
| ------------ | ------------------------------------------- | ------------------------------------------ |
| viewer       | ViewerUser                                  | 人數階梯，每階量 60 秒                      |
| checkin      | CheckinUser                                 | 32 位隊長同時報到一次                       |
| registration | RegistrationUser                            | 200 隊同時送出報名一次                      |
| login        | LoginUser                                   | 人數階梯，每階量 60 秒，同步登入            |
| mixed        | ViewerMixedUser、PollerMixedUser、CheckinMixedUser | 固定人數跑 5 分鐘，第 60 秒起報到尖峰 |

階梯的每一階先「爬升」（讓人數到位、不計入），再清掉統計量滿 60 秒；每階結束把 p50／p95／p99／RPS／錯誤率
寫進 `<OUT_PREFIX>_stages.csv` 與 `_endpoints.csv`。p95 超過 1 秒或錯誤率超過 1% 就停止。
輪詢間隔照前端常數：對戰表與單場頁 5 秒、未讀通知 30 秒、下一場 60 秒。
"""

import csv
import json
import os
import random
import time
from collections import Counter
from itertools import count
from urllib.parse import urlparse

import gevent
import requests
from gevent.event import Event
from gevent.pool import Pool
from locust import HttpUser, LoadTestShape, constant, constant_pacing, events, task
from locust.env import Environment
from locust.exception import StopUser
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

SCENARIO = os.environ.get("SCENARIO", "viewer")
OUT_PREFIX = os.environ.get("OUT_PREFIX", "scripts/load/reports/run")
MEASURE_SECONDS = int(os.environ.get("MEASURE_SECONDS", "60"))
P95_LIMIT_MS = 1000
ERROR_LIMIT = 0.01
SPAWN_RATE = 200

# 前端的輪詢間隔（秒）：BRACKET_POLL_INTERVAL_MS、MATCH_POLL_INTERVAL_MS、UNREAD_POLL_INTERVAL_MS、NEXT_MATCHES_REFETCH_MS
BRACKET_POLL_S = 5
MATCH_POLL_S = 5
UNREAD_POLL_S = 30
NEXT_MATCHES_POLL_S = 60
# 觀眾停在對戰表頁與單場頁的比例（一位觀眾同一時間只開一頁）
VIEWER_BRACKET_SHARE = 0.6

API = "/api/v1"


def _load(env_name: str) -> dict:
    path = os.environ.get(env_name)
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


MANIFEST = _load("MANIFEST")
CHECKIN = _load("MANIFEST_CHECKIN") or (MANIFEST if "captains" in MANIFEST else {})

TOKENS: dict[str, str] = {}
STATUS: Counter = Counter()  # 每個狀態碼的回應數
REGISTRATION_STATUS: Counter = Counter()  # 報名尖峰：回應裡的 registration_status
SCENARIO_START = [0.0]
READY = [False]  # 預載 token 等準備工作完成後才開始量測
ABORT = [False]  # 準備失敗或 host 不是本機：不加壓、程序以非零結束
BURST_SENT: list[float] = []  # 一次性尖峰裡每個請求實際送出的時間
GATE = {"expected": 0, "arrived": 0, "timed_out": False}  # 尖峰閘門到齊情況
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCUST_PIN = "2.43.3"


def _is_local(host: str | None) -> bool:
    """精確比對主機名稱（不是比字串開頭：`localhost.evil.com` 必須被擋下）。"""
    try:
        parsed = urlparse(host or "")
        return parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS
    except ValueError:
        return False


def _abort(environment: Environment, message: str) -> None:
    """事件處理器裡的例外會被 Locust 吞掉、只記 log，所以要明確設非零結束碼並停止。"""
    print(f"ABORT: {message}", flush=True)
    ABORT[0] = True
    environment.process_exit_code = 2
    if environment.runner is not None:
        environment.runner.quit()


def _browser_like_retry(user: HttpUser) -> None:
    """GET 遇到伺服器剛好關掉閒置連線（uvicorn 的 keep-alive 是 5 秒，與輪詢週期相同）時重連一次，
    行為與瀏覽器相同；POST 不重送，避免重複報到或重複報名。"""
    adapter = user.client.adapters["http://"]
    adapter.max_retries = Retry(total=1, backoff_factor=0, allowed_methods=frozenset({"GET"}))


def _reset_pacing(user: HttpUser) -> None:
    """重設 constant_pacing 的計時起點。依賴 locust==2.43.3 的私有屬性 `_cp_last_run`、`_cp_last_wait_time`：
    constant_pacing 從 User 建立時就開始計時，on_start 的隨機延遲若不重設，所有人會在第 5 秒再次同步。
    升級 Locust 後屬性不存在就明確報錯，而不是悄悄失效。"""
    if not hasattr(user, "_cp_last_run"):
        raise RuntimeError(f"locust 的私有屬性 _cp_last_run 不存在，本腳本依賴 locust=={LOCUST_PIN}")
    user._cp_last_run = time.time()
    user._cp_last_wait_time = 0


def _bearer(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[email]}"}


def _preload_tokens(host: str, emails: list[str], password: str) -> None:
    """壓測開始前先登入取得 token（不計入統計）；登入尖峰以外的情境都用這些 token。
    網路錯誤與非 200 都重試，最後仍失敗就拋出，由呼叫端中止整個測試。"""

    def login(email: str) -> None:
        last = "未知"
        for _ in range(5):
            try:
                r = requests.post(
                    f"{host}{API}/access-tokens",
                    json={"email": email, "password": password},
                    timeout=60,
                )
                if r.status_code == 200:
                    TOKENS[email] = r.json()["access_token"]
                    return
                last = f"HTTP {r.status_code}"
            except RequestException as exc:
                last = repr(exc)
            time.sleep(2)
        raise RuntimeError(f"預先登入失敗：{email}（{last}）")

    pool = Pool(16)
    for email in emails:
        pool.spawn(login, email)
    pool.join(raise_error=True)


# ----------------------------------------------------------------------------- 事件

@events.test_start.add_listener
def _on_test_start(environment: Environment, **_: object) -> None:
    if not _is_local(environment.host):
        _abort(environment, f"只准打本機：--host 的主機名稱必須是 {sorted(LOCAL_HOSTS)} 之一（收到 {environment.host!r}）")
        return
    password = MANIFEST.get("password", "")
    try:
        if SCENARIO == "checkin":
            _preload_tokens(environment.host, [c["email"] for c in MANIFEST["captains"]], password)
        elif SCENARIO == "registration":
            _preload_tokens(environment.host, [t["email"] for t in MANIFEST["teams"]], password)
        elif SCENARIO == "mixed":
            _preload_tokens(environment.host, MANIFEST["login_emails"][:POLLERS], password)
            _preload_tokens(environment.host, [c["email"] for c in CHECKIN["captains"]], password)
    except Exception as exc:  # noqa: BLE001  任何準備失敗都要中止，不能只留在 log
        _abort(environment, str(exc))
        return
    SCENARIO_START[0] = time.time()  # 量測起點在預載完成之後
    READY[0] = True


@events.request.add_listener
def _on_request(response=None, exception=None, **_: object) -> None:
    code = getattr(response, "status_code", 0) if response is not None else 0
    STATUS[code] += 1


@events.quitting.add_listener
def _on_quitting(environment: Environment, **_: object) -> None:
    summary = {
        "scenario": SCENARIO,
        "status_codes": {str(k): v for k, v in sorted(STATUS.items())},
        "http_5xx": sum(v for k, v in STATUS.items() if k >= 500),
        "no_response": STATUS.get(0, 0),
        "registration_status": dict(REGISTRATION_STATUS),
    }
    with open(f"{OUT_PREFIX}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))


# ----------------------------------------------------------------------------- 觀眾

class ViewerUser(HttpUser):
    """未登入的觀眾：停在對戰表頁（約 60%）或某一場的單場頁（約 40%），每 5 秒輪詢一次。"""

    wait_time = constant_pacing(BRACKET_POLL_S)

    def on_start(self) -> None:
        # 真實觀眾不會同步：隨機錯開第一次輪詢
        gevent.sleep(random.uniform(0, BRACKET_POLL_S))
        _reset_pacing(self)
        _browser_like_retry(self)
        self.on_bracket = random.random() < VIEWER_BRACKET_SHARE
        self.tid = MANIFEST["tournament_id"]
        self.match_id = random.choice(MANIFEST["match_ids"])

    @task
    def poll(self) -> None:
        if self.on_bracket:
            self.client.get(f"{API}/tournaments/{self.tid}/bracket", name="GET bracket")
        else:
            self.client.get(
                f"{API}/tournaments/{self.tid}/matches/{self.match_id}", name="GET match"
            )


# ----------------------------------------------------------------------------- 登入

_login_index = count()


class LoginUser(HttpUser):
    """每 10 秒登入一次；所有人同步開始，每一輪就是 N 個帳號同時登入。

    登入的 401（密碼錯、帳號不存在）屬預期的業務回應，不計入錯誤；其他狀態碼照一般規則。
    """

    wait_time = constant_pacing(10)

    def on_start(self) -> None:
        emails = MANIFEST["login_emails"]
        self.email = emails[next(_login_index) % len(emails)]

    @task
    def login(self) -> None:
        with self.client.post(
            f"{API}/access-tokens",
            json={"email": self.email, "password": MANIFEST["password"]},
            name="POST access-tokens",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401):
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}")


# ----------------------------------------------------------------------------- 一次性尖峰

class _BurstUser(HttpUser):
    """所有人到齊後同時送出一個請求，然後結束。"""

    wait_time = constant(1)
    abstract = True
    expected: int = 0  # 到齊人數
    _arrived = 0
    _go = Event()

    def _wait_for_everyone(self) -> None:
        cls = type(self).__mro__[0]
        GATE["expected"] = cls.expected
        cls._arrived += 1
        GATE["arrived"] = cls._arrived
        if cls._arrived >= cls.expected:
            cls._go.set()
        gevent.sleep(0)
        for _ in range(300):  # 最多等 30 秒
            if cls._go.is_set():
                return
            gevent.sleep(0.1)
        # 逾時放行：記錄到齊人數，stages.csv 會帶出來，這次就不是「同時」
        GATE["timed_out"] = True
        GATE["arrived"] = cls._arrived
        cls._go.set()


class CheckinUser(_BurstUser):
    """32 位隊長在 1 秒內同時報到（預期 201）。"""

    expected = len(MANIFEST.get("captains", [])) if SCENARIO == "checkin" else 0
    _index = count()

    def on_start(self) -> None:
        self.captain = MANIFEST["captains"][next(CheckinUser._index) % len(MANIFEST["captains"])]
        self._wait_for_everyone()

    @task
    def check_in(self) -> None:
        _check_in(self, MANIFEST["tournament_id"], self.captain)
        raise StopUser()


def _check_in(user: HttpUser, tournament_id: str, captain: dict) -> None:
    BURST_SENT.append(time.time())
    with user.client.post(
        f"{API}/tournaments/{tournament_id}/matches/{captain['match_id']}/check-in",
        headers=_bearer(captain["email"]),
        name="POST check-in",
        catch_response=True,
    ) as r:
        if r.status_code == 201:
            r.success()
        else:
            r.failure(f"HTTP {r.status_code} {r.text[:120]}")


class RegistrationUser(_BurstUser):
    """200 位隊長同時送出報名（預期 200；正取或候補都是成功）。"""

    expected = len(MANIFEST.get("teams", [])) if SCENARIO == "registration" else 0
    _index = count()

    def on_start(self) -> None:
        self.team = MANIFEST["teams"][next(RegistrationUser._index) % len(MANIFEST["teams"])]
        self._wait_for_everyone()

    @task
    def submit(self) -> None:
        BURST_SENT.append(time.time())
        with self.client.post(
            f"{API}/teams/{self.team['team_id']}/submission",
            headers=_bearer(self.team["email"]),
            name="POST submission",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                REGISTRATION_STATUS[r.json().get("registration_status", "?")] += 1
                r.success()
            else:
                r.failure(f"HTTP {r.status_code} {r.text[:120]}")
        raise StopUser()


# ----------------------------------------------------------------------------- 混合情境

VIEWERS = int(os.environ.get("MIX_VIEWERS", "75"))
POLLERS = int(os.environ.get("MIX_POLLERS", "50"))
MIX_CHECKIN_AT_S = 60


class ViewerMixedUser(ViewerUser):
    fixed_count = VIEWERS if SCENARIO == "mixed" else 0


class PollerMixedUser(HttpUser):
    """登入使用者：未讀通知每 30 秒、下一場每 60 秒。"""

    wait_time = constant(1)
    fixed_count = POLLERS if SCENARIO == "mixed" else 0
    _index = count()

    def on_start(self) -> None:
        _browser_like_retry(self)
        emails = MANIFEST["login_emails"][:POLLERS]
        self.email = emails[next(PollerMixedUser._index) % len(emails)]
        gevent.sleep(random.uniform(0, UNREAD_POLL_S))
        self.next_unread = time.time()
        self.next_matches = time.time() + random.uniform(0, NEXT_MATCHES_POLL_S)

    @task
    def poll(self) -> None:
        now = time.time()
        if now >= self.next_unread:
            self.next_unread = now + UNREAD_POLL_S
            self.client.get(
                f"{API}/notifications/unread-count",
                headers=_bearer(self.email),
                name="GET unread-count",
            )
        if now >= self.next_matches:
            self.next_matches = now + NEXT_MATCHES_POLL_S
            self.client.get(
                f"{API}/me/next-matches", headers=_bearer(self.email), name="GET next-matches"
            )


class CheckinMixedUser(HttpUser):
    """32 位隊長在開跑 60 秒後同時報到一次。"""

    wait_time = constant(3600)
    fixed_count = len(CHECKIN.get("captains", [])) if SCENARIO == "mixed" else 0
    _index = count()

    def on_start(self) -> None:
        caps = CHECKIN["captains"]
        self.captain = caps[next(CheckinMixedUser._index) % len(caps)]
        delay = SCENARIO_START[0] + MIX_CHECKIN_AT_S - time.time()
        if delay > 0:
            gevent.sleep(delay)

    @task
    def check_in(self) -> None:
        _check_in(self, CHECKIN["tournament_id"], self.captain)
        gevent.sleep(3600)


# ----------------------------------------------------------------------------- 階梯與量測

def _plan() -> list[dict]:
    """每一階：users（總人數）、measure（量測秒數）。"""
    if SCENARIO == "viewer":
        users = [int(x) for x in os.environ.get("STAGES", "25,50,75,100,150,200,400,800,1600,3200").split(",")]
        return [{"users": u, "measure": MEASURE_SECONDS, "stop_on_fail": True} for u in users]
    if SCENARIO == "login":
        users = [int(x) for x in os.environ.get("STAGES", "50,100,200").split(",")]
        return [{"users": u, "measure": MEASURE_SECONDS, "stop_on_fail": True} for u in users]
    if SCENARIO == "checkin":
        return [{"users": len(MANIFEST["captains"]), "measure": 120, "stop_on_fail": False, "until_idle": True}]
    if SCENARIO == "registration":
        # 200 筆送出會在伺服器端排隊處理：等到全部回應（或 15 分鐘上限）才結束，核對才看得到最終狀態
        return [{"users": len(MANIFEST["teams"]), "measure": 900, "stop_on_fail": False, "until_idle": True}]
    if SCENARIO == "mixed":
        total = VIEWERS + POLLERS + len(CHECKIN["captains"])
        return [{"users": total, "measure": int(os.environ.get("MIX_SECONDS", "300")), "stop_on_fail": False}]
    raise SystemExit(f"未知的 SCENARIO：{SCENARIO}")


class StageShape(LoadTestShape):
    """階梯加壓：爬升（不計）→ 清統計 → 量測 → 記錄這一階 → 下一階。"""

    def __init__(self) -> None:
        super().__init__()
        self.plan = _plan()
        self.stage = 0
        self.phase = "ramp"
        self.phase_start: float | None = None
        self.prev_users = 0
        self.ramp_s = 0.0
        self.measure_started = 0.0
        self.stage_rows: list[dict] = []
        self._write_header()

    # -- 輸出
    def _write_header(self) -> None:
        with open(f"{OUT_PREFIX}_stages.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["scenario", "stage", "users", "start_utc", "end_utc", "measure_s", "requests", "failures",
                 "error_pct", "rps", "p50_ms", "p95_ms", "p99_ms", "max_ms", "verdict", "gate_arrived", "gate_timed_out", "send_spread_ms"]
            )
        with open(f"{OUT_PREFIX}_endpoints.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["stage", "users", "name", "requests", "failures", "p50_ms", "p95_ms", "p99_ms", "max_ms"])

    def _record(self, users: int, started: float, ended: float) -> dict:
        stats = self.runner.stats
        total = stats.total
        elapsed = max(ended - started, 1e-6)
        requests_n = total.num_requests
        err = total.num_failures / requests_n if requests_n else 1.0
        p50, p95, p99 = (total.get_response_time_percentile(p) or 0 for p in (0.5, 0.95, 0.99))
        ok = requests_n > 0 and p95 <= P95_LIMIT_MS and err <= ERROR_LIMIT
        row = {
            "scenario": SCENARIO, "stage": self.stage + 1, "users": users,
            "start_utc": time.strftime("%H:%M:%S", time.gmtime(started)),
            "end_utc": time.strftime("%H:%M:%S", time.gmtime(ended)),
            "measure_s": round(elapsed), "requests": requests_n, "failures": total.num_failures,
            "error_pct": round(err * 100, 2), "rps": round(requests_n / elapsed, 1),
            "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "max_ms": round(total.max_response_time),
            "verdict": "PASS" if ok else "FAIL",
            # 一次性尖峰才有：閘門到齊人數／是否逾時放行／請求實際送出時間的最大差值（毫秒）
            "gate_arrived": f"{GATE['arrived']}/{GATE['expected']}" if GATE["expected"] else "",
            "gate_timed_out": GATE["timed_out"] if GATE["expected"] else "",
            "send_spread_ms": round((max(BURST_SENT) - min(BURST_SENT)) * 1000) if BURST_SENT else "",
        }
        with open(f"{OUT_PREFIX}_stages.csv", "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row.values())
        with open(f"{OUT_PREFIX}_endpoints.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for (name, _method), e in sorted(stats.entries.items()):
                w.writerow([self.stage + 1, users, name, e.num_requests, e.num_failures,
                            e.get_response_time_percentile(0.5), e.get_response_time_percentile(0.95),
                            e.get_response_time_percentile(0.99), round(e.max_response_time)])
        top = sorted(stats.errors.values(), key=lambda e: -e.occurrences)[:5]
        for e in top:
            print(f"STAGE {self.stage + 1} ERROR x{e.occurrences}: {e.method} {e.name} {e.error}")
        print("STAGE", json.dumps(row, ensure_ascii=False))
        return row

    # -- 狀態機
    def tick(self):
        now = time.time()
        if ABORT[0]:
            return None
        if not READY[0]:  # token 還在預載：先不加壓、不開始量測
            return 0, SPAWN_RATE
        if self.stage >= len(self.plan):
            return None
        spec = self.plan[self.stage]
        users = spec["users"]
        if self.phase_start is None:
            self.phase_start = now
            delta = max(users - self.prev_users, 0)
            # 階梯：照 SPAWN_RATE 讓新增的人數到位，再多給 10 秒穩定；一次性尖峰與混合情境從開跑就量
            # （尖峰靠 User 的到齊閘門同時送出；混合情境的報到尖峰在第 60 秒）
            burst = SCENARIO in ("checkin", "registration", "mixed")
            self.ramp_s = 0.0 if burst else delta / SPAWN_RATE + 10
            if self.ramp_s == 0:
                self.runner.stats.reset_all()
                self.phase = "measure"
                self.measure_started = now
        if self.phase == "ramp" and now - self.phase_start >= self.ramp_s:
            self.runner.stats.reset_all()
            self.phase = "measure"
            self.measure_started = now
        idle = (
            spec.get("until_idle")
            and now - self.measure_started > 5
            and self.runner.stats.total.num_requests > 0
            and self.runner.user_count == 0
        )
        if self.phase == "measure" and (now - self.measure_started >= spec["measure"] or idle):
            row = self._record(users, self.measure_started, now)
            self.stage_rows.append(row)
            self.prev_users = users
            self.stage += 1
            self.phase, self.phase_start = "ramp", None
            if spec["stop_on_fail"] and row["verdict"] == "FAIL":
                return None
            if self.stage >= len(self.plan):
                return None
            users = self.plan[self.stage]["users"]
            return users, SPAWN_RATE
        return users, SPAWN_RATE
