import React from 'react';
import { motion } from 'framer-motion';
import './GameInfo.css';

interface GameInfoProps {
  turn: 'w' | 'b';
  isCheck: boolean;
  isCheckmate: boolean;
  isDraw: boolean;
  moveHistory: string[];
  onReset: () => void;
  onUndo: () => void;
}

export const GameInfo: React.FC<GameInfoProps> = ({
  turn,
  isCheck,
  isCheckmate,
  isDraw,
  moveHistory,
  onReset,
  onUndo
}) => {
  const getMoveNotation = () => {
    const moves: Array<{ white: string; black?: string }> = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      moves.push({
        white: moveHistory[i],
        black: moveHistory[i + 1]
      });
    }
    return moves;
  };

  const getStatusMessage = () => {
    if (isCheckmate) {
      return `체크메이트! ${turn === 'w' ? '흑' : '백'}팀 승리!`;
    }
    if (isDraw) {
      return '무승부!';
    }
    if (isCheck) {
      return `체크! ${turn === 'w' ? '백' : '흑'}팀 차례`;
    }
    return `${turn === 'w' ? '백' : '흑'}팀 차례`;
  };

  return (
    <div className="game-info">
      <motion.div 
        className="status-panel"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <h2 className={`status-message ${isCheck ? 'check' : ''} ${isCheckmate ? 'checkmate' : ''}`}>
          {getStatusMessage()}
        </h2>
        <div className="turn-indicator">
          <div className={`piece-indicator ${turn === 'w' ? 'active' : ''}`}>
            <div className="white-piece">♔</div>
            <span>백</span>
          </div>
          <div className={`piece-indicator ${turn === 'b' ? 'active' : ''}`}>
            <div className="black-piece">♚</div>
            <span>흑</span>
          </div>
        </div>
      </motion.div>

      <div className="move-history">
        <h3>기보 ({moveHistory.length}수)</h3>
        <div className="moves-list">
          {moveHistory.length === 0 ? (
            <div style={{ textAlign: 'center', opacity: 0.6, padding: '20px' }}>
              아직 기보가 없습니다
            </div>
          ) : (
            getMoveNotation().map((move, index) => (
              <div key={index} className="move-pair">
                <span className="move-number">{index + 1}.</span>
                <span className="move-white">{move.white}</span>
                {move.black && <span className="move-black">{move.black}</span>}
              </div>
            ))
          )}
        </div>
      </div>

      <div className="controls">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onUndo}
          className="control-btn undo-btn"
          disabled={moveHistory.length === 0}
        >
          ↶ 무르기
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onReset}
          className="control-btn reset-btn"
        >
          ↻ 새 게임
        </motion.button>
      </div>
    </div>
  );
};
