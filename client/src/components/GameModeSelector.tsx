import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FaTimes } from 'react-icons/fa';
import './GameModeSelector.css';

interface GameMode {
  id: string;
  title: string;
  description: string;
  icon: string;
}

interface GameModeSelectorProps {
  onSelectMode: (mode: string, difficulty?: number, player?: string) => void;
  onClose: () => void;
}

export const GameModeSelector: React.FC<GameModeSelectorProps> = ({
  onSelectMode,
  onClose
}) => {
  const [selectedMode, setSelectedMode] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<number>(5);
  const [selectedPlayer, setSelectedPlayer] = useState<string>('');

  const gameModes: GameMode[] = [
    {
      id: 'vs-ai',
      title: 'AI와 대결',
      description: 'Stockfish AI와 체스 게임을 즐겨보세요',
      icon: '🤖'
    },
    {
      id: 'vs-player',
      title: '플레이어 대결',
      description: '로컬에서 친구와 함께 플레이하세요',
      icon: '👥'
    },
    {
      id: 'vs-top-player',
      title: 'TOP 플레이어',
      description: '실제 프로 선수의 플레이 스타일과 대결',
      icon: '🏆'
    },
    {
      id: 'puzzle',
      title: '퍼즐 모드',
      description: '체스 전술 퍼즐을 풀어보세요',
      icon: '🧩'
    },
    {
      id: 'analysis',
      title: '게임 분석',
      description: '체스 게임을 분석하고 개선하세요',
      icon: '📊'
    }
  ];

  const topPlayers = [
    { name: '매그너스 칼슨', rating: 2830, style: 'aggressive' },
    { name: '이안 네포므냐치', rating: 2750, style: 'positional' },
    { name: '딩 리렌', rating: 2780, style: 'tactical' },
    { name: '파비아노 카루아나', rating: 2800, style: 'solid' },
    { name: '알리레자 피루자', rating: 2785, style: 'dynamic' }
  ];

  const handleModeClick = (modeId: string) => {
    setSelectedMode(modeId);
  };

  const handleStart = () => {
    if (selectedMode === 'vs-ai') {
      onSelectMode('vs-ai', difficulty);
    } else if (selectedMode === 'vs-top-player' && selectedPlayer) {
      onSelectMode('vs-top-player', difficulty, selectedPlayer);
    } else {
      onSelectMode(selectedMode || 'vs-player');
    }
  };

  return (
    <motion.div
      className="game-mode-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="game-mode-modal"
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.8, opacity: 0 }}
      >
        <h2 className="modal-title">♟️ CheckmateAI</h2>
        <p className="modal-subtitle">당신의 체스 여정을 시작하세요</p>

        <div className="game-modes-grid">
          {gameModes.map((mode) => (
            <motion.div
              key={mode.id}
              className={`game-mode-card ${selectedMode === mode.id ? 'selected' : ''}`}
              onClick={() => handleModeClick(mode.id)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <div className="mode-icon">{mode.icon}</div>
              <h3>{mode.title}</h3>
              <p>{mode.description}</p>
            </motion.div>
          ))}
        </div>

        <AnimatePresence>
          {selectedMode === 'vs-ai' && (
            <motion.div
              className="difficulty-selector"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
            >
              <h3>난이도 선택</h3>
              <div className="difficulty-slider">
                <input
                  type="range"
                  min="1"
                  max="20"
                  value={difficulty}
                  onChange={(e) => setDifficulty(Number(e.target.value))}
                />
                <span className="difficulty-value">레벨 {difficulty}</span>
              </div>
            </motion.div>
          )}

          {selectedMode === 'vs-top-player' && (
            <motion.div
              className="player-selector"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
            >
              <h3>선수 선택</h3>
              <div className="players-list">
                {topPlayers.map((player) => (
                  <motion.div
                    key={player.name}
                    className={`player-option ${selectedPlayer === player.name ? 'selected' : ''}`}
                    onClick={() => setSelectedPlayer(player.name)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <div className="player-info-option">
                      <span className="player-name-option">{player.name}</span>
                      <span className="player-rating-option">⭐ {player.rating}</span>
                    </div>
                    <span className="player-style">{player.style}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.button
          className="start-btn"
          onClick={handleStart}
          disabled={!selectedMode || (selectedMode === 'vs-top-player' && !selectedPlayer)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          게임 시작
        </motion.button>
      </motion.div>
    </motion.div>
  );
};
