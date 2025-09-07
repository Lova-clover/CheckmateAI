from __future__ import annotations
import os, sys, shutil
from typing import List, Optional, Tuple
import json
import streamlit as st
import chess, chess.engine
import pyrebase
from streamlit.components.v1 import html

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ==================== SESSION STATE ====================
def initialize_session_state():
    defaults = {
        "board": chess.Board(),
        "puzzle_board": chess.Board(),
        "engine_ms": 600,
        "user_elo": 1200,
        "user_logged_in": False,
        "username": "",
        "user_info": None,
        "solved_puzzles": set(),
        "puzzle": None,
        "worker": None,
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
        st.error(f"Firebase init failed: {e}")
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
                    st.session_state.solved_puzzles = set(user_data.get("solved_puzzles", []))
                else:
                    db.child("users").child(user['localId']).set({"email": email, "elo": 1200})
                st.success("Login successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with col2:
        st.subheader("Register")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register"):
            try:
                user = auth.create_user_with_email_and_password(reg_email, reg_password)
                db.child("users").child(user['localId']).set({"email": reg_email, "elo": 1200})
                st.success("Registration successful! Please login.")
            except Exception as e:
                st.error(f"Registration failed: {e}")

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
                logs.append(f"✗ Failed: {cand} ({e})")
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
    st.session_state.clear()
    initialize_session_state()
    st.rerun()

with st.sidebar.expander("Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}")
    st.write(f"Engine: {engine_path or '(none)'}")
    for l in engine_logs: st.write(l)

TAB_PLAY, TAB_PUZZLE, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# ==================== Helper: Render Chessboard.JS ====================
def render_chessboard(board_fen: str, key: str):
    js_code = f"""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
    <div id="board_{key}" style="width: {board_size}px"></div>
    <script>
    var board_{key} = Chessboard('board_{key}', {{
        draggable: true,
        position: '{board_fen}',
        onDrop: function(source, target) {{
            const move = source + target;
            fetch("/?move_{key}=" + move).then(() => location.reload());
        }}
    }});
    </script>
    """
    html(js_code, height=board_size + 50)

# ==================== Play vs AI ====================
with TAB_PLAY:
    st.subheader("Play vs AI")
    render_chessboard(st.session_state.board.fen(), "play")
    
    move_param = st.experimental_get_query_params().get("move_play")
    if move_param:
        try:
            uci_move = move_param[0]
            m = chess.Move.from_uci(uci_move)
            if m in st.session_state.board.legal_moves:
                st.session_state.board.push(m)
                if st.session_state.worker and not st.session_state.board.is_game_over():
                    ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
                    if ai_move:
                        st.session_state.board.push(ai_move)
                st.experimental_rerun()
        except Exception:
            st.warning("Illegal move.")
    
    st.text_area("Moves",
                 value=" ".join([st.session_state.board.san(m) for m in st.session_state.board.move_stack]),
                 height=150, disabled=True)

    if st.session_state.board.is_game_over():
        st.info(f"Game over: {st.session_state.board.result()}")
    if st.session_state.worker:
        infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
        for i, info in enumerate(infos, 1):
            st.write(f"{i}. {pv_to_san_line(st.session_state.board, info.get('pv', []), 6)} ({pretty_score(info, st.session_state.board)})")

# ==================== Puzzle ====================
with TAB_PUZZLE:
    st.subheader("Puzzle")
    if not st.session_state.puzzle:
        # 예시 퍼즐 (실제 DB에서 가져와도 됨)
        st.session_state.puzzle_board.set_fen("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        st.session_state.puzzle = st.session_state.puzzle_board.copy()
    
    render_chessboard(st.session_state.puzzle_board.fen(), "puzzle")
    
    move_param = st.experimental_get_query_params().get("move_puzzle")
    if move_param:
        try:
            uci_move = move_param[0]
            m = chess.Move.from_uci(uci_move)
            if m in st.session_state.puzzle_board.legal_moves:
                st.session_state.puzzle_board.push(m)
                # 단순 검증: 마지막 move가 checkmate이면 성공
                if st.session_state.puzzle_board.is_checkmate():
                    st.success("Puzzle solved!")
                    st.session_state.solved_puzzles.add(st.session_state.puzzle_board.fen())
                    st.session_state.user_elo += 10
                    db.child("users").child(st.session_state.user_info['localId']).update({
                        "elo": st.session_state.user_elo,
                        "solved_puzzles": list(st.session_state.solved_puzzles)
                    })
                st.experimental_rerun()
            else:
                st.warning("Illegal move.")
        except Exception:
            st.warning("Invalid move.")

# ==================== Analysis ====================
with TAB_ANALYSIS:
    st.subheader("Analysis")
    render_chessboard(st.session_state.board.fen(), "analysis")
    if st.session_state.worker:
        infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
        for i, info in enumerate(infos, 1):
            st.write(f"{i}. PV: {pv_to_san_line(st.session_state.board, info.get('pv', []), 6)} | Score: {pretty_score(info, st.session_state.board)}")
