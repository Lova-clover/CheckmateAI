import React, { useState, useEffect } from 'react';
import Chessboard from 'chessboardjsx';
import { Chess, Square } from 'chess.js';
import { initializeApp } from "firebase/app";
import { getAuth, onAuthStateChanged, signInWithEmailAndPassword, signOut, createUserWithEmailAndPassword } from "firebase/auth";
import './App.css';

const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

function App() {
  const [game, setGame] = useState(new Chess());
  const [position, setPosition] = useState('start');
  const [boardWidth, setBoardWidth] = useState(window.innerWidth > 500 ? 500 : window.innerWidth - 20);
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [promotionModalOpen, setPromotionModalOpen] = useState(false);
  const [promotionPending, setPromotionPending] = useState<{ from: Square; to: Square } | null>(null);
  const [movePairs, setMovePairs] = useState<[string, string | null][]>([]);
  const [winnerMessage, setWinnerMessage] = useState<string>('');
  const [useAI, setUseAI] = useState(true); // true면 AI 대국, false면 사람 vs 사람
  const [aiLevel, setAiLevel] = useState<'easy' | 'medium' | 'hard'>('easy'); // 난이도
  const [puzzleFen, setPuzzleFen] = useState('');
  const [puzzleGame, setPuzzleGame] = useState(new Chess());
  const [puzzleSolution, setPuzzleSolution] = useState<string[]>([]);
  const [puzzleMessage, setPuzzleMessage] = useState('');
  const [puzzleActive, setPuzzleActive] = useState(false);
  const [puzzleHint, setPuzzleHint] = useState('');
  const [showHint, setShowHint] = useState(false);
  const [showSolution, setShowSolution] = useState(false);
  const [userMoves, setUserMoves] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState(''); 
  const [puzzleId, setPuzzleId] = useState<string>('');
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [userScore, setUserScore] = useState<number | null>(null);
  const [showMyPage, setShowMyPage] = useState(false);
  const [userStats, setUserStats] = useState<null | {
    score: number;
    total: number;
    success: number;
    success_rate: number;
    recent: { puzzle_id: string; solved: boolean; time: number; date: string }[];
    recent_games?: { game_id: string; result: string; moves: number; date: string }[]; 
  }>(null);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [moveEval, setMoveEval] = useState<null | { white: number; black: number; draw: number }>(null);

  const BACKEND_URL =
    process.env.NODE_ENV === 'production'
      ? 'https://checkmateai-s5qg.onrender.com' // 🟢 배포된 Flask 서버 주소
      : 'http://localhost:5000';              // 🧪 로컬 개발용   

  useEffect(() => {
    onAuthStateChanged(auth, (user) => {
      if (user) {
        setUserId(user.uid);
        setUserEmail(user.email); // 이메일 저장
      } else {
        setUserId(null);
        setUserEmail(null);
      }
    });
  }, []);
  
  const handleSignup = async () => {
    try {
      const userCred = await createUserWithEmailAndPassword(auth, email, password);
      setUserId(userCred.user.uid);
    } catch (e: any) {
      alert("회원가입 실패: " + e.message);
    }
  };

  const handleLogin = async () => {
    try {
      const userCred = await signInWithEmailAndPassword(auth, email, password);
      setUserId(userCred.user.uid);
    } catch (e: any) {
      alert("로그인 실패: " + e.message);
    }
  };

  const handleLogout = () => {
    signOut(auth);
  };

  useEffect(() => {
    if (puzzleActive && puzzleSolution.length > 0) {
      const nextHint = puzzleSolution[userMoves.length] || '';
      setPuzzleHint(nextHint);
    }
  }, [userMoves, puzzleActive, puzzleSolution]);

  useEffect(() => {
    const handleResize = () => {
      setBoardWidth(window.innerWidth > 500 ? 500 : window.innerWidth - 20);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const updateMovePairs = (historyVerbose: any[]) => {
    const pairs: [string, string | null][] = [];
    for (let i = 0; i < historyVerbose.length; i += 2) {
      const white = historyVerbose[i]?.san ?? '';
      const black = historyVerbose[i + 1]?.san ?? null;
      pairs.push([white, black]);
    }
    setMovePairs(pairs);
  };

  const isPromotionMove = (from: Square, to: Square) => {
    const piece = game.get(from);
    if (!piece || piece.type !== 'p') return false;
    const rank = to[1];
    return (piece.color === 'w' && rank === '8') || (piece.color === 'b' && rank === '1');
  };

  const handlePromotion = (from: Square, to: Square) => {
    setPromotionPending({ from, to });
    setPromotionModalOpen(true);
  };

  const confirmPromotion = (promotion: 'q' | 'r' | 'b' | 'n') => {
    if (!promotionPending) return;

    const moveObj = {
      from: promotionPending.from,
      to: promotionPending.to,
      promotion,
    };

    const legalMoves = game.moves({ verbose: true });
    const isLegal = legalMoves.some(
      (m) =>
        m.from === moveObj.from &&
        m.to === moveObj.to &&
        m.promotion === promotion
    );

    if (!isLegal) {
      console.warn('⚠️ Illegal promotion move 시도됨:', moveObj);
      setPromotionModalOpen(false);
      setPromotionPending(null);
      return;
    }

    const move = game.move(moveObj);

    if (move) {
      setPosition(game.fen());
      updateMovePairs(game.history({ verbose: true }));
      checkGameOver(game);

      if (!puzzleActive && useAI && game.turn() === 'b' && !game.isGameOver()) {
        setTimeout(() => {
          playAIMove();
        }, 300);
      }
    }

    setPromotionModalOpen(false);
    setPromotionPending(null);
  };


  const checkGameOver = (gameInstance: Chess) => {
    const saveGameResult = async (result: 'win' | 'loss' | 'draw') => {
      if (!userId) return;

      const endTime = Date.now();
      const timeTaken = startTime ? Math.floor((endTime - startTime) / 1000) : 0;

      const history = game.history({ verbose: true });
      const uciMoves = history.map(m => m.from + m.to + (m.promotion ?? ''));

      try {
        await fetch(`${BACKEND_URL}/ai/game/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            result,
            time: timeTaken,
            moves: uciMoves
          })
        });
        console.log("✅ 게임 기록 저장 완료");
      } catch (e) {
        console.error("❌ 게임 기록 저장 실패:", e);
      }
    };

    if (gameInstance.isCheckmate()) {
      const winner = gameInstance.turn() === 'w' ? '흑' : '백';
      setWinnerMessage(`체크메이트! ${winner} 승리!`);
      
      // 기록 저장 호출
      if (useAI) saveGameResult(winner === '백' ? 'win' : 'loss');

    } else if (gameInstance.isDraw() || gameInstance.isStalemate()) {
      setWinnerMessage('무승부입니다.');

      // 무승부도 기록 저장
      if (useAI) saveGameResult('draw');

    } else if (gameInstance.isGameOver()) {
      setWinnerMessage('게임이 종료되었습니다.');

      // 기타 종료 상태도 처리
      if (useAI) saveGameResult('draw');

    } else {
      setWinnerMessage('');
    }
  };

  
  function fetchWithTimeout(resource: RequestInfo, options: any = {}, timeout = 10000): Promise<Response> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("⏱ 요청 시간이 초과되었습니다.")), timeout);
      fetch(resource, options)
        .then(response => {
          clearTimeout(timer);
          resolve(response);
        })
        .catch(err => {
          clearTimeout(timer);
          reject(err);
        });
    });
  }

  const playAIMove = async () => {
    try {
      const res = await fetchWithTimeout(`${BACKEND_URL}/ai/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fen: game.fen(), level: aiLevel }),
      }, 5000);  // ⏱ 10초 제한

      const data = await res.json();
      if (!data.move) throw new Error("AI 응답 없음");

      const from = data.move.slice(0, 2);
      const to = data.move.slice(2, 4);
      const move = game.move({ from, to, promotion: 'q' });
      if (move) {
        setPosition(game.fen());
        updateMovePairs(game.history({ verbose: true }));
        checkGameOver(game);
      }
    } catch (error) {
      console.error("❌ AI 호출 실패:", error);
      alert("AI 응답에 실패했습니다. 네트워크나 서버 상태를 확인해주세요.");
    }
  };


  const onDrop = async ({ sourceSquare, targetSquare }: { sourceSquare: Square; targetSquare: Square }) => {
    if (game.isGameOver()) return;

    if (puzzleActive) {
      try {
        const move = game.move({ from: sourceSquare, to: targetSquare, promotion: 'q' });
        if (!move) return;

        setPosition(game.fen());

        const userMove = move.from + move.to + (move.promotion ?? '');
        const correctMove = puzzleSolution[userMoves.length];

        if (userMove === correctMove) {
          const newUserMoves = [...userMoves, userMove];
          setUserMoves(newUserMoves);

          if (newUserMoves.length === puzzleSolution.length) {
            setPuzzleMessage('🎉 정답입니다!');
            setPuzzleActive(false);
            setUseAI(false);

            try {
              const res = await fetch(`${BACKEND_URL}/ai/puzzle/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  user_id: userId,
                  puzzle_id: puzzleId,
                  solved: true,
                  time: startTime ? Math.floor((Date.now() - startTime) / 1000) : 10
                })
              });
              const result = await res.json();
              const { new_score, delta } = result;

              alert(`🎉 퍼즐 성공! 현재 점수: ${new_score} (${delta >= 0 ? '+' : ''}${delta})`);
            } catch (e) {
              console.error('점수 제출 실패:', e);
            }
          } else {
            setPuzzleMessage('👍 계속 진행하세요');
            setTimeout(() => {
              const nextUCI = puzzleSolution[newUserMoves.length]; // ✅ UCI 기반 정답
              const legalMoves = game.moves({ verbose: true });

              const autoMove = legalMoves.find(
                m => m.from + m.to + (m.promotion ?? '') === nextUCI
              );

              if (autoMove) {
                game.move(autoMove);
                setPosition(game.fen());
                setUserMoves([
                  ...newUserMoves,
                  autoMove.from + autoMove.to + (autoMove.promotion ?? '')
                ]);
                checkGameOver(game);
              }
            }, 500);
          }
        } else {
          game.undo();
          setPosition(game.fen());
          setPuzzleMessage('❌ 오답입니다. 퍼즐이 종료되었습니다.');
          setPuzzleActive(false); // 🔴 퍼즐 종료
          setUseAI(false);        // AI도 끔

          try {
            const res = await fetch(`${BACKEND_URL}/ai/puzzle/submit`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                user_id: userId,
                puzzle_id: puzzleId,
                solved: false,
                time: startTime ? Math.floor((Date.now() - startTime) / 1000) : 10
              })
            });
            const result = await res.json();
            const { new_score, delta } = result;

            alert(`❌ 퍼즐 실패! 현재 점수: ${new_score} (${delta >= 0 ? '+' : ''}${delta})`);
          } catch (e) {
            console.error('오답 제출 실패:', e);
          }
        }
      } catch (e) {
        console.error('퍼즐 오류:', e);
      }
      return;
    }


    const piece = game.get(sourceSquare);
    if (!piece || piece.color !== game.turn()) return;

    if (isPromotionMove(sourceSquare, targetSquare)) {
      handlePromotion(sourceSquare, targetSquare);
      return;
    }

    try {
      const legalMoves = game.moves({ verbose: true });
      const matchedMove = legalMoves.find(
        (m) => m.from === sourceSquare && m.to === targetSquare
      );

      if (!matchedMove) {
        console.warn("⚠️ Illegal move:", sourceSquare, targetSquare);
        return;
      }

      const move = game.move(matchedMove);

      if (move === null) {
        setPosition(game.fen());
        return;
      }

      setPosition(game.fen());
      updateMovePairs(game.history({ verbose: true }));
      checkGameOver(game);

      try {
        const evalRes = await fetch(`${BACKEND_URL}/ai/eval`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fen: game.fen(), // 수를 둔 후의 FEN
            move: matchedMove.from + matchedMove.to
          })
        });
        const evalData = await evalRes.json();
        setMoveEval(evalData);
      } catch (e) {
        console.warn("move eval 실패:", e);
      }

      if (!puzzleActive && useAI && game.turn() === 'b' && !game.isGameOver()) {
        setTimeout(() => {
          playAIMove();
        }, 300);
      }
    } catch (error) {
      console.warn('잘못된 수입니다:', error);
      setPosition(game.fen()); // 원래 위치로 복원
    }
  };

  const startPuzzle = async () => {
    if (!userId) {
      alert("로그인 후 이용 가능합니다.");
      return;
    }

    try {
      console.log("🧩 퍼즐 시작 요청 중... userId:", userId);
      const res = await fetch(`${BACKEND_URL}/ai/puzzle?user_id=${userId}`);
      
      if (!res.ok) {
        throw new Error(`퍼즐 API 호출 실패: ${res.status} ${res.statusText}`);
      }

      const data = await res.json();
      console.log("✅ 퍼즐 API 응답:", data);

      const newPuzzle = new Chess(data.fen);

      setPuzzleFen(data.fen);
      setPuzzleGame(newPuzzle);
      setPosition(data.fen);
      setPuzzleSolution(data.solution);
      setPuzzleMessage('');
      setShowHint(false);
      setShowSolution(false);
      setPuzzleActive(true);
      setGame(newPuzzle);
      setUserMoves([]);
      setPuzzleId(data.puzzle_id); 
      setUserScore(data.score);
      setStartTime(Date.now()); 

      if (data.solution.length > 0) {
        const firstMoveUCI = data.solution[0];
        const legalMoves = newPuzzle.moves({ verbose: true });
        const autoMove = legalMoves.find(
          m => m.from + m.to + (m.promotion ?? '') === firstMoveUCI
        );

        if (autoMove) {
          setTimeout(() => {
            newPuzzle.move(autoMove);
            setGame(newPuzzle);
            setPosition(newPuzzle.fen());
            setUserMoves([firstMoveUCI]);
          }, 1000); // 🔁 1초 후 애니메이션
        }
      }
    } catch (err) {
      console.error("🚨 퍼즐 시작 중 에러:", err);
      alert("퍼즐을 불러오는데 실패했습니다. 콘솔을 확인하세요.");
    }
  };

  const resetGame = () => {
    const newGame = new Chess();
    setGame(newGame);
    setPosition(newGame.fen());
    setMovePairs([]);
    setWinnerMessage('');
  };

  useEffect(() => {
    if (!puzzleActive && useAI && game.turn() === 'b' && !game.isGameOver()) {
      const timer = setTimeout(() => {
        playAIMove();
      }, 300);
      return () => clearTimeout(timer); // cleanup
    }
  }, [game.fen(), useAI, puzzleActive]); 

  const fetchUserStats = async () => {
    if (!userId) return;
    try {
      const res = await fetch(`${BACKEND_URL}/ai/user/stats?user_id=${userId}`);
      const data = await res.json();
      setUserStats(data);
    } catch (e) {
      console.error("마이페이지 불러오기 실패:", e);
    }
  };

  const renderMyPage = () => {
    if (!userStats) return <p className="text-center mt-4">📡 불러오는 중...</p>;

    return (
      <div className="container mt-4">
        <h4 className="text-center mb-3">📊 마이페이지</h4>
        <div className="text-center mt-3">
          <button className="btn btn-outline-primary" onClick={() => setShowMyPage(false)}>
            🏠 메인페이지로 돌아가기
          </button>
        </div>

        {userStats.recent_games && (
          <>
            <h5 className="mt-4">🤖 최근 AI 대국 기록</h5>
            <table className="table table-bordered">
              <thead>
                <tr>
                  <th>게임 ID</th>
                  <th>결과</th>
                  <th>총 수</th>
                  <th>날짜</th>
                </tr>
              </thead>
              <tbody>
                {userStats.recent_games.map((g, idx) => (
                  <tr key={idx}>
                    <td>{g.game_id}</td>
                    <td>{g.result}</td>
                    <td>{g.moves} 수</td>
                    <td>{new Date(g.date).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <p><strong>현재 점수:</strong> {userStats.score}</p>
        <p><strong>전체 시도:</strong> {userStats.total}회</p>
        <p><strong>성공 횟수:</strong> {userStats.success}회</p>
        <p><strong>성공률:</strong> {userStats.success_rate}%</p>

        <h5 className="mt-4">🕓 최근 5개 퍼즐 기록</h5>
        <table className="table table-striped">
          <thead>
            <tr>
              <th>퍼즐 ID</th>
              <th>성공 여부</th>
              <th>걸린 시간</th>
              <th>날짜</th>
            </tr>
          </thead>
          <tbody>
            {userStats.recent.map((r, idx) => (
              <tr key={idx}>
                <td>{r.puzzle_id}</td>
                <td>{r.solved ? "✅ 성공" : "❌ 실패"}</td>
                <td>{r.time}s</td>
                <td>{new Date(r.date).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };
  
  const turn = game.turn() === 'w' ? '백' : '흑';
  const inCheck = game.inCheck() ? '체크!' : '';
  const gameOver = game.isGameOver();

  const renderAIModeToggle = () => (
    <div style={{ textAlign: 'center', marginTop: 10 }}>
      <label style={{ fontSize: 16, marginRight: 10 }}>AI와 대국하기</label>
      <input
        type="checkbox"
        checked={useAI}
        onChange={() => setUseAI(!useAI)}
        style={{ transform: 'scale(1.2)' }}
      />
    </div>
  );

  const renderAIDifficultySelector = () => (
    <div style={{ textAlign: 'center', marginTop: 10 }}>
      <label style={{ fontSize: 16, marginRight: 10 }}>난이도</label>
      <select
        value={aiLevel}
        onChange={(e) => setAiLevel(e.target.value as 'easy' | 'medium' | 'hard')}
        style={{ fontSize: 16, padding: 5 }}
      >
        <option value="easy">🙃 바보 수준</option>
        <option value="medium">😐 사람 같은 수준</option>
        <option value="hard">🤖 마스터 AI</option>
      </select>
    </div>
  );

  const renderPromotionModal = () =>
    promotionModalOpen && (
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
        <div style={{ background: 'white', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
          <h3>승급할 기물을 선택하세요</h3>
          <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: 10 }}>
            {(['q', 'r', 'b', 'n'] as const).map((p) => (
              <button
                key={p}
                onClick={() => confirmPromotion(p)}
                style={{ fontSize: 20, margin: '0 10px', padding: '10px 20px', borderRadius: 8, cursor: 'pointer' }}>
                {{ q: '퀸', r: '룩', b: '비숍', n: '나이트' }[p]}
              </button>
            ))}
          </div>
        </div>
      </div>
    );

  
  const renderAuthForm = () => (
    <div className="container d-flex justify-content-center align-items-center" style={{ minHeight: '100vh' }}>
      <div className="card shadow auth-box">
        <div className="card-body">
          <h3 className="text-center mb-4">{mode === 'login' ? '🔐 로그인' : '✍️ 회원가입'}</h3>
          <input type="email" className="form-control mb-3" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" className="form-control mb-4" placeholder="비밀번호" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className={`btn ${mode === 'login' ? 'btn-primary' : 'btn-success'} w-100 mb-3`} onClick={mode === 'login' ? handleLogin : handleSignup}>
            {mode === 'login' ? '로그인' : '회원가입'}
          </button>
          <p className="text-center">
            {mode === 'login' ? '계정이 없으신가요?' : '이미 계정이 있으신가요?'}{' '}
            <button className="btn btn-link p-0" onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}>
              {mode === 'login' ? '회원가입' : '로그인'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );

  const playSolutionSequence = async () => {
    if (puzzleSolution.length === 0) return;

    const tempGame = new Chess(puzzleFen);
    for (const move of puzzleSolution) {
      await new Promise((resolve) => setTimeout(resolve, 1000)); // 1초 간격
      const legal = tempGame.moves({ verbose: true }).find(
        m => m.from + m.to + (m.promotion ?? '') === move
      );
      if (legal) {
        tempGame.move(legal);
        setGame(tempGame);
        setPosition(tempGame.fen());
      }
    }
  };

  return (
  <>
    {!userId ? (
      renderAuthForm()
    ) : showMyPage ? (
      renderMyPage()
    ) : (
      <>
        {/* 기존 UI 전체를 이 블록에 넣어야 합니다 */}
        <div className="text-center py-3 bg-light shadow-sm">
          <h4 className="fw-bold text-primary m-0">CheckmateAI ♟️</h4>
        </div>

        {/* 👤 로그인 후 이메일 + 로그아웃 */}
        <div className="d-flex flex-column align-items-center justify-content-center" style={{ marginTop: 60 }}>
          <p className="text-muted">✅ 로그인됨: {userEmail}</p>
          <button onClick={handleLogout} className="btn btn-outline-secondary">로그아웃</button>
        </div>

        {/* 마이페이지 버튼 */}
        <div className="text-center mt-3">
          <button
            className="btn btn-outline-dark"
            onClick={() => {
              setShowMyPage(true);
              fetchUserStats();
            }}
          >
            📊 마이페이지
          </button>
        </div>
        {renderPromotionModal()}
        {renderAIModeToggle()}
        {renderAIDifficultySelector()}
      <div style={{ textAlign: 'center', margin: '20px', fontWeight: 'bold', fontSize: 24, color: puzzleMessage.includes('정답') ? 'green' : puzzleMessage.includes('오답') ? 'red' : '#333' }}>
        {puzzleMessage.includes('정답') || puzzleMessage.includes('오답') ? '' :
          puzzleActive
            ? `🤔 퍼즐 진행 중 (${turn} 차례)`
            : gameOver
              ? `🛑 ${winnerMessage}`
              : `🎯 ${turn} 차례입니다 ${inCheck}`}
      </div>

      {puzzleActive && (
        <div style={{ textAlign: 'center', fontSize: 18, color: '#333' }}>
          {puzzleMessage}
        </div>
      )}

      {puzzleActive && (
        <div style={{ textAlign: 'center', margin: '12px 0' }}>
          <button
            onClick={() => setShowHint(true)}
            style={{ margin: '0 10px', padding: '6px 12px', borderRadius: 6, fontSize: 14 }}
          >
            💡 힌트 보기
          </button>
          {!showSolution && (
          <button
            onClick={async () => {
              setShowSolution(true);
              setPuzzleActive(false);
              setUseAI(false);
              setPuzzleMessage('');
              setWinnerMessage('');
              try {
                await fetch(`${BACKEND_URL}/ai/puzzle/submit`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    user_id: userId,
                    puzzle_id: puzzleId,
                    solved: false,
                    time: 10
                  })
                });
                alert("정답을 열람하였습니다. 점수가 감소합니다.");
                await playSolutionSequence();  // ✅ 정답 수순 재생
              } catch (e) {
                console.error('정답 열람 실패:', e);
              }
            }}
            style={{
              marginRight: 10,
              padding: '10px 20px',
              backgroundColor: '#607D8B',
              color: 'white',
              borderRadius: 8,
            }}
          >
            ▶️ 정답 수순 보기
          </button>
          )}
          <div style={{ marginTop: 10 }}>
            {showHint && <div style={{ fontStyle: 'italic', color: '#555' }}>힌트: {puzzleHint || '없음'}</div>}
            {showSolution && (
              <div style={{ marginTop: 5 }}>
                정답 수순: {puzzleSolution.join(' → ')}
              </div>
            )}
          </div>
        </div>
      )}

      {!puzzleActive && (puzzleMessage.includes('정답') || puzzleMessage.includes('오답')) && (
        <div style={{ textAlign: 'center', margin: '20px' }}>
          {!showSolution && (
            <button
              onClick={playSolutionSequence}
              style={{
                marginRight: 10,
                padding: '10px 20px',
                backgroundColor: '#607D8B',
                color: 'white',
                borderRadius: 8,
              }}
            >
              ▶️ 정답 수순 보기
            </button>
          )}
          <button
            onClick={startPuzzle}
            style={{
              padding: '10px 20px',
              backgroundColor: '#FF9800',
              color: 'white',
              borderRadius: 8,
            }}
          >
            ▶️ 다음 퍼즐 도전
          </button>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'center', gap: 24 }}>
        <div style={{ width: boardWidth, boxShadow: '0 8px 24px rgba(0, 0, 0, 0.2)', borderRadius: 12, padding: 12, background: 'linear-gradient(145deg, #e4cfa0, #f0d9b5)' }}>
          <Chessboard
            position={position}
            onDrop={onDrop}
            width={boardWidth}
            draggable={true}
            transitionDuration={200}
          />
        </div>

        {moveEval && (
          <div style={{ textAlign: 'center', marginTop: 10 }}>
            <div style={{ fontWeight: 'bold' }}>이 수의 예상 결과:</div>
            <div style={{ width: '80%', margin: '8px auto', height: 16, display: 'flex', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ width: `${moveEval.white}%`, background: '#ffffff' }} title={`백: ${moveEval.white}%`} />
              <div style={{ width: `${moveEval.draw}%`, background: '#a0a0a0' }} title={`무승부: ${moveEval.draw}%`} />
              <div style={{ width: `${moveEval.black}%`, background: '#000000' }} title={`흑: ${moveEval.black}%`} />
            </div>
          </div>
        )}


        <div style={{ minWidth: 160, maxHeight: boardWidth, overflowY: 'auto', background: '#fffbe6', padding: 12, borderRadius: 8, boxShadow: '0 0 8px rgba(0,0,0,0.1)' }}>
          <h4>수순</h4>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {movePairs.map(([white, black], i) => (
                <li key={i}>
                  {i + 1}. {white} {black}
                </li>
              ))}
            </ul>
        </div>
      </div>
      
      <button
        onClick={startPuzzle}
        style={{ display: 'block', margin: '20px auto', padding: '12px 24px', fontWeight: 'bold', fontSize: 16, borderRadius: 8, border: 'none', backgroundColor: '#2196F3', color: 'white', cursor: 'pointer', boxShadow: '0 4px 10px rgba(0, 0, 0, 0.2)', transition: 'all 0.2s ease-in-out' }}
        onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#1976D2')}
        onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#2196F3')}
      >
        🧩 퍼즐 시작하기
      </button>

      <button
        onClick={resetGame}
        style={{ display: 'block', margin: '20px auto', padding: '12px 24px', fontWeight: 'bold', fontSize: 16, borderRadius: 8, border: 'none', backgroundColor: '#4CAF50', color: 'white', cursor: 'pointer', boxShadow: '0 4px 10px rgba(0, 0, 0, 0.2)', transition: 'all 0.2s ease-in-out' }}
        onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#45A049')}
        onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#4CAF50')}
      >
        🔁 게임 다시 시작
      </button>
    </>
        )}
    </>
  );
}

export default App;
