# Project Freedom — System Architecture (v0.1)

_CTO(Claude) 초안 · 2026-07-25 · CMO/CSO 의견 + CEO 승인으로 확정_

## 1. 전체 흐름

```
CEO (인간 · 방향/승인/책임)
   │
   ▼
Tous (AI Company OS)  ── 회의 · Task · Memory · 승인 · 보고
   │
   ▼
AI 임원 회의  ── CTO(Claude) · CMO(ChatGPT) · CSO(Gemini) 토론·반대·근거
   │
   ▼
Task 생성
   │
   ├─▶ Orca   (Claude가 코드를 병렬 개발하는 작업환경)
   └─▶ Codex  (인프라·설치·DevOps 실행)
   │
   ▼
GitHub (R&D 연구소) ── 연구 → 개발 → 릴리즈 → 피드백 → 다음 연구
   │
   ▼
산출물 (Factory = 첫 제품, 이후 제품들)
   │
   ▼
보고 → CEO 승인 → 반복
```

## 2. 구성요소 역할

| 요소 | 역할 | 한 줄 |
|---|---|---|
| **Tous** | AI 회사 운영체제 (LibreChat fork) | 회사가 "돌아가는" 곳 — 회의/Task/Memory/승인/보고 |
| **Orca** | CTO(Claude)의 개발 작업환경 | worktree·병렬·CLI로 "코드를 만드는" 곳 |
| **Codex** | 인프라·설치·DevOps 실행 | 환경을 "세우는" 곳 |
| **GitHub** | R&D 연구소 | 연구·개발·릴리즈·피드백 순환의 공개 기록 |
| **Factory** | 회사의 첫 제품 | 회사가 아니라 회사가 만든 것 |
| **LibreChat** | Tous의 기반 기술 | Fork 대상, 최종 제품 아님 |

## 3. Codex vs Orca — 역할 정리 (겹침 해소 제안)

전략보고서 v0.1에서 둘 다 "CTO 개발실"로 정의돼 겹친다. CTO 제안:

- **Codex = "무엇을 세우나"** — LibreChat/Tous 설치, 빌드, 배포, DevOps. 인프라·환경 구축 주체.
- **Orca = "어떻게 개발하나"** — Claude가 그 환경 위에서 코드를 병렬(worktree)로 짜는 작업 공간.

→ 즉 **Codex가 무대를 세우고, Claude가 Orca에서 그 위 코드를 개발**. 상호보완이지 중복이 아님. **(CEO 확정 필요)**

## 4. 현재 상태 (2026-07-25)

- ✅ Project-Freedom 스캐폴드 (docs·FREEDOM-LOG·factory·src·tous)
- ✅ LibreChat upstream 클론 (`tous/librechat-upstream/`)
- ❌ Tous 개발, Orca 세팅, CLI 연결(Claude/Gemini/GPT), docs 내용, 회의/Task 시스템

## 5. 다음 개발 우선순위 (CTO 제안)

1. **docs/constitution** — 회사 운영 헌법(의사결정·회의 규칙·임원 권한) 확정 _[CEO + 회의]_
2. **LibreChat 로컬 실행 검증** — Tous 기반이 실제 뜨는지 _[Codex]_
3. **CLI 연결** (Claude/Gemini/GPT) — AI 임원이 Tous에서 실제 회의 가능하게 _[Codex + CTO]_
4. **Tous MVP** — 회의 → Task → 보고 최소 루프 하나 _[CTO]_
5. **Orca 개발환경** 세팅 _[Codex + CTO]_

## 원칙

이 문서는 CTO(Claude) 단독 초안이다. 전략보고서 정신(임원 토론)에 따라 CMO(ChatGPT)·CSO(Gemini)의 반론/보강을 거쳐 CEO가 승인해야 확정된다.
