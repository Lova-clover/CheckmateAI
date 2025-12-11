import { useState, useEffect, useCallback, useRef } from 'react';

export interface TimerState {
  whiteTime: number;
  blackTime: number;
  isRunning: boolean;
  activeColor: 'white' | 'black';
}

export const useChessTimer = (initialTime: number = 600) => {
  const [whiteTime, setWhiteTime] = useState(initialTime);
  const [blackTime, setBlackTime] = useState(initialTime);
  const [isRunning, setIsRunning] = useState(false);
  const [activeColor, setActiveColor] = useState<'white' | 'black'>('white');
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isRunning) {
      intervalRef.current = setInterval(() => {
        if (activeColor === 'white') {
          setWhiteTime((prev) => Math.max(0, prev - 0.1));
        } else {
          setBlackTime((prev) => Math.max(0, prev - 0.1));
        }
      }, 100);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isRunning, activeColor]);

  const start = useCallback(() => {
    setIsRunning(true);
  }, []);

  const pause = useCallback(() => {
    setIsRunning(false);
  }, []);

  const switchTurn = useCallback(() => {
    setActiveColor((prev) => (prev === 'white' ? 'black' : 'white'));
  }, []);

  const reset = useCallback((time: number = initialTime) => {
    setIsRunning(false);
    setWhiteTime(time);
    setBlackTime(time);
    setActiveColor('white');
  }, [initialTime]);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return {
    whiteTime,
    blackTime,
    isRunning,
    activeColor,
    start,
    pause,
    switchTurn,
    reset,
    formatTime
  };
};
