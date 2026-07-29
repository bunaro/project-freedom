# -*- coding: utf-8 -*-
"""Notify — CEO(태영님)에게 텔레그램으로 요청을 보낸다.

AI 임원이 회의로 결정하고 CTO(Claude Code)가 실행하다가,
사람만 할 수 있는 일(결재·인증·계정 생성·비용 발생)에 막히면 여기서 CEO를 부른다.
CEO는 폰으로 받고, 처리한 뒤 remote.py로 답하거나 직접 처리한다.

    python notify.py "결제 API 키가 필요합니다"
    python notify.py --type 승인 "판매 페이지 초안 검토 요청"

설정: .env 의 TELEGRAM_BOT_TOKEN, TOUS_CHAT_ID (remote.py와 공유)
"""
import os, sys, json, urllib.parse, urllib.request, urllib.error, datetime

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(BASE, ".env")
LOG = os.path.join(BASE, "requests.json")      # 보낸 요청 기록(회의에서 미처리 건을 볼 수 있게)
API = "https://api.telegram.org/bot{token}/{method}"
MAXLEN = 3800

# 요청 유형 — CEO가 무엇을 해야 하는지 한눈에 알도록
KINDS = {
    "승인": "결재·승인 요청",
    "인증": "로그인·API 키·계정 인증 필요",
    "비용": "지출 승인 필요",
    "결정": "AI가 판단할 수 없는 결정",
    "확인": "확인 요청",
}


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


def _log(entry):
    """요청 이력 — 다음 회의에서 '아직 CEO 처리 대기'로 이어받을 수 있다."""
    items = []
    if os.path.exists(LOG):
        try:
            with open(LOG, encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
    entry["id"] = max([i.get("id", 0) for i in items], default=0) + 1
    items.append(entry)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return entry["id"]


def notify(message, kind="확인", context="", meeting=None):
    """CEO에게 요청 전송. (성공여부, 안내문) 반환.

    텔레그램이 안 되더라도 요청은 requests.json에 남는다 — 알림 실패로 요청이 사라지면 안 된다."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rid = _log({"time": now, "kind": kind, "message": message,
                "context": context, "meeting": meeting, "status": "open"})

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat = env.get("TOUS_CHAT_ID", "")
    if not token or not chat:
        return False, f"요청 #{rid} 기록됨 (텔레그램 미설정 — .env 확인 필요)"

    label = KINDS.get(kind, kind)
    body = [f"🔔 <b>[{label}] CEO 요청 #{rid}</b>", ""]
    if meeting:
        body.append(f"회의 #{meeting:03d} 관련")
    body.append(message)
    if context:
        body += ["", f"<i>{context[:800]}</i>"]
    body += ["", f"— Tous · {now}"]
    text = "\n".join(body)[:MAXLEN]

    url = API.format(token=token, method="sendMessage")
    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            ok = json.load(r).get("ok", False)
        return (True, f"요청 #{rid} 전송 완료") if ok else (False, f"요청 #{rid} 기록됨 (전송 실패)")
    except Exception as e:
        return False, f"요청 #{rid} 기록됨 (전송 오류: {str(e)[:100]})"


def open_requests():
    """CEO가 아직 처리하지 않은 요청 — 회의 이월에 쓴다."""
    if not os.path.exists(LOG):
        return []
    try:
        with open(LOG, encoding="utf-8") as f:
            return [i for i in json.load(f) if i.get("status") == "open"]
    except Exception:
        return []


if __name__ == "__main__":
    args = sys.argv[1:]
    kind = "확인"
    if args and args[0] == "--type" and len(args) >= 2:
        kind, args = args[1], args[2:]
    if not args:
        print(__doc__); sys.exit(0)
    ok, msg = notify(" ".join(args), kind=kind)
    print(msg)
