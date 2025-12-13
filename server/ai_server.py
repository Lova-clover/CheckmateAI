import os
import sys
import chess
import chess.engine
import chess.pgn
import io
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random

# ai_engine 모듈을 import할 수 있도록 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- FastAPI 앱 생성 및 CORS 설정 ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Stockfish 엔진 설정 ---
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish", "stockfish-windows-x86-64-avx2.exe")

if not os.path.exists(STOCKFISH_PATH):
    print(f"⚠️  Stockfish 엔진을 찾을 수 없습니다: {STOCKFISH_PATH}")
    print("   Stockfish를 다운로드하여 server/stockfish/ 폴더에 추가해주세요.")
    STOCKFISH_PATH = None

# Stockfish 엔진 초기화
engine = None
if STOCKFISH_PATH:
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        print(f"✅ Stockfish 엔진 초기화 완료: {STOCKFISH_PATH}")
    except Exception as e:
        print(f"❌ Stockfish 초기화 실패: {e}")

# --- Pydantic 모델 ---
class MoveRequest(BaseModel):
    fen: str
    difficulty: int = 5

# --- 엔드포인트 ---
@app.get("/")
def root():
    return {"message": "CheckmateAI 서버가 실행 중입니다 ♟️"}

@app.post("/ai/move")
async def ai_move(request: MoveRequest):
    """
    주어진 FEN 포지션에서 AI의 최선의 수를 계산
    """
    try:
        fen = request.fen
        difficulty = request.difficulty
        
        board = chess.Board(fen)
        
        # Stockfish 엔진이 있으면 사용
        if engine:
            # 난이도에 따라 엔진 설정 조정
            depth = min(difficulty * 2, 20)
            time_limit = min(difficulty * 0.2, 2.0)
            
            # Stockfish 엔진으로 최선의 수 계산
            result = engine.play(
                board,
                chess.engine.Limit(depth=depth, time=time_limit)
            )
            
            if result.move:
                return {"move": result.move.uci(), "success": True}
        
        # Fallback: 랜덤 합법수 (Stockfish 없을 때)
        legal_moves = list(board.legal_moves)
        if legal_moves:
            random_move = random.choice(legal_moves)
            return {"move": random_move.uci(), "success": True, "fallback": True}
        else:
            raise HTTPException(status_code=400, detail="유효한 수를 찾을 수 없습니다")
            
    except Exception as e:
        print(f"❌ AI move 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/puzzle")
async def get_puzzle(difficulty: str = "medium", user_rating: int = None):
    """
    랜덤 퍼즐 가져오기
    """
    try:
        from ai_engine.puzzle_generator import PuzzleGenerator
        
        puzzle_gen = PuzzleGenerator()
        puzzle = puzzle_gen.get_random_puzzle(difficulty=difficulty, user_rating=user_rating)
        
        return {
            "puzzle_id": puzzle['puzzle_id'],
            "fen": puzzle['fen'],
            "solution": puzzle['solution'],
            "difficulty": puzzle['difficulty'],
            "theme": puzzle['theme'],
            "rating": puzzle['rating'],
            "success": True
        }
    except Exception as e:
        print(f"❌ 퍼즐 로드 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/puzzle/hint")
async def get_puzzle_hint(puzzle_id: str, move_index: int = 0):
    """
    퍼즐 힌트 가져오기
    """
    try:
        from ai_engine.puzzle_generator import PuzzleGenerator
        
        puzzle_gen = PuzzleGenerator()
        hint_data = puzzle_gen.get_hint(puzzle_id, move_index)
        
        if hint_data:
            # hint_data가 딕셔너리면 'hint' 키로 접근, 문자열이면 그대로 반환
            hint_text = hint_data.get('hint') if isinstance(hint_data, dict) else hint_data
            return {"hint": hint_text, "success": True}
        else:
            raise HTTPException(status_code=404, detail="힌트를 찾을 수 없습니다")
    except Exception as e:
        import traceback
        print(f"❌ 힌트 로드 오류: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/top-player/move")
async def get_top_player_move(request: dict):
    """
    TOP Player 스타일로 수 계산
    """
    try:
        fen = request.get("fen")
        player_name = request.get("player_name", "매그너스 칼슨")
        time_limit = request.get("time_limit", 1.0)
        
        if not fen:
            raise HTTPException(status_code=400, detail="FEN이 제공되지 않았습니다")
        
        board = chess.Board(fen)
        
        # Stockfish 엔진이 있으면 TOP Player AI 사용
        if engine:
            from ai_engine.top_player_ai import TopPlayerAI
            top_player_ai = TopPlayerAI(engine)
            move = top_player_ai.get_move(fen, player_name, time_limit)
            
            if move:
                return {"move": move, "player": player_name, "success": True}
        
        # Fallback: 랜덤 합법수 (Stockfish 없을 때)
        legal_moves = list(board.legal_moves)
        if legal_moves:
            random_move = random.choice(legal_moves)
            return {"move": random_move.uci(), "player": player_name, "success": True, "fallback": True}
        else:
            raise HTTPException(status_code=400, detail="유효한 수를 찾을 수 없습니다")
    except Exception as e:
        print(f"❌ TOP Player move 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/top-players")
async def list_top_players():
    """
    사용 가능한 TOP Player 목록
    """
    try:
        from ai_engine.top_player_ai import TopPlayerAI
        
        if not engine:
            raise HTTPException(status_code=500, detail="Stockfish 엔진이 초기화되지 않았습니다")
        
        top_player_ai = TopPlayerAI(engine)
        players = top_player_ai.list_players()
        
        player_info = []
        for player_name in players:
            info = top_player_ai.get_player_info(player_name)
            player_info.append({
                "name": player_name,
                "rating": info['rating'],
                "style": info['style']
            })
        
        return {"players": player_info, "success": True}
    except Exception as e:
        print(f"❌ TOP Players 목록 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AnalyzeRequest(BaseModel):
    pgn: str

@app.post("/ai/analyze")
def analyze_game(request: AnalyzeRequest):
    """게임 PGN을 분석하여 각 수의 평가와 실수를 반환"""
    if not engine:
        raise HTTPException(status_code=503, detail="Stockfish 엔진이 초기화되지 않았습니다")
    
    try:
        board = chess.Board()
        pgn_io = io.StringIO(request.pgn)
        game = chess.pgn.read_game(pgn_io)
        
        if not game:
            raise HTTPException(status_code=400, detail="유효하지 않은 PGN입니다")
        
        analysis_results = []
        move_number = 1
        previous_eval = 0
        
        for node in game.mainline():
            move = node.move
            board.push(move)
            
            # Stockfish로 현재 포지션 평가
            info = engine.analyse(board, chess.engine.Limit(depth=15))
            score = info.get("score")
            
            if score:
                # 점수를 백의 관점으로 변환 (폰 단위)
                if score.is_mate():
                    # 메이트까지 수
                    mate_in = score.relative.mate()
                    evaluation = 100 if mate_in > 0 else -100
                else:
                    # 센티폰을 폰으로 변환
                    evaluation = score.relative.score() / 100.0
            else:
                evaluation = 0
            
            # 최선의 수 찾기
            board.pop()
            best_move_info = engine.analyse(board, chess.engine.Limit(depth=15))
            best_move = best_move_info.get("pv", [None])[0]
            best_move_san = board.san(best_move) if best_move else ""
            board.push(move)
            
            # 수의 분류 (eval 차이로 판단)
            eval_diff = abs(evaluation - previous_eval)
            played_move = node.san()
            
            if played_move == best_move_san:
                classification = "best"
            elif eval_diff < 0.3:
                classification = "good"
            elif eval_diff < 1.0:
                classification = "inaccuracy"
            elif eval_diff < 3.0:
                classification = "mistake"
            else:
                classification = "blunder"
            
            analysis_results.append({
                "move": played_move,
                "moveNumber": move_number,
                "evaluation": round(evaluation, 2),
                "bestMove": best_move_san,
                "classification": classification,
                "evalDiff": round(eval_diff, 2)
            })
            
            previous_eval = evaluation
            
            # 백/흑 번갈아가며 수 번호 증가
            if board.turn == chess.WHITE:
                move_number += 1
        
        return {"analysis": analysis_results, "success": True}
        
    except Exception as e:
        print(f"❌ 게임 분석 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("shutdown")
def shutdown_event():
    if engine:
        engine.quit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
