import React, { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChessBoard } from './components/ChessBoard';
import { GameInfo } from './components/GameInfo';
import { Timer } from './components/Timer';
import { PlayerCard } from './components/PlayerCard';
import { GameModeSelector } from './components/GameModeSelector';
import { PuzzleMode } from './components/PuzzleMode';
import { GameAnalysis } from './components/GameAnalysis';
import { useChessGame } from './hooks/useChessGame';
import { useChessTimer } from './hooks/useChessTimer';
import './App.css';

function App() {
  const { game, gameState, makeMove, resetGame, undoMove } = useChessGame();
  const {
    whiteTime,
    blackTime,
    activeColor,
    formatTime,
    isRunning,
    start,
    pause,
    switchTurn,
    reset: resetTimer
  } = useChessTimer(600);

  const [showModeSelector, setShowModeSelector] = useState(true);
  const [gameMode, setGameMode] = useState<string>('vs-player');
  const [aiDifficulty, setAiDifficulty] = useState<number>(5);
  const [selectedPlayer, setSelectedPlayer] = useState<string>('');
  const [boardOrientation, setBoardOrientation] = useState<'white' | 'black'>('white');
  const [whitePlayer, setWhitePlayer] = useState({ name: '플레이어 1', rating: 1500, isAI: false });
  const [blackPlayer, setBlackPlayer] = useState({ name: '플레이어 2', rating: 1500, isAI: false });

  // 게임이 시작되면 타이머 시작
  useEffect(() => {
    if (!showModeSelector && !isRunning) {
      start();
    }
  }, [showModeSelector, isRunning, start]);

  // 턴이 바뀔 때마다 타이머 전환
  useEffect(() => {
    if (!gameState.isGameOver && isRunning) {
      const newActiveColor = gameState.turn === 'w' ? 'white' : 'black';
      if (activeColor !== newActiveColor) {
        switchTurn();
      }
    }
  }, [gameState.turn, gameState.isGameOver]);

  // 게임 종료 시 타이머 정지
  useEffect(() => {
    if (gameState.isGameOver) {
      pause();
    }
  }, [gameState.isGameOver, pause]);

  const makeAIMove = useCallback(async () => {
    try {
      // Stockfish AI 호출 (서버 API 필요)
      const response = await fetch('http://localhost:5000/ai/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fen: gameState.fen,
          difficulty: aiDifficulty
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.move) {
          const from = data.move.substring(0, 2);
          const to = data.move.substring(2, 4);
          const promotion = data.move.length > 4 ? data.move[4] : undefined;
          makeMove({ from, to, promotion });
        }
      }
    } catch (error) {
      console.error('AI move failed:', error);
      // Fallback: 랜덤 합법수
      const moves = game.moves({ verbose: true });
      if (moves.length > 0) {
        const randomMove = moves[Math.floor(Math.random() * moves.length)];
        makeMove({
          from: randomMove.from,
          to: randomMove.to,
          promotion: randomMove.promotion
        });
      }
    }
  }, [game, gameState.fen, aiDifficulty, makeMove]);

  const makeTopPlayerMove = useCallback(async () => {
    try {
      // TOP Player AI 호출
      const response = await fetch('http://localhost:5000/ai/top-player/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fen: gameState.fen,
          player_name: selectedPlayer,
          time_limit: 2.0
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.move) {
          const from = data.move.substring(0, 2);
          const to = data.move.substring(2, 4);
          const promotion = data.move.length > 4 ? data.move[4] : undefined;
          makeMove({ from, to, promotion });
        }
      }
    } catch (error) {
      console.error('TOP Player move failed:', error);
      // Fallback: 랜덤 합법수
      const moves = game.moves({ verbose: true });
      if (moves.length > 0) {
        const randomMove = moves[Math.floor(Math.random() * moves.length)];
        makeMove({
          from: randomMove.from,
          to: randomMove.to,
          promotion: randomMove.promotion
        });
      }
    }
  }, [game, gameState.fen, selectedPlayer, makeMove]);

  // AI 수 실행
  useEffect(() => {
    if (gameMode === 'vs-ai' && gameState.turn === 'b' && !gameState.isGameOver) {
      const timer = setTimeout(() => {
        makeAIMove();
      }, 500);
      return () => clearTimeout(timer);
    }
    
    if (gameMode === 'vs-top-player' && gameState.turn === 'b' && !gameState.isGameOver) {
      const timer = setTimeout(() => {
        makeTopPlayerMove();
      }, 700);
      return () => clearTimeout(timer);
    }
  }, [gameState.fen, gameMode, gameState.turn, gameState.isGameOver, makeAIMove, makeTopPlayerMove]);

  const handlePieceDrop = (sourceSquare: string, targetSquare: string): boolean => {
    // 프로모션 체크 - FEN에서 현재 보드 상태 확인
    const piece = game.get(sourceSquare as any);
    const isPawn = piece && piece.type === 'p';
    const isPromotion = isPawn && (targetSquare[1] === '8' || targetSquare[1] === '1');

    const result = makeMove({
      from: sourceSquare,
      to: targetSquare,
      promotion: isPromotion ? 'q' : undefined
    });

    return result;
  };

  const handleModeSelect = (mode: string, difficulty?: number, player?: string) => {
    setGameMode(mode);
    
    if (mode === 'puzzle') {
      // 퍼즐 모드는 별도 컴포넌트로 처리
      setShowModeSelector(false);
      return;
    }
    
    if (mode === 'vs-ai') {
      setAiDifficulty(difficulty || 5);
      setWhitePlayer({ name: '나', rating: 1500, isAI: false });
      setBlackPlayer({ name: `Stockfish Lv.${difficulty}`, rating: 2000 + (difficulty || 5) * 100, isAI: true });
    } else if (mode === 'vs-top-player' && player) {
      setSelectedPlayer(player);
      setWhitePlayer({ name: '나', rating: 1500, isAI: false });
      setBlackPlayer({ name: player, rating: 2800, isAI: true });
    } else {
      setWhitePlayer({ name: '플레이어 1', rating: 1500, isAI: false });
      setBlackPlayer({ name: '플레이어 2', rating: 1500, isAI: false });
    }
    
    setShowModeSelector(false);
    resetGame();
    resetTimer();
  };

  const handleReset = () => {
    resetGame();
    resetTimer();
    start();
  };

  const handleUndo = () => {
    undoMove();
  };

  const toggleBoardOrientation = () => {
    setBoardOrientation(prev => prev === 'white' ? 'black' : 'white');
  };

  return (
    <div className="app">
      <AnimatePresence>
        {showModeSelector && (
          <GameModeSelector
            onSelectMode={handleModeSelect}
            onClose={() => setShowModeSelector(false)}
          />
        )}
      </AnimatePresence>

      {!showModeSelector && gameMode === 'analysis' && (
        <GameAnalysis
          onBackToMenu={() => setShowModeSelector(true)}
        />
      )}

      {!showModeSelector && gameMode === 'puzzle' && (
        <PuzzleMode
          onBackToMenu={() => setShowModeSelector(true)}
        />
      )}

      {!showModeSelector && gameMode !== 'puzzle' && gameMode !== 'analysis' && (
        <motion.div
          className="game-container"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
        >
          <div className="game-header">
            <motion.h1
              className="game-title"
              initial={{ y: -50 }}
              animate={{ y: 0 }}
              transition={{ type: 'spring', stiffness: 120 }}
            >
              ♟️ CheckmateAI
            </motion.h1>
            <motion.button
              className="mode-btn"
              onClick={() => setShowModeSelector(true)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              게임 모드 변경
            </motion.button>
          </div>

          <div className="game-layout">
            <div className="left-panel">
              <PlayerCard
                name={blackPlayer.name}
                rating={blackPlayer.rating}
                isAI={blackPlayer.isAI}
                color="black"
              />
              
              <Timer
                whiteTime={whiteTime}
                blackTime={blackTime}
                activeColor={activeColor}
                formatTime={formatTime}
                isRunning={isRunning}
              />
            </div>

            <div className="center-panel">
              <ChessBoard
                position={gameState.fen}
                onPieceDrop={handlePieceDrop}
                boardOrientation={boardOrientation}
                animationDuration={300}
                arePiecesDraggable={!gameState.isGameOver}
              />
              
              <motion.button
                className="flip-board-btn"
                onClick={toggleBoardOrientation}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                🔄 보드 뒤집기
              </motion.button>
            </div>

            <div className="right-panel">
              <PlayerCard
                name={whitePlayer.name}
                rating={whitePlayer.rating}
                isAI={whitePlayer.isAI}
                color="white"
              />

              <GameInfo
                turn={gameState.turn}
                isCheck={gameState.isCheck}
                isCheckmate={gameState.isCheckmate}
                isDraw={gameState.isDraw}
                moveHistory={gameState.moveHistory}
                onReset={handleReset}
                onUndo={handleUndo}
              />
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

export default App;
