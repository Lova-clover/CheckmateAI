from __future__ import annotations
import os, sys, sqlite3, math, threading, stat, shutil
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
import traceback

import streamlit as st
import pandas as pd
import chess, chess.engine, chess.svg
from streamlit_chessboard import chessboard

# =============== 1. PAGE CONFIG (MUST BE THE FIRST STREAMLIT COMMAND) ===============
st.set_page_config(page_title="CheckmateAI", layout="wide")

# =============== 2. SESSION STATE INITIALIZATION ===============
if "board" not in st.session_state:
    st.session_state.board = chess.Board()
if "history" not in st.session_state:
    st.session_state.history = []
if "engine_ms" not in st.session_state:
    st.session_state.engine_ms = 600
if "user_elo" not in st.session_state:
    st.session_state.user_elo = 1200
if "user_elo_widget" not in st.session_state:
    st.session_state.user_elo_widget = st.session_state.user_elo
if "puzzle" not in st.session_state:
    st.session_state.puzzle = None
if "puzzle_board" not in st.session_state:
    st.session_state.puzzle_board = chess.Board()

# =============== ENGINE SETUP ===============
def _engine_candidates() -> List[str]:
    cands = [
        os.path.abspath("engine/stockfish"),
        "/usr/bin/stockfish",
        shutil.which("stockfish") or "",
    ]
    if os.name == "nt":
        cands.insert(1, os.path.abspath("engine/stockfish.exe"))
    return [c for c in cands if c]

@st.cache_resource(show_spinner="Starting chess engine...")
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs, engine, chosen = [], None, None
    for cand in _engine_candidates():
        if not os.path.exists(cand):
            logs.append(f"✗ Not found: {cand}")
            continue
        try:
            if os.name != "nt" and not os.access(cand, os.X_OK):
                logs.append(f"⚠️ Adding execute permission to: {cand}")
                os.chmod(cand, os.stat(cand).st_mode | stat.S_IXUSR)
        except Exception as e:
            logs.append(f"• chmod failed: {e}")
        try:
            eng = chess.engine.SimpleEngine.popen_uci(cand, setpgrp=True)
            try: eng.configure({"Threads": 1, "Hash": 64})
            except Exception: pass
            engine, chosen = eng, cand
            logs.append(f"✓ Engine started: {cand}")
            break
        except Exception as e:
            logs.append(f"✗ Failed to start: {cand} ({e})")
    if engine is None:
        logs.append("No usable Stockfish binary found.")
    return engine, chosen, logs

class EngineWorker:
    def __init__(self, engine: chess.engine.SimpleEngine):
        self.engine = engine
    def analyse(self, board: chess.Board, multipv: int, think_ms: int) -> List[chess.engine.InfoDict]:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        return self.engine.analyse(board, limit=limit, multipv=multipv)
    def play(self, board: chess.Board, think_ms: int) -> Optional[chess.Move]:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        try:
            res = self.engine.play(board, limit)
            return res.move
        except Exception:
            return None
    def quit(self):
        self.engine.quit()

# =============== DATABASE LOGIC ===============
@st.cache_resource(show_spinner="Connecting to puzzle database...")
def get_db_conn(db_path: str = "puzzles.db"):
    # ... (Database download and setup logic remains the same)
    if not os.path.exists(db_path):
        db_url = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1"
        try:
            r = requests.get(db_url, stream=True)
            r.raise_for_status()
            with open(db_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to download puzzle database: {e}")
            return None
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_puzzles_rating'")
    if cursor.fetchone() is None:
        conn.execute("CREATE INDEX idx_puzzles_rating ON puzzles (rating)")
        conn.commit()
    return conn

@st.cache_data(show_spinner=False, ttl=60)
def get_puzzle_near_rating(target_elo: int) -> Optional[Dict[str, Any]]:
    conn = get_db_conn()
    if not conn: return None
    row = conn.execute("""
        SELECT puzzle_id, fen, moves, rating, themes FROM puzzles 
        WHERE puzzle_id NOT IN (SELECT puzzle_id FROM solved_puzzles)
        ORDER BY ABS(rating - ?) LIMIT 1
    """, (int(target_elo),)).fetchone()
    if not row: return None # Fallback if all puzzles are solved
    cols = ["puzzle_id","fen","moves","rating","themes"]
    return dict(zip(cols, row))

# (Dummy table for solved puzzles in this session, for a better UX)
conn = get_db_conn()
if conn:
    conn.execute("CREATE TABLE IF NOT EXISTS solved_puzzles (puzzle_id TEXT PRIMARY KEY)")

# =============== HELPER FUNCTIONS ===============
def pretty_score(info: chess.engine.InfoDict, board: chess.Board) -> str:
    sc = info.get("score")
    if sc is None: return "?"
    pov = sc.pov(board.turn)
    if pov.is_mate(): return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    b = board.copy(); parts = []
    for m in pv[:n]:
        try: parts.append(b.san(m)); b.push(m)
        except Exception: break
    return " ".join(parts)

# =============== APP EXECUTION & SIDEBAR ===============
engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None

st.sidebar.title("CheckmateAI")
board_size = st.sidebar.slider("Board Size (px)", 280, 600, 420, step=20)
st.session_state.engine_ms = st.sidebar.slider("Engine Think Time (ms)", 100, 3000, 600)
st.session_state.user_elo = st.sidebar.number_input("Your Training ELO", 400, 3000, st.session_state.user_elo)

with st.sidebar.expander("⚙️ Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}")
    st.write(f"Chosen engine: {engine_path or '(none)'}")
    for line in engine_logs: st.write(line)

# =============== MAIN LAYOUT ===============
TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

with TAB_PLAY:
    st.subheader("Play vs AI")
    col1, col2 = st.columns([1.7, 1])
    with col1:
        fen = chessboard(st.session_state.board, key="play_board", board_size=board_size)
        if fen != st.session_state.board.fen():
            st.session_state.board.set_fen(fen)
            st.session_state.history.append({"ply": len(st.session_state.history)+1, "san": st.session_state.board.peek().uci()})
            if st.session_state.worker and not st.session_state.board.is_game_over():
                ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
                if ai_move:
                    st.session_state.history[-1]["san"] = st.session_state.board.san(st.session_state.board.peek())
                    san_ai = st.session_state.board.san(ai_move)
                    st.session_state.board.push(ai_move)
                    st.session_state.history.append({"ply": len(st.session_state.history)+1, "san": san_ai})
            st.rerun()

        c1, c2 = st.columns(2)
        if c1.button("⏮️ New Game"):
            st.session_state.board, st.session_state.history = chess.Board(), []
            st.rerun()
        if c2.button("⬅️ Undo (2 plies)"):
            if len(st.session_state.board.move_stack) > 1:
                st.session_state.board.pop(); st.session_state.board.pop()
                if len(st.session_state.history) > 1:
                    st.session_state.history.pop(); st.session_state.history.pop()
                st.rerun()

    with col2:
        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()} — {st.session_state.board.outcome().termination}")
        st.markdown("**Engine Analysis**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                line = pv_to_san_line(st.session_state.board, info.get("pv", []), 6)
                st.write(f"{i}. **{line}** `({pretty_score(info, st.session_state.board)})`")
        st.divider()
        st.write("**Move History**")
        st.dataframe(pd.DataFrame(st.session_state.history).tail(30), use_container_width=True, hide_index=True)

with TAB_PUZZLES:
    st.subheader("Rating-based Puzzle")
    if st.button("Load New Puzzle"):
        st.session_state.puzzle = get_puzzle_near_rating(st.session_state.user_elo)
        if st.session_state.puzzle:
            st.session_state.puzzle_board.set_fen(st.session_state.puzzle["fen"])
            st.rerun()

    if st.session_state.puzzle:
        pz = st.session_state.puzzle
        st.caption(f"Puzzle {pz['puzzle_id']} • Rating {pz['rating']} • Find the best move for {'White' if pz['fen'].split()[1] == 'w' else 'Black'}")
        
        fen = chessboard(st.session_state.puzzle_board, key="puzzle_board", board_size=board_size)

        if fen != st.session_state.puzzle_board.fen():
            user_move = st.session_state.puzzle_board.find_move(chess.Board(pz['fen']), chess.Board(fen))
            solution_move = st.session_state.puzzle_board.parse_uci(pz['moves'].split()[0])

            if user_move == solution_move:
                st.success("Correct! +20 ELO")
                st.session_state.user_elo += 20
                if conn: conn.execute("INSERT OR IGNORE INTO solved_puzzles (puzzle_id) VALUES (?)", (pz['puzzle_id'],))
            else:
                st.error(f"Not quite. The best move was {solution_move.uci()}")
                st.session_state.user_elo -= 15
            
            st.session_state.puzzle = None # Clear puzzle after attempting
            st.rerun()

with TAB_ANALYSIS:
    st.subheader("Position Analysis")
    fen_to_analyze = st.text_input("FEN String", st.session_state.board.fen())
    if fen_to_analyze:
        board_to_analyze = chess.Board(fen_to_analyze)
        a1, a2 = st.columns([1.6, 1])
        with a1:
            chessboard(board_to_analyze, key="ana_board_static", board_size=board_size, show_FEN_input=False, readonly=True)
        with a2:
            if st.button("Analyse Position", key="analyse_btn") and st.session_state.worker:
                infos = st.session_state.worker.analyse(board_to_analyze, 5, st.session_state.engine_ms)
                rows = []
                for i, info in enumerate(infos, 1):
                    line = pv_to_san_line(board_to_analyze, info.get("pv", []), 10)
                    rows.append({
                        "Rank": i, "Score": pretty_score(info, board_to_analyze),
                        "Line": line
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)