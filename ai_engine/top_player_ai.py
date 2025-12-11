import chess
import chess.engine
import random
from typing import Optional, Dict

class TopPlayerAI:
    """실제 TOP 플레이어의 플레이 스타일을 모방하는 AI"""
    
    def __init__(self, engine):
        self.engine = engine
        self.player_styles = {
            "마그누스 칼슨": {
                "rating": 2830,
                "style": "aggressive",
                "opening_preference": "dynamic",
                "endgame_skill": 95,
                "tactics_preference": 85,
                "positional_preference": 90,
                "risk_taking": 75
            },
            "이안 네포므냐치": {
                "rating": 2750,
                "style": "positional",
                "opening_preference": "solid",
                "endgame_skill": 85,
                "tactics_preference": 75,
                "positional_preference": 95,
                "risk_taking": 40
            },
            "딩 리렌": {
                "rating": 2780,
                "style": "tactical",
                "opening_preference": "sharp",
                "endgame_skill": 88,
                "tactics_preference": 92,
                "positional_preference": 80,
                "risk_taking": 65
            },
            "파비아노 카루아나": {
                "rating": 2800,
                "style": "solid",
                "opening_preference": "classical",
                "endgame_skill": 92,
                "tactics_preference": 85,
                "positional_preference": 88,
                "risk_taking": 50
            },
            "알리레자 피루자": {
                "rating": 2785,
                "style": "dynamic",
                "opening_preference": "aggressive",
                "endgame_skill": 85,
                "tactics_preference": 90,
                "positional_preference": 82,
                "risk_taking": 80
            }
        }
    
    def get_move(self, fen: str, player_name: str, time_limit: float = 1.0) -> Optional[str]:
        """
        특정 플레이어 스타일로 수 계산
        fen: 현재 보드 상태
        player_name: 플레이어 이름
        time_limit: 계산 시간 제한
        """
        if player_name not in self.player_styles:
            # 기본 스타일로 대체
            return self._get_default_move(fen, time_limit)
        
        style = self.player_styles[player_name]
        board = chess.Board(fen)
        
        # 스타일에 따라 엔진 설정 조정
        depth = self._calculate_depth(style)
        
        try:
            # Stockfish로 상위 N개 수 분석
            info = self.engine.analyse(
                board,
                chess.engine.Limit(time=time_limit, depth=depth),
                multipv=3  # 상위 3개 수 분석
            )
            
            # 스타일에 따라 수 선택
            chosen_move = self._select_move_by_style(info, style, board)
            
            if chosen_move:
                return chosen_move.uci()
            else:
                # Fallback: 최선의 수
                result = self.engine.play(
                    board,
                    chess.engine.Limit(time=time_limit, depth=depth)
                )
                return result.move.uci() if result.move else None
                
        except Exception as e:
            print(f"TOP Player AI 오류: {e}")
            return self._get_default_move(fen, time_limit)
    
    def _calculate_depth(self, style: Dict) -> int:
        """스타일에 따른 탐색 깊이 계산"""
        base_depth = 15
        
        # 엔드게임 실력이 높으면 깊이 증가
        endgame_bonus = style['endgame_skill'] // 20
        
        return base_depth + endgame_bonus
    
    def _select_move_by_style(self, analysis_info, style: Dict, board: chess.Board):
        """스타일에 따라 수 선택"""
        if not analysis_info:
            return None
        
        moves_with_scores = []
        
        for line in analysis_info:
            if 'pv' not in line or not line['pv']:
                continue
            
            move = line['pv'][0]
            score = line.get('score', None)
            
            if score:
                # 센티폰 점수 추출
                if score.is_mate():
                    cp_score = 10000 if score.mate() > 0 else -10000
                else:
                    cp_score = score.relative.score(mate_score=10000)
                
                moves_with_scores.append((move, cp_score))
        
        if not moves_with_scores:
            return None
        
        # 최선의 수 점수
        best_score = moves_with_scores[0][1]
        
        # 스타일에 따라 수 선택
        risk_threshold = style['risk_taking']
        
        for move, score in moves_with_scores:
            # 점수 차이 계산
            score_diff = abs(best_score - score)
            
            # 공격적 스타일: 전술적 복잡함 선호
            if style['style'] == 'aggressive':
                # 약간 손해를 보더라도 공격적인 수 선택
                if score_diff <= 50 and self._is_attacking_move(move, board):
                    return move
            
            # 포지셔널 스타일: 안정적인 수 선호
            elif style['style'] == 'positional':
                # 최선의 수만 선택
                if score_diff <= 20:
                    return move
            
            # 전술적 스타일: 날카로운 수 선호
            elif style['style'] == 'tactical':
                if score_diff <= 40 and self._is_tactical_move(move, board):
                    return move
            
            # 견고한 스타일: 위험 최소화
            elif style['style'] == 'solid':
                if score_diff <= 10:
                    return move
            
            # 역동적 스타일: 복잡한 포지션 선호
            elif style['style'] == 'dynamic':
                if score_diff <= 60 and self._is_complex_move(move, board):
                    return move
        
        # 기본: 최선의 수 선택
        return moves_with_scores[0][0]
    
    def _is_attacking_move(self, move: chess.Move, board: chess.Board) -> bool:
        """공격적인 수인지 판단"""
        # 체크, 캡처, 중앙 진출 등을 공격으로 판단
        temp_board = board.copy()
        temp_board.push(move)
        
        return (
            board.is_capture(move) or  # 기물 잡기
            temp_board.is_check() or   # 체크
            move.to_square in [chess.E4, chess.D4, chess.E5, chess.D5]  # 중앙 점령
        )
    
    def _is_tactical_move(self, move: chess.Move, board: chess.Board) -> bool:
        """전술적인 수인지 판단"""
        return (
            board.is_capture(move) or
            board.gives_check(move) or
            self._creates_threat(move, board)
        )
    
    def _is_complex_move(self, move: chess.Move, board: chess.Board) -> bool:
        """복잡한 포지션을 만드는 수인지 판단"""
        temp_board = board.copy()
        temp_board.push(move)
        
        # 합법수가 많으면 복잡한 포지션
        return len(list(temp_board.legal_moves)) > 30
    
    def _creates_threat(self, move: chess.Move, board: chess.Board) -> bool:
        """위협을 만드는 수인지 판단"""
        temp_board = board.copy()
        temp_board.push(move)
        
        # 다음 수에 캡처 가능한지 확인
        for next_move in temp_board.legal_moves:
            if temp_board.is_capture(next_move):
                return True
        
        return False
    
    def _get_default_move(self, fen: str, time_limit: float) -> Optional[str]:
        """기본 수 계산 (Fallback)"""
        try:
            board = chess.Board(fen)
            result = self.engine.play(
                board,
                chess.engine.Limit(time=time_limit, depth=15)
            )
            return result.move.uci() if result.move else None
        except:
            return None
    
    def get_player_info(self, player_name: str) -> Optional[Dict]:
        """플레이어 정보 가져오기"""
        return self.player_styles.get(player_name)
    
    def list_players(self):
        """사용 가능한 플레이어 목록"""
        return list(self.player_styles.keys())
