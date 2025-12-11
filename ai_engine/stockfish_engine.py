import chess
import chess.engine
import os
from pathlib import Path

class StockfishEngine:
    def __init__(self, stockfish_path=None):
        """
        Stockfish 엔진 초기화
        stockfish_path: Stockfish 실행 파일 경로 (없으면 자동 탐색)
        """
        if stockfish_path is None:
            # 프로젝트 내 stockfish 폴더에서 찾기
            project_root = Path(__file__).parent.parent
            possible_paths = [
                project_root / 'server' / 'stockfish' / 'stockfish.exe',
                project_root / 'server' / 'stockfish' / 'stockfish',
                'stockfish',  # 시스템 PATH에 있는 경우
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    stockfish_path = str(path)
                    break
        
        if stockfish_path and os.path.exists(stockfish_path):
            self.engine_path = stockfish_path
            self.engine = None
            print(f"✅ Stockfish 경로 설정: {stockfish_path}")
        else:
            raise FileNotFoundError(
                "Stockfish 엔진을 찾을 수 없습니다. "
                "stockfish.exe를 다운로드하여 server/stockfish/ 폴더에 넣어주세요."
            )
    
    def start_engine(self):
        """엔진 시작"""
        if self.engine is None:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            print("🚀 Stockfish 엔진 시작됨")
    
    def stop_engine(self):
        """엔진 종료"""
        if self.engine:
            self.engine.quit()
            self.engine = None
            print("⏹️ Stockfish 엔진 종료됨")
    
    def get_best_move(self, fen: str, difficulty: int = 10, time_limit: float = 1.0):
        """
        최선의 수 찾기
        fen: 현재 보드 상태 (FEN 표기법)
        difficulty: 난이도 (1-20, 1이 가장 약함)
        time_limit: 생각 시간 (초)
        """
        try:
            self.start_engine()
            
            board = chess.Board(fen)
            
            # 난이도에 따라 엔진 설정 조정
            if difficulty <= 5:
                # 약한 수준: 제한된 탐색 깊이
                result = self.engine.play(
                    board, 
                    chess.engine.Limit(depth=difficulty * 2, time=time_limit * 0.5)
                )
            elif difficulty <= 10:
                # 중간 수준
                result = self.engine.play(
                    board,
                    chess.engine.Limit(depth=difficulty * 2, time=time_limit)
                )
            else:
                # 고급 수준: 더 많은 시간과 깊이
                result = self.engine.play(
                    board,
                    chess.engine.Limit(depth=20, time=time_limit * 1.5)
                )
            
            return result.move.uci() if result.move else None
            
        except Exception as e:
            print(f"❌ AI 수 생성 오류: {e}")
            return None
    
    def analyze_position(self, fen: str, time_limit: float = 2.0):
        """
        현재 포지션 분석
        fen: 현재 보드 상태
        time_limit: 분석 시간
        """
        try:
            self.start_engine()
            
            board = chess.Board(fen)
            info = self.engine.analyse(
                board,
                chess.engine.Limit(time=time_limit)
            )
            
            return {
                'score': str(info.get('score', 'N/A')),
                'best_move': info.get('pv', [None])[0].uci() if info.get('pv') else None,
                'depth': info.get('depth', 0)
            }
            
        except Exception as e:
            print(f"❌ 포지션 분석 오류: {e}")
            return None
    
    def get_top_moves(self, fen: str, num_moves: int = 3, time_limit: float = 2.0):
        """
        상위 N개의 수 추천
        fen: 현재 보드 상태
        num_moves: 추천할 수의 개수
        time_limit: 분석 시간
        """
        try:
            self.start_engine()
            
            board = chess.Board(fen)
            info = self.engine.analyse(
                board,
                chess.engine.Limit(time=time_limit),
                multipv=num_moves
            )
            
            top_moves = []
            for i, line in enumerate(info):
                if 'pv' in line and line['pv']:
                    top_moves.append({
                        'move': line['pv'][0].uci(),
                        'score': str(line.get('score', 'N/A')),
                        'rank': i + 1
                    })
            
            return top_moves
            
        except Exception as e:
            print(f"❌ 상위 수 분석 오류: {e}")
            return []

# 전역 엔진 인스턴스
_engine = None

def get_engine():
    """싱글톤 패턴으로 엔진 인스턴스 반환"""
    global _engine
    if _engine is None:
        _engine = StockfishEngine()
    return _engine
