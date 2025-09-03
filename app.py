# [ Lovaclover AI Transformed Code ]
from __future__ import annotations
import os, sys, sqlite3, math, threading, stat, shutil
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import requests

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import chess, chess.engine, chess.svg

import streamlit as st
import os
import subprocess

# --- 디버깅 블록 시작 ---
st.write("--- App Reloaded ---")
st.write(f"Python Version: {sys.version}")

# stchess 임포트 테스트
try:
    from stchess import board as _st_board
    _HAS_STCHESS_DEBUG = True
    st.success("✅ stchess library imported successfully!")
except Exception as e:
    _HAS_STCHESS_DEBUG = False
    st.error(f"Failed to import stchess: {e}")

# Stockfish 파일 존재 및 권한 확인
stockfish_path = "/usr/bin/stockfish"
st.write(f"Checking for Stockfish at: {stockfish_path}")
if os.path.exists(stockfish_path):
    st.success(f"✅ Found Stockfish file at {stockfish_path}")
    
    # 실행 권한 확인
    if os.access(stockfish_path, os.X_OK):
        st.success("✅ Stockfish has execute permissions.")
        try:
            # 직접 실행하여 버전 확인
            result = subprocess.run([stockfish_path, "uci"], capture_output=True, text=True, timeout=5)
            if "Stockfish" in result.stdout:
                st.success(f"✅ Stockfish engine is working! Output:\n{result.stdout[:200]}...")
            else:
                st.warning(f"Stockfish ran but returned unexpected output: {result.stdout}")
        except Exception as e:
            st.error(f"Failed to execute Stockfish: {e}")
    else:
        st.error("❌ Stockfish does NOT have execute permissions.")
else:
    st.error("❌ Stockfish file not found.")
# --- 디버깅 블록 끝 ---

# =============== 1. Session State 초기화 (가장 먼저 실행) ===============
# 이 부분이 스크립트 최상단에 위치해야 합니다.
if "board_px" not in st.session_state:
    st.session_state.board_px = 420  # 기본 보드 크기
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

# =============== 2. 페이지 설정 및 반응형 CSS ===============
st.set_page_config(page_title="CheckmateAI", layout="wide")

# f-string을 사용하여 session_state 값을 안전하게 주입하고, CSS 선택자를 단순화하여 안정성을 높였습니다.
st.markdown(f"""
<style>
    /* st.html로 생성되는 모든 체스보드 컨테이너에 적용 */
    section[data-testid="st.main"] [data-testid="stHtml"] {{
        max-width: {st.session_state.board_px}px;
        margin: 0 auto; /* 가운데 정렬 */
    }}
    section[data-testid="st.main"] [data-testid="stHtml"] iframe {{
        width: 100%;
        aspect-ratio: 1 / 1;
        height: auto !important;
    }}
</style>
""", unsafe_allow_html=True)


# =============== Interactive board (stchess) ===============
try:
    from stchess import board as _st_board
    _HAS_STCHESS = True
except Exception:
    _HAS_STCHESS = False

def st_chessboard(initial_fen: str, key: str, allow_moves: bool = True) -> str:
    """stchess가 있으면 드래그 가능 보드, 없으면 읽기전용 SVG."""
    # CSS가 크기를 조절하므로 height는 st.session_state.board_px 값을 사용합니다.
    height = st.session_state.board_px
    
    if _HAS_STCHESS:
        try:
            return _st_board(fen=initial_fen, key=key, height=height, interactive=allow_moves)
        except TypeError:
            try:
                return _st_board(fen=initial_fen, key=key, height=height, allow_moves=allow_moves)
            except TypeError:
                return _st_board(fen=initial_fen, key=key, height=height)
    
    # Fallback: static SVG
    try:
        svg = chess.svg.board(chess.Board(initial_fen))
        components.html(f'<div class="board-container">{svg}</div>', height=height + 15)
    except Exception:
        st.warning("Static board render failed; showing FEN.")
        st.code(initial_fen)
    return initial_fen

# =============== Engine candidates & helpers ===============
def _engine_candidates() -> List[str]:
    """OS별로 맞는 후보만 리턴."""
    cands = [
        "/usr/bin/stockfish",
        os.environ.get("STOCKFISH_PATH") or "",
        shutil.which("stockfish") or "",
        os.path.abspath("server/stockfish/stockfish-linux-x86-64-avx2"),
        os.path.abspath("server/stockfish/stockfish"),
        os.path.abspath("engine/stockfish"),
    ]
    if os.name == "nt":
        cands.insert(1, os.path.abspath("server/stockfish/stockfish-windows-x86-64-avx2.exe"))
    return [c for c in cands if c]

ENGINE_MULTIPV = 3

# =============== DB cache =================
@st.cache_resource(show_spinner="Downloading puzzle database...")
def get_db_conn(db_path: str = "puzzles.db"):
    if not os.path.exists(db_path):
        db_url = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1"
        try:
            r = requests.get(db_url, stream=True)
            r.raise_for_status()
            with open(db_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            print("✅ Puzzle DB downloaded successfully.")
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to download puzzle database: {e}")
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE puzzles(puzzle_id TEXT, fen TEXT, moves TEXT, rating INT, themes TEXT)")
            conn.execute("INSERT INTO puzzles VALUES(?,?,?,?,?)", ("demo_1", "8/8/8/8/8/8/5K2/6Rk w - - 0 1", "Rg1#", 1200, "mateIn1"))
            conn.commit()
            return conn
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_puzzles_rating'")
    if cursor.fetchone() is None:
        print("⚡ Creating index on 'rating' column for faster puzzle search.")
        conn.execute("CREATE INDEX idx_puzzles_rating ON puzzles (rating)")
        conn.commit()
    return conn

@st.cache_data(show_spinner=False, ttl=60)
def get_puzzle_near_rating(target_elo: int, k: int = 1) -> List[Dict[str, Any]]:
    conn = get_db_conn()
    rows = conn.execute("""
        SELECT puzzle_id, fen, moves, rating, themes FROM puzzles ORDER BY ABS(rating - ?) LIMIT ?
    """, (int(target_elo), int(k))).fetchall()
    cols = ["puzzle_id","fen","moves","rating","themes"]
    return [dict(zip(cols, r)) for r in rows]

# =============== Engine opener (with diagnostics) ===============
@st.cache_resource(show_spinner=False)
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs: List[str] = []
    engine = None
    chosen = None
    for cand in _engine_candidates():
        if cand.lower().endswith(".exe") and os.name != "nt":
            logs.append(f"↷ {cand} — skipped (Windows .exe on {sys.platform})")
            continue
        if not os.path.exists(cand):
            logs.append(f"✗ {cand} — not found")
            continue
        try:
            if os.name != "nt":
                mode = os.stat(cand).st_mode
                if not (mode & stat.S_IXUSR):
                    os.chmod(cand, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logs.append(f"• {cand} — chmod attempt: {e}")
        try:
            eng = chess.engine.SimpleEngine.popen_uci(cand)
            try:
                eng.configure({"Threads": 1, "Hash": 64})
            except Exception: pass
            engine, chosen = eng, cand
            logs.append(f"✓ {cand} — started successfully")
            break
        except Exception as e:
            logs.append(f"✗ {cand} — failed to start ({e})")
    if engine is None:
        logs.append("No usable Stockfish binary found. Check packages.txt and reboot the app.")
    return engine, chosen, logs

# =============== Eval helpers ===============
def cp_to_winprob(cp: Optional[int]) -> float:
    if cp is None: return 0.5
    return 1.0 / (1.0 + math.exp(-max(min(cp, 3000), -3000) / 350.0))

def pretty_score(info: chess.engine.InfoDict, white_to_move: bool) -> str:
    sc = info.get("score")
    if sc is None: return "?"
    pov = sc.pov(chess.WHITE if white_to_move else chess.BLACK)
    if pov.is_mate(): return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    b = board.copy()
    parts = []
    for m in pv[:n]:
        parts.append(b.san(m))
        b.push(m)
    return " ".join(parts)

def infer_last_move(old_b: chess.Board, new_b: chess.Board) -> Tuple[Optional[chess.Move], Optional[str]]:
    target_fen = new_b.fen()
    for mv in old_b.legal_moves:
        san = old_b.san(mv)
        old_b.push(mv)
        if old_b.fen() == target_fen:
            old_b.pop()
            return mv, san
        old_b.pop()
    return None, None

# =============== Engine worker ===============
class EngineWorker:
    def __init__(self, engine: chess.engine.SimpleEngine):
        self.engine = engine
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.lock = threading.Lock()

    def analyse(self, board: chess.Board, multipv: int, think_ms: int) -> List[chess.engine.InfoDict]:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        with self.lock:
            infos = self.engine.analyse(board, limit=limit, multipv=multipv)
        return infos if isinstance(infos, list) else [infos]

    def play(self, board: chess.Board, think_ms: int) -> chess.Move:
        limit = chess.engine.Limit(time=max(0.05, think_ms / 1000.0))
        with self.lock:
            res = self.engine.play(board, limit)
        return res.move

# --- App Execution ---
engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None
st.session_state.engine_path = engine_path

# =============== Sidebar ===============
st.sidebar.title("CheckmateAI — Streamlit")
st.sidebar.slider("Board Max Size (px)", 280, 560, 420, step=20, key="board_px")
st.sidebar.slider("Engine think time (ms)", 100, 3000, key="engine_ms")
st.sidebar.toggle("Auto-reply by AI", value=True, key="auto_ai")
st.sidebar.number_input("Your training ELO", 400, 3000, key="user_elo_widget")
st.session_state.user_elo = int(st.session_state.user_elo_widget)

with st.sidebar.expander("⚙️ Diagnostics", expanded=(engine is None or not _HAS_STCHESS)):
    st.write("OS:", os.name, "| platform:", sys.platform, "| Python:", sys.version.split()[0])
    st.write("Chosen engine:", st.session_state.engine_path or "(none)")
    for line in engine_logs: st.write(line)
    st.write("stchess installed:", _HAS_STCHESS)

TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# =============== Tab: Play vs AI ===============
with TAB_PLAY:
    st.subheader("Play vs AI (drag to move)")
    col1, col2 = st.columns([1.7, 1])

    with col1:
        b: chess.Board = st.session_state.board
        fen_before = b.fen()
        
        # 3. st_chessboard 호출 시 height 인자 제거
        updated_fen = st_chessboard(fen_before, key="main_board", allow_moves=True)
        
        # (이하 로직은 기존과 동일)
        if updated_fen and updated_fen != fen_before:
            new_b = chess.Board(updated_fen)
            mv, san = infer_last_move(b, new_b)
            st.session_state.board = new_b
            if mv and san:
                st.session_state.history.append({"ply": len(st.session_state.history)+1, "san": san, "eval_cp": None, "winprob": None})
            if st.session_state.worker and st.session_state.auto_ai and not new_b.is_game_over():
                ai = st.session_state.worker.play(new_b, st.session_state.engine_ms)
                if ai:
                    san_ai = new_b.san(ai)
                    new_b.push(ai)
                    post = st.session_state.worker.analyse(new_b, 1, st.session_state.engine_ms)
                    sc = post[0].get("score"); cp = sc.pov(new_b.turn).score(mate_score=100000) if sc else 0
                    st.session_state.history.append({"ply": len(st.session_state.history)+1, "san": san_ai, "eval_cp": cp, "winprob": cp_to_winprob(cp)})
                    st.session_state.board = new_b
                    st.rerun()

    # ... (이하 나머지 코드는 제공된 원본 파일과 동일하게 유지)
    # ... (c1, c2, c3 버튼 로직, col2 로직 등)
        c1, c2, c3 = st.columns(3)
        if c1.button("⏮️ New game"):
            st.session_state.board = chess.Board()
            st.session_state.history.clear()
            st.rerun()
        if c2.button("⬅️ Undo"):
            if len(st.session_state.board.move_stack) > 0:
                st.session_state.board.pop()
                if st.session_state.history: st.session_state.history.pop()
                st.rerun()
        if c3.button("🤖 AI move") and st.session_state.worker and not st.session_state.board.is_game_over():
            mv = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
            if mv:
                san_ai = st.session_state.board.san(mv)
                st.session_state.board.push(mv)
                post = st.session_state.worker.analyse(st.session_state.board, 1, st.session_state.engine_ms)
                sc = post[0].get("score"); cp = sc.pov(st.session_state.board.turn).score(mate_score=100000) if sc else 0
                st.session_state.history.append({"ply": len(st.session_state.history)+1, "san": san_ai, "eval_cp": cp, "winprob": cp_to_winprob(cp)})
                st.rerun()

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
        else:
            st.warning("Engine not running. See diagnostics in the sidebar.")
        st.divider()
        st.write("**Move history**")
        if st.session_state.history:
            st.dataframe(pd.DataFrame(st.session_state.history).tail(30), use_container_width=True, hide_index=True)
        else:
            st.caption("No moves yet.")

# =============== Tab: Puzzles (drag to answer) ===============
with TAB_PUZZLES:
    st.subheader("Rating-based puzzle (drag your first move)")
    puzzles = get_puzzle_near_rating(st.session_state.user_elo, k=1)
    if puzzles:
        pz = puzzles[0]
        st.caption(f"Puzzle {pz['puzzle_id']} • Rating {pz['rating']} • Themes: {pz['themes']}")
        pzb = chess.Board(pz['fen'])
        fen_before = pzb.fen()
        
        updated_fen = st_chessboard(fen_before, key="pz_board", allow_moves=True) # height 인자 제거
        
        if updated_fen and updated_fen != fen_before:
            new_b = chess.Board(updated_fen)
            mv, san = infer_last_move(pzb, new_b)
            if mv is None:
                st.warning("이동을 감지하지 못했습니다. 다시 시도해 주세요.")
            else:
                first = (pz["moves"].strip().split())[0]
                correct_uci = pzb.parse_san(first.replace("+","").replace("#","")).uci() if ("#" in first or "+" in first) else (pzb.parse_san(first).uci() if not first.islower() else first)
                ok = (mv.uci() == correct_uci)
                if ok:
                    st.success("Correct! +20 ELO")
                    st.session_state.user_elo = min(3000, st.session_state.user_elo + 20)
                else:
                    st.error(f"Not quite. Solution starts with: {first}")
                    st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
                st.session_state.user_elo_widget = st.session_state.user_elo
                st.rerun()
    else:
        st.warning("No puzzles found in DB.")

# =============== Tab: Analysis ===============
with TAB_ANALYSIS:
    st.subheader("Position analysis & win probability")
    a1, a2 = st.columns([1.6, 1])
    with a1:
        # 3. st_chessboard 호출 시 height 인자 제거
        st_chessboard(initial_fen=st.session_state.board.fen(), key="ana_board", allow_moves=False)
        
        if st.button("Analyse current position") and st.session_state.worker:
            st.session_state.last_analysis = st.session_state.worker.analyse(
                st.session_state.board, ENGINE_MULTIPV, st.session_state.engine_ms
            )
    with a2:
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