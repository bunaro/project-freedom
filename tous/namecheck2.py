# -*- coding: utf-8 -*-
"""회사명 후보 전수 검증 — 다섯 곳을 한 번에 본다.

기존 namecheck.py는 도메인·웹 검색만 봤다. 그래서 Kaelun이 통과했는데
나중에 GitHub·Docker Hub에서 막혔다(2026-07-29). 그 실패를 반복하지 않기 위해
회사명이 실제로 쓰이는 다섯 곳을 처음부터 전부 확인한다.

    python namecheck2.py avelo lunaro meriku ...
    python namecheck2.py --file cands.txt

판정: 다섯 곳 모두 비어야 [OK]. 하나라도 막히면 [TAKEN].
"""
import os, sys, socket, concurrent.futures as cf
import urllib.request, urllib.error

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TLDS = ("com", "ai", "io", "co")
TIMEOUT = 10


def _dns_taken(name):
    """도메인 4종 중 하나라도 물리면 선점."""
    for tld in TLDS:
        try:
            socket.getaddrinfo(f"{name}.{tld}", None)
            return f"{name}.{tld}"
        except socket.gaierror:
            continue
        except Exception:
            return None          # 확인 불가
    return ""


def _http_taken(url):
    """404면 비어 있음, 200이면 선점, 그 외는 확인 불가(None)."""
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "namecheck2"}),
            timeout=TIMEOUT)
        return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def check(name):
    n = name.strip().lower()
    if not n:
        return None
    checks = {
        "GitHub": f"https://api.github.com/users/{n}",
        "npm":    f"https://registry.npmjs.org/{n}",
        "PyPI":   f"https://pypi.org/pypi/{n}/json",
        "Docker": f"https://hub.docker.com/v2/users/{n}/",
    }
    hit = []
    dns = _dns_taken(n)
    if dns:
        hit.append(f"도메인({dns})")
    elif dns is None:
        hit.append("도메인(확인불가)")
    for label, url in checks.items():
        r = _http_taken(url)
        if r is True:
            hit.append(label)
        elif r is None:
            hit.append(f"{label}(확인불가)")
    return {"name": n, "ok": not hit, "blocked": hit}


def main(names):
    names = [n.strip().lower() for n in names if n.strip()]
    print(f"검증 대상 {len(names)}개 · 도메인4종 + GitHub·npm·PyPI·Docker Hub\n")
    results = []
    # 후보가 많으므로 병렬로 — 순차로 돌리면 80개에 20분 넘게 걸린다
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(check, names):
            if r:
                results.append(r)
                mark = "[OK]   " if r["ok"] else "[TAKEN]"
                detail = "다섯 곳 전부 비어 있음" if r["ok"] else ", ".join(r["blocked"][:3])
                print(f"  {mark} {r['name']:12} {detail}")
    ok = [r["name"] for r in results if r["ok"]]
    print(f"\n{'='*58}")
    print(f"통과 {len(ok)}/{len(results)}개")
    if ok:
        print("  " + ", ".join(ok))
    print("\n※ 최종 확정 전 상표DB(USPTO/KIPRIS) 확인은 별도.")
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    if args[0] == "--file" and len(args) > 1:
        raw = open(args[1], encoding="utf-8").read()
        names = [x for x in raw.replace("\n", ",").split(",")]
    else:
        names = args
    main(names)
