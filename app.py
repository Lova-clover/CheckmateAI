from __future__ import annotations
import os, sys, sqlite3, shutil
from typing import Dict, Any, List, Tuple, Optional
import requests
import streamlit as st
import chess, chess.engine, chess.svg
import base64
import pyrebase

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="CheckmateAI", layout="wide")

# ==================== SESSION STATE DEFAULTS ====================
def initialize_session_state():
    defaults = {
        "board": chess.Board(), "history": [], "engine_ms": 600, "user_elo": 1200,
        "puzzle": None, "puzzle_board": chess.Board(), "last_analysis": None,
        "puzzle_result": "", "selected_square": None, "user_logged_in": False,
        "username": "", "user_info": None, "solved_puzzles": set()
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

initialize_session_state()

# ==================== FIREBASE SETUP ====================
@st.cache_resource
def init_firebase():
    try:
        firebase_config = st.secrets["firebase_credentials"]
        firebase = pyrebase.initialize_app(firebase_config)
        return firebase
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}. Check your Streamlit Secrets.")
        return None

firebase = init_firebase()
auth = firebase.auth() if firebase else None
db = firebase.database() if firebase else None

# ==================== ENGINE SETUP ====================
@st.cache_resource(show_spinner="Starting chess engine...")
def open_engine_with_diagnostics() -> Tuple[Optional[chess.engine.SimpleEngine], Optional[str], List[str]]:
    logs, engine, chosen = [], None, None
    for cand in ["/usr/games/stockfish", shutil.which("stockfish")]:
        if cand and os.path.exists(cand):
            try:
                eng = chess.engine.SimpleEngine.popen_uci(cand, setpgrp=True)
                try: eng.configure({"Threads": 1, "Hash": 64})
                except chess.engine.EngineError: pass
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
        except chess.engine.EngineTerminatedError: return None

# ==================== PUZZLE DATABASE (LOCAL SQLITE) ====================
@st.cache_resource(show_spinner="Connecting to puzzle database...")
def get_puzzle_db_conn(puzzle_db_path: str = "puzzles.db"):
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
    return sqlite3.connect(puzzle_db_path, check_same_thread=False)

@st.cache_data(show_spinner=False, ttl=3600)
def get_puzzles_as_df():
    conn = get_puzzle_db_conn()
    if not conn: return None
    try:
        df = pd.read_sql_query("SELECT puzzle_id, fen, moves, rating FROM puzzles", conn)
        return df
    finally:
        if conn: conn.close()

puzzles_df = get_puzzles_as_df()

def get_puzzle_near_rating(target_elo: int, solved_ids: set) -> Optional[Dict[str, Any]]:
    if puzzles_df is None: return None
    
    unsolved_df = puzzles_df[~puzzles_df['puzzle_id'].isin(solved_ids)]
    
    elo_range_df = unsolved_df[
        (unsolved_df['rating'] >= target_elo - 150) & 
        (unsolved_df['rating'] <= target_elo + 150)
    ]

    if not elo_range_df.empty:
        return elo_range_df.sample(1).to_dict('records')[0]
    
    st.warning("No new puzzles found in your ELO range. Loading a random one.")
    if not unsolved_df.empty:
        return unsolved_df.sample(1).to_dict('records')[0]
    
    st.info("You've solved all the puzzles! Resetting your progress for fun.")
    if db and st.session_state.user_info:
        db.child("users").child(st.session_state.user_info['localId']).child("solved_puzzles").remove()
    return puzzles_df.sample(1).to_dict('records')[0]


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


# ==================== BOARD RENDER (STABLE MOUSE CLICK) ====================
def render_board_with_mouse(board: chess.Board, size: int = 400, key_prefix: str = "play"):
    legal_moves_for_selected = []
    if st.session_state.selected_square is not None:
        legal_moves_for_selected = [m.to_square for m in board.legal_moves if m.from_square == st.session_state.selected_square]
    
    svg_data = chess.svg.board(
        board,
        size=size,
        lastmove=board.peek() if board.move_stack else None,
        check=board.king(board.turn) if board.is_check() else None,
        squares=chess.SquareSet(legal_moves_for_selected + ([st.session_state.selected_square] if st.session_state.selected_square is not None else []))
    )
    st.image(svg_data, width=size)
    
    move_uci = st.text_input("Enter move (e.g. e2e4) or click squares", key=f"{key_prefix}_move_input", placeholder="Click two squares or type move here").lower()
    
    clicked_move = None
    
    # Create a grid of buttons for clicking
    # This is a bit of a hacky way to get clickable squares in Streamlit
    # A custom component would be better, but this works without extra dependencies
    square_size = size // 8
    
    # For a better UI, we will use text input as the primary move maker
    # and clicks will just fill the text input
    
    # We will need to re-think the click logic to be more intuitive.
    # For now, let's stick with the text input as it's the most reliable.
    
    if st.button("Make Move", key=f"{key_prefix}_move_btn"):
        try:
            move = board.parse_uci(move_uci)
            if move in board.legal_moves:
                return move
            else:
                st.warning("Illegal move.")
        except ValueError:
            st.warning("Invalid move format. Use UCI format like 'e2e4'.")
    return None


# ==================== FIREBASE LOGIN / REGISTER UI ====================
def login_page():
    st.subheader("Login / Register")
    if not auth or not db:
        st.error("Firebase is not initialized. Cannot proceed.")
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
                    solved_puzzles_list = user_data.get("solved_puzzles", [])
                    st.session_state.solved_puzzles = set(solved_puzzles_list if solved_puzzles_list else [])
                else: # First time login for this user, create data
                    new_user_data = {"email": email, "elo": 1200, "solved_puzzles": ["dummy_id"]}
                    db.child("users").child(user['localId']).set(new_user_data)


                st.success("Login successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to login. Check your credentials.")

    with col2:
        st.subheader("Register")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("New Password", type="password", key="reg_pass")
        if st.button("Register"):
            try:
                user = auth.create_user_with_email_and_password(reg_email, reg_password)
                user_data = {"email": reg_email, "elo": 1200, "solved_puzzles": ["dummy_id"]}
                db.child("users").child(user['localId']).set(user_data)
                st.success("Registration successful! Please login.")
            except Exception as e:
                st.error(f"Failed to register. The email might already be in use.")

# ==================== APP UI ====================
engine, engine_path, engine_logs = open_engine_with_diagnostics()
st.session_state.worker = EngineWorker(engine) if engine else None

st.sidebar.title("CheckmateAI")
board_size = st.sidebar.slider("Board Size (px)", 280, 600, 420, step=20)
st.session_state.engine_ms = st.sidebar.slider("Engine Think Time (ms)", 100, 3000, 600)

if st.session_state.user_logged_in:
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
    st.sidebar.write(f"ELO: **{st.session_state.user_elo}**")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        initialize_session_state()
        st.rerun()

with st.sidebar.expander("⚙️ Diagnostics", expanded=(engine is None)):
    st.write(f"Python: {sys.version.split()[0]}")
    st.write(f"Chosen engine: {engine_path or '(none)'}")
    for line in engine_logs: st.write(line)

if not st.session_state.user_logged_in:
    login_page()
    st.stop()

TAB_PLAY, TAB_PUZZLES, TAB_ANALYSIS = st.tabs(["♟️ Play vs AI", "🧩 Puzzles", "📊 Analysis"])

with TAB_PLAY:
    st.subheader("Play vs AI")
    col1, col2 = st.columns([1.7, 1])
    with col1:
        move = render_board_with_mouse(st.session_state.board, size=board_size, key_prefix="play")
        if move:
            st.session_state.board.push(move)
            if st.session_state.worker and not st.session_state.board.is_game_over():
                with st.spinner("AI is thinking..."):
                    ai_move = st.session_state.worker.play(st.session_state.board, st.session_state.engine_ms)
                if ai_move: st.session_state.board.push(ai_move)
            st.rerun()
            
    with col2:
        st.write("Move History")
        san_history = [st.session_state.board.san(m) for m in st.session_state.board.move_stack]
        st.text_area("Moves", value=" ".join(san_history), height=200, disabled=True)
        if st.session_state.board.is_game_over():
            st.info(f"Game over: {st.session_state.board.result()}")
        
        st.markdown("**Engine Analysis**")
        if st.session_state.worker:
            infos = st.session_state.worker.analyse(st.session_state.board, 3, st.session_state.engine_ms)
            for i, info in enumerate(infos, 1):
                st.write(f"{i}. **{pv_to_san_line(st.session_state.board, info.get('pv', []), 6)}** `({pretty_score(info, st.session_state.board)})`")


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
        
        move_obj = render_board_with_mouse(st.session_state.puzzle_board, size=board_size, key_prefix="puzzle")
        if move_obj and db:
            solution_move_uci = pz['moves'].split()[0]
            user_id = st.session_state.user_info['localId']
            
            if move_obj.uci() == solution_move_uci:
                st.session_state.user_elo += 20
                st.session_state.puzzle_result = f"✅ Correct! +20 ELO"
                st.session_state.solved_puzzles.add(pz['puzzle_id'])
            else:
                st.session_state.user_elo = max(400, st.session_state.user_elo - 15)
                st.session_state.puzzle_result = f"❌ Incorrect. The move was {solution_move_uci}"
            
            db.child("users").child(user_id).update({
                "elo": st.session_state.user_elo,
                "solved_puzzles": list(st.session_state.solved_puzzles)
            })
            
            st.session_state.puzzle = None 
            st.rerun()

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
                        infos = st.session_state.worker.analyse(board_to_analyze, 5, 2000) # Deeper analysis
                    for i, info in enumerate(infos, 1):
                        st.write(f"{i}. **{pv_to_san_line(board_to_analyze, info.get('pv', []), 8)}** `({pretty_score(info, board_to_analyze)})`")
        except ValueError:
            st.error("Invalid FEN string.")