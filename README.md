# ♟️ CheckmateAI

**체스 실력을 키워주는 AI 기반 웹 애플리케이션**

👉 [checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)

---

## 🧠 소개

**CheckmateAI**는 Stockfish 엔진을 기반으로 퍼즐 훈련 및 AI와의 대국을 제공하는 웹 체스 플랫폼입니다.  
초보자부터 중급자까지 누구나 실전 플레이와 퍼즐 풀이를 통해 실력을 키울 수 있도록 설계되었습니다.

### 🔑 주요 기능

- 🤖 **AI 체스 게임**  
  - 3가지 난이도 선택 (easy / medium / hard)  
  - Stockfish 기반 AI와 실시간 대국

- 🧩 **체스 퍼즐 모드**  
  - 사용자 점수 기반으로 난이도 자동 조절  
  - 퍼즐 성공 시 점수 상승, 실패 시 하락

- 💡 **힌트 및 정답 보기**  
  - 힌트(다음 수) 보기  
  - 정답 수순 전체 재생 기능 제공

- 📝 **기록 저장**  
  - Firebase를 통한 퍼즐/게임 결과 저장  
  - 최근 AI 대국 및 퍼즐 결과 마이페이지에서 확인 가능

- 📱 **반응형 UI 지원**  
  - 모바일, 태블릿, 데스크탑 전부 호환

---

## 🌐 데모 사이트

▶ [https://checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)

---

## 🛠️ 기술 스택

### 프론트엔드
- React + TypeScript
- chessboardjsx
- Firebase Auth
- Bootstrap + Custom CSS

### 백엔드
- Flask (Python)
- python-chess
- Stockfish
- Firestore (Firebase DB)
- Flask-CORS

---

## 📂 프로젝트 구조

<pre>
CheckmateAI/
├── client/               # React 프론트엔드
│   ├── App.tsx           # 주요 게임/퍼즐 로직 포함
│   └── ...               # 스타일 및 Firebase 설정
├── server/               
│   ├── ai_server.py      # Flask 백엔드: 퍼즐 및 AI 수 생성
│   ├── stockfish/        # Stockfish 실행 파일
│   └── puzzles.db        # 퍼즐 데이터 (SQLite)
└── README.md
</pre>

---

## 🚧 향후 추가 예정 기능

- 👥 **실시간 유저 매칭 대국 시스템**  
  - 다른 유저와 온라인 대결 (Elo 기반 매칭)

- 🧑‍🎓 **탑 플레이어 AI 모드**  
  - 실제 유명 선수의 플레이스타일을 모방한 AI 대국  
  - 예: "카스파로프라면 다음 수는 무엇일까?"

- 📊 **경기 분석 기능**  
  - 수별 승률 분석, 전략 추천, AI 수 평가 시각화

- 🧠 **체계적 체스 트레이닝 커리큘럼**  
  - 난이도 상승 기반 퍼즐 훈련 프로그램 구성

---

## ✅ 배포 환경

- 프론트엔드: [Vercel](https://vercel.com/)
- 백엔드: [Render](https://render.com/)
- 인증 및 DB: Firebase (Auth + Firestore)
