import React from 'react';
import { Chessboard } from 'react-chessboard';
import './ChessBoard.css';

interface ChessBoardProps {
  position: string;
  onPieceDrop: (sourceSquare: string, targetSquare: string) => boolean;
  boardOrientation?: 'white' | 'black';
  customBoardStyle?: React.CSSProperties;
  showCoordinates?: boolean;
  animationDuration?: number;
  arePiecesDraggable?: boolean;
}

export const ChessBoard: React.FC<ChessBoardProps> = ({
  position,
  onPieceDrop,
  boardOrientation = 'white',
  customBoardStyle = {},
  showCoordinates = true,
  animationDuration = 300,
  arePiecesDraggable = true
}) => {
  return (
    <div className="chess-board-container">
      <Chessboard
        position={position}
        onPieceDrop={onPieceDrop}
        boardOrientation={boardOrientation}
        customBoardStyle={{
          borderRadius: '8px',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
          ...customBoardStyle
        }}
        animationDuration={animationDuration}
        areArrowsAllowed={true}
        arePiecesDraggable={arePiecesDraggable}
        customDarkSquareStyle={{ backgroundColor: '#779952' }}
        customLightSquareStyle={{ backgroundColor: '#edeed1' }}
      />
    </div>
  );
};
