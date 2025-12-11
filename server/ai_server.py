import os
import sys
import chess
import chess.engine
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
        player_name = request.get("player_name", "마그누스 칼슨")
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

@app.on_event("shutdown")
def shutdown_event():
    if engine:
        engine.quit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
