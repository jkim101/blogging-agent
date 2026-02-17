# Blogging Agent System 설계서

**Version:** 2.0
**Date:** 2026-02-13
**Author:** Jihoon
**Status:** Draft

---

## 목차

1. [개요 (Overview)](#1-개요-overview)
2. [파이프라인 아키텍처 (Pipeline Architecture)](#2-파이프라인-아키텍처-pipeline-architecture)
3. [에이전트 상세 설계 (Agent Specifications)](#3-에이전트-상세-설계-agent-specifications)
4. [이중 언어 전략 (Bilingual Strategy)](#4-이중-언어-전략-bilingual-strategy)
5. [Human-in-the-Loop 설계](#5-human-in-the-loop-설계)
6. [기술 스택 (Tech Stack)](#6-기술-스택-tech-stack)
7. [상태 설계 (State Design)](#7-상태-설계-state-design)
8. [피드백 루프 설계 (Feedback Loop)](#8-피드백-루프-설계-feedback-loop)
9. [에러 핸들링 (Error Handling)](#9-에러-핸들링-error-handling)
10. [배포 및 보안 (Deployment & Security)](#10-배포-및-보안-deployment--security)
11. [비용 관리 (Cost Management)](#11-비용-관리-cost-management)
12. [출력 및 발행 (Output & Publishing)](#12-출력-및-발행-output--publishing)
13. [로깅 및 테스트 (Logging & Testing)](#13-로깅-및-테스트-logging--testing)
14. [프로젝트 구조 (Project Structure)](#14-프로젝트-구조-project-structure)
15. [확장 포인트 (Extension Points)](#15-확장-포인트-extension-points)

---

## 1. 개요 (Overview)

### 1.1 목적 (Purpose)

Blogging Agent System은 다양한 소스 콘텐츠(URL, PDF, RSS)를 입력받아 **한글과 영문 두 벌의 고품질 블로그 포스트**를 자동으로 생성하는 개인용 다중 에이전트 파이프라인이다. 생성된 블로그는 Medium 등 플랫폼에 발행되며, 각 에이전트는 역할이 명확히 분리되어 있고, 사람이 핵심 시점에 개입하여 방향과 품질을 통제할 수 있다.

### 1.2 범위 (Scope)

본 시스템은 단일 오케스트레이터가 7개의 전문 에이전트를 순차 호출하는 내부 파이프라인으로, 외부 에이전트와의 통신(A2A Protocol)은 범위에 포함하지 않는다. Human-in-the-Loop 체크포인트를 통해 웹 대시보드에서 사람이 아웃라인 승인과 최종 발행 승인을 수행한다. 개인용 도구로서 단일 사용자, 클라우드 상시 운영 환경을 전제한다.

### 1.3 핵심 설계 원칙 (Design Principles)

| 원칙 | 설명 |
|------|------|
| **관심사 분리** | 각 에이전트는 단일 책임만 담당하며, 다른 에이전트의 내부 로직에 의존하지 않는다 |
| **Human-in-the-Loop** | 사람이 핵심 의사결정 시점에 개입하여 방향과 품질을 통제한다 |
| **사실 우선** | Fact Checker가 Critic보다 먼저 실행되어, 항상 정확한 정보 위에서 품질 평가가 이루어진다 |
| **반복 개선** | Critic 반려 시 Writer가 재작성하는 피드백 루프를 통해 품질을 점진적으로 개선한다 (최대 3회) |
| **스타일 보존** | SEO Optimizer는 Editor가 확정한 스타일을 훼손하지 않는 범위에서만 최적화한다 |
| **비용 효율** | 한글 완성 후 영문 변환 전략으로 Fact Check/Critic을 1회만 실행하여 비용을 절감한다 |

---

## 2. 파이프라인 아키텍처 (Pipeline Architecture)

### 2.1 전체 흐름 (Pipeline Flow)

시스템은 7개의 에이전트가 순차적으로 실행되며, 2개의 Human-in-the-Loop 체크포인트와 1개의 자동 피드백 루프를 포함한다. **한글 블로그를 먼저 완성한 후, Translator 에이전트가 영문 버전을 생성**한다:

```
Research Planner → [🧑 아웃라인 승인] → Writer(KO) → Fact Checker → Critic ──→ Editor(KO) → SEO Optimizer(KO)
                                                       ↑              ↓                           ↓
                                                       └── (fail) ← Writer(KO) (재작성, 최대 3회)  ↓
                                                                                          Translator(→EN)
                                                                                                ↓
                                                                                    Editor(EN) → SEO Optimizer(EN)
                                                                                                ↓
                                                                                  [🧑 발행 승인 (KO+EN)] → Publish
```

### 2.2 데이터 흐름 (Data Flow)

모든 에이전트는 `PipelineState`라는 단일 상태 객체를 공유한다. 각 에이전트는 자신이 담당하는 필드만 읽고 쓰며, 상태는 파이프라인을 흐르면서 누적적으로 풍부해진다. 에이전트 간 상태 오염 방지는 코드 컨벤션으로 관리한다.

| 에이전트 | 입력 (Input) | 출력 (Output) |
|----------|-------------|---------------|
| **Research Planner** | `sources[]` | `research_summary`, `outline` |
| **Writer** | `outline`, `research_summary`, `critic_feedback?` | `draft_ko` |
| **Fact Checker** | `draft_ko`, `sources[]` | `fact_check` (FactCheckResult) |
| **Critic** | `draft_ko`, `outline`, `fact_check` | `critic_feedback` (CriticFeedback) |
| **Translator** | `draft_ko` (Critic 통과 후) | `draft_en` |
| **Editor** | `draft_ko`/`draft_en`, `style_guide` | `edited_draft_ko`, `edited_draft_en` |
| **SEO Optimizer** | `edited_draft_ko`/`edited_draft_en`, `outline` | `seo_metadata_ko`, `seo_metadata_en`, `final_post_ko`, `final_post_en` |

### 2.3 소스 콘텐츠 처리 (Source Content Processing)

**다중 소스 통합:** 여러 소스(URL 복수, PDF, RSS)가 입력되면 항상 하나의 블로그 글로 통합한다. Research Planner가 소스 간 연결점과 통찰을 추출하여 단일 아웃라인을 생성한다.

**소스 언어 처리:** 소스 콘텐츠의 언어와 무관하게 Claude가 다국어 소스를 직접 이해하고 처리한다. 별도 번역 단계 없이 LLM이 자연스럽게 한글/영문 각각의 블로그를 생성한다.

**긴 콘텐츠 처리 (청크 + 요약):** 소스 콘텐츠가 길 경우(PDF 수십 페이지, 긴 기사 등) 컨텍스트 창 초과를 방지하기 위해:
1. 콘텐츠를 적절한 크기의 청크로 분할
2. 각 청크를 LLM으로 요약
3. 요약된 결과를 Research Planner에 전달

---

## 3. 에이전트 상세 설계 (Agent Specifications)

### 3.1 Research Planner

**역할:** 소스 콘텐츠를 분석하고, 핵심 요약을 추출하며, 블로그 글감 및 아웃라인을 생성한다.

**모델:** Claude Opus 4.6 (복잡한 추론과 다중 소스 분석이 필요)

**입력:** `SourceContent[]` — URL, PDF, RSS에서 파싱된 콘텐츠 목록

**출력:** `research_summary` (str), `outline` (Outline 객체: topic, angle, target_audience, key_points, structure, estimated_word_count)

**성공 기준:** 아웃라인이 Writer가 초고를 작성할 수 있을 만큼 충분히 구체적이고, 고유한 관점(angle)이 명확해야 한다.

**아웃라인 공유:** 한글/영문 블로그는 동일한 아웃라인을 공유한다. 아웃라인은 언어 중립적으로 작성된다.

### 3.2 Writer

**역할:** 승인된 아웃라인을 바탕으로 **한글** 블로그 포스트 초고를 작성하며, Critic 반려 시 피드백을 반영하여 재작성한다.

**모델:** Claude Sonnet 4.5

**입력:** `outline`, `research_summary`, [`critic_feedback`, `fact_check` — 재작성 시]

**출력:** `draft_ko` (Markdown 형식 블로그 포스트)

**섹션별 순차 생성:** 긴 콘텐츠의 경우 outline의 structure를 기준으로 섹션별로 나눠 생성하고 합친다. 이전 섹션을 컨텍스트로 전달하여 연결성을 유지하되, 최종 트랜지션 다듬기는 Editor가 담당한다.

**재작성 로직:** Critic 피드백의 weaknesses와 rewrite_instructions를 구체적으로 반영하며, strengths는 유지한다.

### 3.3 Fact Checker

**역할:** 한글 초고의 사실 관계, 출처, 데이터 정확성을 검증한다. 한글 초고에 대해서만 실행하며, 검증 결과는 영문 버전에도 공유된다.

**모델:** Claude Sonnet 4.5

**입력:** `draft_ko`, `sources[]`

**출력:** `FactCheckResult` (claims_checked, issues_found[], overall_accuracy, suggestions[])

**심각도 분류:**
- **high** — 사실 오류, 오해 소지가 있는 주장
- **medium** — 부정확, 과장, 중요한 맥락 누락
- **low** — 미세한 부정확, 더 정밀할 수 있는 표현

**원칙:** 의견이나 예측은 검증 대상이 아니며, 소스 자료와 교차 검증이 불가능한 주장을 '검증 불가'로 플래그한다. 할루시네이션 감지는 소스에 없는 주장을 플래그하는 방식으로 수행한다.

**Fact Check Diff 추적:** 재작성 루프에서 이전 라운드의 이슈 목록과 비교하여 resolved/new/remaining으로 분류한다. 전체 이력은 저장하지 않고 diff만 추적한다.

### 3.4 Critic

**역할:** 한글 초고의 논리, 구조, 깊이를 평가하고 통과(pass) 또는 반려(fail)를 판정한다.

**모델:** Claude Opus 4.6 (엄격하고 일관된 품질 평가 필요)

**입력:** `draft_ko`, `outline`, `fact_check`, `rewrite_count`

**출력:** `CriticFeedback` (verdict, score, strengths[], weaknesses[], specific_feedback, rewrite_instructions)

**판정 기준:**
- `score ≥ 7` AND high-severity fact issue 없음 → **PASS**
- 그 외 → **FAIL**

**반려 루프:** FAIL 시 Writer로 돌아가며, 최대 3회까지 반복. 3회차에는 minor issue에 대해 관대하게 평가한다.

### 3.5 Translator

**역할:** Critic을 통과한 한글 초고를 영문으로 변환한다. 단순 번역이 아니라, 영어권 독자에게 자연스러운 블로그 포스트로 변환한다.

**모델:** Claude Sonnet 4.5

**입력:** `draft_ko` (Critic 통과 후 확정된 한글 초고)

**출력:** `draft_en` (Markdown 형식 영문 블로그 포스트)

**원칙:** 원문의 논리 구조와 핵심 주장을 유지하되, 영어권 문화에 맞는 표현과 예시로 적절히 조정한다. Fact Check/Critic에서 확인된 사실 정확성은 보존한다.

### 3.6 Editor

**역할:** 스타일 가이드에 따라 톤, 포맷, 문체를 최종 다듬는다. 한글/영문 각각에 대해 실행된다. 섹션 간 트랜지션과 흐름도 이 단계에서 최종 조정한다.

**모델:** Claude Sonnet 4.5

**입력:** `draft_ko`/`draft_en`, `style_guide` (YAML)

**출력:** `edited_draft_ko`, `edited_draft_en` (Markdown)

**제약:** 사실적 내용이나 전체 구조를 변경하지 않으며, 단어 선택, 문장 리듬, 전환 표현, 명확성, 섹션 간 연결성에 집중한다.

### 3.7 SEO Optimizer

**역할:** 검색 엔진 최적화를 수행하되, 편집된 스타일을 훼손하지 않는다. 한글/영문 각각에 대해 실행된다.

**모델:** Claude Sonnet 4.5

**입력:** `edited_draft_ko`/`edited_draft_en`, `outline`

**출력:** `SEOMetadata` (optimized_title, meta_description, primary_keyword, secondary_keywords[], suggested_slug), `final_post_ko`, `final_post_en`

**권한 범위:** 제목, 메타 디스크립션, 헤딩 구조, 키워드 밀도 최적화. 본문 텍스트 재작성은 금지된다.

---

## 4. 이중 언어 전략 (Bilingual Strategy)

### 4.1 비용 효율적 이중 언어 생성

한글과 영문 블로그를 하나의 파이프라인에서 모두 생성하되, **비용 절감을 위해 한글을 먼저 완성한 후 영문으로 변환**하는 전략을 사용한다:

1. **Research Planner** → 아웃라인 1개 (언어 중립, 한글/영문 공유)
2. **Writer** → 한글 초고만 생성
3. **Fact Checker** → 한글 초고만 검증 (1회)
4. **Critic** → 한글 초고만 평가 (1회)
5. **Translator** → 한글 → 영문 변환
6. **Editor** → 한글/영문 각각 스타일 편집
7. **SEO Optimizer** → 한글/영문 각각 SEO 최적화

이 전략으로 Fact Checker와 Critic의 LLM 호출을 절반으로 줄여 비용을 절감한다.

### 4.2 동기화 루프

Critic → Writer 재작성 루프는 한글 초고에 대해서만 실행된다. 한글 초고가 Critic을 통과한 후에야 Translator가 영문 변환을 수행하므로, 영문 버전에 대한 별도 Critic 루프는 없다.

### 4.3 발행 시 플랫폼 선택

HITL 발행 승인 화면에서 한글/영문 최종 포스트를 모두 확인한 후, 각 언어별로 발행 여부와 대상 플랫폼을 선택할 수 있다:
- 한글 → Medium, 영문 → Medium (둘 다 같은 플랫폼)
- 한글만 발행, 영문은 저장만
- 기타 조합 자유 선택

플랫폼-언어 매핑은 고정되지 않으며, 매 발행 시점에 사용자가 결정한다.

---

## 5. Human-in-the-Loop 설계

### 5.1 체크포인트 위치 및 근거

| 체크포인트 | 위치 | 의사결정 | 근거 |
|-----------|------|---------|------|
| **#1 아웃라인 승인** | Research Planner 이후 | Approve / Edit / Reject | 방향이 틀어지면 이후 전 단계가 낭비 |
| **#2 발행 승인** | SEO Optimizer(KO+EN) 이후 | Publish / Edit / Reject | 최종 품질 게이트, 한글/영문 모두 확인, 언어별 플랫폼 선택 |

**중간 취소:** 파이프라인 실행 중 중간 취소는 지원하지 않는다. HITL 체크포인트에서 Reject로 종료한다.

### 5.2 개입 방식

**인터페이스:** FastAPI + Jinja2 + HTMX 기반 웹 대시보드

**의사결정 옵션:**
- **Approve** — 그대로 다음 단계로 진행
- **Edit (Approve with Notes)** — 사람의 메모(텍스트)를 반영하여 다음 단계 진행. 아웃라인 인라인 편집은 지원하지 않으며, 자유 텍스트 메모로 지시한다.
- **Reject** — 파이프라인 종료

### 5.3 구현 메커니즘

LangGraph의 `interrupt_before` 기능을 활용하여 해당 노드 진입 전에 실행을 일시 중단한다. 웹 UI에서 사람이 의사결정을 내리면 `update_state()`로 상태를 주입하고 파이프라인을 재개한다. `SqliteSaver` checkpointer가 중단 시점의 상태를 로컬 파일로 영속화하여, 서버 재시작 시에도 상태가 유지된다.

### 5.4 진행 상황 실시간 표시

HTMX의 `hx-trigger="every 2s"` 폴링으로 파이프라인 상태 엔드포인트를 주기적으로 조회한다:
- 각 에이전트 실행 중 → 로딩 스피너 표시
- 단계 완료 시 → 체크마크 표시
- Critic 루프 내 현재 라운드 표시 (예: "재작성 2/3")

### 5.5 발행 승인 화면 정보

**요약 + 펼치기 구조:**
- **상단 요약**: Critic 점수, Fact Check 요약 (이슈 수/심각도), 재작성 횟수
- **펼치기 상세**: Critic 상세 피드백, Fact Check 이슈 목록, SEO 메타데이터, 원본 아웃라인
- **최종 포스트**: 한글/영문 탭 전환으로 양쪽 모두 미리보기
- **발행 선택**: 각 언어별 발행 여부 및 대상 플랫폼 선택

### 5.6 작업 단계별 처리방식 요약

| 단계 | 에이전트 판단 | 스크립트 | Human |
|------|-------------|---------|-------|
| **소스 입력** | — | URL/PDF/RSS 파서가 소스를 파싱하여 `SourceContent[]` 생성 | 대시보드에서 URL 텍스트 입력, PDF 파일 업로드, RSS URL 입력 (항목 추가 버튼으로 복수 입력) |
| **리서치 + 기획** | Research Planner가 소스를 분석하여 요약, 글감, 관점, 아웃라인 생성 | tool_use로 구조화 출력 + Pydantic 검증으로 `Outline` 객체 변환 | — |
| **🧑 아웃라인 승인** | — | `interrupt_before`로 파이프라인 일시 중단, 웹 UI에 아웃라인 표시 | 아웃라인 검토 후 Approve / Edit(메모 추가) / Reject 결정 |
| **초고 작성 (KO)** | Writer가 승인된 아웃라인 + 리서치 요약 기반으로 한글 Markdown 초고 작성 (섹션별 순차 생성) | Human 메모가 있으면 프롬프트에 주입 | — |
| **사실 검증** | Fact Checker가 한글 초고의 모든 주장을 소스와 교차 검증, 이슈별 심각도 분류 | tool_use + Pydantic으로 `FactCheckResult` 변환, diff 추적 | — |
| **품질 평가** | Critic이 논리/구조/깊이 평가 후 점수 산출, pass/fail 판정 | 판정 결과에 따라 조건부 라우팅 (pass → Translator, fail → Writer) | — |
| **↩️ 재작성 루프** | Writer가 Critic 피드백 + Fact Check 이슈를 반영하여 한글 초고 재작성 | `rewrite_count` 증가, 최대 3회 초과 시 강제 pass로 Translator 진행 | — |
| **영문 변환** | Translator가 확정된 한글 초고를 영문 블로그로 변환 | — | — |
| **스타일 편집** | Editor가 `style_guide.yaml` 기준으로 한글/영문 각각 톤, 포맷, 문체, 트랜지션 다듬기 | YAML 스타일 가이드를 프롬프트에 주입 | — |
| **SEO 최적화** | SEO Optimizer가 한글/영문 각각 제목, 메타, 헤딩, 키워드 최적화 (본문 재작성 금지) | tool_use + Pydantic으로 `SEOMetadata` + `final_post` 추출 | — |
| **🧑 발행 승인** | — | `interrupt_before`로 파이프라인 일시 중단, 한글/영문 최종 포스트 + 통계 표시 | 양쪽 포스트 확인, 언어별 발행 플랫폼 선택 후 Publish / Edit / Reject 결정 |
| **발행** | — | 선택된 플랫폼(Medium API)으로 발행 + `output/` 디렉토리에 Markdown 저장 | — |

---

## 6. 기술 스택 (Tech Stack)

| 영역 | 기술 | 비고 |
|------|------|------|
| **LLM** | Claude API (Opus 4.6 + Sonnet 4.5 혼합) | Research Planner, Critic → Opus / Writer, Fact Checker, Translator, Editor, SEO Optimizer → Sonnet |
| **LLM 출력 파싱** | Anthropic tool_use + Pydantic | tool_use로 구조 보장, Pydantic으로 비즈니스 로직 검증 (score 범위 등) |
| **오케스트레이터** | LangGraph | 상태 관리 + 조건부 흐름 + HITL interrupt 지원 |
| **상태 영속성** | LangGraph SqliteSaver | SQLite 파일로 체크포인트 영속화, 서버 재시작 시 상태 유지 |
| **웹 UI** | FastAPI + Jinja2 + HTMX | 경량 대시보드, HTMX 폴링으로 실시간 업데이트 |
| **URL 파싱** | Trafilatura | 웹 콘텐츠 추출 전문 라이브러리, 노이즈 제거 + 메타데이터 추출 내장 |
| **PDF 파싱** | PyMuPDF | 빠른 PDF 텍스트 추출 |
| **RSS 파싱** | feedparser + Trafilatura | RSS/Atom 피드 수집 후 항목별 원문 URL을 Trafilatura로 추출 |
| **블로그 발행** | Medium API | MVP에서 Medium 직접 발행 지원 |
| **출력 포맷** | Markdown + YAML frontmatter | SEO 메타데이터, Critic 점수 등 파이프라인 정보를 frontmatter에 포함 |
| **인증** | 환경변수 기반 단일 비밀번호 | 개인용 클라우드 배포 시 간단한 인증 |

---

## 7. 상태 설계 (State Design)

### 7.1 PipelineState 구조

`PipelineState`는 TypedDict로 정의되며, 파이프라인의 모든 데이터를 담는 중앙 상태 객체이다. 에이전트 간 상태 오염 방지는 코드 컨벤션으로 관리한다 (각 에이전트는 자신이 담당하는 필드만 쓴다).

| 필드 | 타입 | 설명 |
|------|------|------|
| `sources` | `list[SourceContent]` | 파싱된 소스 콘텐츠 목록 |
| `research_summary` | `str` | 리서치 요약 |
| `outline` | `Outline` | 글감, 관점, 아웃라인 (한글/영문 공유) |
| `outline_decision` | `HumanDecision` | HITL #1 의사결정 |
| `outline_human_notes` | `str` | 사람의 메모 |
| `draft_ko` | `str` | 한글 Markdown 초고 |
| `draft_en` | `str` | 영문 Markdown 초고 (Translator 출력) |
| `rewrite_count` | `int` | 재작성 횟수 (0~3) |
| `fact_check` | `FactCheckResult` | 사실 검증 결과 |
| `fact_check_diff` | `FactCheckDiff` | 재작성 시 이전 이슈 대비 diff (resolved/new/remaining) |
| `critic_feedback` | `CriticFeedback` | 비평 결과 및 판정 |
| `edited_draft_ko` | `str` | 편집된 한글 최종 초고 |
| `edited_draft_en` | `str` | 편집된 영문 최종 초고 |
| `seo_metadata_ko` | `SEOMetadata` | 한글 SEO 최적화 메타데이터 |
| `seo_metadata_en` | `SEOMetadata` | 영문 SEO 최적화 메타데이터 |
| `final_post_ko` | `str` | 최종 한글 블로그 포스트 |
| `final_post_en` | `str` | 최종 영문 블로그 포스트 |
| `publish_decision` | `HumanDecision` | HITL #2 의사결정 |
| `publish_targets` | `list[PublishTarget]` | 언어별 발행 플랫폼 선택 |
| `current_step` | `str` | 현재 파이프라인 단계 |

### 7.2 핵심 데이터 모델

**SourceContent:** `source_type` (URL/PDF/RSS), `origin`, `title`, `content`, `metadata`

**Outline:** `topic`, `angle`, `target_audience`, `key_points[]`, `structure[]`, `estimated_word_count`

**FactCheckResult:** `claims_checked`, `issues_found[]`, `overall_accuracy`, `suggestions[]`

**FactCheckDiff:** `resolved[]`, `new[]`, `remaining[]` — 재작성 루프에서 이전 라운드 대비 변경 추적

**CriticFeedback:** `verdict` (pass/fail), `score` (1-10), `strengths[]`, `weaknesses[]`, `specific_feedback`, `rewrite_instructions`

**SEOMetadata:** `optimized_title`, `meta_description`, `primary_keyword`, `secondary_keywords[]`, `suggested_slug`

**PublishTarget:** `language` (ko/en), `platform` (medium/none), `publish` (bool)

---

## 8. 피드백 루프 설계 (Feedback Loop)

### 8.1 Critic → Writer 반려 루프

Critic이 FAIL 판정을 내리면 Writer가 피드백을 반영하여 **한글 초고**를 재작성한다. 재작성된 초고는 Fact Checker부터 다시 검증을 거친다. 영문 버전은 한글 초고가 최종 확정된 후에만 생성되므로 재작성 루프에 포함되지 않는다.

| 항목 | 설정 |
|------|------|
| **최대 반복 횟수** | 3회 (`MAX_REWRITE_ATTEMPTS` 환경변수로 설정 가능) |
| **반려 시 경로** | Writer(KO) → Fact Checker → Critic (매 반복마다 사실 검증 보장) |
| **최대 횟수 초과 시** | 현재 초고로 Translator로 진행 (무한 루프 방지) |
| **3회차 평가 정책** | Critic이 minor issue에 대해 관대하게 평가 (프롬프트에 명시) |

### 8.2 Writer 재작성 시 입력 데이터

재작성 시 Writer는 다음을 모두 입력받아 종합적으로 반영한다:
- 이전 한글 초고 (`draft_ko`)
- Critic의 피드백 (점수, 약점, 재작성 지침)
- Fact Checker의 이슈 목록 + diff (resolved/new/remaining)
- 사람의 메모 (있는 경우)

### 8.3 Fact Check Diff 추적

재작성 루프에서 Fact Checker는 이전 라운드의 이슈 목록과 현재 이슈를 비교한다:
- **resolved**: 이전에 발견되었으나 수정된 이슈
- **new**: 새로 발견된 이슈
- **remaining**: 여전히 남아있는 이슈

이 diff는 Critic에게 전달되어 개선 추이를 평가하는 데 활용된다.

---

## 9. 에러 핸들링 (Error Handling)

### 9.1 단계별 격리 실패 (Stage-Isolated Failure)

각 에이전트 노드가 독립적으로 실패를 처리하며, 실패한 단계의 상태를 보존하여 해당 단계부터 재실행할 수 있다.

| 실패 유형 | 처리 전략 |
|-----------|----------|
| **Claude API 호출 실패** | Exponential backoff로 재시도 (최대 3회). Rate limit, 네트워크 오류 등 대응 |
| **LLM 응답 JSON 파싱 실패** | tool_use가 기본 구조를 보장하므로 발생 빈도 낮음. Pydantic 검증 실패 시 에러 메시지와 함께 LLM에 재요청 (최대 2회) |
| **파서 타임아웃/실패** | URL 파싱 실패 시 해당 소스를 스킵하고 경고 로그. 전체 소스가 실패하면 파이프라인 중단 |
| **체크포인터 실패** | SQLite 쓰기 실패 시 파이프라인 중단 및 에러 로그 |

### 9.2 재실행 메커니즘

SqliteSaver가 각 단계 완료 시 상태를 체크포인트하므로, 실패 시 마지막 성공 체크포인트부터 재실행할 수 있다. 대시보드에서 실패한 파이프라인의 에러 상태와 재시작 옵션을 표시한다.

---

## 10. 배포 및 보안 (Deployment & Security)

### 10.1 배포 환경

**클라우드 상시 운영:** 클라우드 VM에 배포하여 언제든 웹 대시보드에 접속할 수 있는 환경. HITL 체크포인트에서 대기 시간이 길어도 SqliteSaver가 상태를 보존한다.

### 10.2 인증

**단일 비밀번호 인증:** 환경변수(`DASHBOARD_PASSWORD`)로 설정한 비밀번호로 로그인. 개인용 도구이므로 이 수준으로 충분하다. API 키와 파이프라인 결과가 외부에 노출되지 않도록 보호한다.

### 10.3 환경변수 관리

`.env` 파일로 관리하는 주요 환경변수:
- `ANTHROPIC_API_KEY` — Claude API 키
- `MEDIUM_API_TOKEN` — Medium 발행 토큰
- `DASHBOARD_PASSWORD` — 대시보드 로그인 비밀번호
- `MAX_REWRITE_ATTEMPTS` — 최대 재작성 횟수 (기본값: 3)
- `SQLITE_DB_PATH` — SQLite 체크포인터 파일 경로

---

## 11. 비용 관리 (Cost Management)

### 11.1 예산

- **월 예산:** $20 이내 (2026-02-13 기준, 2주 후 재검토)

### 11.2 비용 절감 전략

| 전략 | 설명 |
|------|------|
| **한글 우선 + 영문 변환** | Fact Checker/Critic을 한글에 대해서만 1회 실행하여 LLM 호출을 절반으로 절감 |
| **모델 혼합** | 추론 집약 에이전트(Research Planner, Critic)만 Opus, 나머지는 Sonnet으로 비용 최적화 |
| **청크 요약** | 긴 소스 콘텐츠를 요약하여 입력 토큰 절감 |
| **섹션별 생성** | 출력 토큰 제한에 걸리지 않도록 분할 생성, 불필요한 재시도 방지 |

### 11.3 비용 추적

Python logging으로 파이프라인 실행 시 다음 항목을 로그에 기록:
- 에이전트별 입력/출력 토큰 수
- 에이전트별 API 호출 횟수
- 파이프라인 전체 토큰 사용량 및 추정 비용

별도 비용 제한이나 차단 기능은 두지 않으며, 로그 기반으로 추이를 파악한다.

---

## 12. 출력 및 발행 (Output & Publishing)

### 12.1 출력 포맷

**Markdown + YAML frontmatter:** 각 언어별 블로그 포스트를 별도 Markdown 파일로 저장하며, 파일 상단에 YAML frontmatter로 메타데이터를 포함한다.

```yaml
---
title: "최적화된 제목"
date: 2026-02-13
language: ko
meta_description: "메타 디스크립션"
primary_keyword: "주요 키워드"
secondary_keywords: ["키워드1", "키워드2"]
slug: suggested-slug
critic_score: 8
rewrite_count: 1
fact_check_accuracy: 0.95
pipeline_id: "uuid"
---

# 블로그 포스트 본문...
```

**파일 네이밍:** `{slug}_{language}.md` (예: `ai-agent-design_ko.md`, `ai-agent-design_en.md`)

### 12.2 Medium 발행

MVP에서 Medium API를 연동하여 직접 발행한다. HITL 발행 승인 화면에서 사용자가 언어별로 발행 여부와 대상 플랫폼을 선택한다.

- 발행 성공 시 Medium URL을 frontmatter에 추가 기록
- 발행과 별개로 항상 output/ 디렉토리에 Markdown 파일 저장

### 12.3 파이프라인 이력 조회

대시보드에 이전 파이프라인 실행 목록을 간단하게 표시:
- 글 제목, 실행 일시, 상태 (publish/reject/in-progress)
- 클릭하면 해당 파이프라인의 최종 포스트 확인 가능

---

## 13. 로깅 및 테스트 (Logging & Testing)

### 13.1 로깅

**Python 표준 logging 모듈** 사용:
- 단계별 로그 레벨 분리 (INFO: 단계 시작/완료, DEBUG: LLM 입출력 상세, ERROR: 실패 상세)
- 파일 로그로 기록
- 토큰 사용량, 실행 시간, API 호출 횟수를 각 에이전트별로 기록

### 13.2 테스트

**Mock LLM 단위 테스트:**
- LLM 응답을 mock하여 파이프라인 로직 테스트
- 상태 전이 정확성 검증 (각 에이전트가 올바른 필드만 읽고 쓰는지)
- 에러 핸들링 테스트 (API 실패, 파싱 실패 시 재시도/복구 동작)
- Critic 루프 조건부 라우팅 테스트 (pass/fail 분기, 최대 횟수 초과)
- HITL 체크포인트 중단/재개 테스트

---

## 14. 프로젝트 구조 (Project Structure)

```
auto-blog-agent/
├── config/
│   ├── settings.py              # 환경 설정, API 키
│   └── style_guide.yaml         # 블로그 스타일 가이드 (Editor용, 웹에서 읽기 전용 미리보기)
├── prompts/
│   ├── research_planner.py      # Research Planner 시스템 프롬프트
│   ├── writer.py                # Writer 시스템 프롬프트
│   ├── fact_checker.py          # Fact Checker 시스템 프롬프트
│   ├── critic.py                # Critic 시스템 프롬프트
│   ├── translator.py            # Translator 시스템 프롬프트
│   ├── editor.py                # Editor 시스템 프롬프트
│   └── seo_optimizer.py         # SEO Optimizer 시스템 프롬프트
├── agents/
│   ├── base_agent.py            # Claude API 래퍼 베이스 클래스
│   ├── research_planner.py      # Research Planner 에이전트
│   ├── writer.py                # Writer 에이전트
│   ├── fact_checker.py          # Fact Checker 에이전트
│   ├── critic.py                # Critic 에이전트
│   ├── translator.py            # Translator 에이전트
│   ├── editor.py                # Editor 에이전트
│   └── seo_optimizer.py         # SEO Optimizer 에이전트
├── parsers/
│   ├── url_parser.py            # Trafilatura 기반 웹 콘텐츠 추출
│   ├── pdf_parser.py            # PyMuPDF 기반 PDF 파싱
│   └── rss_parser.py            # feedparser + Trafilatura RSS 수집
├── core/
│   ├── state.py                 # PipelineState 및 데이터 모델 정의 (Pydantic)
│   ├── graph.py                 # LangGraph 파이프라인 + HITL interrupt + SqliteSaver
│   └── runner.py                # 파이프라인 실행 매니저
├── web/
│   ├── app.py                   # FastAPI 웹 애플리케이션 (비밀번호 인증 포함)
│   ├── templates/
│   │   ├── base.html            # 기본 레이아웃
│   │   ├── login.html           # 로그인 페이지
│   │   ├── dashboard.html       # 메인 대시보드 (파이프라인 이력 목록 포함)
│   │   ├── new_pipeline.html    # 소스 입력 폼 (URL/PDF/RSS)
│   │   ├── review_outline.html  # 아웃라인 리뷰 페이지
│   │   ├── review_publish.html  # 발행 리뷰 페이지 (KO/EN 탭 + 요약/펼치기 + 플랫폼 선택)
│   │   └── style_guide.html     # 스타일 가이드 읽기 전용 미리보기
│   └── static/
│       └── style.css            # 대시보드 스타일
├── output/                      # 생성된 블로그 포스트 (Markdown + YAML frontmatter)
├── data/
│   └── pipeline.db              # SQLite 체크포인터 DB
├── tests/
│   ├── test_pipeline.py         # 파이프라인 로직 단위 테스트 (Mock LLM)
│   ├── test_parsers.py          # 파서 단위 테스트
│   └── test_agents.py           # 에이전트 단위 테스트 (Mock LLM)
├── main.py                      # CLI 진입점
├── requirements.txt             # Python 의존성
└── .env.example                 # 환경변수 템플릿
```

| 경로 | 설명 |
|------|------|
| `config/settings.py` | 환경 설정, API 키, 비용 추적 설정 |
| `config/style_guide.yaml` | 블로그 스타일 가이드 (Editor용, 톤/포맷 고정) |
| `prompts/*.py` | 에이전트별 시스템 프롬프트 (로직과 분리), Translator 포함 |
| `agents/base_agent.py` | Claude API 래퍼 베이스 클래스 (tool_use + Pydantic 파싱) |
| `agents/*.py` | 7개 에이전트 구현체 |
| `parsers/url_parser.py` | Trafilatura 기반 웹 콘텐츠 추출 (노이즈 제거) |
| `parsers/rss_parser.py` | RSS 항목별 별도 SourceContent + 원문 URL Trafilatura 추출 |
| `core/state.py` | PipelineState 및 데이터 모델 정의 (이중 언어 필드 포함) |
| `core/graph.py` | LangGraph 파이프라인 + HITL interrupt + SqliteSaver |
| `core/runner.py` | 파이프라인 실행 매니저 (에러 핸들링, 재실행 지원) |
| `web/app.py` | FastAPI 웹 애플리케이션 (비밀번호 인증, HTMX 폴링) |
| `web/templates/*.html` | 로그인, 대시보드, 소스입력, 아웃라인 리뷰, 발행 리뷰, 스타일가이드 미리보기 |
| `data/pipeline.db` | SqliteSaver 체크포인터 DB |
| `tests/*.py` | Mock LLM 기반 단위 테스트 |
| `main.py` | CLI 진입점 |

---

## 15. 확장 포인트 (Extension Points)

### 15.1 단기 확장

**웹 검색 통합:** Fact Checker에 외부 웹 검색 도구를 추가하여 소스 자료 외의 사실도 검증

**추가 발행 플랫폼:** LinkedIn, WordPress, Ghost 등 Medium 외 플랫폼 API 연동

**스타일 가이드 웹 편집:** 현재 읽기 전용 미리보기에서, 대시보드에서 직접 YAML 편집 가능하도록 확장

### 15.2 장기 확장

**Fact Checker + Critic 병렬 실행:** LangGraph의 병렬 노드를 활용하여 두 에이전트를 동시 실행하고 결과를 병합

**A2A Protocol 확장:** 외부 에이전트와 협업이 필요할 경우, 각 에이전트를 Agent Card로 노출하여 MoE 시스템과 연동

**영문 독립 Critic:** 비용 여유가 생기면 영문 버전에도 별도 Critic 루프를 추가하여 번역 품질을 검증

**Critic 루브릭 기반 판정:** 점수 대신 구체적인 루브릭(구조, 논리, 깊이 등)별로 pass/fail 판정하여 평가 일관성 향상

**Docker 컨테이너화:** 배포 편의를 위한 Docker Compose 구성
