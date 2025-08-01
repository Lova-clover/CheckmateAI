import sys
import chess
import chess.engine

fen = sys.argv[1]
board = chess.Board(fen)

with chess.engine.SimpleEngine.popen_uci("/usr/bin/stockfish") as engine:
    result = engine.play(board, chess.engine.Limit(time=0.1))
    print(result.move.uci())
