from __future__ import annotations
import os, sys, sqlite3, shutil
from typing import Dict, Any, List, Tuple, Optional
import requests
import streamlit as st
import pandas as pd
import chess, chess.engine, chess.svg
import io, base64
from hashlib import sha256
from streamlit_image_coordinates import streamlit_image_coordinates

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ==================== SESSION STATE DEFAULTS ====================
session_defaults = {
    "board": chess.Board(),
    "history": [],
    "engine_ms": 600,
    "user_elo": 1200,
    "puzzle": None,
    "puzzle_board": chess.Board(),
    "last_analysis": None,
    "puzzle_result": "",
    "selected_square": None,
    "user_logged_in": False,
    "username": ""
}
for k, v in session_defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ==================== ENGINE SETUP ====================
def _engine_candidates() -> list[str]:
    candidates = ["/usr/games/stockfish", shutil.which("stockfish")]
    return [c for c in candidates if c and os.path.exists(c)]

@st.cache_resource(show_spinner="Starting chess engine...")
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs, engine, chosen = [], None, None
    for cand in _engine_candidates():
        if not os.path.exists(cand):
            logs.append(f"✗ Not found: {cand}"); continue
        try:
            eng = chess.engine.SimpleEngine.popen_uci(cand, setpgrp=True)
            try: eng.configure({"Threads": 1, "Hash": 64})
            except: pass
            engine, chosen = eng, cand
            logs.append(f"✓ Engine started: {cand}"); break
        except Exception as e:
            logs.append(f"✗ Failed to start: {cand} ({e})")
    if engine is None: logs.append("No usable Stockfish binary found.")
    return engine, chosen, logs

class EngineWorker:
    def __init__(self, engine: chess.engine.SimpleEngine): self.engine = engine
    def analyse(self, board: chess.Board, multipv: int, think_ms: int) -> List[chess.engine.InfoDict]:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        return self.engine.analyse(board, limit=limit, multipv=multipv)
    def play(self, board: chess.Board, think_ms: int) -> Optional[chess.Move]:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        try: return self.engine.play(board, limit).move
        except: return None

# ==================== DATABASE ====================
@st.cache_resource(show_spinner="Connecting to database...")
def get_db_conn(db_path: str = "puzzles.db"):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                   username TEXT PRIMARY KEY,
                   password_hash TEXT,
                   elo INTEGER DEFAULT 1200
               )""")
    c.execute("CREATE TABLE IF NOT EXISTS solved_puzzles (puzzle_id TEXT PRIMARY KEY)")
    conn.commit()

    try:
        c.execute("SELECT count(*) FROM puzzles")
        puzzle_count = c.fetchone()[0]
    except sqlite3.OperationalError:
        puzzle_count = 0

    if puzzle_count == 0:
        with st.spinner("Puzzle database is empty. Downloading..."):
            temp_db_path = "temp_puzzles.db"
            db_url = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1"
            try:
                r = requests.get(db_url, stream=True)
                r.raise_for_status()
                with open(temp_db_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                temp_conn = sqlite3.connect(temp_db_path)
                df = pd.read_sql_query("SELECT * FROM puzzles", temp_conn)
                df.to_sql("puzzles", conn, if_exists="replace", index=False)
                conn.commit()
                temp_conn.close()
                os.remove(temp_db_path)
                st.success("Puzzle database downloaded and integrated.")
                st.rerun()

            except requests.exceptions.RequestException as e:
                st.error(f"Failed to download puzzle database: {e}")
                if os.path.exists(temp_db_path): os.remove(temp_db_path)
                return None
            except Exception as e:
                st.error(f"Failed to integrate puzzle data: {e}")
                if os.path.exists(temp_db_path): os.remove(temp_db_path)
                return None
    return conn

@st.cache_data(show_spinner=False, ttl=60)
def get_puzzle_near_rating(target_elo: int) -> Optional[Dict[str, Any]]:
    conn = get_db_conn()
    if not conn: return None
    try:
        row = conn.execute(
            "SELECT puzzle_id, fen, moves, rating FROM puzzles WHERE puzzle_id NOT IN (SELECT puzzle_id FROM solved_puzzles) AND rating BETWEEN ? AND ? ORDER BY RANDOM() LIMIT 1",
            (target_elo - 100, target_elo + 100)
        ).fetchone()
        if not row: return None
        return dict(zip(["puzzle_id", "fen", "moves", "rating"], row))
    except sqlite3.OperationalError as e:
        st.error(f"Database error while fetching puzzle: {e}")
        return None

def top3_puzzles() -> List[Dict[str, Any]]:
    conn = get_db_conn()
    if not conn: return []
    try:
        rows = conn.execute(
            "SELECT puzzle_id, fen, moves, rating FROM puzzles ORDER BY rating DESC LIMIT 3"
        ).fetchall()
        return [dict(zip(["puzzle_id", "fen", "moves", "rating"], r)) for r in rows]
    except sqlite3.OperationalError as e:
        st.error(f"Database error while fetching top puzzles: {e}")
        return []

# ==================== HELPERS ====================
def pretty_score(info: chess.engine.InfoDict, board: chess.Board) -> str:
    sc = info.get("score"); pov = sc.pov(board.turn) if sc else None
    if pov is None: return "?"
    if pov.is_mate(): return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    b = board.copy(); parts = []
    for m in pv[:n]:
        try: parts.append(b.san(m)); b.push(m)
        except: break
    return " ".join(parts)

def hash_pw(pw: str) -> str: return sha256(pw.encode()).hexdigest()

def coords_to_square(x, y, board_size):
    file_idx = int(x / (board_size / 8))
    rank_idx = 7 - int(y / (board_size / 8))
    return chess.square(file_idx, rank_idx)

# ==================== BOARD RENDER ====================
def render_board_and_handle_clicks(board: chess.Board, size: int = 400, key_prefix: str = "play"):
    last_move = board.peek() if board.move_stack else None
    
    squares_to_check = []
    if st.session_state.selected_square is not None:
        squares_to_check.append(st.session_state.selected_square)
        for move in board.legal_moves:
            if move.from_square == st.session_state.selected_square:
                squares_to_check.append(move.to_square)

    svg_data = chess.svg.board(board, size=size, lastmove=last_move, check=board.king(board.turn) if board.is_check() else None, squares=chess.SquareSet(squares_to_check))
    b64 = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
    
    coords = streamlit_image_coordinates(f"data:image/svg+xml;base64,{b64}", width=size, height=size, key=f"{key_prefix}_board")

    if coords:
        square = coords_to_square(coords["x"], coords["y"], size)
        
        if st.session_state.selected_square is not None:
            move = chess.Move(st.session_state.selected_square, square)
            piece = board.piece_at(st.session_state.selected_square)
            if piece and piece.piece_type == chess.PAWN:
                if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                    move.promotion = chess.QUEEN
            
            if move in board.legal_moves:
                st.session_state.selected_square = None
                return move
            else:
                st.session_state.selected_square = square if board.piece_at(square) else None
        else:
            if board.piece_at(square) is not None:
                 st.session_state.selected_square = square

    return None

# ==================== LOGIN / REGISTER ====================
def login_page():
    st.subheader("Login / Register")
    conn = get_db_conn()
    if not conn:
        st.error("Database connection failed. Please refresh.")
        st.stop()
        
    c = conn.cursor()
    col1, col2 = st.columns(2)

    with col1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            row = c.execute("SELECT password_hash, elo FROM users WHERE username=?", (username,)).fetchone()
            if row and row[0] == hash_pw(password):
                st.session_state.user_logged_in = True
                st.session_state.username = username
                st.session_state.user_elo = row[1]
                st.success(f"Welcome back {username}!")
                st.rerun() 
            else: st.error("Invalid credentials")
    with col2:
        reg_username = st.text_input("New Username")
        reg_password = st.text_input("New Password", type="password", key="reg_pw")
        if st.button("Register"):
            if not reg_username or not reg_password:
                st.warning("Fill username and password")
                return
            if c.execute("SELECT * FROM users WHERE username=?", (reg_username,)).fetchone():
                st.warning("Username already exists")
            else:
                c.execute("INSERT INTO users (username, password_hash, elo) VALUES (?, ?, ?)",
                          (reg_username, hash_pw(reg_password), 1200))
                conn.commit()
                st.success("Registered! Please login.")

# ==================== APP UI ====================
engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None

st.sidebar.title("CheckmateAI")
board_size = st.sidebar.slider("Board Size (px)", 280, 600, 420, step=20)
st.session_state.engine_ms = st.sidebar.slider("Engine Think Time (ms)", 100, 3000, 600)

if st.session_state.user_logged_in:
    st.sidebar.write(f"Logged in as: {st.session_state.username}")
    st.sidebar.write(f"ELO: {st.session_state.user_elo}")
    if st.sidebar.button("Logout"):
        for key in list(session_defaults.keys()):
            st.session_state[key] = session_defaults[key]
        st.rerun()

with st.sidebar.expander("⚙️ Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}")
    st.write(f"Chosen engine: {engine_path or '(none)'}")
    for line in engine_logs: st.write(line)

if not st.session_state.user_logged_in:
    login_page()
    st.stop()

TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# ==================== PLAY ====================
with TAB_PLAY:
    st.subheader("Play vs AI")
    col1, col2 = st.columns([1.7, 1])
    with col1:
        move = render_board_and_handle_clicks(st.session_state.board, size=board_size, key_prefix="play")
        if move:
            st.session_state.history.append({"ply": len(st.session_state.history) + 1, "san": st.session_state.board.san(move)})
            st.session_state.board.push(move)
            
            if st.session_state.worker and not st.session_state.board.is_game_over():
                with st.spinner("AI is thinking..."):
                    ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
                if ai_move:
                    st.session_state.history.append({"ply": len(st.session_state.history) + 1, "san": st.session_state.board.san(ai_move)})
                    st.session_state.board.push(ai_move)
            st.rerun()

    with col2:
        st.write("Move History")
        st.dataframe(pd.DataFrame(st.session_state.history).tail(30), use_container_width=True, hide_index=True)
        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()} — {st.session_state.board.outcome().termination}")
        st.markdown("**Engine Analysis**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                st.write(f"{i}. **{pv_to_san_line(st.session_state.board, info.get('pv', []), 6)}** `({pretty_score(info, st.session_state.board)})`")

# ==================== PUZZLES ====================
with TAB_PUZZLES:
    st.subheader("Rating-based Puzzle")
    if st.session_state.puzzle_result:
        st.success(st.session_state.puzzle_result) if "Correct" in st.session_state.puzzle_result else st.error(st.session_state.puzzle_result)
    
    if st.button("Load New Puzzle"):
        st.session_state.puzzle = get_puzzle_near_rating(st.session_state.user_elo)
        st.session_state.puzzle_result = ""
        if st.session_state.puzzle:
            st.session_state.puzzle_board.set_fen(st.session_state.puzzle["fen"])
        st.rerun()

    if st.session_state.puzzle:
        pz = st.session_state.puzzle
        st.info(f"Your color: {'White' if st.session_state.puzzle_board.turn else 'Black'}")
        
        move_obj = render_board_and_handle_clicks(st.session_state.puzzle_board, size=board_size, key_prefix="puzzle")

        if move_obj:
            solution_move_uci = pz['moves'].split()[0]
            conn = get_db_conn()
            if move_obj.uci() == solution_move_uci:
                st.session_state.user_elo += 20
                st.session_state.puzzle_result = f"✅ Correct! +20 ELO ({solution_move_uci})"
                if conn:
                    conn.execute("INSERT OR IGNORE INTO solved_puzzles (puzzle_id) VALUES (?)", (pz['puzzle_id'],))
                    conn.execute("UPDATE users SET elo=? WHERE username=?", (st.session_state.user_elo, st.session_state.username))
                    conn.commit()
            else:
                st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
                st.session_state.puzzle_result = f"❌ Not quite. The best move was {solution_move_uci}"
                if conn:
                    conn.execute("UPDATE users SET elo=? WHERE username=?", (st.session_state.user_elo, st.session_state.username))
                    conn.commit()
            
            st.session_state.puzzle = None 
            st.rerun()

    st.subheader("Top 3 Puzzles")
    for p in top3_puzzles():
        st.markdown(f"{p['puzzle_id']} — Rating: {p['rating']} — Moves: {p['moves']}")

# ==================== ANALYSIS ====================
with TAB_ANALYSIS:
    st.subheader("Position Analysis")
    fen_to_analyze = st.text_input("FEN String", st.session_state.board.fen())
    if fen_to_analyze:
        try:
            board_to_analyze = chess.Board(fen_to_analyze)
            a1, a2 = st.columns([1.6, 1])
            with a1: 
                svg_data = chess.svg.board(board_to_analyze, size=board_size)
                b64 = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
                st.image(f"data:image/svg+xml;base64,{b64}")
            with a2:
                if st.button("Analyse Position", key="analyse_btn"):
                    if st.session_state.worker:
                        st.session_state.last_analysis = st.session_state.worker.analyse(board_to_analyze, 5, st.session_state.engine_ms)
                if st.session_state.last_analysis:
                    rows = [{"Rank": i+1, "Score": pretty_score(info, board_to_analyze), "Line": pv_to_san_line(board_to_analyze, info.get("pv", []), 10)} for i, info in enumerate(st.session_state.last_analysis)]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except ValueError: st.error("Invalid FEN string.")