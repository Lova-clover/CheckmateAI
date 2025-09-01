from __future__ import annotations
import os, sqlite3, json, math, threading, stat, shutil
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, List, Tuple, Optional

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import chess
import chess.engine
import chess.svg  # for static SVG fallback

# === Page & global style ======================================================
st.set_page_config(page_title="CheckmateAI", layout="wide")
st.markdown("""
<style>
/* 아래 여백을 넉넉히 두어 '아래가 짤림' 방지 */
.block-container { padding-bottom: 6rem; }
/* 우측 표 높이를 보드에 맞춰 자연스럽게 */
div[data-testid="stSidebar"] { min-width: 320px; }
</style>
""", unsafe_allow_html=True)

# === Optional interactive board (stchess). Fallback to static =================
try:
    from stchess import board as _st_board  # returns new FEN after user moves
    _HAS_STCHESS = True
except Exception:
    _HAS_STCHESS = False

def st_chessboard(initial_fen: str, key: str, height: int = 440) -> str:
    """If stchess is available, render interactive board and return updated FEN.
       Otherwise render a static SVG and return original FEN."""
    if _HAS_STCHESS:
        return _st_board(fen=initial_fen, key=key, height=height)
    # Fallback: static SVG (read-only)
    try:
        svg = chess.svg.board(chess.Board(initial_fen))
        components.html(svg, height=height, scrolling=False)
    except Exception:
        st.warning("Static board render failed; showing FEN only.")
        st.code(initial_fen)
    return initial_fen

# === Config ===================================================================
# 🧠 엔진 탐색 후보: 환경변수 → repo 경로(사용자 제공) → 일반 경로
ENGINE_CANDIDATES = [
    os.environ.get("STOCKFISH_PATH") or "",                                   # 1) ENV
    os.path.abspath("server/stockfish/stockfish-linux-x86-64-avx2"),          # 2) 사용자 제공 경로
    os.path.abspath("server/stockfish/stockfish"),                            #    여분 이름
    os.path.abspath("engine/stockfish"),                                      # 3) 기존 기본값
    "/usr/bin/stockfish",                                                     # 4) apt 설치
    shutil.which("stockfish") or "",                                          # 5) PATH
]
ENGINE_MILLIS_PER_MOVE = 600
ENGINE_MULTIPV = 3
DEFAULT_USER_ELO = 1200
MAX_HISTORY = 200

# === Cache: engine & DB =======================================================
@st.cache_resource(show_spinner=False)
def get_engine() -> chess.engine.SimpleEngine:
    chosen = None
    for p in ENGINE_CANDIDATES:
        if p and os.path.exists(p):
            chosen = p
            break
    if not chosen:
        tested = [p for p in ENGINE_CANDIDATES if p]
        raise FileNotFoundError(
            "Stockfish binary not found.\nTried:\n- " + "\n- ".join(tested)
            + "\n\nFix: (1) STOCKFISH_PATH 환경변수를 지정하거나"
              " (2) 서버에 'server/stockfish/stockfish-linux-x86-64-avx2'를 포함시키세요."
        )

    # ensure executable bit
    try:
        mode = os.stat(chosen).st_mode
        if not (mode & stat.S_IXUSR):
            os.chmod(chosen, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    st.caption(f"Using engine: {chosen}")
    eng = chess.engine.SimpleEngine.popen_uci(chosen)
    try:
        eng.configure({"Threads": 1, "Hash": 64})
    except Exception:
        pass
    return eng

@st.cache_resource(show_spinner=False)
def get_db_conn(db_path: str = "puzzles.db"):
    if not os.path.exists(db_path):
        # 인메모리 데모 DB (없어도 앱이 죽지 않도록)
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE puzzles(puzzle_id TEXT, fen TEXT, moves TEXT, rating INT, themes TEXT)")
        conn.execute(
            "INSERT INTO puzzles VALUES(?,?,?,?,?)",
            ("demo_1", "8/8/8/8/8/8/5K2/6Rk w - - 0 1", "Rg1#", 1200, "mateIn1")
        )
        conn.commit()
        return conn
    return sqlite3.connect(db_path, check_same_thread=False)

@st.cache_data(show_spinner=False, ttl=60)
def get_puzzle_near_rating(target_elo: int, k: int = 1) -> List[Dict[str, Any]]:
    conn = get_db_conn()
    rows = conn.execute("""
        SELECT puzzle_id, fen, moves, rating, themes
        FROM puzzles
        ORDER BY ABS(rating - ?)
        LIMIT ?
    """, (int(target_elo), int(k))).fetchall()
    cols = ["puzzle_id", "fen", "moves", "rating", "themes"]
    return [dict(zip(cols, r)) for r in rows]

# === Eval helpers =============================================================
def cp_to_winprob(cp: Optional[int]) -> float:
    if cp is None:
        return 0.5
    cp = max(min(cp, 3000), -3000)
    return 1.0 / (1.0 + math.exp(-cp / 350.0))

def pretty_score(info: chess.engine.InfoDict, pov_white_turn: bool) -> str:
    sc = info.get("score")
    if sc is None:
        return "?"
    pov = sc.pov(chess.WHITE if pov_white_turn else chess.BLACK)
    if pov.is_mate():
        return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    b = board.copy()
    parts = []
    for m in pv[:n]:
        parts.append(b.san(m))
        b.push(m)
    return " ".join(parts)

def infer_last_move(old_b: chess.Board, new_b: chess.Board) -> Tuple[Optional[chess.Move], Optional[str]]:
    """Find which legal move from old_b leads exactly to new_b (FEN full match)."""
    target = new_b.fen()  # include counters/castling/ep
    for mv in list(old_b.legal_moves):
        san = old_b.san(mv)
        old_b.push(mv)
        if old_b.fen() == target:
            old_b.pop()
            return mv, san
        old_b.pop()
    return None, None

# === Async engine worker ======================================================
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

    def play(self, board: chess.Board, think_ms: int = ENGINE_MILLIS_PER_MOVE) -> chess.Move:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000.0))
        with self.lock:
            res = self.engine.play(board, limit)
        return res.move

# === Session bootstrap ========================================================
if "board" not in st.session_state:
    st.session_state.board = chess.Board()
if "history" not in st.session_state:
    st.session_state.history: List[Dict[str, Any]] = []
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

# === Sidebar =================================================================
st.sidebar.title("CheckmateAI — Streamlit")
st.sidebar.write("Drag & drop moves • Cached engine/DB • Stable sessions")
st.sidebar.slider("Board size (px)", 360, 640, 440, step=20, key="board_px")
st.sidebar.slider("Engine think time (ms)", 100, 3000, key="engine_ms")
st.sidebar.toggle("Auto-reply by AI", value=True, key="auto_ai")
st.sidebar.number_input("Your training ELO", 400, 3000, key="user_elo")

# === Tabs ====================================================================
TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# --- Tab: Play vs AI ----------------------------------------------------------
with TAB_PLAY:
    st.subheader("Play vs AI (drag to move)")
    col1, col2 = st.columns([1.7, 1])
    with col1:
        board: chess.Board = st.session_state.board
        fen_before = board.fen()

        # Interactive board (or static fallback)
        board_fen = st_chessboard(fen_before, key="main_board", height=st.session_state.board_px)

        # If user dragged a move (interactive path → FEN changed)
        if board_fen and board_fen != fen_before:
            new_board = chess.Board(board_fen)
            mv, san = infer_last_move(board, new_board)
            st.session_state.board = new_board
            if mv and san:
                st.session_state.history.append({
                    "ply": len(st.session_state.history) + 1,
                    "san": san, "eval_cp": None, "winprob": None
                })
            # Auto AI reply if enabled
            if st.session_state.worker and st.session_state.auto_ai and not new_board.is_game_over():
                infos = st.session_state.worker.analyse(new_board, ENGINE_MULTIPV, st.session_state.engine_ms)
                ai_move = infos[0].get("pv", [None])[0] if infos and infos[0].get("pv") else None
                if ai_move:
                    san_ai = new_board.san(ai_move)
                    new_board.push(ai_move)
                    post = st.session_state.worker.analyse(new_board, 1, st.session_state.engine_ms)
                    sc = post[0].get("score")
                    cp = sc.pov(new_board.turn).score(mate_score=100000) if sc else 0
                    st.session_state.history.append({
                        "ply": len(st.session_state.history) + 1,
                        "san": san_ai, "eval_cp": cp, "winprob": cp_to_winprob(cp),
                    })
                    st.session_state.board = new_board

        # Controls
        c1, c2, c3 = st.columns(3)
        if c1.button("⏮️ New game"):
            st.session_state.board = chess.Board()
            st.session_state.history.clear()
        if c2.button("⬅️ Undo"):
            if len(st.session_state.board.move_stack) > 0:
                st.session_state.board.pop()
                if st.session_state.history:
                    st.session_state.history.pop()
        if c3.button("🤖 AI move") and st.session_state.worker:
            if not st.session_state.board.is_game_over():
                infos = st.session_state.worker.analyse(st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms)
                mv = infos[0].get("pv", [None])[0] if infos and infos[0].get("pv") else None
                if mv:
                    san_ai = st.session_state.board.san(mv)
                    st.session_state.board.push(mv)
                    post = st.session_state.worker.analyse(st.session_state.board, 1, st.session_state.engine_ms)
                    sc = post[0].get("score")
                    cp = sc.pov(st.session_state.board.turn).score(mate_score=100000) if sc else 0
                    st.session_state.history.append({
                        "ply": len(st.session_state.history) + 1,
                        "san": san_ai, "eval_cp": cp, "winprob": cp_to_winprob(cp),
                    })

        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()} — {st.session_state.board.outcome().termination}")

    with col2:
        st.markdown("**Engine candidates (MultiPV):**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                pv = info.get("pv") or []
                line = pv_to_san_line(st.session_state.board, pv, 6) if pv else ""
                st.write(f"{i}. {line}  •  {pretty_score(info, st.session_state.board.turn)}")
        st.divider()
        st.write("**Move history**")
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            st.dataframe(df.tail(30), use_container_width=True, hide_index=True)
        else:
            st.caption("No moves yet.")

# --- Tab: Puzzles -------------------------------------------------------------
with TAB_PUZZLES:
    st.subheader("Rating-based puzzle (auto curriculum)")
    puzzles = get_puzzle_near_rating(st.session_state.user_elo, k=1)
    if puzzles:
        pz = puzzles[0]
        st.caption(f"Puzzle {pz['puzzle_id']} • Rating {pz['rating']} • Themes: {pz['themes']}")
        st_chessboard(initial_fen=pz['fen'], key="pz_board", height=st.session_state.board_px)
        user_try = st.text_input("First move (SAN or UCI)", key="pz_try")
        if st.button("Check move"):
            try:
                # Normalize solution first move
                pz_board = chess.Board(pz['fen'])
                first = (pz["moves"].strip().split())[0]
                # Accept SAN/uci
                try:
                    mv = pz_board.parse_san(user_try)
                    user_norm = mv.uci()
                except Exception:
                    user_norm = user_try
                ok = (user_norm.replace("+","").replace("#","") ==
                      first.replace("+","").replace("#",""))
                if ok:
                    st.success("Correct! +20 ELO")
                    st.session_state.user_elo = min(3000, st.session_state.user_elo + 20)
                else:
                    st.error(f"Not quite. Solution starts with: {first}")
                    st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
            except Exception as e:
                st.warning(f"Could not validate: {e}")
    else:
        st.warning("No puzzles found in DB.")

# --- Tab: Analysis ------------------------------------------------------------
with TAB_ANALYSIS:
    st.subheader("Position analysis & win probability")
    b1, b2 = st.columns([1.6, 1])
    with b1:
        st_chessboard(initial_fen=st.session_state.board.fen(), key="ana_board", height=st.session_state.board_px)
        if st.button("Analyse current position") and st.session_state.worker:
            st.session_state.last_analysis = st.session_state.worker.analyse(
                st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms
            )
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
                    "WinProb": round(cp_to_winprob(cp)*100, 1),
                    "Line": pv_to_san_line(st.session_state.board, pv, 10)
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("Run an analysis to see details.")
