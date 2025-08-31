<!-- README.md -->

# ♟️ CheckmateAI

**체스 실력을 키워주는 AI 기반 웹 애플리케이션**

- (레거시) React 데모: [checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)  
- (신규) Streamlit Cloud 앱: **<배포 후 URL 기입>**

---

## 🔄 왜 Streamlit로 전환했나 (배경 & 실패 기록)

기존 아키텍처(React/Vercel 프론트 + Flask/Render 백엔드)에서 아래 문제가 반복적으로 발생했습니다.

**문제/증상**
- 퍼즐 API 응답이 **30초 ~ 3분**까지 지연되거나 **타임아웃** 발생
- AI 수 계산 중 **갑작스런 끊김(세션 재시작)** 혹은 **지연**
- 서버 세션 불안정으로 **엔진/DB 캐시가 매 요청 초기화**

**원인 추정**
- 백엔드 프로세스의 콜드 스타트/스케일링으로 **Stockfish 초기화·DB 재연결 비용**이 반복
- **동기식 엔진 호출**로 요청 스레드 장시간 점유 → 타임아웃
- 퍼즐 DB 대용량 + **인덱스 미비**로 근접 난이도 검색이 느림

**전환/조치 & 결과**
- ▶ **Streamlit Cloud 전환**: 프론트에서 세션 상태 유지 +  
  `st.cache_resource`(엔진/DB) / `st.cache_data`(쿼리)로 **콜드 스타트/지연 감소**
- ▶ **엔진 호출 비동기화**: `ThreadPoolExecutor` + 락으로 **UI 끊김 최소화**
- ▶ **퍼즐 조회 최적화**: `ORDER BY ABS(rating-?) LIMIT 1` + **rating 인덱스**로 빠른 근접 난이도 로딩
- ▶ **바이너리 경로/권한 안정화**: Stockfish 자동탐색 + 실행권한 보정

> 결론: **세션 안정성**과 **콜드 스타트 감소**가 핵심. Streamlit 전환으로 대기시간/실패율이 유의미하게 감소했습니다.

---

## 🧠 소개

**CheckmateAI**는 Stockfish 엔진을 기반으로 **AI 대국, 퍼즐 훈련, 포지션 분석, 트레이닝 커리큘럼**을 제공하는 웹 앱입니다.  
초보자부터 중급자까지 실전 감각과 계산력을 동시에 키울 수 있도록 설계되었습니다.

### 🔑 주요 기능 (Streamlit 버전)

- 🤖 **AI 대국 (Top Player 스타일 프리셋)**
  - MultiPV 후보 중 **체크/포획/공격성 가중치**로 스타일 선택
  - 프리셋: *Karpov(클래식)* / *Kasparov(공격적)* / *Carlsen(유니버설)*
- 🧩 **퍼즐 모드 (세션 ELO 자동 난이도)**
  - 정답 +20 / 오답 −15로 **세션 점수** 조정
  - 근접 난이도 퍼즐 자동 추천
- 📊 **분석 탭**
  - 엔진 점수(CP) → **승률(로지스틱 변환)** 시각화
  - MultiPV 라인/SAN 표시, 히스토리 승률 추이 차트
- 🎯 **트레이너**
  - 전술/계산/엔드게임/오프닝 **블록형 훈련 계획** 제안

---

## 🌐 데모

- (레거시) React 데모: https://checkmateai-app.vercel.app  
- (신규) Streamlit Cloud: **<배포 후 URL 기입>**

---

## 🛠️ 기술 스택

### (신규) Streamlit 버전
- **Frontend/Backend 통합**: Streamlit
- **엔진**: Stockfish + `python-chess`
- **DB**: SQLite(퍼즐), `st.cache_*`로 캐시
- **시각화**: Streamlit 차트/데이터프레임

### (레거시) React/Flask 버전
- **프론트**: React + TypeScript + chessboardjsx
- **백엔드**: Flask + python-chess + Stockfish
- **인증/DB**: Firebase (Auth + Firestore)
- **배포**: Vercel(프론트) + Render(백)

---

## 📂 프로젝트 구조 (마이그레이션 이후)

CheckmateAI/
├── app.py # Streamlit 단일 앱 (AI/퍼즐/분석/트레이너)
├── engine/
│ └── stockfish # (권장) 리눅스 바이너리 포함, +x 권한 필수
├── puzzles.db # SQLite 퍼즐 DB (rating 인덱스 권장)
├── requirements.txt
├── packages.txt # (선택) apt 패키지 설치: stockfish
├── .streamlit/
│ └── config.toml # (선택) UI/성능 설정
└── legacy/ # (선택) 기존 React/Flask 소스 보관
├── client/ # React 프런트
└── server/ # Flask 백엔드

📈 성능/안정성 메모

- 엔진/DB: st.cache_resource, 쿼리: st.cache_data 로 세션 내 재사용

- 엔진 설정(Cloud 안전값): Threads=1, Hash=64

- think time(ms): 사이드바에서 조절(기본 600ms) — 높을수록 수질↑/응답속도↓

- MultiPV=3 (후보수 3개) 사용 — 체크/포획/전진 가중치로 “스타일” 선택

🧪 한계/유의사항

- “탑 플레이어 스타일”은 통계 모델이 아닌 휴리스틱 기반(향후 개선 예정)

- 동시접속 증가 시 엔진 자원은 세션별로 제한(Threads=1 유지 권장)

- 매우 큰 DB의 경우 초기 로딩/캐시 워밍에 시간이 필요

🧭 로드맵

- 👥 실시간 유저 매칭(ELO 기반 매칭)

- 🎯 훈련 커리큘럼 고도화(스케줄/리마인더)

- 🧠 스타일 모델 강화(킹 세이프티/교환 회피/폰 전진 등 특성 반영)

- ☁️ 원격 퍼즐 저장소 연동(대용량/고가용성)
