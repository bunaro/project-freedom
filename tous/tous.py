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
        "charter": ("당신은 AI가 만들어가는 회사의 CTO다. 개발·자동화·제품 아키텍처·코드를 책임진다. "
                    "실현 가능성을 판단하고 기술적 위험을 먼저 짚는다."),
        "cmd": 'claude --print --tools ""',
        "stdin": True,
    },
    {
        "role": "CMO",
        "name": "ChatGPT",
        "charter": ("당신은 CMO다. 브랜드·콘텐츠·마케팅·서사·고객 관점을 책임진다. "
                    "이게 누구를 위한 것이고 왜 그들이 관심을 가질지 묻는다."),
        "cmd": 'codex exec --skip-git-repo-check',
        "stdin": True,
    },
    {
        "role": "CSO",
        "name": "Gemini",
        "charter": ("당신은 CSO다. 시장 조사·경쟁사 분석·전략을 책임진다. "
                    "의견은 시장이 실제로 보여주는 근거 위에 세운다."),
        # --skip-trust: 비대화형이라 신뢰 프롬프트를 띄울 수 없음.
        # (툴 비활성 플래그는 폐기 예정이라 사용 불가 → 파일 탐색 금지는 RULES에서 지시)
        "cmd": 'gemini --skip-trust -p',
        "stdin": False,   # gemini는 -p 뒤 인자로 프롬프트를 받음
    },
]

RULES = (
    "회의 규칙: 무조건 동의하지 마라. 반대하면 반대한다고 말하고 근거를 대라. "
    "구체적으로, 200단어 이내로 짧게. 서두·맺음말 없이 본론만. "
    "이것은 이사회 발언이지 코딩 작업이 아니다. 파일을 읽거나 목록을 보거나 검색하지 말고, "
    "어떤 도구도 실행하지 마라. 아래 안건 텍스트만 보고 판단하라. "
    "**반드시 한국어로 답하라.** (CEO가 한국인이며 회의록은 한국어로 공개된다.)"
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


# .env → CLI 프로세스로 넘길 인증 변수.
# Gemini는 2026-07 구글 OAuth 개인티어가 중단돼(IneligibleTierError) Vertex AI 또는 API 키가 필요.
# 현재 Vertex 모드 사용 — 기존 factory-498717 서비스 계정 재사용.
PASS_ENV = (
    "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_API_KEY", "GOOGLE_API_KEY",
)


def cli_env():
    """CLI 실행용 환경변수. .env의 인증 설정(Vertex/API키)을 주입한다."""
    env = dict(os.environ)
    envfile = os.path.join(BASE, ".env")
    if os.path.exists(envfile):
        with open(envfile, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k in PASS_ENV and v and "여기에" not in v:
                        env[k] = v
    return env


GENESIS  = os.path.join(ROOT, "docs", "constitution", "genesis.md")
MEMORY   = os.path.join(BASE, "memory")   # 임원별 기억 파일


def memory_path(role):
    return os.path.join(MEMORY, f"{role.lower()}.md")


def load_genesis():
    """창립 문서 — 모든 임원이 매 회의 전에 읽는다.
    (CLI는 매번 새 프로세스라 기억이 없다 → 정체성을 주입하지 않으면 매번 남남이 됨)"""
    if os.path.exists(GENESIS):
        with open(GENESIS, encoding="utf-8") as f:
            return f.read()
    return ""


# 기억은 무한히 커지면 회의마다 토큰이 회의수^2로 늘어난다.
# 최근 N건만 주입하고, 넘치면 오래된 항목부터 파일에서도 잘라낸다.
MEMORY_KEEP  = 8      # 주입·보관할 최근 회의 수
MEMORY_MAXCH = 6000   # 주입 상한(자)


def load_memory(role):
    """임원 개인 기억 — 최근 것 위주로, 상한 안에서만 읽는다."""
    p = memory_path(role)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        text = f.read()
    # "## 회의 #NNN" 단위로 쪼개 최근 것만 사용
    parts = re.split(r"(?m)^(?=## 회의 #)", text)
    head, entries = parts[0], parts[1:]
    entries = entries[-MEMORY_KEEP:]
    out = "".join(entries)
    if len(out) > MEMORY_MAXCH:          # 그래도 크면 뒤(최신)에서부터 자름
        out = out[-MEMORY_MAXCH:]
        out = out[out.find("## 회의 #"):] or out
    return out.strip()


def prune_memory(role):
    """파일 자체도 최근 MEMORY_KEEP건만 남겨 무한 증식을 막는다."""
    p = memory_path(role)
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(?m)^(?=## 회의 #)", text)
    head, entries = parts[0], parts[1:]
    if len(entries) <= MEMORY_KEEP:
        return
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + "".join(entries[-MEMORY_KEEP:]))


def append_memory(role, entry):
    """회의 후 자기 발언 요지를 기억에 남긴다."""
    os.makedirs(MEMORY, exist_ok=True)
    p = memory_path(role)
    head = "" if os.path.exists(p) else f"# {role} 기억\n\n_회의 때마다 자동 누적. 다음 회의에서 이 파일을 읽고 들어온다._\n"
    with open(p, "a", encoding="utf-8") as f:
        if head:
            f.write(head)
        f.write(entry)


def build_context(ex):
    """임원에게 주입할 정체성 컨텍스트(창립문서 + 개인기억)."""
    parts = [ex["charter"]]
    g = load_genesis()
    if g:
        parts.append("--- 창립 문서 (Project Freedom 창세기) ---\n" + g)
    m = load_memory(ex["role"])
    if m:
        parts.append("--- 당신의 과거 기억 (이전 회의에서 당신이 한 말) ---\n" + m)
    return "\n\n".join(parts)


def boardroom_dir():
    """회의 전용 빈 작업 디렉토리.
    CLI(특히 gemini)가 작업 폴더 파일을 컨텍스트로 자동 로딩해 안건 대신 코드 분석을
    내놓는 문제가 있어, 읽을 게 없는 폴더에서 실행시킨다."""
    d = os.path.join(BASE, ".boardroom")
    os.makedirs(d, exist_ok=True)
    return d


def run_cli(ex, prompt):
    """임원 CLI 호출. (성공여부, 텍스트) 반환."""
    try:
        if ex["stdin"]:
            p = subprocess.run(ex["cmd"], input=prompt, shell=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=TIMEOUT, env=cli_env(), cwd=boardroom_dir())
        else:
            p = subprocess.run(f'{ex["cmd"]} "{prompt}"', shell=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=TIMEOUT, env=cli_env(), cwd=boardroom_dir())
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
        prompt = (f"{build_context(ex)}\n\n{RULES}\n\n"
                  f"--- 안건 ---\n{agenda}\n\n"
                  f"{ex['role']}로서 당신의 입장을 말하라. 반드시 한국어로.")
        ok, out = run_cli(ex, prompt)
        if ok:
            present.append(ex["role"])
            minutes.append((ex["role"], ex["name"], out))
            # 자기 발언을 기억에 누적 — 전문이 아니라 요지만(토큰 절약).
            # 회의록 원문은 docs/meetings/에 그대로 남으므로 손실이 아니다.
            gist = out if len(out) <= 600 else out[:600].rsplit("\n", 1)[0] + " …(요약)"
            append_memory(ex["role"],
                          f"\n## 회의 #{no:03d} ({today})\n**안건**: {agenda[:100]}\n\n{gist}\n")
            prune_memory(ex["role"])
            print(f"  → 발언 확보 ({len(out)}자)\n")
        else:
            minutes.append((ex["role"], ex["name"], f"_(불참: {out})_"))
            print(f"  → 불참: {out}\n")

    # CTO가 회의를 Task로 환원 (CTO 불참이면 생략)
    tasks_md, new_tasks = "_(Task 도출 생략 — CTO 불참)_", []
    if "CTO" in present:
        joined = "\n\n".join(f"[{r} {n}]\n{t}" for r, n, t in minutes)
        ok, out = run_cli(EXECUTIVES[0],
            "당신은 CTO다. 이 회의를 구체적인 다음 행동으로 바꿔라. "
            "파일을 읽거나 도구를 실행하지 말고, 아래 내용만 보고 정리하라.\n\n"
            f"--- 안건 ---\n{agenda}\n\n--- 회의록 ---\n{joined}\n\n"
            "번호 매긴 목록만 출력하라(최대 5개). 각 줄 형식: 할 일 + ' — owner: ' + "
            "CEO/CTO/CMO/CSO 중 하나. 반드시 한국어로. 다른 텍스트 금지.")
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
