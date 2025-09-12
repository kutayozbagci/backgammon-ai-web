"""
@author: ranger
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Tuple, Dict, Any
import uuid, random

from .player import Player   # your rules + apply_path
# DRLagent is used inside Player.brain

# -------- models --------
class NewGameReq(BaseModel):
    ai_side: str = "TWO"   # AI plays "ONE" or "TWO" (you pick)

class RollReq(BaseModel):
    game_id: str

class HumanMoveReq(BaseModel):
    game_id: str
    dice: Tuple[int, int]
    path: List[Tuple[int, int, int]]   # (index, die, type) type: 0 move, -1 bear, 1 enter

class AiMoveReq(BaseModel):
    game_id: str
    dice: Tuple[int, int]

# -------- app --------
app = FastAPI()

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://[::1]:5500",   # IPv6 localhost (what your http.server is using)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------- state --------
GAMES: Dict[str, Dict[str, Any]] = {}

def initial_state() -> List[int]:
    # [own_broken, own_collected, opp_broken, opp_collected] + 24 points
    # kept from the CURRENT side-to-move perspective
    return [0, 0, 0, 0, 2, 0, 0, 0, 0, -5, 0, -3, 0, 0, 0, 5, -5, 0, 0, 0, 3, 0, 5, 0, 0, 0, 0, -2]

def flip_state(s: List[int]) -> List[int]:
    s = s.copy()
    table = s[4:28]
    table = [-x for x in reversed(table)]
    s[0], s[1], s[2], s[3] = s[2], s[3], s[0], s[1]
    s[4:28] = table
    return s

# -------- load single AI --------
AI = Player()
try:
    AI.brain.load_model("backend/models/best_brain.pth")
except Exception as e:
    print("WARNING: failed to load best_brain.pth:", e)
    # it will still run, but choose() must handle no-weights case

# -------- enumerate legal paths (for UI + validation) --------
def enumerate_paths(player: Player, state: List[int], d1: int, d2: int) -> List[List[Tuple[int,int,int]]]:
    dieleft = 4 if d1 == d2 else 2
    allpaths: List[List[Tuple[int,int,int]]] = []

    def rec(st, a, b, left, path):
        # ---- LEAF: all dice consumed -> record this complete path
        if left == 0:
            allpaths.append(path.copy())
            return

        die = a if left > 1 else b

        # won already (edge case if bearing off completes mid-sequence)
        if player.check_if_won(st):
            allpaths.append(path.copy()); return

        # on the bar -> must enter if possible
        if st[0] > 0:
            if player.can_enter(st, die):
                s2 = st.copy(); player.enter(s2, die)
                rec(s2, a, b, left-1, path + [(3+die, die, 1)])
            else:
                # cannot enter with this die; stop this branch
                if path: allpaths.append(path.copy())
            return

        # inside bear-off phase
        if player.check_if_collectable(st):
            branched = False
            # A) bear off (if legal)
            if player.can_collect(st, die):
                sA = st.copy(); idx = player.collect(sA, die)
                rec(sA, a, b, left-1, path + [(idx, die, -1)])
                branched = True
            # B) or move within home board
            for i in range(22, 28):
                if st[i] > 0 and i + die < 28 and (st[i + die] >= -1):
                    sB = st.copy(); player.move_state(sB, i, die)
                    rec(sB, a, b, left-1, path + [(i, die, 0)])
                    branched = True
            if not branched and path:
                allpaths.append(path.copy())
            return

        # regular movement
        moved = False
        for i in range(4, 28):
            if st[i] > 0 and i + die < 28 and (st[i + die] >= -1):
                sN = st.copy(); player.move_state(sN, i, die)
                rec(sN, a, b, left-1, path + [(i, die, 0)])
                moved = True
        if not moved and path:
            allpaths.append(path.copy())

    # try both die orders when not doubles
    rec(state.copy(), d1, d2, dieleft, [])
    if d1 != d2:
        rec(state.copy(), d2, d1, dieleft, [])

    # enforce rules: play as many dice as possible and higher-die rule
    if allpaths:
        max_len = max(len(p) for p in allpaths)
        allpaths = [p for p in allpaths if len(p) == max_len]
        if max_len == 1 and d1 != d2:
            hi = max(d1, d2)
            if any(p[0][1] == hi for p in allpaths):
                allpaths = [p for p in allpaths if p[0][1] == hi]

    # dedupe by afterstate
    seen = {}
    for p in allpaths:
        s_after = AI.apply_path(state.copy(), p)
        seen.setdefault(tuple(s_after), p)
    return list(seen.values())


# -------- endpoints --------
@app.post("/game/new")
def new_game(req: NewGameReq):
    gid = uuid.uuid4().hex
    s = initial_state()                          # ALWAYS human perspective
    ai_side = req.ai_side.upper()
    if ai_side not in ("ONE", "TWO"):
        raise HTTPException(400, "ai_side must be 'ONE' or 'TWO'")
    # if AI plays TWO, you (human) start
    turn = "HUMAN" if ai_side == "TWO" else "AI"
    GAMES[gid] = {"state": s, "ai_side": ai_side, "dice": None, "turn": turn}
    return {"game_id": gid, "state": s, "ai_side": ai_side, "turn": turn}


@app.post("/game/roll")
def roll(req: RollReq):
    g = GAMES.get(req.game_id)
    if not g: raise HTTPException(404, "bad game_id")
    if g["dice"] is not None:
        return {"dice": g["dice"], "turn": g["turn"]}  # already rolled
    d1, d2 = random.randint(1,6), random.randint(1,6)
    g["dice"] = (d1, d2)
    return {"dice": g["dice"], "turn": g["turn"]}


@app.post("/game/legal")
def legal(req: RollReq):
    g = GAMES.get(req.game_id)
    if not g: raise HTTPException(404, "bad game_id")
    if g["turn"] != "HUMAN":
        return {"paths": [], "turn": g["turn"], "can_pass": False}
    if not g["dice"]:
        raise HTTPException(400, "roll first")

    d1, d2 = g["dice"]
    s_human = g["state"]
    paths = enumerate_paths(AI, s_human, d1, d2)
    can_pass = (len(paths) == 0)
    return {"paths": paths, "turn": g["turn"], "can_pass": can_pass}


# HUMAN move: no flip anywhere
@app.post("/game/move/human")
def move_human(req: HumanMoveReq):
    g = GAMES.get(req.game_id)
    if not g: raise HTTPException(404, "bad game_id")
    if g["turn"] != "HUMAN":
        raise HTTPException(400, "not human's turn")
    if not g.get("dice"):
        raise HTTPException(400, "roll first")
    if tuple(req.dice) != tuple(g["dice"]):
        raise HTTPException(400, "dice mismatch; roll again")

    s_h = g["state"]
    d1, d2 = g["dice"]
    legal = enumerate_paths(AI, s_h, d1, d2)

    # -------- PASS when no legal moves --------
    if not legal:
        if req.path == []:
            g["dice"] = None          # consume the roll
            g["turn"] = "AI"          # give turn to AI
            return {"state": g["state"], "done": False, "turn": g["turn"], "passed": True}
        else:
            raise HTTPException(400, "no legal moves; send empty path [] to pass")

    # -------- Normal move --------
    if req.path not in legal:
        raise HTTPException(400, "illegal move for these dice")

    s2_h = AI.apply_path(s_h.copy(), req.path)
    done = (s2_h[1] == 15)

    g["state"] = s2_h
    g["dice"]  = None
    g["turn"]  = "HUMAN" if done else "AI"

    return {"state": g["state"], "done": done, "turn": g["turn"], "passed": False}

# AI move: flip ONLY to compute/apply; flip back before storing/returning
@app.post("/game/move/ai")
def move_ai(req: AiMoveReq):
    g = GAMES.get(req.game_id)
    if not g: raise HTTPException(404, "bad game_id")
    if g["turn"] != "AI":   raise HTTPException(400, "not AI's turn")
    if not g.get("dice"):   raise HTTPException(400, "roll first")
    if tuple(req.dice) != tuple(g["dice"]): raise HTTPException(400, "dice mismatch")

    s_ai = flip_state(g["state"])                   # AI perspective
    d1, d2 = g["dice"]
    paths = enumerate_paths(AI, s_ai, d1, d2)

    if not paths:
        # pass turn; no state change; still keep HUMAN perspective
        g["dice"] = None
        g["turn"] = "HUMAN"
        return {"state": g["state"], "path": [], "done": False, "turn": g["turn"]}

    afters = [AI.flatten(AI.apply_path(s_ai.copy(), p)) for p in paths]
    idx, _ = AI.brain.choose(afters)
    path = paths[idx]

    s2_ai = AI.apply_path(s_ai.copy(), path)        # AI perspective result
    done  = (s2_ai[1] == 15)
    s2_h  = flip_state(s2_ai)                       # back to HUMAN perspective

    g["state"] = s2_h
    g["dice"]  = None                               # <-- clear used dice
    g["turn"]  = "AI" if done else "HUMAN"          # <-- toggle turn

    # (Optionally omit 'path' to avoid mapping across perspectives.)
    return {"state": g["state"], "path": [], "done": done, "turn": g["turn"]}


