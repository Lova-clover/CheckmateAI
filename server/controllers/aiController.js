const { calculateMove } = require('../services/aiService');

exports.getAIMove = (req, res) => {
  const { fen } = req.body;
  try {
    const move = calculateMove(fen);  // ai_engine 통해 계산
    res.json({ move });
  } catch (error) {
    console.error('AI move error:', error);
    res.status(500).json({ error: 'AI 실패' });
  }
};
