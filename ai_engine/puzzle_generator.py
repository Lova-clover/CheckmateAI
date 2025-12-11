import sqlite3
import random
import os
import chess


class PuzzleGenerator:
    """Generate and manage chess puzzles from SQLite database"""
    
    def __init__(self):
        """Initialize the puzzle generator and connect to database"""
        self.db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'puzzles.db')
        self.conn = None
        self._connect_db()
    
    def _connect_db(self):
        """Initialize SQLite connection with check_same_thread=False"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            cursor = self.conn.cursor()
            
            # Create index on rating column for ULTRA fast queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating ON puzzles(rating)")
            
            # Get puzzle count
            cursor.execute("SELECT COUNT(*) FROM puzzles")
            count = cursor.fetchone()[0]
            print(f"✅ 퍼즐 데이터베이스 연결 성공: {count:,}개의 퍼즐")
            
        except sqlite3.Error as e:
            print(f"❌ 퍼즐 데이터베이스 연결 실패: {e}")
            self.conn = None
    
    def get_random_puzzle(self, difficulty="medium", user_rating=None):
        """
        Return random puzzle based on rating (BLAZING FAST - smart random selection)
        
        Args:
            difficulty: 'easy' (600-1200), 'medium' (1200-1800), 'hard' (1800-2500)
            user_rating: Optional user rating to narrow the range
            
        Returns:
            dict: Puzzle data with puzzle_id, fen, solution, difficulty, theme, rating
        """
        if not self.conn:
            return self._get_fallback_puzzle()
        
        # Define rating ranges
        rating_ranges = {
            'easy': (600, 1200),
            'medium': (1200, 1800),
            'hard': (1800, 2500)
        }
        
        min_rating, max_rating = rating_ranges.get(difficulty, (1200, 1800))
        
        try:
            cursor = self.conn.cursor()
            
            # BLAZING FAST METHOD:
            # 1. Pick a random rating within the range
            # 2. Get the first puzzle at or above that rating
            # This avoids ORDER BY RANDOM() which scans the entire table
            random_rating = random.randint(min_rating, max_rating)
            
            cursor.execute("""
                SELECT puzzle_id, fen, moves, rating, themes 
                FROM puzzles 
                WHERE rating >= ? AND rating <= ?
                LIMIT 1
            """, (random_rating, max_rating))
            
            row = cursor.fetchone()
            
            # If no puzzle found at that rating, try from the start of range
            if not row:
                cursor.execute("""
                    SELECT puzzle_id, fen, moves, rating, themes 
                    FROM puzzles 
                    WHERE rating >= ? AND rating <= ?
                    LIMIT 1
                """, (min_rating, max_rating))
                row = cursor.fetchone()
            
            if row:
                # Parse the moves (space-separated UCI format)
                solution_moves = row['moves'].split() if row['moves'] else []
                
                return {
                    'puzzle_id': row['puzzle_id'],
                    'fen': row['fen'],
                    'solution': solution_moves,
                    'difficulty': difficulty,
                    'theme': row['themes'].split()[0] if row['themes'] else 'tactics',
                    'rating': row['rating']
                }
            else:
                return self._get_fallback_puzzle()
                
        except sqlite3.Error as e:
            print(f"❌ 퍼즐 로드 실패: {e}")
            return self._get_fallback_puzzle()
    
    def _get_fallback_puzzle(self):
        """Return hardcoded fallback puzzle if DB fails"""
        return {
            'puzzle_id': 'fallback_001',
            'fen': 'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4',
            'solution': ['f3e5', 'f6e4', 'e5f7'],  # Scholar's mate variation
            'difficulty': 'easy',
            'theme': 'Fork',
            'rating': 1000
        }
    
    def get_puzzle_by_id(self, puzzle_id):
        """
        Get specific puzzle by ID
        
        Args:
            puzzle_id: The puzzle identifier
            
        Returns:
            dict: Puzzle data or None if not found
        """
        if not self.conn:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT puzzle_id, fen, moves, rating, themes 
                FROM puzzles 
                WHERE puzzle_id = ?
            """, (puzzle_id,))
            
            row = cursor.fetchone()
            
            if row:
                solution_moves = row['moves'].split() if row['moves'] else []
                
                # Determine difficulty based on rating
                rating = row['rating']
                if rating < 1200:
                    difficulty = 'easy'
                elif rating < 1800:
                    difficulty = 'medium'
                else:
                    difficulty = 'hard'
                
                return {
                    'puzzle_id': row['puzzle_id'],
                    'fen': row['fen'],
                    'solution': solution_moves,
                    'difficulty': difficulty,
                    'theme': row['themes'] if row['themes'] else 'Unknown',
                    'rating': row['rating']
                }
            else:
                return None
                
        except sqlite3.Error as e:
            print(f"Error fetching puzzle by ID: {e}")
            return None
    
    def get_hint(self, puzzle_id, move_index=0):
        """
        Convert UCI move to SAN (Standard Algebraic Notation) as hint
        
        Args:
            puzzle_id: The puzzle identifier
            move_index: Index of the move to get hint for (default: 0)
            
        Returns:
            dict: Hint information with 'move' (SAN notation) and 'from_square', 'to_square'
        """
        puzzle = self.get_puzzle_by_id(puzzle_id)
        
        if not puzzle or move_index >= len(puzzle['solution']):
            return None
        
        try:
            # Create board from FEN
            board = chess.Board(puzzle['fen'])
            
            # Get the UCI move at the specified index
            uci_move = puzzle['solution'][move_index]
            move = chess.Move.from_uci(uci_move)
            
            # Convert to SAN
            san_move = board.san(move)
            
            return {
                'move': san_move,
                'from_square': move.from_square,
                'to_square': move.to_square,
                'uci': uci_move
            }
            
        except (ValueError, chess.IllegalMoveError) as e:
            print(f"Error converting move to SAN: {e}")
            return None
    
    def validate_solution(self, puzzle_id, user_moves):
        """
        Validate user's solution against the puzzle solution
        
        Args:
            puzzle_id: The puzzle identifier
            user_moves: List of user's moves in UCI format
            
        Returns:
            dict: Validation result with 'correct' (bool), 'message' (str), 
                  'correct_moves' (int), 'total_moves' (int)
        """
        puzzle = self.get_puzzle_by_id(puzzle_id)
        
        if not puzzle:
            return {
                'correct': False,
                'message': 'Puzzle not found',
                'correct_moves': 0,
                'total_moves': 0
            }
        
        expected_solution = puzzle['solution']
        
        # Check if user provided moves
        if not user_moves:
            return {
                'correct': False,
                'message': 'No moves provided',
                'correct_moves': 0,
                'total_moves': len(expected_solution)
            }
        
        # Count correct moves
        correct_moves = 0
        for i, (user_move, expected_move) in enumerate(zip(user_moves, expected_solution)):
            if user_move == expected_move:
                correct_moves += 1
            else:
                # First incorrect move
                return {
                    'correct': False,
                    'message': f'Incorrect move at position {i + 1}',
                    'correct_moves': correct_moves,
                    'total_moves': len(expected_solution)
                }
        
        # Check if user provided all moves
        if len(user_moves) < len(expected_solution):
            return {
                'correct': False,
                'message': 'Solution incomplete',
                'correct_moves': correct_moves,
                'total_moves': len(expected_solution)
            }
        
        # Check if user provided too many moves
        if len(user_moves) > len(expected_solution):
            return {
                'correct': False,
                'message': 'Too many moves',
                'correct_moves': correct_moves,
                'total_moves': len(expected_solution)
            }
        
        # All checks passed
        return {
            'correct': True,
            'message': 'Correct solution!',
            'correct_moves': correct_moves,
            'total_moves': len(expected_solution)
        }
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("Database connection closed")
            self.conn = None


# Example usage
if __name__ == "__main__":
    generator = PuzzleGenerator()
    
    # Test getting a random puzzle
    puzzle = generator.get_random_puzzle(difficulty='medium')
    print(f"\nRandom Puzzle:")
    print(f"ID: {puzzle['puzzle_id']}")
    print(f"FEN: {puzzle['fen']}")
    print(f"Solution: {puzzle['solution']}")
    print(f"Rating: {puzzle['rating']}")
    print(f"Theme: {puzzle['theme']}")
    
    # Test getting a hint
    hint = generator.get_hint(puzzle['puzzle_id'], 0)
    if hint:
        print(f"\nHint for first move: {hint['move']} ({hint['uci']})")
    
    # Test validation
    result = generator.validate_solution(puzzle['puzzle_id'], puzzle['solution'])
    print(f"\nValidation: {result['message']} ({result['correct_moves']}/{result['total_moves']})")
    
    generator.close()
