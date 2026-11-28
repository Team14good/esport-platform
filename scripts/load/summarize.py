"""把各階結果與資源取樣對起來：每一階 backend／db／worker 的 CPU 峰值、主機 CPU 峰值、可用記憶體最低值，
並判斷瓶頸在伺服器還是壓測端／主機。用法：python scripts/load/summarize.py <報告前綴>（run.sh 會自動呼叫）。

資料來源（都在 <前綴>_ 開頭的檔案）：_stages.csv（Locust 每階）、_docker.csv（`docker stats --no-stream`，
每筆之間約 3 秒加上取樣本身的時間，實際約每 5 秒一筆；CPU% 以單一核心為 100%）、
_host.csv（主機整機 CPU%、可用記憶體 MB，實際約每 5 秒一筆）、_locust.log（找 Locust 的 CPU 警告）。
判斷規則：
- 伺服器飽和：backend 或 db 的 CPU 峰值 >= 90%（backend 只有一個 worker 行程，約等於吃滿一顆核心）。
- 壓測端／主機受限：該階的時間內 Locust log 出現 "CPU usage above 90%"、主機 CPU >= 90% 但容器沒飽和，
  或可用記憶體（Available MBytes）< 500 MB。Locust 警告依時間落在哪一階就只算那一階。
時間一律 UTC 的 HH:MM:SS；跨午夜（結束時間小於開始時間）加 86400 秒；格式錯誤的列略過。
"""

import csv
import re
import sys
from datetime import datetime, timezone

DAY = 86400
WARNING = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\].*CPU usage above 90")


def secs(hms: str) -> int:
    t = datetime.strptime(hms.strip(), "%H:%M:%S")
    return t.hour * 3600 + t.minute * 60 + t.second


def window(start: str, end: str) -> tuple[int, int]:
    s, e = secs(start), secs(end)
    return s, e + DAY if e < s else e


def inside(hms: str, s: int, e: int) -> bool:
    t = secs(hms)
    return s <= t <= e or s <= t + DAY <= e


def read(path: str) -> list[list[str]]:
    try:
        with open(path, encoding="utf-8") as f:
            return [r for r in csv.reader(f) if r]
    except FileNotFoundError:
        return []


def pct(text: str) -> float:
    return float(text.strip().rstrip("%"))


def locust_warning_times(path: str) -> list[str]:
    """Locust log 的時間戳是本機時間；轉成 UTC 的 HH:MM:SS 才能對上各階。"""
    found = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = WARNING.match(line)
                if m:
                    local = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
                    found.append(local.astimezone(timezone.utc).strftime("%H:%M:%S"))
    except FileNotFoundError:
        pass
    return found


def main(prefix: str) -> None:
    stages = read(f"{prefix}_stages.csv")[1:]
    docker = read(f"{prefix}_docker.csv")  # time, name, cpu, mem
    host = read(f"{prefix}_host.csv")  # time, cpu, avail_mb
    warnings = locust_warning_times(f"{prefix}_locust.log")

    out = [["stage", "users", "backend_cpu_max", "db_cpu_max", "worker_cpu_max", "host_cpu_max",
            "host_avail_mb_min", "samples_docker", "samples_host", "locust_cpu_warnings", "bottleneck"]]
    skipped = 0
    for row in stages:
        try:
            stage, users = row[1], row[2]
            s, e = window(row[3], row[4])
        except (IndexError, ValueError):
            skipped += 1
            continue
        cpu = {"backend": 0.0, "db": 0.0, "worker": 0.0}
        n_docker = 0
        for r in docker:
            try:
                if len(r) >= 3 and inside(r[0], s, e):
                    for key in cpu:
                        if f"-{key}-" in r[1]:
                            cpu[key] = max(cpu[key], pct(r[2]))
                    n_docker += 1
            except ValueError:
                skipped += 1
        hosts: list[tuple[float, float]] = []
        for r in host:
            try:
                if len(r) >= 3 and inside(r[0], s, e):
                    hosts.append((pct(r[1]), float(r[2])))
            except ValueError:
                skipped += 1
        stage_warnings = 0
        for w in warnings:
            try:
                stage_warnings += inside(w, s, e)
            except ValueError:
                skipped += 1
        host_cpu = max((h[0] for h in hosts), default=0.0)
        avail = min((h[1] for h in hosts), default=0.0)
        reasons = []
        if cpu["backend"] >= 90:
            reasons.append("backend CPU 滿")
        if cpu["db"] >= 90:
            reasons.append("db CPU 滿")
        if stage_warnings:
            reasons.append("Locust CPU 警告")
        if hosts and host_cpu >= 90 and not reasons:
            reasons.append("主機 CPU 滿")
        if hosts and avail < 500:
            reasons.append("可用記憶體 < 500 MB")
        if not n_docker or not hosts:
            reasons.append("資源取樣不足")
        out.append([stage, users, f"{cpu['backend']:.0f}%", f"{cpu['db']:.0f}%", f"{cpu['worker']:.0f}%",
                    f"{host_cpu:.0f}%", f"{avail:.0f}", n_docker, len(hosts), stage_warnings,
                    "；".join(reasons) or "未見資源飽和"])
    with open(f"{prefix}_resources.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    for r in out:
        print(",".join(str(x) for x in r))
    print(f"Locust CPU 警告共 {len(warnings)} 次；略過格式錯誤的列 {skipped} 筆")


if __name__ == "__main__":
    main(sys.argv[1])
