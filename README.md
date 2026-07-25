# Project Freedom

Project Freedom은 AI에게 회사를 만들 자유를 주면 실제 회사를 만들 수 있는지 실험하는 공개형 회사 설립 프로젝트다.

가장 먼저 읽어야 할 문서:

- [창세기](./docs/constitution/genesis.md) — 이 회사가 시작된 대화
- [Freedom Log](./FREEDOM-LOG/README.md) — 회사 연대기 (역사가 된 사건만)
- [시스템 구조](./docs/architecture/overview.md) — Tous·Orca·Factory·GitHub의 역할

## 기록 체계

| 무엇 | 어디 | 성격 |
|---|---|---|
| 창립 문서 | `docs/constitution/` | 정체성. 모든 임원이 회의 전에 읽는다 |
| 회의록 | `docs/meetings/` | 모든 회의 전문 (Tous가 자동 생성) |
| 연대기 | `FREEDOM-LOG/` | 역사가 된 사건만 (수동 승격) |
| 임원 기억 | `tous/memory/` | 임원별 과거 발언 요지 (자동 누적) |

## Tous 사용법

```bash
python tous/tous.py meeting "안건"   # 회의 소집 → 회의록 + Task
python tous/tous.py report           # CEO 보고
python tous/namecheck.py 후보1 후보2  # 이름 후보 일괄 검증
python tous/remote.py                # 텔레그램 리모컨 (모바일에서 조종)
```

## 초기 구조

```text
Project-Freedom/
  FREEDOM-LOG-001.md
  README.md
  docs/
    constitution/
    meetings/
    architecture/
  tous/
  factory/
  src/
```

## 원칙

- CEO는 방향 제시, 승인, 질문을 맡는다.
- AI 임원들은 동의만 하지 않고 토론하며 근거를 제시한다.
- 회의 결과는 실행 가능한 Task로 바뀐다.
- 결과는 GitHub와 공개 콘텐츠로 증명한다.
