# ♟️ CheckmateAI

**체스 실력을 키워주는 AI 기반 웹 애플리케이션**

👉 [checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)

---

## 🧠 소개

**CheckmateAI**는 Stockfish 엔진을 활용하여 다양한 체스 기능을 제공하는 AI 체스 웹앱입니다.  
체스 초보자부터 중급자까지 모두가 **실전 플레이**와 **퍼즐 훈련**을 통해 실력을 키울 수 있도록 설계되었습니다.

### 주요 기능

- 🎮 **AI 체스 게임**: Stockfish AI와 다양한 난이도로 실시간 대국
- 🧩 **체스 퍼즐 모드**: 실전 기반의 Mate-in-N 퍼즐을 AI가 자동 생성
- 💡 **힌트 기능**: 퍼즐에서 다음 수에 대한 AI 힌트 제공
- ✅ **정답 보기**: 퍼즐 정답을 한 수씩 확인 가능
- 🔄 **탭 전환**: 게임 모드와 퍼즐 모드를 탭으로 손쉽게 전환
- 📱 **반응형 UI**: 모바일과 데스크탑 모두 지원

---

## 🌐 데모 사이트

▶ [https://checkmateai-app.vercel.app](https://checkmateai-app.vercel.app)

---

## 🛠️ 기술 스택

### 프론트엔드
- React + TypeScript
- chessboardjsx
- ShadCN/UI
- Tailwind CSS

### 백엔드
- Flask (Python)
- python-chess
- Stockfish
- Flask-CORS

---

## 📂 프로젝트 구조

<pre>
CheckmateAI/
├── client/          # React 프론트엔드
│   ├── components/  # 체스보드, 퍼즐 탭 등 UI 구성 요소
│   └── pages/       # 라우팅 페이지
├── server/          # Flask 백엔드
│   ├── ai_server.py # AI 게임 및 퍼즐 엔드포인트
│   └── stockfish/   # Stockfish 바이너리 위치
└── README.md
</pre>

---

### 🔍 향후 개선 예정
- 사용자 로그인 및 기록 저장 기능

- 난이도 별 훈련 커리큘럼

- 더 다양한 퍼즐 유형 (전술, 트랩, 전략 등)

- 수 평가 추가
