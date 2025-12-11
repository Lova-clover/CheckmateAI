import React from 'react';
import { motion } from 'framer-motion';
import './Timer.css';

interface TimerProps {
  whiteTime: number;
  blackTime: number;
  activeColor: 'white' | 'black';
  formatTime: (seconds: number) => string;
  isRunning: boolean;
}

export const Timer: React.FC<TimerProps> = ({
  whiteTime,
  blackTime,
  activeColor,
  formatTime,
  isRunning
}) => {
  const isWhiteActive = activeColor === 'white';
  const isBlackActive = activeColor === 'black';
  const isWhiteLow = whiteTime < 60;
  const isBlackLow = blackTime < 60;

  return (
    <div className="timer-container">
      <motion.div
        className={`timer black-timer ${isBlackActive && isRunning ? 'active' : ''} ${isBlackLow ? 'low-time' : ''}`}
        animate={{
          scale: isBlackActive && isRunning ? [1, 1.02, 1] : 1,
        }}
        transition={{
          duration: 1,
          repeat: isBlackActive && isRunning ? Infinity : 0,
        }}
      >
        <div className="timer-label">흑</div>
        <div className="timer-display">{formatTime(blackTime)}</div>
        <div className="timer-piece">♚</div>
      </motion.div>

      <motion.div
        className={`timer white-timer ${isWhiteActive && isRunning ? 'active' : ''} ${isWhiteLow ? 'low-time' : ''}`}
        animate={{
          scale: isWhiteActive && isRunning ? [1, 1.02, 1] : 1,
        }}
        transition={{
          duration: 1,
          repeat: isWhiteActive && isRunning ? Infinity : 0,
        }}
      >
        <div className="timer-label">백</div>
        <div className="timer-display">{formatTime(whiteTime)}</div>
        <div className="timer-piece">♔</div>
      </motion.div>
    </div>
  );
};
