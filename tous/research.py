# -*- coding: utf-8 -*-
"""Research Lab — Vertex AI Grounding으로 실제 웹을 검색해 근거를 가져온다.

회의 임원들은 각자 구독 CLI로 발언한다(무과금). 그러나 CLI들은 실검색이 불가하거나
(Gemini CLI: 도구는 호출되나 결과 0건) 대가가 크다(Copilot: 1회 113k 토큰).
그래서 리서치만 Vertex AI를 직접 호출한다 — 여기서만 종량과금이 발생하므로,
회의 발언이 아니라 "근거가 필요한 순간"에만 부른다.

    python research.py "2026년 AI 컨설팅 시장 단가"
"""
import os, sys, json, urllib.request, urllib.error

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = os.path.join(BASE, "vertex_key.json")
MODEL = "gemini-2.5-flash"     # 실측: 이 모델에서 grounding 정상 작동(2.0-flash는 404)
TIMEOUT = 120


def _config():
    """.env에서 프로젝트/리전을 읽는다(없으면 서비스 계정 키에서)."""
    proj = loc = None
    envfile = os.path.join(BASE, ".env")
    if os.path.exists(envfile):
        with open(envfile, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("GOOGLE_CLOUD_PROJECT="):
                    proj = s.split("=", 1)[1].strip()
                elif s.startswith("GOOGLE_CLOUD_LOCATION="):
                    loc = s.split("=", 1)[1].strip()
    if not proj and os.path.exists(KEY):
        with open(KEY, encoding="utf-8") as f:
            proj = json.load(f).get("project_id")
    return proj, (loc or "us-central1")


def _token():
    import google.auth, google.auth.transport.requests
    creds, _ = google.auth.load_credentials_from_file(
        KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def research(question, max_words=200):
    """웹 검색 기반 조사. (성공여부, 본문, 출처목록) 반환."""
    if not os.path.exists(KEY):
        return False, "vertex_key.json 없음 — Research Lab 사용 불가", []
    proj, loc = _config()
    if not proj:
        return False, "GCP 프로젝트 미설정", []
    try:
        tok = _token()
    except Exception as e:
        return False, f"인증 실패: {str(e)[:150]}", []

    url = (f"https://{loc}-aiplatform.googleapis.com/v1/projects/{proj}"
           f"/locations/{loc}/publishers/google/models/{MODEL}:generateContent")
    prompt = (f"{question}\n\n"
              f"웹에서 검색해 사실에 근거해 한국어로 답하라. {max_words}단어 이내. "
              "추측은 추측이라고 밝히고, 찾지 못한 것은 '자료 없음'이라고 말하라. "
              "인사말·서두 없이 본론만.")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"temperature": 1.0}}   # 공식 문서 권장값
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=TIMEOUT))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", {}).get("message", "")[:200]
        except Exception:
            msg = f"HTTP {e.code}"
        return False, f"호출 실패: {msg}", []
    except Exception as e:
        return False, f"호출 오류: {str(e)[:150]}", []

    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    gm = cand.get("groundingMetadata", {}) or {}
    sources = []
    for ch in gm.get("groundingChunks", []) or []:
        w = ch.get("web") or {}
        if w.get("uri"):
            sources.append({"title": (w.get("title") or "")[:120], "uri": w["uri"]})
    if not text.strip():
        return False, "빈 응답", sources
    return True, text.strip(), sources


def format_brief(question, ok, text, sources):
    """회의에 주입할 리서치 브리프(마크다운)."""
    if not ok:
        return f"_(리서치 실패: {text})_"
    out = [f"**조사 질문**: {question}", "", text]
    if sources:
        out += ["", "**출처**"] + [f"- [{s['title'] or s['uri'][:60]}]({s['uri']})"
                                   for s in sources[:6]]
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    q = " ".join(sys.argv[1:])
    ok, text, src = research(q)
    print(format_brief(q, ok, text, src))
