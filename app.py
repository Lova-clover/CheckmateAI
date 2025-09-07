from __future__ import annotations
import os, sys, sqlite3, shutil
from typing import Dict, Any, List, Optional, Tuple
import requests, json
import streamlit as st
import chess, chess.engine, chess.svg
import pyrebase

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ==================== SESSION STATE DEFAULTS ====================
def initialize_session_state():
    defaults = {
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
        "username": "",
        "user_info": None,
        "solved_puzzles": set(),
        "play_move_input": "",
        "puzzle_move_input": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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
        st.error("Firebase not initialized.")
        st.stop()
    
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
                    solved_list = user_data.get("solved_puzzles", [])
                    st.session_state.solved_puzzles = set(solved_list if isinstance(solved_list, list) else [])
                else:
                    db.child("users").child(user['localId']).set({"email": email, "elo": 1200})
                st.success("Login successful!")
                st.rerun()
            except requests.exceptions.HTTPError as e:
                error_data = e.args[1] if len(e.args) > 1 else "{}"
                try: error_msg = json.loads(error_data).get("error", {}).get("message", "UNKNOWN_ERROR")
                except json.JSONDecodeError: error_msg = "INVALID_CREDENTIALS"
                st.error(f"Login failed: {error_msg.replace('_',' ').capitalize()}")
            except Exception: st.error("Unexpected login error.")

    with col2:
        st.subheader("Register")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register"):
            try:
                user = auth.create_user_with_email_and_password(reg_email, reg_password)
                db.child("users").child(user['localId']).set({"email": reg_email, "elo": 1200})
                st.success("Registration successful! Please login.")
            except requests.exceptions.HTTPError as e:
                error_data = e.args[1] if len(e.args) > 1 else "{}"
                try: error_msg = json.loads(error_data).get("error", {}).get("message", "UNKNOWN_ERROR")
                except json.JSONDecodeError: error_msg = "INVALID_EMAIL_OR_PASSWORD"
                st.error(f"Registration failed: {error_msg.replace('_',' ').capitalize()}")
            except Exception: st.error("Unexpected registration error.")

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
                engine, chosen = eng, cand
                logs.append(f"✓ Engine started: {cand}")
                break
            except Exception as e:
                logs.append(f"✗ Failed to start: {cand} ({e})")
    if engine is None: logs.append("No usable Stockfish binary found.")
    return engine, chosen, logs

class EngineWorker:
    def __init__(self, engine: chess.engine.SimpleEngine): self.engine = engine
    def analyse(self, board: chess.Board, multipv: int, think_ms: int) -> List[chess.engine.InfoDict]:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000))
        return self.engine.analyse(board, limit=limit, multipv=multipv)
    def play(self, board: chess.Board, think_ms: int) -> Optional[chess.Move]:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000))
        try: return self.engine.play(board, limit).move
        except chess.engine.EngineTerminatedError: return None

engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None

# ==================== HELPERS ====================
def render_board_with_click(board: chess.Board, size=400, key_prefix="play"):
    move_input_key = f"{key_prefix}_move_input"
    selected = st.session_state.selected_square

    legal_moves_for_selected = [m.to_square for m in board.legal_moves if selected is not None and m.from_square == selected]
    squares_highlight = chess.SquareSet(legal_moves_for_selected + ([selected] if selected is not None else []))

    svg = chess.svg.board(board, size=size,
                          lastmove=board.peek() if board.move_stack else None,
                          squares=squares_highlight)
    st.image(svg, width=size)

    cols = st.columns(8)
    for i in range(8):
        for j in range(8):
            square = chess.square(i, 7-j)
            btn_key = f"{key_prefix}_btn_{square}"
            if cols[i].button(" ", key=btn_key):
                if selected is None:
                    st.session_state.selected_square = square
                    st.session_state[move_input_key] = chess.SQUARE_NAMES[square]
                else:
                    from_sq = chess.SQUARE_NAMES[selected]
                    to_sq = chess.SQUARE_NAMES[square]
                    st.session_state[move_input_key] = f"{from_sq}{to_sq}"
                    st.session_state.selected_square = None

    move_text = st.text_input("Move (UCI)", st.session_state.get(move_input_key, ""),
                              key=move_input_key, placeholder="Click or type move")
    
    if st.button("Make Move", key=f"{key_prefix}_move_btn"):
        try:
            move = board.parse_uci(st.session_state[move_input_key])
            if move in board.legal_moves:
                st.session_state[move_input_key] = ""
                st.session_state.selected_square = None
                return move
            else: st.warning("Illegal move.")
        except ValueError:
            st.warning("Invalid move format.")
    return None

def pretty_score(info, board):
    sc = info.get("score")
    pov = sc.pov(board.turn) if sc else None
    if pov is None: return "?"
    if pov.is_mate(): return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board, pv, n=6):
    b = board.copy()
    out = []
    for m in pv[:n]:
        try: out.append(b.san(m)); b.push(m)
        except: break
    return " ".join(out)

# ==================== APP UI ====================
st.sidebar.title("CheckmateAI")
board_size = st.sidebar.slider("Board Size", 280, 600, 420, step=20)
st.session_state.engine_ms = st.sidebar.slider("Engine Think Time (ms)", 100, 3000, 600)
st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
st.sidebar.write(f"ELO: **{st.session_state.user_elo}**")
if st.sidebar.button("Logout"):
    st.session_state.clear(); initialize_session_state(); st.rerun()

with st.sidebar.expander("Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}")
    st.write(f"Engine: {engine_path or '(none)'}")
    for l in engine_logs: st.write(l)

TAB_PLAY, TAB_PUZZLE, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

with TAB_PLAY:
    st.subheader("Play vs AI")
    move = render_board_with_click(st.session_state.board, size=board_size, key_prefix="play")
    if move:
        st.session_state.board.push(move)
        if st.session_state.worker and not st.session_state.board.is_game_over():
            with st.spinner("AI thinking..."):
                ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
            if ai_move: st.session_state.board.push(ai_move)
        st.rerun()
    st.text_area("Moves", value=" ".join([st.session_state.board.san(m) for m in st.session_state.board.move_stack]),
                 height=150, disabled=True)
    if st.session_state.board.is_game_over(): st.info(f"Game over: {st.session_state.board.result()}")
    if st.session_state.worker:
        infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
        for i, info in enumerate(infos, 1):
            st.write(f"{i}. {pv_to_san_line(st.session_state.board, info.get('pv', []), 6)} ({pretty_score(info, st.session_state.board)})")
