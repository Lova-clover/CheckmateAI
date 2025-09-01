from __future__ import annotations
import os, sqlite3, math, threading, stat, shutil
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import chess, chess.engine, chess.svg

# ================= Page & base styles =================
st.set_page_config(page_title="CheckmateAI", layout="wide")
st.markdown("""
<style>
.block-container { padding-bottom: 6rem; } /* 하단 여백으로 '아래 짤림' 방지 */
div[data-testid="stSidebar"] { min-width: 320px; }
</style>
""", unsafe_allow_html=True)

# =============== Interactive board (stchess) ===============
try:
    from stchess import board as _st_board
    _HAS_STCHESS = True
except Exception:
    _HAS_STCHESS = False

def st_chessboard(initial_fen: str, key: str, height: int = 420, allow_moves: bool = True) -> str:
    """stchess가 있으면 드래그 가능 보드, 없으면 읽기전용 SVG."""
    if _HAS_STCHESS:
        # stchess 버전마다 인자가 조금씩 달라서 순차 시도
        try:
            return _st_board(fen=initial_fen, key=key, height=height, interactive=allow_moves)
        except TypeError:
            try:
                return _st_board(fen=initial_fen, key=key, height=height, allow_moves=allow_moves)
            except TypeError:
                return _st_board(fen=initial_fen, key=key, height=height)
    # Fallback: static SVG (read-only)
    try:
        svg = chess.svg.board(chess.Board(initial_fen))
        components.html(svg, height=height, scrolling=False)
    except Exception:
        st.warning("Static board render failed; showing FEN.")
        st.code(initial_fen)
    return initial_fen

# =============== Engine candidates & helpers ===============
def _engine_candidates() -> List[str]:
    return [
        os.environ.get("STOCKFISH_PATH") or "",                         # 1) ENV override
        "/usr/bin/stockfish",                                           # 2) OS package (packages.txt)
        shutil.which("stockfish") or "",                                # 3) PATH
        os.path.abspath("server/stockfish/stockfish-windows-x86-64-avx2.exe"),# 4) repo binary 
        os.path.abspath("server/stockfish/stockfish"),                  #    alt name
        os.path.abspath("engine/stockfish"),                            # 5) legacy path
    ]

ENGINE_MULTIPV = 3
DEFAULT_ENGINE_MS = 600

# =============== DB cache =================
@st.cache_resource(show_spinner=False)
def get_db_conn(db_path: str = "puzzles.db"):
    if not os.path.exists(db_path):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE puzzles(puzzle_id TEXT, fen TEXT, moves TEXT, rating INT, themes TEXT)")
        conn.execute("INSERT INTO puzzles VALUES(?,?,?,?,?)",
                     ("demo_1", "8/8/8/8/8/8/5K2/6Rk w - - 0 1", "Rg1#", 1200, "mateIn1"))
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
    cols = ["puzzle_id","fen","moves","rating","themes"]
    return [dict(zip(cols, r)) for r in rows]

# =============== Engine opener (with diagnostics) ===============
@st.cache_resource(show_spinner=False)
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs: List[str] = []
    engine = None
    chosen = None
    for cand in _engine_candidates():
        if not cand:
            continue
        if not os.path.exists(cand):
            logs.append(f"✗ {cand} — not found")
            continue
        # ensure exec bit
        try:
            mode = os.stat(cand).st_mode
            if not (mode & stat.S_IXUSR):
                os.chmod(cand, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            logs.append(f"• {cand} — chmod attempt: {e}")
        # try run
        try:
            eng = chess.engine.SimpleEngine.popen_uci(cand)
            try:
                eng.configure({"Threads": 1, "Hash": 64})
            except Exception:
                pass
            engine, chosen = eng, cand
            logs.append(f"✓ {cand} — started successfully")
            break
        except Exception as e:
            logs.append(f"✗ {cand} — failed to start ({e})")
    if engine is None:
        logs.append(
            "No usable Stockfish binary.\n"
            "👉 해결: 리포 루트에 packages.txt 생성 후 아래 한 줄만 넣으세요.\n"
            "    stockfish\n"
            "그럼 Cloud에 /usr/bin/stockfish가 설치됩니다(가장 안정적)."
        )
    return engine, chosen, logs

# =============== Eval helpers ===============
def cp_to_winprob(cp: Optional[int]) -> float:
    if cp is None: return 0.5
    cp = max(min(cp, 3000), -3000)
    return 1.0 / (1.0 + math.exp(-cp / 350.0))

def pretty_score(info: chess.engine.InfoDict, white_to_move: bool) -> str:
    sc = info.get("score")
    if sc is None: return "?"
    pov = sc.pov(chess.WHITE if white_to_move else chess.BLACK)
    if pov.is_mate(): return f"M{pov.mate()}" if pov.mate() is not None else "M?"
    return f"{pov.score()} cp"

def pv_to_san_line(board: chess.Board, pv: List[chess.Move], n: int = 6) -> str:
    b = board.copy(); parts = []
    for m in pv[:n]:
        parts.append(b.san(m)); b.push(m)
    return " ".join(parts)

def infer_last_move(old_b: chess.Board, new_b: chess.Board) -> Tuple[Optional[chess.Move], Optional[str]]:
    target = new_b.fen()
    for mv in list(old_b.legal_moves):
        san = old_b.san(mv)
        old_b.push(mv)
        if old_b.fen() == target:
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
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000.0))
        with self.lock:
            infos = self.engine.analyse(board, limit=limit, multipv=multipv)
        if isinstance(infos, dict): infos = [infos]
        return infos
    def play(self, board: chess.Board, think_ms: int) -> chess.Move:
        limit = chess.engine.Limit(time=max(0.05, think_ms/1000.0))
        with self.lock:
            res = self.engine.play(board, limit)
        return res.move

# =============== Session bootstrap ===============
if "board" not in st.session_state:
    st.session_state.board = chess.Board()
if "history" not in st.session_state:
    st.session_state.history: List[Dict[str, Any]] = []
if "engine_ms" not in st.session_state:
    st.session_state.engine_ms = DEFAULT_ENGINE_MS
# ⚠️ 위젯-상태 분리: user_elo ↔ user_elo_widget
if "user_elo" not in st.session_state:
    st.session_state.user_elo = 1200
if "user_elo_widget" not in st.session_state:
    st.session_state.user_elo_widget = st.session_state.user_elo

engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None
st.session_state.engine_path = engine_path

# =============== Sidebar ===============
st.sidebar.title("CheckmateAI — Streamlit")
st.sidebar.slider("Board size (px)", 340, 640, 420, step=20, key="board_px")
st.sidebar.slider("Engine think time (ms)", 100, 3000, key="engine_ms")
st.sidebar.toggle("Auto-reply by AI", value=True, key="auto_ai")
# 분리된 위젯: 숫자 입력 → 내부 상태 동기화
st.sidebar.number_input("Your training ELO", 400, 3000, key="user_elo_widget")
st.session_state.user_elo = int(st.session_state.user_elo_widget)

with st.sidebar.expander("⚙️ Engine diagnostics", expanded=(engine is None)):
    st.write("Chosen:", st.session_state.engine_path or "(none)")
    for line in engine_logs: st.write(line)
    if not _HAS_STCHESS:
        st.error("Interactive board disabled: `stchess` 미설치. requirements.txt에 `stchess==0.0.1` 추가하세요.")

TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

# =============== Tab: Play vs AI ===============
with TAB_PLAY:
    st.subheader("Play vs AI (drag to move)")
    col1, col2 = st.columns([1.7, 1])

    with col1:
        b: chess.Board = st.session_state.board
        fen_before = b.fen()

        updated_fen = st_chessboard(fen_before, key="main_board",
                                    height=st.session_state.board_px, allow_moves=True)

        # 드래그로 수를 둔 경우(FEN 변경)
        if updated_fen and updated_fen != fen_before:
            new_b = chess.Board(updated_fen)
            mv, san = infer_last_move(b, new_b)
            st.session_state.board = new_b
            if mv and san:
                st.session_state.history.append({"ply": len(st.session_state.history)+1,
                                                 "san": san, "eval_cp": None, "winprob": None})
            # AI 자동 응수
            if st.session_state.worker and st.session_state.auto_ai and not new_b.is_game_over():
                infos = st.session_state.worker.analyse(new_b, 3, st.session_state.engine_ms)
                ai = infos[0].get("pv", [None])[0] if infos and infos[0].get("pv") else None
                if ai:
                    san_ai = new_b.san(ai)
                    new_b.push(ai)
                    post = st.session_state.worker.analyse(new_b, 1, st.session_state.engine_ms)
                    sc = post[0].get("score"); cp = sc.pov(new_b.turn).score(mate_score=100000) if sc else 0
                    st.session_state.history.append({"ply": len(st.session_state.history)+1,
                                                     "san": san_ai, "eval_cp": cp,
                                                     "winprob": cp_to_winprob(cp)})
                    st.session_state.board = new_b

        c1, c2, c3 = st.columns(3)
        if c1.button("⏮️ New game"):
            st.session_state.board = chess.Board()
            st.session_state.history.clear()
        if c2.button("⬅️ Undo"):
            if len(st.session_state.board.move_stack) > 0:
                st.session_state.board.pop()
                if st.session_state.history: st.session_state.history.pop()
        if c3.button("🤖 AI move") and st.session_state.worker and not st.session_state.board.is_game_over():
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            mv = infos[0].get("pv", [None])[0] if infos and infos[0].get("pv") else None
            if mv:
                san_ai = st.session_state.board.san(mv)
                st.session_state.board.push(mv)
                post = st.session_state.worker.analyse(st.session_state.board, 1, st.session_state.engine_ms)
                sc = post[0].get("score"); cp = sc.pov(st.session_state.board.turn).score(mate_score=100000) if sc else 0
                st.session_state.history.append({"ply": len(st.session_state.history)+1,
                                                 "san": san_ai, "eval_cp": cp,
                                                 "winprob": cp_to_winprob(cp)})
        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()} — {st.session_state.board.outcome().termination}")

    with col2:
        st.markdown("**Engine candidates (MultiPV):**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                pv = info.get("pv") or []
                line = pv_to_san_line(st.session_state.board, pv, 6) if pv else ""
                st.write(f"{i}. {line}  •  {pretty_score(info, st.session_state.board.turn)}")
        else:
            st.warning("Engine not running. See diagnostics in the sidebar.")
        st.divider()
        st.write("**Move history**")
        if st.session_state.history:
            st.dataframe(pd.DataFrame(st.session_state.history).tail(30),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("No moves yet.")

# =============== Tab: Puzzles (drag to answer) ===============
with TAB_PUZZLES:
    st.subheader("Rating-based puzzle (drag your first move)")
    puzzles = get_puzzle_near_rating(st.session_state.user_elo, k=1)
    if puzzles:
        pz = puzzles[0]
        st.caption(f"Puzzle {pz['puzzle_id']} • Rating {pz['rating']} • Themes: {pz['themes']}")
        # 퍼즐은 '첫 수' 정답만 검증
        pzb = chess.Board(pz['fen'])
        fen_before = pzb.fen()
        # 사용자 드래그(또는 클릭) 유도
        updated_fen = st_chessboard(fen_before, key="pz_board",
                                    height=st.session_state.board_px, allow_moves=True)

        if updated_fen and updated_fen != fen_before:
            new_b = chess.Board(updated_fen)
            mv, san = infer_last_move(pzb, new_b)
            if mv is None:
                st.warning("이동을 감지하지 못했습니다. 다시 시도해 주세요.")
            else:
                # 정답 첫수 비교 (SAN/기호 제거 후 비교)
                first = (pz["moves"].strip().split())[0]
                # 정답/사용자 모두 +/# 제거 후 UCI 비교
                correct_uci = pzb.parse_san(first.replace("+","").replace("#","")).uci() \
                              if ("#" in first or "+" in first) else \
                              (pzb.parse_san(first).uci() if not first.islower() else first)
                ok = (mv.uci() == correct_uci)
                if ok:
                    st.success("Correct! +20 ELO")
                    st.session_state.user_elo = min(3000, st.session_state.user_elo + 20)
                    st.session_state.user_elo_widget = st.session_state.user_elo  # 위젯 동기화
                else:
                    st.error(f"Not quite. Solution starts with: {first}")
                    st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
                    st.session_state.user_elo_widget = st.session_state.user_elo  # 위젯 동기화
    else:
        st.warning("No puzzles found in DB.")

# =============== Tab: Analysis ===============
with TAB_ANALYSIS:
    st.subheader("Position analysis & win probability")
    a1, a2 = st.columns([1.6, 1])
    with a1:
        st_chessboard(initial_fen=st.session_state.board.fen(), key="ana_board",
                      height=st.session_state.board_px, allow_moves=False)
        if st.button("Analyse current position") and st.session_state.worker:
            st.session_state.last_analysis = st.session_state.worker.analyse(
                st.session_state.board, 3, st.session_state.engine_ms
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
