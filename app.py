from __future__ import annotations
import os, time, sqlite3, json, math, threading, stat, shutil
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, List, Tuple, Optional

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import chess
import chess.engine
import chess.svg  # for SVG fallback board

# -----------------------------------------------------------------------------
# Optional interactive board: stchess (PyPI). Fallback to static SVG if missing.
# -----------------------------------------------------------------------------
try:
    from stchess import board as _st_board  # returns FEN string after user moves
    _HAS_STCHESS = True
except Exception:
    _HAS_STCHESS = False

def st_chessboard(initial_fen: str, key: str, theme: str = "green",
                  allow_moves: bool = True, height: int = 520) -> str:
    """
    Drop-in replacement for previous `streamlit_chessboard.st_chessboard`.
    If `stchess` is available, show interactive board and return updated FEN.
    Otherwise render a static SVG board and return the original FEN.
    """
    if _HAS_STCHESS:
        # stchess doesn't expose theme/allow_moves toggles,
        # but returns current FEN after user interaction.
        return _st_board(fen=initial_fen, key=key, height=height)
    # Fallback: static SVG (read-only)
    try:
        svg = chess.svg.board(chess.Board(initial_fen))
        components.html(svg, height=height, scrolling=False)
    except Exception:
        st.warning("Static board render failed; showing FEN only.")
        st.code(initial_fen)
    return initial_fen

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ---------------------------
# Constants & Config
# ---------------------------
DEFAULT_ENGINE_PATH = os.environ.get("STOCKFISH_PATH", os.path.abspath("engine/stockfish"))
ENGINE_MILLIS_PER_MOVE = 600  # cloud-friendly default
ENGINE_MULTIPV = 3            # candidates for style pick
MAX_HISTORY = 200

# Simple ELO-like session profile
DEFAULT_USER_ELO = 1200

# ---------------------------
# Caching: engine & DB
# ---------------------------
@st.cache_resource(show_spinner=False)
def get_engine(path: str = DEFAULT_ENGINE_PATH) -> chess.engine.SimpleEngine:
    # Resolve engine path for Streamlit Cloud
    candidates = []
    # 1) ENV
    if path:
        candidates.append(path)
    # 2) Repo binary
    candidates.append(os.path.abspath("engine/stockfish"))
    # 3) System PATH (apt install stockfish -> /usr/bin/stockfish)
    which = shutil.which("stockfish")
    if which:
        candidates.append(which)

    chosen = None
    for p in candidates:
        if p and os.path.exists(p):
            chosen = p
            break
    if not chosen:
        raise FileNotFoundError(
            "Stockfish binary not found. Put it at ./engine/stockfish or set STOCKFISH_PATH, "
            "or add 'stockfish' to PATH (packages.txt)."
        )

    # Ensure executable bit (git may drop it on some flows)
    try:
        st.caption(f"Using engine: {chosen}")
        mode = os.stat(chosen).st_mode
        if not (mode & stat.S_IXUSR):
            os.chmod(chosen, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    engine = chess.engine.SimpleEngine.popen_uci(chosen)
    # Cloud-safe config: 1 thread, small hash
    try:
        engine.configure({"Threads": 1, "Hash": 64})
    except Exception:
        pass
    return engine

@st.cache_resource(show_spinner=False)
def get_db_conn(db_path: str = "puzzles.db"):
    if not os.path.exists(db_path):
        # Create a tiny demo DB in-memory if missing, so the app still runs
        conn = sqlite3.connect(":memory:")
        c = conn.cursor()
        c.execute("CREATE TABLE puzzles(puzzle_id TEXT, fen TEXT, moves TEXT, rating INT, themes TEXT)")
        # one toy puzzle (mate in 1)
        c.execute("INSERT INTO puzzles VALUES(?,?,?,?,?)",
                  ("demo_1", "8/8/8/8/8/8/5K2/6Rk w - - 0 1", "Rg1#", 1200, "mateIn1"))
        conn.commit()
        return conn
    # Disk DB connection
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn

@st.cache_data(show_spinner=False, ttl=60)
def get_puzzle_near_rating(target_elo: int, k: int = 1) -> List[Dict[str, Any]]:
    conn = get_db_conn()
    q = """
    SELECT puzzle_id, fen, moves, rating, themes
    FROM puzzles
    ORDER BY ABS(rating - ?)
    LIMIT ?
    """
    rows = conn.execute(q, (int(target_elo), int(k))).fetchall()
    cols = ["puzzle_id", "fen", "moves", "rating", "themes"]
    return [dict(zip(cols, r)) for r in rows]

# ---------------------------
# Utility: Eval → Win probability
# ---------------------------
def cp_to_winprob(cp: Optional[int], is_white_to_move: bool) -> float:
    if cp is None:
        return 0.5
    # Cap crazy values
    cp = max(min(cp, 3000), -3000)
    # Logistic with scale ~ 350 cp
    p = 1.0 / (1.0 + math.exp(-cp / 350.0))
    return float(p)

def pretty_score(info: chess.engine.InfoDict, turn_white: bool) -> str:
    sc = info.get("score")
    if sc is None:
        return "?"
    pov = sc.pov(chess.WHITE if turn_white else chess.BLACK)
    if pov.is_mate():
        return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

# ---------------------------
# Helpers
# ---------------------------
def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    """Convert a PV move list to SAN string by applying moves on a copy."""
    b = board.copy()
    parts = []
    for m in pv[:n]:
        parts.append(b.san(m))
        b.push(m)
    return " ".join(parts)

def normalize_first_solution(board: chess.Board, first_str: str) -> Optional[str]:
    """Normalize the first solution move to UCI; accept UCI or SAN like 'Rg1#'."""
    # 1) Try UCI as-is
    try:
        m = chess.Move.from_uci(first_str)
        return m.uci()
    except Exception:
        pass
    # 2) Try SAN (strip check/mate symbols)
    try:
        m = board.parse_san(first_str.replace("+", "").replace("#", ""))
        return m.uci()
    except Exception:
        pass
    return None

# ---------------------------
# Async Engine Worker
# ---------------------------
class EngineWorker:
    def __init__(self, engine: chess.engine.SimpleEngine):
        self.engine = engine
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.lock = threading.Lock()

    def analyse(self, board: chess.Board, multipv: int = ENGINE_MULTIPV,
                think_ms: int = ENGINE_MILLIS_PER_MOVE) -> List[chess.engine.InfoDict]:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000.0))
        with self.lock:
            infos = self.engine.analyse(board, limit=limit, multipv=multipv)
        if isinstance(infos, dict):
            infos = [infos]
        return infos

    def analyse_async(self, board: chess.Board, multipv: int = ENGINE_MULTIPV,
                      think_ms: int = ENGINE_MILLIS_PER_MOVE) -> Future:
        return self.pool.submit(self.analyse, board.copy(), multipv, think_ms)

    def play(self, board: chess.Board, think_ms: int = ENGINE_MILLIS_PER_MOVE) -> chess.Move:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000.0))
        with self.lock:
            res = self.engine.play(board, limit)
        return res.move

# ---------------------------
# Style presets for "Top Player" emulation (heuristic pick among MultiPV)
# ---------------------------
STYLE_PRESETS: Dict[str, Dict[str, float]] = {
    "Classical/Karpov": {"check_bias": 5.0, "capture_bias": 2.0, "attack_bias": 1.0},
    "Aggressive/Kasparov": {"check_bias": 12.0, "capture_bias": 6.0, "attack_bias": 4.0},
    "Universal/Carlsen": {"check_bias": 6.0, "capture_bias": 4.0, "attack_bias": 3.0},
}

def score_candidate(board: chess.Board, move: chess.Move, base_cp: int, style: Dict[str, float]) -> float:
    """Light heuristic on top of engine cp score to choose 'style' move among MultiPV."""
    s = float(base_cp)
    # Prefer checks
    board.push(move)
    if board.is_check():
        s += style.get("check_bias", 0.0) * 100
    # Prefer captures
    board.pop()
    if board.is_capture(move):
        s += style.get("capture_bias", 0.0) * 50
    # "attack" proxy: into enemy half
    if (board.turn == chess.WHITE and chess.square_rank(move.to_square) >= 4) or \
       (board.turn == chess.BLACK and chess.square_rank(move.to_square) <= 3):
        s += style.get("attack_bias", 0.0) * 20
    return s

def pick_styled_move(board: chess.Board, infos: List[chess.engine.InfoDict], style_name: str) -> chess.Move:
    style = STYLE_PRESETS.get(style_name, STYLE_PRESETS["Universal/Carlsen"])
    cands: List[Tuple[float, chess.Move]] = []
    for info in infos:
        pv = info.get("pv")
        if not pv:
            continue
        first = pv[0]
        pov = info.get("score")
        base_cp = pov.pov(board.turn).score(mate_score=100000) if pov else 0
        cands.append((score_candidate(board, first, base_cp, style), first))
    if not cands:
        return infos[0]["pv"][0]
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]

# ---------------------------
# Session bootstrap
# ---------------------------
if "board" not in st.session_state:
    st.session_state.board = chess.Board()
if "history" not in st.session_state:
    st.session_state.history: List[Dict[str, Any]] = []  # list of {ply, san, eval_cp, winprob}
if "user_elo" not in st.session_state:
    st.session_state.user_elo = DEFAULT_USER_ELO
if "engine_ms" not in st.session_state:
    st.session_state.engine_ms = ENGINE_MILLIS_PER_MOVE
if "style" not in st.session_state:
    st.session_state.style = "Universal/Carlsen"
if "worker" not in st.session_state:
    try:
        st.session_state.worker = EngineWorker(get_engine())
    except Exception as e:
        st.session_state.worker = None
        st.error(f"Engine init failed: {e}")

# ---------------------------
# Sidebar
# ---------------------------
st.sidebar.title("CheckmateAI — Streamlit")
st.sidebar.write("Session-stable, cached engine & DB. No flaky server sessions ✨")
st.sidebar.number_input("Your training ELO", 400, 3000, key="user_elo")
st.sidebar.slider("Engine think time (ms)", 100, 3000, key="engine_ms")
st.sidebar.selectbox("AI style preset", list(STYLE_PRESETS.keys()), key="style")

# ---------------------------
# Tabs
# ---------------------------
TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS, TAB_TRAINER = st.tabs(
    ["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis", "🎯 Trainer"]
)

# ---------------------------------
# Tab 1: Play vs AI
# ---------------------------------
with TAB_PLAY:
    st.subheader("Play vs AI (with style presets)")
    col1, col2 = st.columns([2, 1])
    with col1:
        board: chess.Board = st.session_state.board
        fen_before = board.fen()
        # (interactive if stchess exists; static SVG otherwise)
        board_fen = st_chessboard(
            initial_fen=fen_before,
            key="main_board",
            theme="green",
            allow_moves=not board.is_game_over(),
            height=520,
        )
        # If user moved on the board (interactive path)
        if board_fen and board_fen != fen_before:
            try:
                st.session_state.board = chess.Board(board_fen)
            except Exception:
                pass

        # Minimal text move input (works also in fallback mode)
        user_move_typed = st.text_input("Type your move (SAN or UCI), e.g. 'e4' or 'e2e4'", key="play_try")
        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
        if bcol1.button("⏮️ New game"):
            st.session_state.board = chess.Board()
            st.session_state.history = []

        if bcol2.button("👤 Make my move") and user_move_typed:
            try:
                try:
                    mv = st.session_state.board.parse_san(user_move_typed)
                except Exception:
                    mv = chess.Move.from_uci(user_move_typed)
                if mv in st.session_state.board.legal_moves:
                    san_str = st.session_state.board.san(mv)
                    st.session_state.board.push(mv)
                    st.session_state.history.append({
                        "ply": len(st.session_state.history)+1,
                        "san": san_str,
                        "eval_cp": 0,
                        "winprob": 0.5,
                    })
                else:
                    st.warning("Illegal move.")
            except Exception as e:
                st.warning(f"Could not parse move: {e}")

        if bcol3.button("🤖 AI move") and st.session_state.worker:
            if not st.session_state.board.is_game_over():
                # Analyse, pick a move
                infos = st.session_state.worker.analyse(
                    st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms
                )
                mv = pick_styled_move(st.session_state.board, infos, st.session_state.style)
                # Compute SAN BEFORE pushing
                san_str = st.session_state.board.san(mv)
                # Make move
                st.session_state.board.push(mv)
                # Post-move eval
                post_infos = st.session_state.worker.analyse(st.session_state.board, 1, st.session_state.engine_ms)
                sc = post_infos[0].get("score")
                cp = sc.pov(st.session_state.board.turn).score(mate_score=100000) if sc else 0
                st.session_state.history.append({
                    "ply": len(st.session_state.history)+1,
                    "san": san_str,
                    "eval_cp": cp,
                    "winprob": cp_to_winprob(cp, st.session_state.board.turn),
                })

        if bcol4.button("⬅️ Undo"):
            if len(st.session_state.board.move_stack) > 0:
                st.session_state.board.pop()
                if st.session_state.history:
                    st.session_state.history.pop()

        # Game status
        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()} — {st.session_state.board.outcome().termination}")

    with col2:
        st.markdown("**Engine candidates (MultiPV):**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(
                st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms
            )
            for i, info in enumerate(infos, 1):
                pv = info.get("pv") or []
                line = pv_to_san_line(st.session_state.board, pv, 6) if pv else ""
                st.write(f"{i}. {line}  •  {pretty_score(info, st.session_state.board.turn)}")
        st.divider()
        st.write("**Move history**")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            st.dataframe(df.tail(20), use_container_width=True, hide_index=True)
        else:
            st.caption("No moves yet.")

# ---------------------------------
# Tab 2: Puzzles
# ---------------------------------
with TAB_PUZZLES:
    st.subheader("Rating-based puzzle (auto curriculum)")
    # Load a puzzle near user's rating
    puzzles = get_puzzle_near_rating(st.session_state.user_elo, k=1)
    if puzzles:
        pz = puzzles[0]
        st.caption(f"Puzzle {pz['puzzle_id']} • Rating {pz['rating']} • Themes: {pz['themes']}")
        pz_board = chess.Board(pz['fen'])
        st_chessboard(initial_fen=pz_board.fen(), key="pz_board", allow_moves=False, height=520)
        user_try = st.text_input("Enter your first move (SAN or UCI)", key="pz_try")
        if st.button("Check move"):
            try:
                # Normalize solution first move
                sol_moves = pz["moves"].strip().split()
                first = sol_moves[0]
                first_norm = normalize_first_solution(pz_board, first)

                # Normalize user input
                move_obj = None
                try:
                    move_obj = pz_board.parse_san(user_try)
                except Exception:
                    try:
                        move_obj = chess.Move.from_uci(user_try)
                    except Exception:
                        move_obj = None

                user_norm = move_obj.uci() if move_obj else None

                if first_norm and user_norm and user_norm == first_norm:
                    st.success("Correct! +20 ELO")
                    st.session_state.user_elo = min(3000, st.session_state.user_elo + 20)
                else:
                    st.error(f"Not quite. Solution starts with: {first}")
                    st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
            except Exception as e:
                st.warning(f"Could not validate: {e}")
    else:
        st.warning("No puzzles found in DB.")

# ---------------------------------
# Tab 3: Analysis
# ---------------------------------
with TAB_ANALYSIS:
    st.subheader("Position analysis & win probability")
    b1, b2 = st.columns([2,1])
    with b1:
        st_chessboard(initial_fen=st.session_state.board.fen(), key="ana_board", allow_moves=False, height=520)
        if st.button("Analyse current position") and st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms)
            st.session_state.last_analysis = infos
    with b2:
        if "last_analysis" in st.session_state:
            infos = st.session_state.last_analysis
            rows = []
            for i, info in enumerate(infos, 1):
                pv = info.get("pv") or []
                sc = info.get("score")
                cp = sc.pov(st.session_state.board.turn).score(mate_score=100000) if sc else 0
                rows.append({
                    "Rank": i,
                    "Score": pretty_score(info, st.session_state.board.turn),
                    "WinProb": round(cp_to_winprob(cp, st.session_state.board.turn)*100, 1),
                    "Line": pv_to_san_line(st.session_state.board, pv, 10)
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("Run an analysis to see details.")

    st.divider()
    st.markdown("**Win probability over game history**")
    if st.session_state.history:
        x = list(range(1, len(st.session_state.history)+1))
        y = [h["winprob"] for h in st.session_state.history]
        st.line_chart(pd.DataFrame({"ply": x, "win_prob": y}).set_index("ply"))
    else:
        st.caption("Play a few moves to see the chart.")

# ---------------------------------
# Tab 4: Trainer
# ---------------------------------
with TAB_TRAINER:
    st.subheader("Structured training plan")
    plan = [
        {"Block": "Tactics Basics", "Target": "+100 ELO", "Drills/day": 15},
        {"Block": "Calculation", "Target": "+150 ELO", "Drills/day": 20},
        {"Block": "Endgames Core", "Target": "+120 ELO", "Drills/day": 10},
        {"Block": "Opening Review", "Target": "+80 ELO", "Drills/day": 8},
    ]
    st.table(pd.DataFrame(plan))
    st.caption("Tip: your puzzle difficulty auto-tracks your session ELO. Solve streaks push it up; misses pull it down.")

# ---------------------------
# Footer
# ---------------------------
st.divider()
st.caption("💡 Performance: Engine & DB are cached per session. If you see engine timeouts, reduce think time or Threads.")
