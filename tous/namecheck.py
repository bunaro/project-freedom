# -*- coding: utf-8 -*-
"""회사명 후보 일괄 검증 — 도메인·웹 선점 여부를 한 번에 거른다.

회의에서 이름 하나 내고 → 검색해서 탈락 → 다시 회의를 3번 반복했다(Ours/Aivora/Duova).
후보를 대량으로 받아 자동으로 걸러내고, 살아남은 것만 회의에 올린다.

사용:
    python namecheck.py Nyvexa Feronis Kaelun Verumo Isnara

판정:
    [OK]    DNS 미등록 + 웹 검색결과 희박 → 유력
    [WARN]  DNS 없음이나 웹에 흔적 있음 → 수동 확인
    [TAKEN] 도메인 사용중 → 탈락

주의: DNS 조회만으로는 등록 여부를 확정할 수 없다(등록해도 DNS 미설정이면 빈 것처럼 보임).
      최종 확정 전에는 반드시 상표DB(USPTO/KIPRIS)를 사람이 직접 확인해야 한다.
"""
import sys, socket, urllib.parse, urllib.request, json

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TLDS = ("com", "ai", "io", "co")
UA = {"User-Agent": "Mozilla/5.0 (namecheck)"}


def dns_taken(domain):
    """DNS A레코드 존재 = 확실히 사용중."""
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def web_hits(name):
    """DuckDuckGo로 해당 이름의 웹 흔적을 센다(무료·키 불필요)."""
    try:
        url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(f'"{name}"')
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
        return html.count('class="result__a"')
    except Exception:
        return -1   # 조회 실패


def check(name):
    taken = [f"{name.lower()}.{t}" for t in TLDS if dns_taken(f"{name.lower()}.{t}")]
    hits = web_hits(name)
    if taken:
        verdict, note = "TAKEN", f"도메인 사용중: {', '.join(taken)}"
    elif hits > 8:
        verdict, note = "WARN", f"웹 검색결과 {hits}건 — 기존 브랜드 가능성"
    elif hits < 0:
        verdict, note = "WARN", "웹 검색 실패 — 수동 확인 필요"
    else:
        verdict, note = "OK", f"도메인 4종 미등록, 웹 흔적 {hits}건"
    return verdict, note


def main(names):
    if not names:
        print(__doc__); return
    print(f"{'판정':6} {'이름':12} 근거")
    print("-" * 70)
    survivors = []
    for n in names:
        v, note = check(n)
        mark = {"OK": "[OK]   ", "WARN": "[WARN] ", "TAKEN": "[TAKEN]"}[v]
        print(f"{mark} {n:12} {note}")
        if v == "OK":
            survivors.append(n)
    print("-" * 70)
    print(f"통과: {', '.join(survivors) if survivors else '없음'}")
    print("※ 최종 확정 전 상표DB(USPTO/KIPRIS) 직접 확인 필수.")


if __name__ == "__main__":
    main(sys.argv[1:])
