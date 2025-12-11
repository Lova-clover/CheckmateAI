import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { FaLightbulb, FaEye, FaArrowLeft, FaTrophy, FaCheckCircle, FaTimesCircle, FaChevronRight } from 'react-icons/fa';
import { ChessBoard } from './ChessBoard';
import { useChessGame } from '../hooks/useChessGame';
import './PuzzleMode.css';

interface PuzzleModeProps {
  difficulty?: string;
  onBackToMenu?: () => void;
}

interface Puzzle {
  puzzle_id: string;
  fen: string;
  solution: string[];
  difficulty: string;
  theme: string;
  rating: number;
}

export const PuzzleMode: React.FC<PuzzleModeProps> = ({
  difficulty = 'medium',
  onBackToMenu
}) => {
  const { game, gameState, makeMove, resetGame, loadFen, undoMove } = useChessGame();
  const [currentPuzzle, setCurrentPuzzle] = useState<Puzzle | null>(null);
  const [loading, setLoading] = useState(false);
  const [userMoves, setUserMoves] = useState<string[]>([]);
  const [currentSolutionIndex, setCurrentSolutionIndex] = useState(0);
  const [puzzleStatus, setPuzzleStatus] = useState<'solving' | 'correct' | 'incorrect' | 'hint-shown'>('solving');
  const [hint, setHint] = useState<string>('');
  const [showSolution, setShowSolution] = useState(false);
  const [puzzlesSolved, setPuzzlesSolved] = useState(0);
  const [totalAttempts, setTotalAttempts] = useState(0);
  const [isShowingSolution, setIsShowingSolution] = useState(false);

  // 퍼즐 불러오기
  useEffect(() => {
    loadNewPuzzle();
  }, []);

  const loadNewPuzzle = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:5000/ai/puzzle?difficulty=${difficulty}`, {
        method: 'GET'
      });

      if (response.ok) {
        const data = await response.json();
        console.log('퍼즐 데이터:', data);
        setCurrentPuzzle(data);
        
        // FEN 로드 (loadFen 함수 사용하여 gameState도 함께 업데이트)
        const loaded = loadFen(data.fen);
        if (loaded) {
          console.log('퍼즐 FEN 로드 성공:', data.fen);
        } else {
          console.error('FEN 로드 실패');
        }
        
        // 상태 초기화
        setUserMoves([]);
        setCurrentSolutionIndex(0);
        setPuzzleStatus('solving');
        setHint('');
        setShowSolution(false);
        setIsShowingSolution(false);
      } else {
        console.error('퍼즐 로드 실패:', response.status, response.statusText);
        alert(`퍼즐을 불러올 수 없습니다. 서버가 실행 중인지 확인해주세요.
서버 실행: python server/ai_server.py`);
      }
    } catch (error) {
      console.error('퍼즐 로드 실패:', error);
      alert(`서버 연결 실패: ${error}
서버가 실행 중인지 확인해주세요 (http://localhost:5000)`);
    } finally {
      setLoading(false);
    }
  };

  const handlePieceDrop = (sourceSquare: string, targetSquare: string): boolean => {
    if (!currentPuzzle) return false;
    
    // correct 상태일 때만 이동 불가 (solving, hint-shown, incorrect는 가능)
    if (puzzleStatus === 'correct') return false;

    // 프로모션 체크
    const piece = game.get(sourceSquare as any);
    const isPawn = piece && piece.type === 'p';
    const isPromotion = isPawn && (targetSquare[1] === '8' || targetSquare[1] === '1');

    const result = makeMove({
      from: sourceSquare,
      to: targetSquare,
      promotion: isPromotion ? 'q' : undefined
    });

    if (!result) return false;

    // 수 검증
    const move = `${sourceSquare}${targetSquare}${isPromotion ? 'q' : ''}`;
    const expectedMove = currentPuzzle.solution[currentSolutionIndex];
    
    console.log('플레이어 수:', move);
    console.log('예상 수:', expectedMove);
    console.log('현재 인덱스:', currentSolutionIndex, '/', currentPuzzle.solution.length);
    
    if (move === expectedMove || move.substring(0, 4) === expectedMove.substring(0, 4)) {
      setUserMoves([...userMoves, move]);
      
      if (currentSolutionIndex + 1 >= currentPuzzle.solution.length) {
        // 퍼즐 완료!
        console.log('퍼즐 완료!');
        setPuzzleStatus('correct');
        setPuzzlesSolved(puzzlesSolved + 1);
        setTotalAttempts(totalAttempts + 1);
      } else {
        // 다음 수로 이동
        const nextIndex = currentSolutionIndex + 1;
        setCurrentSolutionIndex(nextIndex);
        console.log('정답! 다음 수로 이동');
        
        // AI(퍼즐)의 응수를 자동으로 두기
        if (nextIndex < currentPuzzle.solution.length) {
          setTimeout(() => {
            makePuzzleMove(nextIndex);
          }, 500);
        }
      }
    } else {
      // 오답 - undo하고 다시 시도 가능
      console.log('오답! 되돌립니다.');
      undoMove();
      setPuzzleStatus('incorrect');
      
      // 0.8초 후 즉시 다시 solving 상태로 (빠른 재시도 가능)
      setTimeout(() => {
        setPuzzleStatus('solving');
      }, 800);
    }

    return true;
  };
  
  // 퍼즐의 수를 두는 함수
  const makePuzzleMove = (index: number) => {
    if (!currentPuzzle || index >= currentPuzzle.solution.length) return;
    
    const puzzleMove = currentPuzzle.solution[index];
    const from = puzzleMove.substring(0, 2);
    const to = puzzleMove.substring(2, 4);
    const promotion = puzzleMove.length > 4 ? puzzleMove[4] : undefined;
    
    console.log('퍼즐 AI 수:', puzzleMove);
    
    const result = makeMove({ from, to, promotion: promotion as any });
    
    if (result) {
      setCurrentSolutionIndex(index + 1);
      
      // 마지막 수인지 확인
      if (index + 1 >= currentPuzzle.solution.length) {
        console.log('퍼즐 완료!');
        setPuzzleStatus('correct');
        setPuzzlesSolved(puzzlesSolved + 1);
        setTotalAttempts(totalAttempts + 1);
      }
    }
  };

  const handleHint = async () => {
    if (!currentPuzzle || isShowingSolution) return;

    try {
      // 현재 퍼즐의 다음 수를 힌트로 표시
      const nextMove = currentPuzzle.solution[currentSolutionIndex];
      if (nextMove) {
        const from = nextMove.substring(0, 2);
        const to = nextMove.substring(2, 4);
        const hintText = `${from} → ${to}`;
        setHint(hintText);
        console.log('힌트:', hintText);
      } else {
        setHint('더 이상 힌트가 없습니다');
      }
    } catch (error) {
      console.error('힌트 로드 실패:', error);
      setHint('힌트를 가져올 수 없습니다');
    }
  };

  const handleShowSolution = () => {
    if (!currentPuzzle) return;
    
    // 현재 위치에서 다음 한 수만 보여주기
    if (currentSolutionIndex < currentPuzzle.solution.length) {
      const move = currentPuzzle.solution[currentSolutionIndex];
      const from = move.substring(0, 2);
      const to = move.substring(2, 4);
      const promotion = move.length > 4 ? move[4] : undefined;
      
      console.log(`정답 한 수 보여주기 ${currentSolutionIndex + 1}/${currentPuzzle.solution.length}: ${move}`);
      const result = makeMove({ from, to, promotion: promotion as any });
      
      if (result) {
        const newIndex = currentSolutionIndex + 1;
        setCurrentSolutionIndex(newIndex);
        setHint(`수 ${newIndex}/${currentPuzzle.solution.length}: ${from}→${to}`);
        
        // 마지막 수였다면 완료 처리
        if (newIndex >= currentPuzzle.solution.length) {
          setPuzzleStatus('correct');
          setPuzzlesSolved(puzzlesSolved + 1);
          setTotalAttempts(totalAttempts + 1);
          setIsShowingSolution(false);
        }
      }
    }
  };

  const handleNextPuzzle = () => {
    loadNewPuzzle();
  };

  if (loading) {
    return (
      <div className="puzzle-loading">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        >
          ♟️
        </motion.div>
        <p>퍼즐 로딩 중...</p>
      </div>
    );
  }

  if (!currentPuzzle) {
    return (
      <div className="puzzle-error">
        <p>퍼즐을 불러올 수 없습니다.</p>
        <button onClick={loadNewPuzzle}>다시 시도</button>
      </div>
    );
  }

  const successRate = totalAttempts > 0 
    ? Math.round((puzzlesSolved / totalAttempts) * 100) 
    : 0;

  return (
    <div className="puzzle-mode">
      <div className="puzzle-header">
        <motion.button
          className="back-btn"
          onClick={onBackToMenu}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <FaArrowLeft /> 메인 메뉴
        </motion.button>

        <div className="puzzle-info">
          <h2>♟️ 체스 퍼즐</h2>
          <div className="puzzle-details">
            <span className={`difficulty-badge ${currentPuzzle.difficulty}`}>
              {currentPuzzle.difficulty.toUpperCase()}
            </span>
            <span className="theme-badge">{currentPuzzle.theme}</span>
            <span className="rating-badge">⭐ {currentPuzzle.rating}</span>
          </div>
        </div>

        <div className="puzzle-stats">
          <div className="stat">
            <FaTrophy />
            <span>{puzzlesSolved} / {totalAttempts}</span>
          </div>
          <div className="stat">
            <span>{successRate}% 성공률</span>
          </div>
        </div>
      </div>

      <div className="puzzle-content">
        <div className="puzzle-board-section">
          {/* 현재 턴 표시 */}
          <div className="turn-indicator">
            {gameState.turn === 'w' ? (
              <div className="turn-badge white-turn">
                ⚪ 백의 차례
              </div>
            ) : (
              <div className="turn-badge black-turn">
                ⚫ 흑의 차례
              </div>
            )}
          </div>

          <ChessBoard
            position={gameState.fen}
            onPieceDrop={handlePieceDrop}
            boardOrientation="white"
            animationDuration={300}
            arePiecesDraggable={puzzleStatus === 'solving' && !isShowingSolution}
          />
        </div>

        <div className="puzzle-right">
          {/* 컨트롤 버튼들 */}
          <div className="puzzle-controls-panel">
            <h3>🎮 컨트롤</h3>
            
            <motion.button
              className="control-btn hint-btn"
              onClick={handleHint}
              disabled={puzzleStatus !== 'solving' || isShowingSolution}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <FaLightbulb /> 힌트 보기
            </motion.button>

            <motion.button
              className="control-btn solution-btn"
              onClick={handleShowSolution}
              disabled={isShowingSolution || currentSolutionIndex >= currentPuzzle.solution.length}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <FaEye /> 다음 수 보기 ({currentSolutionIndex}/{currentPuzzle.solution.length})
            </motion.button>

            <motion.button
              className="control-btn next-btn"
              onClick={handleNextPuzzle}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <FaChevronRight /> 다음 퍼즐
            </motion.button>
          </div>

          {/* 진행 상황 */}
          <div className="puzzle-progress">
            <h3>📊 진행 상황</h3>
            <div className="progress-info">
              <span>수 진행: {currentSolutionIndex} / {currentPuzzle.solution.length}</span>
            </div>
            <div className="progress-bar">
              <motion.div
                className="progress-fill"
                initial={{ width: 0 }}
                animate={{ 
                  width: `${(currentSolutionIndex / currentPuzzle.solution.length) * 100}%` 
                }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>

          {hint && (
            <motion.div
              className="hint-panel"
              initial={{ opacity: 0, y: -20, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.9 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
              <div className="hint-header">
                <FaLightbulb className="hint-icon" />
                <span className="hint-label">힌트</span>
              </div>
              <div className="hint-content">
                <span className="hint-move">{hint}</span>
              </div>
            </motion.div>
          )}

          {showSolution && (
            <motion.div
              className="solution-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <h3>정답</h3>
              <div className="solution-moves">
                {currentPuzzle.solution.map((move, index) => (
                  <span 
                    key={index}
                    className={index === currentSolutionIndex ? 'current-move' : ''}
                  >
                    {index + 1}. {move}
                  </span>
                ))}
              </div>
            </motion.div>
          )}

          {puzzleStatus === 'correct' && (
            <motion.div
              className="status-panel success"
              initial={{ opacity: 0, scale: 0.5, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ 
                type: "spring", 
                stiffness: 500, 
                damping: 25,
                delay: 0.1
              }}
            >
              <div className="status-icon-wrapper">
                <motion.div
                  animate={{ 
                    rotate: [0, 360],
                    scale: [1, 1.2, 1]
                  }}
                  transition={{ duration: 0.6 }}
                >
                  <FaCheckCircle className="status-icon" />
                </motion.div>
              </div>
              <h3>완벽합니다! 🎉</h3>
              <p>퍼즐을 성공적으로 해결했습니다!</p>
            </motion.div>
          )}

          {puzzleStatus === 'incorrect' && (
            <motion.div
              className="status-panel error"
              initial={{ opacity: 0, x: -20 }}
              animate={{ 
                opacity: 1, 
                x: [0, -10, 10, -10, 10, 0]
              }}
              transition={{ 
                opacity: { duration: 0.2 },
                x: { duration: 0.5 }
              }}
            >
              <FaTimesCircle className="status-icon" />
              <h3>아쉬워요!</h3>
              <p>다시 시도해보세요</p>
            </motion.div>
          )}

          {isShowingSolution && (
            <motion.div
              className="status-panel info"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <FaEye className="status-icon" />
              <p>정답을 보여주는 중...</p>
            </motion.div>
          )}

          <div className="puzzle-instructions">
            <h3>목표</h3>
            <p>{currentPuzzle.theme}를 찾아 최선의 수를 두세요!</p>
            <ul>
              <li>최선의 수 순서를 찾으세요</li>
              <li>모든 수가 정확해야 합니다</li>
              <li>힌트를 사용할 수 있습니다</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};
