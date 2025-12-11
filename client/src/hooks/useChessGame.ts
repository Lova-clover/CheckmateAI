import { useState, useCallback, useEffect } from 'react';
import { Chess } from 'chess.js';

export interface Move {
  from: string;
  to: string;
  promotion?: string;
}

export interface GameState {
  fen: string;
  pgn: string;
  isGameOver: boolean;
  isCheck: boolean;
  isCheckmate: boolean;
  isDraw: boolean;
  turn: 'w' | 'b';
  moveHistory: string[];
}

export const useChessGame = () => {
  const [game, setGame] = useState(new Chess());
  const [gameState, setGameState] = useState<GameState>({
    fen: game.fen(),
    pgn: game.pgn(),
    isGameOver: false,
    isCheck: false,
    isCheckmate: false,
    isDraw: false,
    turn: 'w',
    moveHistory: []
  });

  const updateGameState = useCallback((chessInstance: Chess) => {
    setGameState({
      fen: chessInstance.fen(),
      pgn: chessInstance.pgn(),
      isGameOver: chessInstance.isGameOver(),
      isCheck: chessInstance.isCheck(),
      isCheckmate: chessInstance.isCheckmate(),
      isDraw: chessInstance.isDraw(),
      turn: chessInstance.turn(),
      moveHistory: chessInstance.history()
    });
  }, []);

  const makeMove = useCallback((move: Move) => {
    try {
      // game 객체를 직접 변경하여 히스토리 유지
      const result = game.move(move);
      
      if (result) {
        // 상태 업데이트
        updateGameState(game);
        return true;
      }
      return false;
    } catch (error) {
      return false;
    }
  }, [game, updateGameState]);

  const resetGame = useCallback(() => {
    const newGame = new Chess();
    setGame(newGame);
    updateGameState(newGame);
  }, [updateGameState]);

  const undoMove = useCallback(() => {
    game.undo();
    updateGameState(game);
  }, [game, updateGameState]);

  const loadPgn = useCallback((pgn: string) => {
    try {
      const newGame = new Chess();
      newGame.loadPgn(pgn);
      setGame(newGame);
      updateGameState(newGame);
      return true;
    } catch {
      return false;
    }
  }, [updateGameState]);

  const loadFen = useCallback((fen: string) => {
    try {
      const newGame = new Chess(fen);
      setGame(newGame);
      updateGameState(newGame);
      return true;
    } catch {
      return false;
    }
  }, [updateGameState]);

  const getLegalMoves = useCallback((square?: string) => {
    if (square) {
      return game.moves({ square: square as any, verbose: true });
    }
    return game.moves({ verbose: true });
  }, [game]);

  return {
    game,
    gameState,
    makeMove,
    resetGame,
    undoMove,
    loadPgn,
    loadFen,
    getLegalMoves
  };
};
