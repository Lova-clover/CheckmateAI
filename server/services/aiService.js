const { spawnSync } = require('child_process');

exports.calculateMove = (fen) => {
  const result = spawnSync('python3', ['ai_engine/engine.py', fen]);
  const move = result.stdout.toString().trim();
  return move;
};
