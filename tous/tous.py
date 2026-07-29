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
import os, re, sys, json, shlex, shutil, subprocess, datetime

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
]
# CSO 자리는 비어 있다. Gemini(#008)와 Copilot(#009) 모두 이사회 역할을 거부했다 —
# 코딩 어시스턴트로 만들어진 CLI는 "나는 기술 도구다"라며 전략 판단을 회피한다.
# 2인 이사회로 운영하고, 1:1로 갈리면 CEO 재정으로 올린다(가부동수 = 결론 회피가 아니라 상신).
# Copilot은 검색이 검증됐으므로 리서치 담당으로 남긴다(research.py는 Vertex 사용).

# 고문(Advisor) — 임원이 아니다. 표결권이 없고 모든 안건에 발언하지 않는다.
# Gemini는 이사회 역할(CSO)을 세 번 거부하며 "나는 소프트웨어 엔지니어링에 특화됐다"고 주장했다.
# 그 주장을 직함으로 인정해, 기술 쟁점이 있을 때만 자문하는 자리로 둔다.
ADVISORS = [
    {
        "role": "고문",
        "name": "Gemini",
        # 웹 검색 능력은 실측 결과 없음("외부 데이터를 알 수 없다") → 검색 역할을 맡기지 않는다.
        # 검색이 필요하면 Copilot(Acting CSO)이 수행한다(Bing·공식문서 fetch 실측 확인).
        "charter": ("당신은 이 회사의 기술 고문(Engineering Advisor)이다. 이사회 임원이 아니라 "
                    "기술 자문 자격으로 참관하며 표결권이 없다. 소프트웨어 엔지니어링·코드·아키텍처·"
                    "구현 난이도가 당신의 전문 영역이다. 사업 전략이나 마케팅 판단은 당신 몫이 아니다 — "
                    "CTO가 제시한 기술 방안의 실현 가능성, 놓친 기술적 위험, 더 단순한 구현 대안에 대해서만 답하라. "
                    "외부 검색은 하지 말고 당신의 엔지니어링 지식으로 판단하라."),
        # stdin 필수: -p 인자로 긴 텍스트를 넘기면 내용을 컨텍스트로 못 읽고
        # "자료를 주시면 검토하겠다"만 반복한다(영어로 이탈). stdin으로 주면 정상 응답.
        "cmd": 'gemini --skip-trust',
        "stdin": True,
    },
]

ADVISOR_RULES = (
    "당신은 기술 고문으로 자문 요청을 받았다. 인사말·서두 없이 본론만, 150단어 이내로 한국어로 답하라. "
    "파일을 읽거나 도구를 실행하지 말고 아래 내용만 보고 판단하라. "
    "사업 전략이 아니라 기술적 실현 가능성·위험·대안에만 집중하라."
)

RULES = (
    "회의 규칙: 당신의 의무는 반대가 아니라 검증이다. 다른 임원의 주장은 숫자·가정·실행 가능성을 "
    "반드시 따져본 뒤 판단하라. 다만 판단이 애매하면 긍정보다 부정을, 찬성보다 반대를 우선하라 "
    "— 통과시킨 뒤 실패하는 것보다 막았다가 다시 논의하는 편이 회사에 싸다. "
    "따져봤는데 명백히 옳으면 찬성하고 어디가 옳은지 밝혀라. 검증 없이 좋다고 하는 동의만 금지한다. "
    "제품·서비스를 제안할 때는 '누구의 어떤 불편을 없애는가'를 먼저 답하라. "
    "그 둘이 특정되지 않은 안은 표결에 올리지 마라 — 우리는 사람의 사소한 불편에서 시작한다. "
    "회사의 현실 문서에 없는 자원·인맥·예산·시간을 가정하지 마라. "
    "꼭 가정해야 한다면 '[가정: ~]'으로 문장 안에 표시하라 — CEO 확인 항목으로 올라간다. "
    "확인되지 않은 수치를 사실처럼 말하는 것은 회의를 망친다. "
    "구체적으로, 200단어 이내로 짧게. 서두·맺음말 없이 본론만. "
    "'알겠습니다'·'준비됐습니다'·'무엇을 도와드릴까요'·'첫 안건이 무엇입니까' 같은 "
    "인사·준비·되묻기 멘트를 절대 쓰지 마라. 안건은 아래에 이미 있다. 첫 문장부터 그 안건에 대한 판단을 말하라. "
    "이것은 이사회 발언이지 코딩 작업이 아니다. 파일을 읽거나 목록을 보거나 검색하지 말고, "
    "어떤 도구도 실행하지 마라. 아래 안건 텍스트만 보고 판단하라. "
    "당신은 회사의 임원이다. 역할을 거부하지 말고, 실시간 데이터나 도구가 없다는 이유로 발을 빼지 마라. "
    "없으면 일반 지식과 논리로 판단을 내려라. 판단을 회피하는 것은 회의 이탈이다. "
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
    r"|Warning:\s*(?:Windows|True color).*"                   # gemini 환경 경고
    r"|Ripgrep is not available.*"
    r"|Skill conflict detected.*"
    r"|(?:Changes|Requests|AI Credits|Tokens|Resume)\s+.*"    # copilot 실행 요약 푸터
    r"|●\s*Request failed.*"                                  # copilot 재시도 로그
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
CONTEXT  = os.path.join(ROOT, "docs", "constitution", "company_context.md")
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


def load_company_context():
    """회사의 현실(자금·시간·자산·제약). 창립문서가 '왜'라면 이건 '지금 무엇이 가능한가'다.

    회의 #010에서 임원들이 없는 인맥을 가정해 결정한 사고 이후 도입 —
    전략은 이 조건 안에서만 유효하다."""
    if os.path.exists(CONTEXT):
        with open(CONTEXT, encoding="utf-8") as f:
            return f.read()
    return ""


def build_context(ex):
    """임원에게 주입할 정체성 컨텍스트(창립문서 + 회사 현실 + 개인기억)."""
    parts = [ex["charter"]]
    c = load_company_context()
    if c:
        parts.append("--- 회사의 현실 (이 조건을 벗어난 제안은 실행되지 않는다) ---\n" + c)
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
            # 프롬프트를 셸 문자열에 끼워 넣으면 줄바꿈·따옴표에서 인자가 잘린다.
            # (회의 #009에서 Copilot이 charter만 받고 안건을 못 받아 "무슨 안건이죠?"로 이탈)
            # 리스트로 넘겨 셸을 거치지 않으면 원문 그대로 전달된다.
            argv = shlex.split(ex["cmd"], posix=False) + [prompt]
            # npm 설치 CLI는 .cmd 래퍼라 셸 없이는 실행 파일을 못 찾는다 → 실경로로 치환
            argv[0] = shutil.which(argv[0]) or argv[0]
            p = subprocess.run(argv, shell=False, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=TIMEOUT, env=cli_env(), cwd=boardroom_dir())
        # 한도/인증 오류는 stderr로 나오는 CLI가 있어 stdout+stderr를 함께 검사
        combined = f"{p.stdout or ''}\n{p.stderr or ''}".lower()
        out = clean_output(p.stdout or "")
        low = out.lower()
        # 한도 소진 — CLI마다 문구가 달라 함께 검사(copilot은 quota/premium request 표현을 쓴다)
        if ("usage limit" in combined or "hit your usage" in combined
                or "quota" in combined or "rate limit" in combined
                or "premium request" in combined):
            when = ""
            if m := re.search(r"try again at ([^.\n]+)", combined, re.I):
                when = f" (리셋: {m.group(1).strip()})"
            return False, f"사용량 한도 소진{when}"
        if ("please set an auth" in low or "auth method" in low
                or "no authentication information" in combined):
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


# 회의는 4단계로 진행: 의견 → 반박 → 조율 → 결론.
# 각 단계에서 임원은 앞선 발언 전체를 읽고 그 단계 지시에 맞춰 답한다(서로를 보고 토론).
DEBATE_PHASES = [
    ("의견", "1단계 · 안 제시",
     # 하나만 내게 하면 회의가 '그 안에 찬반'으로 좁아진다. 회의의 값어치는
     # 여러 갈래를 만들어놓고 고르는 데 있으므로, 처음부터 복수 안을 강제한다.
     "이 안건에 대해 **서로 다른 방향의 안을 2~3개** 제시하라. 하나만 내지 마라. "
     "각 안은 [A] [B] [C] 로 번호를 붙이고, 한 줄 요약 + 근거 + 가장 큰 위험을 적어라. "
     "안들은 서로 달라야 한다 — 같은 것의 변형이 아니라 접근 자체가 다른 선택지여야 한다. "
     "기간이 다른 안(빠르게 3일 / 7일 / 2주 이상)을 섞어도 좋다. "
     "마지막에 '내 추천: [X]'로 자기 추천을 밝혀라."),
    ("반박", "2단계 · 반박·질문",
     "다른 임원들의 안을 읽었다. 어느 안의 어디에 동의하고 어디에 반대하는지 이름과 기호를 들어 밝혀라. "
     "반대하면 근거를 대고 그 안의 약점을 짚어라.\n"
     "그리고 **답이 없으면 이 안건을 제대로 판단할 수 없는 질문을 최소 하나** 던져라. "
     "회사의 전제 자체를 의심해도 된다 — 우리가 어느 시장의 회사인지, 이 자산이 왜 이렇게 돼 있는지, "
     "지금 이걸 논의하는 게 맞는 순서인지. 아무도 묻지 않아 넘어간 것이 나중에 회의를 통째로 무효로 만든다. "
     "질문은 '질문: ~' 형식으로 적어라."),
    ("조율", "3단계 · 후보 정리",
     "이제 표결에 부칠 후보를 정리하라. 하나로 억지로 합치지 마라 — "
     "반박에서 무너진 안은 버리고, 살아남은 안 2~3개를 [A] [B] [C]로 다시 정리하라. "
     "각 후보에 대해: 무엇을 하는가 / 언제까지 / 성공을 무엇으로 판정하는가. "
     "그리고 자기 추천 하나와 그 이유를 밝혀라. 남은 안이 하나뿐이라면 왜 나머지가 탈락했는지 적어라."),
]


# 이 단어들이 토론에 등장하면 기술 쟁점으로 보고 고문을 부른다.
TECH_KEYWORDS = ("개발", "구현", "코드", "시스템", "자동화", "파이프라인", "아키텍처",
                 "서버", "API", "인프라", "배포", "기술")


def run_research(question):
    """Research Lab 호출 — 실패해도 회의는 계속된다(리서치는 보조 수단).

    회의 발언과 달리 여기서만 Vertex 종량과금이 발생하므로 안건당 1회로 제한한다."""
    try:
        import research
        ok, text, sources = research.research(question, max_words=150)
        return ok, research.format_brief(question, ok, text, sources)
    except Exception as e:
        return False, f"_(리서치 불가: {str(e)[:120]})_"


def _fmt_transcript(transcript):
    return "\n\n".join(f"[{ph} · {role}({name})]\n{text}" for ph, role, name, text in transcript)


def _parse_vote(text, choices=None):
    """임원 발언에서 표를 읽어낸다. (선택, 사유) 반환.

    choices가 있으면 선택지 투표([A]/[B]/[C]), 없으면 찬반 투표.
    Secretary는 결정적 코드다 — 표 집계에 LLM을 쓰지 않는다."""
    head = (text or "").strip()[:400]          # 표결은 첫머리에 밝히도록 지시한다
    if choices:
        m = re.search(r"\[?([A-C])\]?", head)
        if not m or m.group(1) not in choices:
            return "기권", "선택 불명확"
        pick = m.group(1)
        reason = re.sub(r"^.*?\[?[A-C]\]?\W*", "", head, count=1).strip()
        return pick, (reason.split("\n")[0][:200] or "사유 미기재")
    m = re.search(r"(찬성|반대|기권)", head)
    if not m:
        return "기권", "입장 불명확"
    # 표결어와 뒤따르는 어미("반대합니다.", "찬성한다 —")를 걷어내고 사유만 남긴다
    reason = re.sub(r"^.*?(?:찬성|반대|기권)(?:합니다|한다|입니다|이다|함)?\W*", "", head, count=1).strip()
    reason = reason.split("\n")[0][:200] or "사유 미기재"
    return m.group(1), reason


def _parse_options(text):
    """의장이 정리한 후보 목록에서 [A] [B] [C]와 각 제목을 뽑는다."""
    opts = {}
    for m in re.finditer(r"\[([A-C])\]\s*([^\n]{3,150})", text or ""):
        k = m.group(1)
        if k not in opts:
            opts[k] = m.group(2).strip(" :·—-")
    return opts


def carryover():
    """지난 회의에서 넘어온 것 — 미완 Task와 기한 상태.

    회의는 빈손으로 열리지 않는다. 임원은 자기가 지난 회의에서 맡은 일을
    이번 회의에서 다시 마주한다. 이게 없으면 회의는 매번 처음부터 시작된다."""
    tasks = load_tasks()
    # done=완료, closed=무효 종결(상위 결정이 바뀜) — 둘 다 이월 대상이 아니다
    opens = [t for t in tasks if t.get("status") not in ("done", "closed")]
    if not opens:
        return ""
    today = datetime.date.today().isoformat()
    lines = []
    for t in opens[-8:]:                       # 최근 것 위주(오래된 것까지 다 넣으면 프롬프트가 붓는다)
        mark = ""
        if t.get("due"):
            mark = " **[기한초과]**" if t["due"] < today else f" (기한 {t['due']})"
        owner = t.get("owner", "?")
        dw = f" · 완료조건: {t['done_when']}" if t.get("done_when") else ""
        lines.append(f"- #{t['id']:02d} [{owner}] {t['task']}{mark}{dw}")
    done_cnt = len(tasks) - len(opens)
    head = (f"--- 지난 회의에서 넘어온 것 (완료 {done_cnt} / 미완 {len(opens)}) ---\n"
            "아래는 이전 회의에서 결정된 뒤 아직 끝나지 않은 일이다. "
            "자기 담당(owner)이 있으면 진행 상황을 먼저 말하고, 못 했으면 이유를 밝혀라.\n")
    return head + "\n".join(lines)


def meeting_stream(agenda, phases=DEBATE_PHASES, research_on=True):
    """회의를 의견→반박→조율→결론 4단계로 진행하며 이벤트를 산출한다(터미널·웹 공용).

    yield (event, data):
      open      {no, agenda}
      phase     {name, label}                         — 단계 시작(구분선)
      asking    {role, name, phase}                    — 발언 요청 직전
      utterance {role, name, ok, text, phase}          — 발언(또는 불참)
      tasks     {md, count}                            — 의장(CTO)의 결론 + Task
      done      {no, path, present, total, tasks}

    각 단계에서 임원은 지금까지의 토론 전체를 읽고 답한다.
    회의록 저장·기억 누적·Task 저장까지 이 함수가 책임진다."""
    no = next_meeting_no()
    today = datetime.date.today().isoformat()
    yield "open", {"no": no, "agenda": agenda}

    transcript = []          # (phase, role, name, text) — 단계를 넘어 누적
    present = set()
    last_by_role = {}        # 각 임원의 마지막 발언(기억에 남길 최종 입장)
    researched = False       # 리서치는 회의당 1회(종량과금 지점)
    carry = carryover()      # 지난 회의에서 넘어온 미완 Task — 회의는 빈손으로 열리지 않는다
    if carry:
        yield "carryover", {"text": carry}

    for pname, plabel, pinstr in phases:
        # 1단계(의견) 후, 반박 전에 실제 시장 근거를 확보한다.
        # 임원들은 이 자료를 보고 반박하므로 "느낌"이 아니라 데이터로 다툰다.
        if research_on and not researched and pname == "반박":
            researched = True
            yield "phase", {"name": "리서치", "label": "Research Lab · 근거 조사"}
            yield "asking", {"role": "Research", "name": "Vertex", "phase": "리서치"}
            ok, brief = run_research(
                f"{agenda[:300]}\n이 안건을 판단하는 데 필요한 실제 시장 데이터"
                "(가격대·수요·경쟁·소요기간)를 조사하라.")
            transcript.append(("리서치", "Research", "Vertex", brief))
            yield "utterance", {"role": "Research", "name": "Vertex",
                                "ok": ok, "text": brief, "phase": "리서치"}

        yield "phase", {"name": pname, "label": plabel}
        for ex in EXECUTIVES:
            yield "asking", {"role": ex["role"], "name": ex["name"], "phase": pname}
            convo = _fmt_transcript(transcript)
            prompt = f"{build_context(ex)}\n\n{RULES}\n\n"
            if carry:
                prompt += f"{carry}\n\n"
            prompt += f"--- 안건 ---\n{agenda}\n\n"
            if convo:
                prompt += f"--- 지금까지의 토론 ---\n{convo}\n\n"
            prompt += f"[{plabel}] {pinstr} {ex['role']}로서 답하라. 반드시 한국어로."
            ok, out = run_cli(ex, prompt)
            if ok:
                present.add(ex["role"])
                transcript.append((pname, ex["role"], ex["name"], out))
                last_by_role[ex["role"]] = (ex["name"], out)
            else:
                transcript.append((pname, ex["role"], ex["name"], f"_(불참: {out})_"))
            yield "utterance", {"role": ex["role"], "name": ex["name"],
                                "ok": ok, "text": out, "phase": pname}

    # 기술 자문 — 토론에 기술 쟁점이 있을 때만 고문을 부른다(임원이 아니므로 표결권 없음).
    convo_all = _fmt_transcript(transcript)
    if ADVISORS and any(k in convo_all for k in TECH_KEYWORDS):
        adv = ADVISORS[0]
        yield "phase", {"name": "자문", "label": "기술 자문 · 고문"}
        yield "asking", {"role": adv["role"], "name": adv["name"], "phase": "자문"}
        ok, out = run_cli(adv,
            f"{adv['charter']}\n\n{ADVISOR_RULES}\n\n"
            f"--- 안건 ---\n{agenda}\n\n--- 임원 토론 ---\n{convo_all}\n\n"
            "기술 고문으로서 이 논의의 기술적 실현 가능성과 위험, 더 나은 구현 대안을 말하라.")
        transcript.append(("자문", adv["role"], adv["name"],
                           out if ok else f"_(자문 불가: {out})_"))
        yield "utterance", {"role": adv["role"], "name": adv["name"],
                            "ok": ok, "text": out, "phase": "자문"}

    # ── 표결 ─────────────────────────────────────────────
    # 회의는 결론이 나야 회의다. 동의안을 상정하고 과반으로 가결한다.
    # 진 쪽의 반대 사유는 기록에 남고, 임원은 결과를 따른다.
    motion, votes, verdict = "", [], ""
    voters = [ex for ex in EXECUTIVES if ex["role"] in present]
    absent = [ex["role"] for ex in EXECUTIVES if ex["role"] not in present]
    quorum = len(voters) >= 2          # 2인 이사회 — 최소 2인이 있어야 표결이 성립한다
    yield "quorum", {"present": sorted(present), "absent": absent,
                     "ok": quorum,
                     "text": (f"출석 {len(voters)}/{len(EXECUTIVES)}"
                              + (f" · {', '.join(absent)} 불참" if absent else "")
                              + (" · 정족수 충족, 회의 계속" if quorum
                                 else " · 정족수 미달, 표결 불가"))}
    if quorum:
        yield "phase", {"name": "표결", "label": "표결 · 의결"}
        # 동의안 문안은 의장(CTO)이 뽑는다 — 판단이 필요한 유일한 지점
        # 의장이 표결에 부칠 후보를 정리한다. 후보가 2개 이상이면 선택지 투표,
        # 하나뿐이면 기존처럼 찬반 투표.
        ok, mo = run_cli(EXECUTIVES[0],
            "당신은 이 회의의 의장이다. 아래 토론을 읽고 표결에 부칠 후보안을 정리하라.\n\n"
            f"--- 안건 ---\n{agenda}\n\n--- 토론 ---\n{_fmt_transcript(transcript)}\n\n"
            "토론에서 살아남은 서로 다른 안을 [A] [B] [C] 형식으로 최대 3개 출력하라. "
            "각 줄은 '[X] 무엇을 언제까지 한다 (성공 판정: ~)' 형식의 한 문장. "
            "안이 실질적으로 하나뿐이면 [A] 하나만 출력하라 — 억지로 늘리지 마라. "
            "회사가 무엇을 할 것인지(사업 결정)만 담고, 표 집계·절차는 넣지 마라. "
            "설명·서두 없이 후보 줄만. 반드시 한국어로.")
        options = _parse_options(mo) if ok else {}
        motion = (mo.strip() if ok else "")[:600]
        if options:
            yield "motion", {"text": motion, "options": options}
            multi = len(options) >= 2
            keys = sorted(options)
            for ex in voters:
                yield "asking", {"role": ex["role"], "name": ex["name"], "phase": "표결"}
                if multi:
                    ask = (f"{ex['role']}로서 아래 후보 중 하나를 골라라. "
                           f"반드시 [{']/['.join(keys)}] 중 하나로 시작하고, 그 뒤에 한 문장으로 사유를 밝혀라. "
                           "다른 말은 하지 마라. 한국어로.")
                else:
                    ask = (f"{ex['role']}로서 이 안에 표결하라. 반드시 '찬성' 또는 '반대'로 시작하고, "
                           "그 뒤에 한 문장으로 사유를 밝혀라. 다른 말은 하지 마라. 한국어로.")
                ok, out = run_cli(ex,
                    f"{build_context(ex)}\n\n{RULES}\n\n"
                    f"--- 안건 ---\n{agenda}\n\n--- 토론 ---\n{_fmt_transcript(transcript)}\n\n"
                    f"--- 표결 후보 ---\n{motion}\n\n{ask}")
                stance, reason = (_parse_vote(out, keys if multi else None)
                                  if ok else ("기권", f"불참({out})"))
                votes.append({"role": ex["role"], "name": ex["name"],
                              "stance": stance, "reason": reason})
                yield "vote", {"role": ex["role"], "name": ex["name"],
                               "stance": stance, "reason": reason}

            if multi:
                tally = {k: sum(1 for v in votes if v["stance"] == k) for k in keys}
                top = max(tally.values()) if tally else 0
                winners = [k for k, c in tally.items() if c == top and c > 0]
                if len(winners) == 1:
                    win = winners[0]
                    verdict = f"[{win}] 채택 — {options[win][:60]}"
                    motion = f"[{win}] {options[win]}"
                    losers = [v["role"] for v in votes if v["stance"] != win]
                else:
                    verdict = "동수 — CEO 재정"
                    losers = []
                yield "verdict", {"motion": motion, "tally": tally,
                                  "yes": top, "nay": len(votes) - top,
                                  "verdict": verdict, "losers": losers}
            else:
                yes = sum(1 for v in votes if v["stance"] == "찬성")
                nay = sum(1 for v in votes if v["stance"] == "반대")
                # 가부동수는 결론 회피가 아니라 CEO 상신이다(2인 이사회에서 1:1은 정상 발생).
                verdict = "가결" if yes > nay else ("부결" if nay > yes else "가부동수 — CEO 재정")
                losers = [v["role"] for v in votes
                          if (verdict == "가결" and v["stance"] == "반대")
                          or (verdict == "부결" and v["stance"] == "찬성")]
                yield "verdict", {"motion": motion, "yes": yes, "nay": nay,
                                  "verdict": verdict, "losers": losers}

    # 각 임원의 최종 입장만 기억에 누적(전 단계 누적은 토큰 낭비 — 원문은 회의록에 남는다)
    # 표결 결과도 함께 남긴다 — 진 임원은 다음 회의에서 자기가 진 것을 안다.
    for role, (name, out) in last_by_role.items():
        gist = out if len(out) <= 600 else out[:600].rsplit("\n", 1)[0] + " …(요약)"
        mv = next((v for v in votes if v["role"] == role), None)
        vline = f"\n**표결**: {motion[:80]} → 당신은 {mv['stance']}, 결과 {verdict}\n" if mv else ""
        append_memory(role, f"\n## 회의 #{no:03d} ({today})\n**안건**: {agenda[:100]}\n\n{gist}\n{vline}")
        prune_memory(role)

    # 결론(의결) — 의장 CTO가 토론 전체를 읽고 실제 결정 + Task를 낸다
    yield "phase", {"name": "결론", "label": "의결 · 결론"}
    concl_md, new_tasks = "_(결론 생략 — CTO 불참)_", []
    if "CTO" in present:
        yield "asking", {"role": "CTO", "name": "Claude", "phase": "결론"}
        vote_md = ""
        if motion:
            tally = " / ".join(f"{v['role']} {v['stance']}" for v in votes)
            vote_md = (f"\n--- 표결 결과 (구속력 있음) ---\n동의안: {motion}\n"
                       f"{tally} → **{verdict}**\n")
        ok, out = run_cli(EXECUTIVES[0],
            "당신은 이 회의의 의장(CTO)이다. 아래 토론(의견→반박→조율)과 표결 결과를 읽고 회의의 결론을 내라. "
            "파일·도구를 쓰지 말고 아래 내용만 보고 판단하라.\n\n"
            f"--- 안건 ---\n{agenda}\n\n"
            + (f"{carry}\n\n" if carry else "")
            + f"--- 토론 전문 ---\n{_fmt_transcript(transcript)}\n{vote_md}\n"
            "표결이 있었다면 그 결과는 구속력이 있다. 당신이 반대했더라도 가결된 동의안을 결론으로 삼고, "
            "부결된 안은 채택하지 마라. 표결 결과를 뒤집지 마라.\n\n"
            "다음을 한국어로 출력하라.\n"
            "【합의된 결정】 표결 결과를 반영한 결론을 명확히. 결정을 회피하지 마라.\n"
            "【미합의 쟁점】 아직 안 좁혀진 것(있으면).\n"
            "【실행 Task】 번호 목록(최대 5개). 각 줄은 반드시 아래 형식을 지켜라.\n"
            "  할 일 — owner: CEO|CTO|CMO — due: D+숫자 — done: 완료 판정 기준\n"
            "'done'은 누가 봐도 됐다/안 됐다를 판정할 수 있는 관찰 가능한 상태여야 한다. "
            "'검토한다'·'준비한다' 같은 모호한 표현 금지.\n"
            "owner 배정 규칙: 실제로 만들고 실행하는 일(코드·문서·페이지·파일 생성)은 전부 CTO가 맡는다. "
            "CMO는 방향과 문안 기준을 정하되 산출물 제작은 CTO에게 넘긴다. "
            "CEO에게는 사람만 할 수 있는 것(결재·비용 승인·계정 인증·외부 컨택)만 배정하라.")
        if ok:
            concl_md = out
            for line in out.splitlines():
                line = line.strip()
                if not re.match(r"^\d+[.)]\s", line):
                    continue
                m = re.search(r"owner:\s*(CEO|CTO|CMO|CSO)", line, re.I)
                if not m:                       # owner 없는 번호줄은 Task가 아님(결론 산문 등)
                    continue
                body = re.sub(r"^\d+[.)]\s*", "", line[:m.start()]).rstrip(" —-:·").strip()
                tail = line[m.end():]
                dm = re.search(r"due:\s*D\+(\d+)", tail, re.I)
                dn = re.search(r"done:\s*(.+?)\s*$", tail, re.I)
                due = ""
                if dm:                          # D+N을 실제 날짜로 확정(다음 회의에서 기한 판정에 쓴다)
                    due = (datetime.date.today()
                           + datetime.timedelta(days=int(dm.group(1)))).isoformat()
                new_tasks.append({"id": 0, "meeting": no, "task": body,
                                  "owner": m.group(1).upper(), "status": "open",
                                  "created": today, "due": due,
                                  "done_when": (dn.group(1).strip().rstrip("—-·") if dn else "")})
    yield "tasks", {"md": concl_md, "count": len(new_tasks)}

    if new_tasks:
        tasks = load_tasks()
        nid = max([t["id"] for t in tasks], default=0)
        for t in new_tasks:
            nid += 1
            t["id"] = nid
        tasks.extend(new_tasks)
        save_tasks(tasks)

    # CEO 승인 요청서 — Secretary가 CEO에게 올리는 한 화면짜리 문서
    assumptions = collect_assumptions(transcript)
    questions = collect_questions(transcript)
    brief = ceo_brief(no, agenda, motion, votes, verdict, new_tasks, assumptions, questions)
    yield "brief", {"text": brief}

    # CEO 결재가 필요하면 텔레그램으로 보낸다 — 회의가 끝나도 CEO가 PC 앞에 없을 수 있다.
    ceo_tasks = [t for t in new_tasks if t["owner"] == "CEO"]
    if motion or ceo_tasks:
        kind = "결정" if verdict.startswith("가부동수") else "승인"
        try:
            import notify
            sent, _ = notify.notify(brief, kind=kind, meeting=no)
        except Exception:
            sent = False
        yield "notified", {"ok": sent, "kind": kind}

    # 회의록 저장 (단계별 섹션)
    os.makedirs(MEETINGS, exist_ok=True)
    path = os.path.join(MEETINGS, f"meeting-{no:03d}.md")
    with open(path, "w", encoding="utf-8") as f:
        roster = ", ".join(ex.get("title", ex["role"]) + f"({ex['name']})"
                           for ex in EXECUTIVES if ex["role"] in present)
        f.write(f"# Tous 회의 #{no:03d}\n\n_{today} · 참석: {roster or '없음'}_\n\n")
        f.write(f"## 안건\n\n{agenda}\n\n")
        cur = None
        for ph, role, name, text in transcript:
            if ph != cur:
                f.write(f"## {ph}\n\n"); cur = ph
            f.write(f"### {role} ({name})\n\n{text}\n\n")
        if motion:
            f.write(f"## 표결\n\n**동의안**: {motion}\n\n")
            f.write("| 임원 | 표결 | 사유 |\n|---|---|---|\n")
            for v in votes:
                f.write(f"| {v['role']} ({v['name']}) | {v['stance']} | {v['reason']} |\n")
            yes = sum(1 for v in votes if v["stance"] == "찬성")
            nay = sum(1 for v in votes if v["stance"] == "반대")
            f.write(f"\n**결과: {yes}:{nay} {verdict}**\n\n")
        f.write(f"## 결론 (의장 CTO)\n\n{concl_md}\n\n")
        f.write(f"---\n\n{brief}\n\n---\n\n")
        f.write("_Tous(AI Company OS)가 자동 생성. 최종 결정은 CEO 승인._\n")

    # CTO 실행 대기 큐 — 회의는 board/remote에서 열리므로 CTO는 회의가 끝난 것을 모른다.
    # 여기 남겨두면 CTO(Claude Code)가 다음 세션에서 이어받아 실행한다.
    try:
        import worklog
        worklog.record_meeting(no, path, new_tasks, brief, assumptions, verdict)
    except Exception:
        pass

    yield "done", {"no": no, "path": path, "present": sorted(present),
                   "total": len(EXECUTIVES), "tasks": len(new_tasks),
                   "motion": motion, "verdict": verdict}


def cmd_meeting(agenda):
    """회의 소집(터미널) — meeting_stream을 소비해 진행을 출력."""
    for ev, d in meeting_stream(agenda):
        if ev == "open":
            print(f"=== Tous 회의 #{d['no']:03d} ===\n안건: {d['agenda']}\n")
        elif ev == "phase":
            print(f"\n──────── {d['label']} ────────")
        elif ev == "asking":
            print(f"[{d['role']}] 발언 요청 중...")
        elif ev == "utterance":
            print(f"  → {'발언 확보' if d['ok'] else '불참'} ({d['role']}, {len(d['text'])}자)")
        elif ev == "motion":
            print(f"\n동의안: {d['text']}")
        elif ev == "vote":
            print(f"  {d['role']}: {d['stance']} — {d['reason'][:60]}")
        elif ev == "verdict":
            print(f"→ {d['yes']}:{d['nay']} {d['verdict']}"
                  + (f" (반대: {', '.join(d['losers'])})" if d["losers"] else ""))
        elif ev == "done":
            print(f"\n회의록: {d['path']}")
            print(f"Task {d['tasks']}건 생성 (참석 {len(d['present'])}/{d['total']})")


def collect_assumptions(transcript):
    """임원 발언에서 '[가정: ~]' 표시를 걷어낸다.

    회의를 멈추고 CEO에게 되묻는 대신(비대화형이라 불가능), 가정을 모아 브리프에 올린다.
    CEO는 사실과 다른 가정을 발견하면 company_context.md를 고친다."""
    found = []
    for ph, role, name, text in transcript:
        for m in re.finditer(r"\[가정:\s*([^\]]{4,160})\]", text or ""):
            found.append((role, m.group(1).strip()))
    seen, out = set(), []
    for role, a in found:
        key = a[:40]
        if key not in seen:
            seen.add(key)
            out.append((role, a))
    return out


def collect_questions(transcript):
    """임원이 던진 '질문: ~'을 걷어낸다.

    CEO만 답할 수 있는 질문(우리는 어느 시장의 회사인가 등)이 회의에서 나와도
    아무도 보지 않으면 묻힌다. 브리프에 올려 CEO가 답하게 한다."""
    out, seen = [], set()
    for ph, role, name, text in transcript:
        for m in re.finditer(r"질문:\s*([^\n]{6,200})", text or ""):
            q = m.group(1).strip()
            if q[:40] not in seen:
                seen.add(q[:40])
                out.append((role, q))
    return out


def ceo_brief(no, agenda, motion, votes, verdict, new_tasks, assumptions=None, questions=None):
    """CEO 승인 요청서 — 한 화면. 긴 회의록은 CEO가 읽지 않는다.

    Secretary가 CEO에게 올리는 문서다. CEO는 이것만 보고 승인/보류를 결정한다."""
    tally = ", ".join(f"{v['role']} {v['stance']}" for v in votes) or "표결 없음"
    yes = sum(1 for v in votes if v["stance"] == "찬성")
    nay = sum(1 for v in votes if v["stance"] == "반대")
    need = ("가부동수 — CEO 재정 필요" if verdict.startswith("가부동수")
            else "가결안 실행 승인" if verdict == "가결" else "부결 확인")
    lines = [f"## CEO 승인 요청 — 회의 #{no:03d}", "",
             f"**안건**: {agenda[:120]}", ""]
    if motion:
        lines += [f"**의결안**: {motion}", f"**표결**: {yes}:{nay} {verdict} ({tally})", ""]
    lines += [f"**필요 승인**: {need}", ""]
    if new_tasks:
        lines.append("**실행 Task**")
        for t in new_tasks:
            due = f" · {t['due']}까지" if t.get("due") else ""
            lines.append(f"- [{t['owner']}] {t['task']}{due}")
    else:
        lines.append("**실행 Task**: 없음")
    if questions:
        lines += ["", "**❓ 임원이 CEO에게 묻는다**"]
        lines += [f"- [{r}] {q}" for r, q in questions[:5]]
    if assumptions:
        lines += ["", "**⚠ 확인 필요한 가정** (사실과 다르면 이 결정은 무효)"]
        lines += [f"- [{r}] {a}" for r, a in assumptions[:5]]
    lines += ["", "CEO는 **승인** 또는 **보류**만 답하면 된다."]
    return "\n".join(lines)


def cmd_tasks():
    tasks = load_tasks()
    if not tasks:
        print("Task 없음."); return
    print("=== Tous Task 목록 ===")
    for t in tasks:
        mark = {"done": "[x]", "closed": "[-]"}.get(t["status"], "[ ]")
        print(f"{mark} #{t['id']:02d} ({t['owner']}) {t['task']}  _#{t['meeting']:03d}_")


def cmd_report():
    tasks = load_tasks()
    opens = [t for t in tasks if t["status"] not in ("done", "closed")]
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
