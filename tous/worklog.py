# -*- coding: utf-8 -*-
"""Worklog — 회의가 끝나면 CTO가 이어서 할 일을 큐에 남긴다.

회의는 board.py(웹) 또는 remote.py(텔레그램)에서 열리므로, 회의가 끝난 사실을
CTO(Claude Code)가 알 방법이 없었다. CEO가 매번 "회의 끝났다"고 알려줘야 했다.
이 파일이 그 단절을 메운다 — 회의 종료 시 실행 대기 큐를 남기고,
CTO는 세션 시작 시 이걸 먼저 확인한다.

    python worklog.py            # 실행 대기 현황(CTO가 세션 시작 시 실행)
    python worklog.py --json     # 기계 판독용
"""
import os, sys, json, datetime

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(BASE, "worklog.json")

# 자율 실행 상한 — CEO 지시 없이 이어질 수 있는 연쇄(회의→실행→회의…)의 최대 길이.
# 회의 수가 아니라 '연쇄'를 세는 이유: 회의 1회당 Task가 5건 나오므로 회의로 세면
# 잘못된 전제 위에서 15건이 쌓일 수 있다. 연쇄로 세면 사슬 자체가 3번에 끊긴다.
AUTORUN_MAX = 3


def _load():
    if os.path.exists(QUEUE):
        try:
            with open(QUEUE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(items):
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def record_meeting(no, path, tasks, brief, assumptions=None, verdict=""):
    """회의 종료 시 호출 — CTO 실행 대기 항목을 남긴다."""
    items = _load()
    cto = [t for t in tasks if t.get("owner") == "CTO"]
    items.append({
        "meeting": no,
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "minutes": path,
        "verdict": verdict,
        "cto_tasks": [{"id": t["id"], "task": t["task"],
                       "due": t.get("due", ""), "done_when": t.get("done_when", "")}
                      for t in cto],
        "assumptions": [{"role": r, "text": a} for r, a in (assumptions or [])],
        "brief": brief[:2000],
        "status": "pending",       # pending → CTO가 처리하면 handled
    })
    _save(items)
    return len(cto)


def pending():
    return [i for i in _load() if i.get("status") == "pending"]


CHAIN = os.path.join(BASE, "autorun_chain.json")


def chain_state():
    """자율 연쇄 상태. CEO가 새로 지시하면 리셋된다."""
    if os.path.exists(CHAIN):
        try:
            with open(CHAIN, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"count": 0, "started": "", "last": ""}


def chain_bump():
    """연쇄 1회 소비. (허용여부, 현재횟수, 사유) 반환."""
    s = chain_state()
    if s["count"] >= AUTORUN_MAX:
        return False, s["count"], f"자율 실행 상한 {AUTORUN_MAX}회 도달 — CEO 지시 대기"
    s["count"] += 1
    s["last"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not s["started"]:
        s["started"] = s["last"]
    with open(CHAIN, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    return True, s["count"], ""


def chain_reset():
    """CEO가 새 지시를 내리면 연쇄를 처음부터 다시 센다."""
    with open(CHAIN, "w", encoding="utf-8") as f:
        json.dump({"count": 0, "started": "", "last": ""}, f, ensure_ascii=False, indent=2)


def can_autorun():
    """자율 실행 가능 여부 판정. (가능, 사유) 반환.

    상한과 별개로 — CEO 확인이 필요한 가정이 있으면 무조건 멈춘다.
    회의 #010에서 임원들이 없는 인맥을 가정해 가결한 사고가 그 이유다."""
    ps = pending()
    if not ps:
        return False, "실행 대기 없음"
    risky = [a for i in ps for a in i.get("assumptions", [])]
    if risky:
        return False, f"CEO 확인 필요한 가정 {len(risky)}건 — 자율 실행 중단, CEO에게 질의"
    s = chain_state()
    if s["count"] >= AUTORUN_MAX:
        return False, f"자율 실행 상한 {AUTORUN_MAX}회 도달 — CEO 지시 대기"
    return True, f"자율 실행 가능 ({s['count']}/{AUTORUN_MAX} 사용)"


def mark_handled(meeting_no):
    items = _load()
    for i in items:
        if i.get("meeting") == meeting_no:
            i["status"] = "handled"
            i["handled_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    _save(items)


def report():
    ps = pending()
    if not ps:
        return "실행 대기 없음 — 새 회의 결과가 없습니다."
    ok, why = can_autorun()
    out = [f"[자율 실행] {'가능' if ok else '중단'} — {why}", ""]
    for i in ps:
        out.append(f"■ 회의 #{i['meeting']:03d} ({i['at']}) — {i.get('verdict') or '표결 없음'}")
        out.append(f"  회의록: {i['minutes']}")
        if i["assumptions"]:
            out.append("  ⚠ CEO 확인 필요한 가정 (사실과 다르면 실행 보류)")
            for a in i["assumptions"]:
                out.append(f"    - [{a['role']}] {a['text']}")
        if i["cto_tasks"]:
            out.append(f"  CTO 실행 대기 {len(i['cto_tasks'])}건")
            for t in i["cto_tasks"]:
                due = f" (~{t['due']})" if t["due"] else ""
                out.append(f"    #{t['id']:02d} {t['task']}{due}")
                if t["done_when"]:
                    out.append(f"        완료조건: {t['done_when']}")
        else:
            out.append("  CTO 실행 대기 없음")
    return "\n".join(out)


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(pending(), ensure_ascii=False, indent=2))
    else:
        print(report())
