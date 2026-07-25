# -*- coding: utf-8 -*-
"""Tous — AI Company Operating System (MVP, CLI-only)

AI 임원들을 CLI로 호출해 회의를 열고, 결과를 회의록/Task/보고로 남긴다.
API 종량과금 0원 — 각 임원은 자기 구독(OAuth) CLI로 답한다.

사용:
    python tous.py meeting "안건 문장"     # 회의 소집 → 회의록 + Task 생성
    python tous.py tasks                   # Task 목록
    python tous.py report                  # CEO 보고서 출력
    python tous.py roster                  # 임원 가용 상태 점검

구조:
    docs/meetings/  회의록(공개 기록, Build in Public)
    tous/tasks.json Task 저장소
"""
import os, re, sys, json, subprocess, datetime

try: sys.stdout.reconfigure(encoding="utf-8")   # Windows cp949 콘솔에서 한글/대시 출력 보장
except Exception: pass

BASE     = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(BASE)
MEETINGS = os.path.join(ROOT, "docs", "meetings")
TASKS    = os.path.join(BASE, "tasks.json")
TIMEOUT  = 600

# ── AI 임원단 ────────────────────────────────────────────────
# cmd: 프롬프트를 인자로 받아 실행할 명령 (shell=True로 실행)
EXECUTIVES = [
    {
        "role": "CTO",
        "name": "Claude",
        "charter": ("You are the CTO of a company being built by AI. You own engineering, "
                    "automation, product architecture, and code. You judge feasibility and "
                    "call out technical risk early."),
        "cmd": 'claude --print --tools ""',
        "stdin": True,
    },
    {
        "role": "CMO",
        "name": "ChatGPT",
        "charter": ("You are the CMO. You own brand, content, marketing, narrative, and the "
                    "customer's point of view. You ask who this is for and why they would care."),
        "cmd": 'codex exec --skip-git-repo-check',
        "stdin": True,
    },
    {
        "role": "CSO",
        "name": "Gemini",
        "charter": ("You are the CSO. You own market research, competitor analysis, and strategy. "
                    "You ground opinions in what the market actually shows."),
        "cmd": 'gemini -p',
        "stdin": False,   # gemini는 -p 뒤 인자로 프롬프트를 받음
    },
]

RULES = (
    "House rules: do not simply agree. If you disagree, say so and give your reason. "
    "Be concrete and brief — under 200 words. No preamble, no sign-off."
)


# CLI가 섞어 뱉는 잡음(프로세스 종료 로그·훅·배너). Codex가 특히 심해 회의록을 오염시킴.
NOISE = re.compile(
    r"^\s*(?:"
    r"(?:오류|정보|경고|ERROR|WARN|INFO)\s*[:：].*"        # 상태 로그
    r"|.*프로세스.*(?:종료|찾을 수 없)\S*.*"                 # taskkill 한글 로그
    r"|.*PID\s+\d+.*"                                       # PID 로그
    r"|hook:\s*\w+.*"                                       # 훅 라인
    r"|\[\d{4}-\d{2}-\d{2}T[\d:.]+\].*"                      # 타임스탬프 배너
    r"|(?:user|assistant|codex|thinking|tokens used)\s*$"     # 역할/메타 라벨
    r")\s*$", re.I)


# Codex는 실행 배너(workdir/model/provider/sandbox…)를 먼저 뱉고 그 뒤에 본문을 낸다.
# 배너 헤더 라인들과 구분선을 통째로 제거.
BANNER = re.compile(
    r"^\s*(?:"
    r"Reading prompt from stdin\.*"
    r"|OpenAI Codex v[\d.]+.*"
    r"|-{4,}"
    r"|(?:workdir|model|provider|approval|sandbox|reasoning\s+\w*|session id|version)\s*:.*"
    r")\s*$", re.I)


def clean_output(raw):
    """CLI 출력에서 잡음·실행배너를 걷어내고 본문만 남긴다."""
    lines = [l for l in (raw or "").splitlines()
             if not NOISE.match(l) and not BANNER.match(l)]
    return "\n".join(lines).strip()


def run_cli(ex, prompt):
    """임원 CLI 호출. (성공여부, 텍스트) 반환."""
    try:
        if ex["stdin"]:
            p = subprocess.run(ex["cmd"], input=prompt, shell=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        else:
            p = subprocess.run(f'{ex["cmd"]} "{prompt}"', shell=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        # 한도/인증 오류는 stderr로 나오는 CLI가 있어 stdout+stderr를 함께 검사
        combined = f"{p.stdout or ''}\n{p.stderr or ''}".lower()
        out = clean_output(p.stdout or "")
        low = out.lower()
        if "usage limit" in combined or "hit your usage" in combined:
            when = ""
            if m := re.search(r"try again at ([^.\n]+)", combined, re.I):
                when = f" (리셋: {m.group(1).strip()})"
            return False, f"사용량 한도 소진{when}"
        if "please set an auth" in low or "auth method" in low:
            return False, "인증 미설정 — CLI 로그인 필요"
        if not out:
            return False, ((p.stderr or "").strip()[:200] or "빈 응답")
        return True, out
    except subprocess.TimeoutExpired:
        return False, f"타임아웃({TIMEOUT}s)"
    except Exception as e:
        return False, f"실행 오류: {e}"


def load_tasks():
    if os.path.exists(TASKS):
        with open(TASKS, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_tasks(tasks):
    with open(TASKS, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def next_meeting_no():
    os.makedirs(MEETINGS, exist_ok=True)
    ns = [int(m.group(1)) for f in os.listdir(MEETINGS)
          if (m := re.match(r"meeting-(\d+)", f))]
    return max(ns, default=0) + 1


def cmd_roster():
    """임원 가용 상태 점검 — 회의 전에 누가 참석 가능한지."""
    print("=== Tous 임원단 점검 ===")
    for ex in EXECUTIVES:
        ok, out = run_cli(ex, "Reply with exactly: OK")
        mark = "[OK]  " if ok else "[FAIL]"
        detail = "응답 정상" if ok else out
        print(f"{mark} {ex['role']:4} ({ex['name']}) — {detail}")


def cmd_meeting(agenda):
    """회의 소집 → 각 임원 발언 수집 → 회의록 저장 → CTO가 Task 도출."""
    no = next_meeting_no()
    today = datetime.date.today().isoformat()
    print(f"=== Tous 회의 #{no:03d} ===\n안건: {agenda}\n")

    minutes, present = [], []
    for ex in EXECUTIVES:
        print(f"[{ex['role']}] 발언 요청 중...")
        prompt = (f"{ex['charter']}\n\n{RULES}\n\n"
                  f"--- AGENDA ---\n{agenda}\n\n"
                  f"Give your position as {ex['role']}.")
        ok, out = run_cli(ex, prompt)
        if ok:
            present.append(ex["role"])
            minutes.append((ex["role"], ex["name"], out))
            print(f"  → 발언 확보 ({len(out)}자)\n")
        else:
            minutes.append((ex["role"], ex["name"], f"_(불참: {out})_"))
            print(f"  → 불참: {out}\n")

    # CTO가 회의를 Task로 환원 (CTO 불참이면 생략)
    tasks_md, new_tasks = "_(Task 도출 생략 — CTO 불참)_", []
    if "CTO" in present:
        joined = "\n\n".join(f"[{r} {n}]\n{t}" for r, n, t in minutes)
        ok, out = run_cli(EXECUTIVES[0],
            "You are the CTO. Turn this meeting into concrete next actions.\n\n"
            f"--- AGENDA ---\n{agenda}\n\n--- MINUTES ---\n{joined}\n\n"
            "Output ONLY a numbered list, max 5 items. Each line: the action, then ' — owner: '"
            " and one of CEO/CTO/CMO/CSO. No other text.")
        if ok:
            tasks_md = out
            for line in out.splitlines():
                line = line.strip()
                if not re.match(r"^\d+[.)]\s", line):
                    continue
                body = re.sub(r"^\d+[.)]\s*", "", line)
                owner = "CTO"
                if m := re.search(r"owner:\s*(CEO|CTO|CMO|CSO)", body, re.I):
                    owner = m.group(1).upper()
                    body = body[:m.start()].rstrip(" —-").strip()
                new_tasks.append({"id": 0, "meeting": no, "task": body,
                                  "owner": owner, "status": "open", "created": today})

    if new_tasks:
        tasks = load_tasks()
        nid = max([t["id"] for t in tasks], default=0)
        for t in new_tasks:
            nid += 1
            t["id"] = nid
        tasks.extend(new_tasks)
        save_tasks(tasks)

    # 회의록 저장 (공개 기록)
    os.makedirs(MEETINGS, exist_ok=True)
    path = os.path.join(MEETINGS, f"meeting-{no:03d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Tous 회의 #{no:03d}\n\n_{today} · 참석: {', '.join(present) or '없음'}_\n\n")
        f.write(f"## 안건\n\n{agenda}\n\n## 임원 발언\n\n")
        for r, n, t in minutes:
            f.write(f"### {r} ({n})\n\n{t}\n\n")
        f.write(f"## 도출된 Task\n\n{tasks_md}\n\n---\n\n")
        f.write("_Tous(AI Company OS)가 자동 생성. 최종 결정은 CEO 승인._\n")

    print(f"회의록: {path}")
    print(f"Task {len(new_tasks)}건 생성 (참석 {len(present)}/{len(EXECUTIVES)})")


def cmd_tasks():
    tasks = load_tasks()
    if not tasks:
        print("Task 없음."); return
    print("=== Tous Task 목록 ===")
    for t in tasks:
        mark = "[x]" if t["status"] == "done" else "[ ]"
        print(f"{mark} #{t['id']:02d} ({t['owner']}) {t['task']}  _#{t['meeting']:03d}_")


def cmd_report():
    tasks = load_tasks()
    opens = [t for t in tasks if t["status"] != "done"]
    os.makedirs(MEETINGS, exist_ok=True)
    meetings = sorted(f for f in os.listdir(MEETINGS) if f.startswith("meeting-"))
    print("=== CEO 보고 ===")
    print(f"회의 {len(meetings)}건 / Task {len(tasks)}건 (미완 {len(opens)})")
    if opens:
        print("\n[승인·처리 대기]")
        for t in opens:
            print(f"  #{t['id']:02d} ({t['owner']}) {t['task']}")
    ceo = [t for t in opens if t["owner"] == "CEO"]
    if ceo:
        print(f"\n★ CEO 직접 처리 필요: {len(ceo)}건")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    c = args[0]
    if c == "meeting":
        if len(args) < 2:
            print("사용: python tous.py meeting \"안건\""); sys.exit(1)
        cmd_meeting(" ".join(args[1:]))
    elif c == "tasks":  cmd_tasks()
    elif c == "report": cmd_report()
    elif c == "roster": cmd_roster()
    else:
        print(f"알 수 없는 명령: {c}"); print(__doc__)
