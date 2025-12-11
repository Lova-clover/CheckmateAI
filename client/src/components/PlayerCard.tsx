import React from 'react';
import { motion } from 'framer-motion';
import { FaChessKing, FaRobot, FaUser } from 'react-icons/fa';
import './PlayerCard.css';

interface PlayerCardProps {
  name: string;
  rating?: number;
  isAI: boolean;
  color: 'white' | 'black';
  avatar?: string;
}

export const PlayerCard: React.FC<PlayerCardProps> = ({
  name,
  rating,
  isAI,
  color,
  avatar
}) => {
  return (
    <motion.div
      className={`player-card ${color}`}
      initial={{ opacity: 0, x: color === 'white' ? -50 : 50 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="player-avatar">
        {avatar ? (
          <img src={avatar} alt={name} />
        ) : (
          <div className="avatar-icon">
            {isAI ? <FaRobot /> : <FaUser />}
          </div>
        )}
      </div>
      
      <div className="player-info">
        <h3 className="player-name">{name}</h3>
        {rating && (
          <div className="player-rating">
            <FaChessKing className="rating-icon" />
            <span>{rating}</span>
          </div>
        )}
        {isAI && <span className="ai-badge">AI</span>}
      </div>
    </motion.div>
  );
};
