import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FaArrowLeft, FaChartLine, FaExclamationTriangle, FaTimes, FaCheckCircle, FaUndo, FaRedo, FaCrown, FaBolt } from 'react-icons/fa';
import { ChessBoard } from './ChessBoard';
import { useChessGame } from '../hooks/useChessGame';
import { Chess } from 'chess.js';
import './GameAnalysis.css';

interface GameAnalysisProps {
  onBackToMenu?: () => void;
}

interface MoveAnalysis {
  move: string;
  moveNumber: number;
  evaluation: number;
  bestMove: string;
  classification: 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder';
  evalDiff: number;
}

export const GameAnalysis: React.FC<GameAnalysisProps> = ({ onBackToMenu }) => {
  const { game, gameState, makeMove, resetGame, undoMove } = useChessGame();
  const [analysis, setAnalysis] = useState<MoveAnalysis[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [gameFinished, setGameFinished] = useState(false);
  const [error, setError] = useState('');
  const [showStats, setShowStats] = useState(true);
  const moveCountRef = React.useRef(0);
  const [lastMoveEval, setLastMoveEval] = useState<number | null>(null);
  const movesListRef = React.useRef<HTMLDivElement>(null);

  // 실시간 분석: 수가 두어질 때마다 분석
  React.useEffect(() => {
    const analyzeMoveAsync = async () => {
      if (gameState.moveHistory.length === 0) return;
      
      // 마지막 수만 분석 (전체 게임 분석은 너무 느림)
      if (gameState.moveHistory.length > moveCountRef.current) {
        moveCountRef.current = gameState.moveHistory.length;
        setIsAnalyzing(true);
        
        try {
          const pgn = game.pgn();
          const response = await fetch('http://localhost:5000/ai/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pgn })
          });

          if (response.ok) {
            const data = await response.json();
            setAnalysis(data.analysis);
            // 마지막 평가값 저장
            if (data.analysis.length > 0) {
              setLastMoveEval(data.analysis[data.analysis.length - 1].evaluation);
            }
            // 자동 스크롤
            setTimeout(() => {
              if (movesListRef.current) {
                movesListRef.current.scrollTop = movesListRef.current.scrollHeight;
              }
            }, 100);
          }
        } catch (err) {
          console.error('분석 오류:', err);
          setError('Stockfish 분석 실패. 서버가 실행 중인지 확인하세요.');
        } finally {
          setIsAnalyzing(false);
        }
      }
    };

    analyzeMoveAsync();
  }, [gameState.moveHistory.length]);

  // 게임 종료 체크
  React.useEffect(() => {
    if (gameState.isGameOver && !gameFinished) {
      setGameFinished(true);
    }
  }, [gameState.isGameOver]);

  const handlePieceDrop = (sourceSquare: string, targetSquare: string): boolean => {
    if (gameState.isGameOver) return false;

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

  const handleReset = () => {
    resetGame();
    setAnalysis([]);
    setGameFinished(false);
    setError('');
    moveCountRef.current = 0;
  };

  const handleUndo = () => {
    undoMove();
    // 분석 결과도 마지막 수 제거
    if (analysis.length > 0) {
      setAnalysis(prev => prev.slice(0, -1));
    }
  };

  const getClassificationColor = (classification: string) => {
    switch (classification) {
      case 'best': return '#22c55e';
      case 'good': return '#84cc16';
      case 'inaccuracy': return '#fbbf24';
      case 'mistake': return '#f97316';
      case 'blunder': return '#ef4444';
      default: return '#94a3b8';
    }
  };

  const getClassificationIcon = (classification: string) => {
    switch (classification) {
      case 'best': return <FaCheckCircle />;
      case 'good': return <FaCheckCircle />;
      case 'inaccuracy': return <FaExclamationTriangle />;
      case 'mistake': return <FaExclamationTriangle />;
      case 'blunder': return <FaTimes />;
      default: return null;
    }
  };

  const getClassificationText = (classification: string) => {
    switch (classification) {
      case 'best': return '최선';
      case 'good': return '좋음';
      case 'inaccuracy': return '부정확';
      case 'mistake': return '실수';
      case 'blunder': return '블런더';
      default: return '';
    }
  };

  const calculateAccuracy = () => {
    if (analysis.length === 0) return 0;
    const goodMoves = analysis.filter(m => 
      m.classification === 'best' || m.classification === 'good'
    ).length;
    return Math.round((goodMoves / analysis.length) * 100);
  };

  return (
    <div className="game-analysis-container">
      {/* 헤더 */}
      <motion.div 
        className="analysis-header"
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
      >
        <motion.button
          className="back-button"
          onClick={onBackToMenu}
          whileHover={{ scale: 1.05, x: -5 }}
          whileTap={{ scale: 0.95 }}
        >
          <FaArrowLeft /> 메인 메뉴
        </motion.button>
        <div className="header-title">
          <FaChartLine className="title-icon" />
          <h1>실시간 게임 분석</h1>
          {isAnalyzing && <span className="analyzing-badge-small">분석 중...</span>}
        </div>
      </motion.div>

      <div className="analysis-content">
        <div className="analysis-left">
          <div className="board-section">
            <ChessBoard
              position={gameState.fen}
              onPieceDrop={handlePieceDrop}
              arePiecesDraggable={!gameState.isGameOver}
              animationDuration={300}
              customBoardStyle={{
                width: '100%',
                maxWidth: '600px',
                margin: '0 auto'
              }}
            />
            
            <div className="game-controls">
              <button
                className="control-btn"
                onClick={handleUndo}
                disabled={gameState.moveHistory.length === 0}
              >
                <FaUndo /> 무르기
              </button>
              <button
                className="control-btn reset-btn"
                onClick={handleReset}
              >
                <FaRedo /> 새 게임
              </button>
            </div>
          </div>

        </div>

        <div className="analysis-right">
          {/* 수순 분석 패널 */}
          <motion.div 
            className="moves-panel"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            <div className="moves-header">
              <h3>📊 실시간 분석</h3>
              {!gameFinished && (
                <div className="live-indicator">
                  <span className="pulse-dot"></span> LIVE
                </div>
              )}
            </div>
            
            <div className="moves-list" ref={movesListRef}>
              {analysis.length === 0 && (
                <div className="empty-state">
                  <p>체스를 두면 실시간으로 분석이 시작됩니다</p>
                </div>
              )}
                {analysis.map((move, index) => (
                  <motion.div
                    key={index}
                    className={`move-item ${move.classification}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    whileHover={{ scale: 1.02, x: 5 }}
                  >
                    <div className="move-content">
                      <div className="move-header">
                        <span className="move-number">{move.moveNumber}.</span>
                        <span className="move-notation">{move.move}</span>
                        <motion.span 
                          className={`eval-badge ${move.evaluation >= 0 ? 'positive' : 'negative'}`}
                          animate={{ scale: [1, 1.1, 1] }}
                          transition={{ duration: 0.3 }}
                        >
                          {move.evaluation > 0 ? '+' : ''}{move.evaluation.toFixed(1)}
                        </motion.span>
                      </div>
                      
                      <div className={`classification-badge ${move.classification}`}>
                        {getClassificationIcon(move.classification)}
                        {getClassificationText(move.classification)}
                      </div>
                    </div>
                    
                    {move.classification !== 'best' && move.classification !== 'good' && (
                      <div className="move-details">
                        <div className="best-move-suggestion">
                          💡 최선수: <strong>{move.bestMove}</strong>
                        </div>
                        <div className="eval-bar-mini">
                          <div 
                            className="eval-fill" 
                            style={{ 
                              width: `${Math.min(Math.abs(move.evaluation) * 10, 100)}%`,
                              backgroundColor: move.evaluation >= 0 ? '#4ade80' : '#ef4444'
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </motion.div>
                ))}
                {analysis.length === 0 && (
                  <div className="empty-state">
                    <p>체스를 두면 실시간으로 분석이 시작됩니다</p>
                  </div>
                )}
              </div>
            </motion.div>
          
          {/* 분석 대기 중 - 제거됨 */}
          {false && (
            <motion.div 
              className="moves-panel"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
            >
              <div className="moves-header">
                <h3>📝 진행 중인 게임</h3>
                <div className="analyzing-indicator">
                  <span className="spinner-small"></span> 분석 중
                </div>
              </div>
              
              <div className="moves-list simple">
                {gameState.moveHistory.map((move, index) => (
                  <motion.div 
                    key={index} 
                    className="move-item-simple"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.03 }}
                  >
                    <span className="move-number">{Math.floor(index / 2) + 1}.</span>
                    <span className="move-notation">{move}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* 통계 패널 */}
          <motion.div 
            className="stats-panel"
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
              <div className="stats-header">
                <h3>
                  <FaBolt /> {gameFinished ? '최종 통계' : '실시간 통계'}
                </h3>
              </div>
              
              <div className="stats-grid">
                <motion.div 
                  className="stat-card"
                  whileHover={{ scale: 1.05, y: -5 }}
                >
                  <div className="stat-label">정확도</div>
                  <div className="stat-value big">{calculateAccuracy()}%</div>
                </motion.div>
                
                <motion.div 
                  className="stat-card"
                  whileHover={{ scale: 1.05, y: -5 }}
                >
                  <div className="stat-label">분석된 수</div>
                  <div className="stat-value">{analysis.length}</div>
                </motion.div>
                
                <motion.div 
                  className="stat-card error-card"
                  whileHover={{ scale: 1.05, y: -5 }}
                >
                  <div className="stat-label">블런더</div>
                  <div className="stat-value error">
                    {analysis.filter(m => m.classification === 'blunder').length}
                  </div>
                </motion.div>
                
                <motion.div 
                  className="stat-card warning-card"
                  whileHover={{ scale: 1.05, y: -5 }}
                >
                  <div className="stat-label">실수</div>
                  <div className="stat-value warning">
                    {analysis.filter(m => m.classification === 'mistake').length}
                  </div>
                </motion.div>
              </div>
            </motion.div>

          {/* 게임 상태 */}
          {(gameState.isGameOver || error) && (
            <motion.div 
              className="game-status-panel"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
            >
              {gameState.isGameOver && (
                <div className="game-over-message">
                  <FaCrown className="crown-icon" />
                  <h4>게임 종료!</h4>
                  <p>
                    {gameState.isCheckmate 
                      ? `체크메이트! ${gameState.turn === 'w' ? '흑' : '백'}의 승리`
                      : gameState.isDraw 
                      ? '무승부'
                      : '게임 종료'
                    }
                  </p>
                </div>
              )}
              
              {error && (
                <div className="error-message">
                  <FaTimes /> {error}
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};
