from __future__ import annotations
import os, sys, sqlite3, shutil
from typing import Dict, Any, List, Tuple, Optional
import requests
import streamlit as st
import chess, chess.engine, chess.svg
import pyrebase
import json

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ==================== SESSION STATE DEFAULTS ====================
def initialize_session_state():
    defaults = {
        "board": chess.Board(), "history": [], "engine_ms": 600, "user_elo": 1200,
        "puzzle": None, "puzzle_board": chess.Board(), "last_analysis": None,
        "puzzle_result": "", "user_logged_in": False,
        "username": "", "user_info": None, "solved_puzzles": set(),
        "play_move_input": "", "puzzle_move_input": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

initialize_session_state()

# ==================== FIREBASE SETUP ====================
@st.cache_resource
def init_firebase():
    try:
        firebase_config = st.secrets["firebase_credentials"]
        return pyrebase.initialize_app(firebase_config)
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}")
        return None

firebase = init_firebase()
auth = firebase.auth() if firebase else None
db = firebase.database() if firebase else None

# ==================== LOGIN / REGISTER ====================
def login_page():
    st.subheader("Login / Register")
    if not auth or not db:
        st.error("Firebase not initialized."); st.stop()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            try:
                user = auth.sign_in_with_email_and_password(email, password)
                st.session_state.user_logged_in = True
                st.session_state.user_info = user
                st.session_state.username = user['email']
                user_data = db.child("users").child(user['localId']).get().val()
                if user_data:
                    st.session_state.user_elo = user_data.get("elo", 1200)
                    solved_puzzles_list = user_data.get("solved_puzzles", [])
                    st.session_state.solved_puzzles = set(solved_puzzles_list if isinstance(solved_puzzles_list, list) else [])
                else:
                    try:
                        db.child("users").child(user['localId']).set({"email": email, "elo": 1200, "solved_puzzles": []})
                    except Exception as e:
                        st.error(f"Failed to create user in DB: {e}")
                st.success("Login successful!"); st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with col2:
        st.subheader("Register")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("New Password", type="password", key="reg_pass")
        if st.button("Register"):
            try:
                user = auth.create_user_with_email_and_password(reg_email, reg_password)
                try:
                    db.child("users").child(user['localId']).set({"email": reg_email, "elo": 1200, "solved_puzzles": []})
                except Exception as e:
                    st.error(f"Failed to create user in DB: {e}")
                st.success("Registration successful! Please login.")
            except Exception as e:
                st.error(f"Registration failed: {e}")

# ==================== APP EXECUTION FLOW ====================
if not st.session_state.user_logged_in:
    login_page()
    st.stop()

# ==================== ENGINE SETUP ====================
@st.cache_resource
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs, engine, chosen = [], None, None
    for cand in ["/usr/games/stockfish", shutil.which("stockfish")]:
        if cand and os.path.exists(cand):
            try:
                eng = chess.engine.SimpleEngine.popen_uci(cand, setpgrp=True)
                try: eng.configure({"Threads": 1, "Hash": 64})
                except chess.engine.EngineError: pass
                engine, chosen = eng, cand; logs.append(f"✓ Engine started: {cand}"); break
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
        except chess.engine.EngineTerminatedError: return None

engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None

# ==================== PUZZLE DATABASE ====================
@st.cache_resource(show_spinner="Connecting to puzzle database...")
def get_puzzle_db_path(puzzle_db_path: str = "puzzles.db"):
    if not os.path.exists(puzzle_db_path):
        with st.spinner("Puzzle database not found. Downloading..."):
            db_url = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1"
            try:
                r = requests.get(db_url, stream=True); r.raise_for_status()
                with open(puzzle_db_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                st.success("Puzzle database downloaded.")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to download puzzle database: {e}"); return None
    return puzzle_db_path

puzzle_db_path = get_puzzle_db_path()

def get_puzzle_near_rating(target_elo: int, solved_ids: set) -> Optional[Dict[str, Any]]:
    if not puzzle_db_path: return None
    conn = sqlite3.connect(puzzle_db_path)
    try:
        placeholders = ','.join('?' for _ in solved_ids) if solved_ids else '""'
        query = f"SELECT * FROM puzzles WHERE puzzle_id NOT IN ({placeholders}) AND rating BETWEEN ? AND ? ORDER BY RANDOM() LIMIT 1"
        params = list(solved_ids) + [target_elo - 150, target_elo + 150]
        cursor = conn.execute(query, params)
        columns = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        if row: return dict(zip(columns, row))
        st.warning("No new puzzles in range. Loading a random one.")
        fallback_query = f"SELECT * FROM puzzles WHERE puzzle_id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT 1"
        cursor = conn.execute(fallback_query, list(solved_ids))
        row = cursor.fetchone()
        if row: return dict(zip(columns, row))
    finally:
        if conn: conn.close()
    return None

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

# ==================== BOARD RENDER (SAN + UCI) ====================
def render_board_text_only(board: chess.Board, key_prefix: str = "play"):
    move_input_key = f"{key_prefix}_move_input"
    move_input = st.session_state.get(move_input_key, "")
    move_input_new = st.text_input("Enter Move (SAN or UCI, e.g., e4 or e2e4):", value=move_input, key=f"{move_input_key}_tmp")
    if st.button("Make Move", key=f"{key_prefix}_move_btn"):
        move = None
        try: move = board.parse_san(move_input_new)
        except ValueError:
            try: move = board.parse_uci(move_input_new)
            except ValueError: st.warning("Invalid move format.")
        if move and move in board.legal_moves:
            st.session_state[move_input_key] = ""
            return move
        elif move: st.warning("Illegal move.")
    st.session_state[move_input_key] = move_input_new
    st.image(chess.svg.board(board, size=420))
    return None

# ==================== APP UI ====================
st.sidebar.title("CheckmateAI")
board_size = st.sidebar.slider("Board Size (px)", 280, 600, 420, step=20)
st.session_state.engine_ms = st.sidebar.slider("Engine Think Time (ms)", 100, 3000, 600)
st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
st.sidebar.write(f"ELO: **{st.session_state.user_elo}**")
if st.sidebar.button("Logout"):
    st.session_state.clear(); initialize_session_state(); st.rerun()
with st.sidebar.expander("⚙️ Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}"); st.write(f"Chosen engine: {engine_path or '(none)'}")
    for line in engine_logs: st.write(line)

TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# ==================== TAB: PLAY ====================
with TAB_PLAY:
    col1, col2 = st.columns([1.7, 1])
    with col1:
        st.subheader("Play vs AI")
        move = render_board_text_only(st.session_state.board, key_prefix="play")
        if move:
            st.session_state.board.push(move)
            if st.session_state.worker and not st.session_state.board.is_game_over():
                with st.spinner("AI is thinking..."):
                    ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
                if ai_move: st.session_state.board.push(ai_move)
            st.rerun()
    with col2:
        st.subheader("Info")
        san_history = [st.session_state.board.san(m) for m in st.session_state.board.move_stack]
        st.text_area("Moves", value=" ".join(san_history), height=150, disabled=True)
        if st.session_state.board.is_game_over(): st.info(f"Game over: {st.session_state.board.result()}")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                st.write(f"{i}. **{pv_to_san_line(st.session_state.board, info.get('pv', []), 6)}** `({pretty_score(info, st.session_state.board)})`")

# ==================== TAB: PUZZLES ====================
with TAB_PUZZLES:
    st.subheader("Rating-based Puzzle")
    if st.session_state.puzzle_result:
        st.success(st.session_state.puzzle_result) if "Correct" in st.session_state.puzzle_result else st.error(st.session_state.puzzle_result)
    if st.button("Load New Puzzle"):
        st.session_state.puzzle = get_puzzle_near_rating(st.session_state.user_elo, st.session_state.solved_puzzles)
        st.session_state.puzzle_result = ""
        if st.session_state.puzzle:
            st.session_state.puzzle_board.set_fen(st.session_state.puzzle["fen"])
        st.rerun()
    if st.session_state.puzzle:
        pz = st.session_state.puzzle
        st.info(f"Your color: {'White' if st.session_state.puzzle_board.turn else 'Black'}")
        move_obj = render_board_text_only(st.session_state.puzzle_board, key_prefix="puzzle")
        if move_obj and db:
            solution_move_uci = pz['moves'].split()[0]
            user_id = st.session_state.user_info['localId']
            try:
                solved_list = list(st.session_state.solved_puzzles) if st.session_state.solved_puzzles else []
                if move_obj.uci() == solution_move_uci:
                    st.session_state.user_elo += 20
                    st.session_state.puzzle_result = "✅ Correct! +20 ELO"
                    st.session_state.solved_puzzles.add(pz['puzzle_id'])
                else:
                    st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
                    st.session_state.puzzle_result = f"❌ Incorrect. The move was {solution_move_uci}"
                # 안전하게 update
                db.child("users").child(user_id).update({"elo": st.session_state.user_elo, "solved_puzzles": solved_list})
            except requests.exceptions.HTTPError as e:
                st.error(f"Failed to update DB: {e}")
            except Exception as e:
                st.error(f"Unexpected DB error: {e}")
            st.session_state.puzzle = None
            st.rerun()

# ==================== TAB: ANALYSIS ====================
with TAB_ANALYSIS:
    st.subheader("Position Analysis")
    fen_to_analyze = st.text_input("FEN String", st.session_state.board.fen())
    if fen_to_analyze:
        try:
            board_to_analyze = chess.Board(fen_to_analyze)
            st.image(chess.svg.board(board_to_analyze, size=board_size))
            if st.button("Analyze Position", key="analyze_btn"):
                if st.session_state.worker:
                    with st.spinner("Analyzing..."):
                        infos = st.session_state.worker.analyse(board_to_analyze, 5, 2000)
                    for i, info in enumerate(infos, 1):
                        st.write(f"{i}. **{pv_to_san_line(board_to_analyze, info.get('pv', []), 8)}** `({pretty_score(info, board_to_analyze)})`")
        except ValueError:
            st.error("Invalid FEN string.")
