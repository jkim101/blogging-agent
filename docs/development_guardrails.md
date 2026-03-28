# Development Guardrails

이 프로젝트를 개발하면서 실제로 겪은 문제들을 바탕으로 작성한 가이드라인.

---

## 1. 서버 & 포트 관리

### 포트 충돌 확인부터 시작
서버를 시작하기 전에 항상 포트가 비어 있는지 확인한다.

```bash
lsof -iTCP -sTCP:LISTEN -P | grep :8000
```

- **Docker 컨테이너와 로컬 서버가 같은 포트를 동시에 점유할 수 있다.**
  IPv4(로컬)와 IPv6(Docker)로 나뉘어 두 프로세스가 공존하는 것처럼 보이지만, 브라우저 요청은 둘 중 하나로만 간다.
- 어느 서버로 요청이 가는지 모르는 상태에서 디버깅하면 시간을 크게 낭비한다.

### 사용하지 않는 컨테이너는 명시적으로 종료
```bash
docker ps        # 실행 중인 컨테이너 확인
docker stop <id> # 명시적으로 종료
```

---

## 2. 데이터 & 상태 관리

### Docker 컨테이너는 volume 없으면 데이터가 날아간다
컨테이너를 종료하면 내부 데이터(DB, 생성 파일)는 사라진다.
로컬 개발에서는 volume mount를 명시하거나, 처음부터 로컬 프로세스로 실행한다.

```bash
# 위험: 데이터 소실
docker run blogging-agent

# 안전: 로컬 디렉토리 마운트
docker run -v $(pwd)/data:/app/data blogging-agent
```

### 파이프라인 ID는 실행 환경에 종속된다
Docker 컨테이너에서 실행한 파이프라인 ID는 로컬 DB에 없다.
어느 환경에서 실행했는지 항상 확인하고, 환경을 섞지 않는다.

---

## 3. 기능 제거 시 범위 확인

### "이건 안 쓸게"의 범위를 반드시 확인
사용자가 "Railway 안 쓸거야"라고 했을 때 → Dockerfile + 퍼블리싱 코드 전부 제거했다가 되돌렸음.

**제거 전 반드시 확인:**
- 제거 대상이 다른 기능과 연결되어 있지 않은가?
- 사용자가 말한 범위가 인프라인지, 기능 자체인지 명확한가?
- 관련 테스트, 설정 파일, 템플릿도 함께 제거해야 하는가?

### 연쇄 영향 파악
코드 하나를 제거하면 import, state, template, test가 동시에 깨진다.
제거할 때는 의존성 그래프 전체를 확인하고 한 번에 처리한다.

---

## 4. 코드 변경 후 서버 재시작

### 코드 수정 후에는 반드시 서버 재시작
`reload=True` 옵션이 있어도 모듈 레벨 import 오류는 재시작 없이 해결되지 않는 경우가 있다.

```bash
pkill -f "main.py serve" && sleep 1 && python main.py serve &
```

### 변경 전후 테스트 실행 습관화
```bash
pytest tests/ -x -q  # 변경 전
# ... 코드 수정 ...
pytest tests/ -x -q  # 변경 후
```

---

## 5. 보안

### 파일 업로드 경로 검증 필수
사용자가 업로드한 파일명을 그대로 경로로 쓰면 경로 순회 공격에 취약하다.

```python
# 위험
save_path = UPLOAD_DIR / pdf_file.filename

# 안전
save_path = UPLOAD_DIR / Path(pdf_file.filename).name
```

### 입력값은 경계에서 검증
외부 입력(파일명, URL, 폼 데이터)은 사용 직전이 아니라 수신 직후에 검증한다.
특히 타입 변환(`int()`, `float()`)은 반드시 try/except로 감싼다.

```python
# 위험
kwargs["word_count"] = int(word_count)

# 안전
try:
    kwargs["word_count"] = int(word_count)
except ValueError:
    print("Invalid input, using default.")
```

---

## 6. 리소스 관리

### 파일/DB/외부 연결은 context manager 사용
예외가 발생해도 리소스가 반드시 해제되도록 한다.

```python
# 위험: 예외 발생 시 close() 미실행
doc = pymupdf.open(path)
pages = [p.get_text() for p in doc]
doc.close()

# 안전
with pymupdf.open(path) as doc:
    pages = [p.get_text() for p in doc]
```

### 예외는 반드시 로깅
Silent failure는 디버깅을 불가능하게 만든다.

```python
# 위험
except Exception:
    pass

# 안전
except Exception as e:
    logger.error("Failed to load %s: %s", resource_id, e)
```

---

## 7. 비동기 처리

### FastAPI async 핸들러에서 blocking 호출 금지
네트워크 요청, 파일 I/O, LLM API 호출은 모두 blocking이다.
async 핸들러 안에서 직접 호출하면 이벤트 루프가 block된다.

```python
# 위험
@app.post("/start")
async def start():
    result = run_long_task()  # blocks event loop

# 안전
@app.post("/start")
async def start():
    result = await asyncio.to_thread(run_long_task)
```

---

## 8. LLM 비용 관리

### max_tokens는 실제 출력량 기준으로 설정
기본값 8192를 그대로 쓰면 실제 출력량의 3~4배를 할당하게 된다.

| 에이전트 유형 | 권장 max_tokens |
|---|---|
| 장문 생성 (Writer, Translator, Editor) | 3000~4000 |
| 구조화 출력 (SEO, Fact Checker, Critic) | 1500~2000 |
| 분석 + 아웃라인 (Research Planner) | 3000 |

### 외부 API는 단일 호출로 통합
동일 입력으로 같은 API를 두 번 호출하는 패턴을 피한다.
(예: `trafilatura.extract()` text/metadata 이중 호출 → JSON 단일 호출로 통합)

---

## 9. 코드 품질

### 공통 로직은 메서드로 추출 (DRY)
같은 패턴이 3개 이상의 파일에 나타나면 공통 메서드로 추출한다.
특히 config 포맷팅, 메시지 빌딩 같은 반복 로직이 대상이다.

### 프롬프트 기준은 수치로 명시
"좋으면 PASS, 나쁘면 FAIL" 같은 주관적 표현은 모델마다 다르게 해석된다.

```
# 모호함
PASS if quality is good

# 명확함
PASS: score >= 7 AND zero high-severity fact issues
FAIL: score < 7 OR one or more high-severity fact issues
```

---

## 10. 배포 전 체크리스트

- [ ] 실행 중인 서버/컨테이너 포트 충돌 없는지 확인
- [ ] 환경변수 `.env` 설정 확인 (API 키, 경로 등)
- [ ] `pytest` 전체 통과 확인
- [ ] 파일 업로드 경로 검증 코드 존재 여부 확인
- [ ] async 핸들러 내 blocking 호출 없는지 확인
- [ ] 로깅 설정 확인 (silent failure 없는지)
- [ ] Docker 사용 시 volume mount 여부 확인
