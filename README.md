# ♟️ CheckmateAI

**체스 실력을 키워주는 AI 기반 웹 애플리케이션**

- (레거시) React 데모: [checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)  
- (신규) Streamlit Cloud 앱: **<배포 후 URL 기입>**

---

## 🔄 Streamlit 전환 배경 & 시도 기록

기존 아키텍처에서 퍼즐 API 지연, AI 수 계산 중 끊김/세션 초기화 등 문제가 반복되어  
Streamlit으로 전환 시도 및 세션 캐시(`st.cache_resource` / `st.cache_data`) 적용.  
현재 일부 환경에서 안정화 확인 필요.

---

## 🧠 CheckmateAI 소개

**CheckmateAI**는 Stockfish 엔진 기반으로 **퍼즐 훈련, AI 대국(텍스트 입력)** 기능을 제공합니다.  
초보~중급자가 실전 감각과 계산력을 연습할 수 있도록 설계되었습니다.

### 🔑 Streamlit 구현 기능 (현재)

- 🧩 **퍼즐 모드**
  - 난이도 기반 퍼즐 랜덤 추천
  - 텍스트 입력으로 수 제출
  - 정답/오답 안내 및 세션 ELO 증감
  - 백/흑 표시

- 🤖 **AI 대국**
  - 텍스트 입력으로 수 제출
  - AI 응답 후 즉시 보드 갱신
  - 단순 대국 + Move History 확인

- 📊 **분석**
  - 엔진 점수 표시(CP)
  - SAN 표시 및 Move History 확인

---

## 🌐 데모

- React/Flask: https://checkmateai-app.vercel.app  
- Streamlit: **<배포 후 URL 기입>**

---

## 🛠️ 기술 스택

- Front/Back: Streamlit
- 엔진: Stockfish + `python-chess`
- DB: SQLite 퍼즐 + `st.cache_*`
- 시각화: Streamlit 데이터프레임 / 이미지 렌더링

---

## 📂 프로젝트 구조

```text
CheckmateAI/
├─ app.py                  # Streamlit 단일 앱
├─ engine/
│  └─ stockfish            # 권장: 리눅스 바이너리, +x 필수
├─ puzzles.db              # SQLite 퍼즐 DB
├─ requirements.txt
├─ packages.txt            # 선택: apt 설치용
├─ .streamlit/config.toml  # UI/성능 설정
└─ legacy/                 # React/Flask 소스

## 🧪 현재 한계 및 향후 개선 계획

### 현재 한계
- AI 대국: 텍스트 입력 방식만 가능, Top Player 스타일/전략 가중치 없음
- 퍼즐 모드: 정답/오답 안내만 제공, 힌트나 단계별 안내 미구현
- 분석: SAN/엔진 점수만 표시, 그래프/승률 추이 시각화 제한
- 트레이너 기능: 미구현
- 동시접속 증가 시 엔진 자원 제한 가능
- DB 초기 로딩 및 캐시 워밍 필요
- Streamlit에서 체스보드 렌더링/입력 UI 제한 → 클릭/드래그 불가, 텍스트 입력만 가능

### 향후 개선 계획
- Top Player 스타일 AI 대국 (공격적/클래식/유니버설)
- MultiPV 후보 및 가중치 기반 수 선택
- 퍼즐 모드 개선: 힌트, 단계별 풀이 안내, 난이도 조절
- 분석 탭 고도화: 승률 차트, 히스토리 시각화
- 트레이너 모드: 전술, 계산, 엔드게임, 오프닝 블록형 훈련 계획
- 실시간 유저 매칭(ELO 기반)
- 원격 퍼즐 저장소 연동: 대용량/고가용성
- 서버/배포 확장: Streamlit Cloud 한계 → Vercel/Render 등 성능 확장 예정

