# -*- coding: utf-8 -*-
"""Tous Remote — 모바일(텔레그램)에서 AI 회사를 원격 조종한다.

CEO가 폰에서 회의를 소집하고, 회의록을 읽고, Task를 승인한다.
Tous는 로컬 PC의 CLI(구독 인증)로 돌기 때문에 이 PC가 켜져 있어야 한다.

명령:
    /meeting <안건>   회의 소집 (오래 걸림 — 끝나면 결과 푸시)
    /tasks            Task 목록
    /done <번호>      Task 완료 처리
    /report           CEO 보고
    /roster           임원 가용 상태
    /minutes [번호]   회의록 보기 (기본: 최신)

보안: TOUS_CHAT_ID에 등록된 채팅만 응답한다(타인 접근 차단).
설정: .env 에 TELEGRAM_BOT_TOKEN, TOUS_CHAT_ID
실행: python remote.py
"""
import os, re, sys, json, time, html, urllib.parse, urllib.request, urllib.error
import tous

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE = os.path.dirname(os.path.abspath(__file__))
ENV  = os.path.join(BASE, ".env")
API  = "https://api.telegram.org/bot{token}/{method}"
MAXLEN = 3800   # 텔레그램 메시지 상한(4096) 여유


def load_env():
    d = {}
    if os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    d[k.strip()] = v.strip()
    return d


def tg(token, method, **params):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=70) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": e.read().decode(errors="replace")[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send(token, chat_id, text):
    """긴 메시지는 잘라서 여러 통으로."""
    for i in range(0, len(text), MAXLEN):
        tg(token, "sendMessage", chat_id=chat_id, text=text[i:i + MAXLEN])


# ── 명령 처리 ────────────────────────────────────────────────
def do_tasks():
    ts = tous.load_tasks()
    if not ts:
        return "Task 없음."
    lines = ["📋 Task 목록"]
    for t in ts:
        mark = "✅" if t["status"] == "done" else "⬜"
        lines.append(f"{mark} #{t['id']:02d} [{t['owner']}] {t['task']}")
    return "\n".join(lines)


def do_done(arg):
    if not arg.strip().isdigit():
        return "사용법: /done 3"
    tid = int(arg.strip())
    ts = tous.load_tasks()
    for t in ts:
        if t["id"] == tid:
            t["status"] = "done"
            tous.save_tasks(ts)
            return f"✅ #{tid:02d} 완료 처리\n{t['task']}"
    return f"#{tid:02d} 없음."


def do_report():
    ts = tous.load_tasks()
    opens = [t for t in ts if t["status"] != "done"]
    ceo = [t for t in opens if t["owner"] == "CEO"]
    meetings = []
    if os.path.isdir(tous.MEETINGS):
        meetings = [f for f in os.listdir(tous.MEETINGS) if f.startswith("meeting-")]
    out = [f"📊 CEO 보고", f"회의 {len(meetings)}건 / Task {len(ts)}건 (미완 {len(opens)})"]
    if ceo:
        out.append(f"\n★ CEO 직접 처리 {len(ceo)}건")
        for t in ceo:
            out.append(f"  #{t['id']:02d} {t['task']}")
    other = [t for t in opens if t["owner"] != "CEO"]
    if other:
        out.append("\n[진행 대기]")
        for t in other:
            out.append(f"  #{t['id']:02d} [{t['owner']}] {t['task']}")
    return "\n".join(out)


def do_roster():
    lines = ["👥 임원 가용 상태"]
    for ex in tous.EXECUTIVES:
        ok, msg = tous.run_cli(ex, "Reply with exactly: OK")
        lines.append(f"{'🟢' if ok else '🔴'} {ex['role']} ({ex['name']}) — {'정상' if ok else msg}")
    return "\n".join(lines)


def do_minutes(arg):
    if not os.path.isdir(tous.MEETINGS):
        return "회의록 없음."
    files = sorted(f for f in os.listdir(tous.MEETINGS) if f.startswith("meeting-"))
    if not files:
        return "회의록 없음."
    name = None
    if arg.strip().isdigit():
        want = f"meeting-{int(arg.strip()):03d}.md"
        name = want if want in files else None
        if not name:
            return f"{want} 없음. 보유: {', '.join(files)}"
    else:
        name = files[-1]
    with open(os.path.join(tous.MEETINGS, name), encoding="utf-8") as f:
        return f.read()


def do_meeting(token, chat_id, agenda):
    if not agenda.strip():
        return "사용법: /meeting 회사명을 정하자"
    send(token, chat_id, f"🏛 회의 소집 중...\n안건: {agenda}\n\n임원 발언을 모으는 중입니다. 몇 분 걸립니다.")
    before = set(os.listdir(tous.MEETINGS)) if os.path.isdir(tous.MEETINGS) else set()
    try:
        tous.cmd_meeting(agenda)
    except Exception as e:
        return f"회의 실패: {e}"
    after = set(os.listdir(tous.MEETINGS)) if os.path.isdir(tous.MEETINGS) else set()
    new = sorted(after - before)
    if not new:
        return "회의는 돌았으나 회의록을 찾지 못했습니다."
    with open(os.path.join(tous.MEETINGS, new[-1]), encoding="utf-8") as f:
        return f.read()


HELP = (
    "🤖 Tous Remote — AI 회사 원격 조종\n\n"
    "/meeting <안건>  회의 소집\n"
    "/minutes [번호]  회의록 보기\n"
    "/tasks           Task 목록\n"
    "/done <번호>     Task 완료\n"
    "/report          CEO 보고\n"
    "/roster          임원 상태\n"
)


def handle(token, chat_id, text):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1] if len(parts) > 1 else ""
    if cmd in ("/start", "/help"):
        return HELP
    if cmd == "/tasks":   return do_tasks()
    if cmd == "/done":    return do_done(arg)
    if cmd == "/report":  return do_report()
    if cmd == "/roster":  return do_roster()
    if cmd == "/minutes": return do_minutes(arg)
    if cmd == "/meeting": return do_meeting(token, chat_id, arg)
    return None   # 명령 아닌 일반 대화는 무시


def main():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    allowed = str(env.get("TOUS_CHAT_ID", "")).strip()
    if not token:
        print("ERROR: .env에 TELEGRAM_BOT_TOKEN 없음."); sys.exit(1)

    me = tg(token, "getMe")
    if not me.get("ok"):
        print(f"ERROR: 봇 인증 실패 — {me.get('error') or me}"); sys.exit(1)
    print(f"Tous Remote 시작 — @{me['result'].get('username')}")
    if not allowed:
        print("⚠️ TOUS_CHAT_ID 미설정: 첫 메시지를 보낸 채팅 ID를 알려주니 .env에 넣으세요.")

    offset = None
    while True:
        r = tg(token, "getUpdates", timeout=60, **({"offset": offset} if offset else {}))
        if not r.get("ok"):
            time.sleep(5); continue
        for u in r.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or u.get("edited_message")
            if not msg or "text" not in msg:
                continue
            cid = str(msg["chat"]["id"])
            if not allowed:
                print(f"👉 이 채팅 ID를 .env의 TOUS_CHAT_ID에 넣으세요: {cid}")
                send(token, cid, f"등록되지 않은 채팅입니다.\n이 ID를 .env에 넣어주세요:\n{cid}")
                continue
            if cid != allowed:
                continue   # 타인 차단(무응답)
            try:
                out = handle(token, cid, msg["text"])
            except Exception as e:
                out = f"오류: {e}"
            if out:
                send(token, cid, out)


if __name__ == "__main__":
    main()
