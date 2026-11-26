"""The rules of the multiplayer games. Pure functions, no database, no Flask - so they are easy to test.

Every game offers the same small set of functions (see GAMES at the bottom):
    new(players, level)         -> state (a dict that can be saved as JSON)
    move(state, who, move)      -> changes the state or raises GameError (an illegal move)
    view(state, me)             -> what ONE player may see (hidden information stays hidden)
    bot_move(state, level)      -> a move for the computer player (or None)
"players" is a list of 1 or 2 names; the computer is the name "bot". state["turn"] is an index into the players.
state["status"] is "playing" or "done"; state["winner"] is a player index, "draw" or None.
The SERVER runs these rules. The browser only draws the board, so nobody can cheat by editing the page.
"""
import random
import time

WORDS = """about above actor adult after again agree ahead alarm album alive allow alone along angry apple argue arise
asset aware award badly baker basic beach begin being below bench birth black blame blank blind block blood board boost
brain brand bread break brick bride brief bring broad brown build cabin candy carry catch cause chain chair chalk chart
cheap check chess chest chief child chord civil claim class clean clear click climb clock close cloud coach coast color
comic count court cover crane crash crazy cream crime cross crowd crown daily dance death delay depth dirty dozen draft
drama dream dress drink drive early earth eight elbow empty enemy enjoy enter equal error event every exact extra faith
false fancy fault feast fence field fifth fight final first flame flash fleet floor flour focus force frame fresh front
fruit funny ghost giant glass globe glory grace grade grain grand grant grape grass great green group guard guess guest
guide habit happy heart heavy honey horse hotel house human humor ideal image index inner input issue joint judge juice
knife knock known label large laser later laugh layer learn least leave legal level light limit local logic loose lucky
lunch magic major maker march match maybe mayor media metal might minor model money month moral motor mount mouse mouth
movie music naive nerve never newly night noise north novel nurse ocean offer often olive onion opera order other outer
owner paint panel paper party pasta pause peace pearl phase phone photo piano piece pilot pitch pizza place plain plane
plant plate point pound power press price pride prime print prize proof proud pupil queen quick quiet radio raise range
rapid ratio reach ready realm refer relax reply rider right rival river robot rocky rough round route royal rugby rural
salad scale scene scope score sense serve seven shade shake shape share sharp sheep sheet shelf shell shift shine shirt
shock shoot short shown sight silly since skill sleep slice slide small smart smile smoke snake solid solve sound south
space spare speak speed spell spend spice split spoon sport spray squad stack staff stage stair stand start state steam
steel stick still stock stone store storm story strip stuff style sugar suite sunny super sweet swing table taste teach
tenth thank theme there thick thing think third those three throw thumb tiger tight timer tired title toast today tooth
topic total touch tough tower trace track trade trail train treat trend trial tribe trick truck truly trust truth twice
uncle under union unity until upper upset urban usage usual valid value video virus visit vital voice waste watch water
wheel where which while white whole whose woman world worry worth would write wrong young youth zebra""".split()

SENTENCES = [
    "the quick brown fox jumps over the lazy dog",
    "a good friend is a treasure that never gets old",
    "practice makes progress when you keep going every day",
    "the best way to learn code is to build small things",
    "we can do hard things when we do them together",
    "clouds drift over the quiet hills while the town sleeps",
    "every great game starts with a simple idea and a lot of testing",
]


class GameError(Exception):
    pass


def _who(state, name):
    if name not in state["players"]:
        raise GameError("You are not in this game.")
    return state["players"].index(name)


def _finish(state, winner):
    state["status"] = "done"
    state["winner"] = winner


def _rng():
    return random.SystemRandom()


# ============================================================================ Tic-Tac-Toe
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
# How often the computer plays the PERFECT move (otherwise a random free cell): easy never, impossible always.
TTT_STRENGTH = {"easy": 0.0, "medium": 0.5, "hard": 0.85, "impossible": 1.0}


def ttt_winner(b):
    for a, c, d in LINES:
        if b[a] is not None and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if all(x is not None for x in b) else None


def _minimax(b, turn, me):
    w = ttt_winner(b)
    if w == me:
        return 1, None
    if w == "draw":
        return 0, None
    if w is not None:
        return -1, None
    best, best_i = (-2, None) if turn == me else (2, None)
    for i, cell in enumerate(b):
        if cell is not None:
            continue
        b[i] = turn
        score, _ = _minimax(b, 1 - turn, me)
        b[i] = None
        if (turn == me and score > best) or (turn != me and score < best):
            best, best_i = score, i
    return best, best_i


def ttt_new(players, level="easy"):
    return {"players": players, "board": [None] * 9, "turn": 0, "status": "playing", "winner": None}


def ttt_move(state, who, move):
    i = _who(state, who)
    if state["status"] != "playing" or state["turn"] != i:
        raise GameError("It is not your turn.")
    cell = move.get("cell") if isinstance(move, dict) else None
    if isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 8 or state["board"][cell] is not None:
        raise GameError("That cell is not free.")
    state["board"][cell] = i
    w = ttt_winner(state["board"])
    if w == "draw":
        _finish(state, "draw")
    elif w is not None:
        _finish(state, w)
    else:
        state["turn"] = 1 - i


def ttt_bot(state, level):
    me = state["turn"]
    free = [i for i, c in enumerate(state["board"]) if c is None]
    if not free:
        return None
    if _rng().random() < TTT_STRENGTH.get(level, 0.5):
        if len(free) == 9:
            return {"cell": _rng().choice([0, 2, 4, 6, 8])}        # any corner/centre is perfect on an empty board
        _, best = _minimax(list(state["board"]), me, me)
        if best is not None:
            return {"cell": best}
    return {"cell": _rng().choice(free)}


# ============================================================================ Checkers (draughts, 8x8)
# Board: 64 cells, 0 = empty, 1/2 = men of player 0/1, 3/4 = kings of player 0/1. Player 0 starts at the bottom and moves up (row index
# decreases). Captures are mandatory and may continue (multi-jump); a man reaching the last row becomes a king.
def ck_new(players, level="easy"):
    b = [0] * 64
    for r in range(8):
        for c in range(8):
            if (r + c) % 2 == 1:
                if r < 3:
                    b[r * 8 + c] = 2
                elif r > 4:
                    b[r * 8 + c] = 1
    return {"players": players, "board": b, "turn": 0, "status": "playing", "winner": None, "must": None}


def _owner(v):
    return None if v == 0 else (0 if v in (1, 3) else 1)


def _dirs(v):
    if v == 3 or v == 4:
        return [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    return [(-1, -1), (-1, 1)] if v == 1 else [(1, -1), (1, 1)]


def _jumps(b, pos, v, player):
    out = []
    r, c = divmod(pos, 8)
    for dr, dc in _dirs(v):
        r1, c1, r2, c2 = r + dr, c + dc, r + 2 * dr, c + 2 * dc
        if 0 <= r2 < 8 and 0 <= c2 < 8 and _owner(b[r1 * 8 + c1]) == 1 - player and b[r2 * 8 + c2] == 0:
            out.append((pos, r2 * 8 + c2, r1 * 8 + c1))
    return out


def _steps(b, pos, v):
    out = []
    r, c = divmod(pos, 8)
    for dr, dc in _dirs(v):
        r1, c1 = r + dr, c + dc
        if 0 <= r1 < 8 and 0 <= c1 < 8 and b[r1 * 8 + c1] == 0:
            out.append((pos, r1 * 8 + c1, None))
    return out


def ck_legal(state):
    """All legal (from, to, captured) moves for the player whose turn it is."""
    b, p = state["board"], state["turn"]
    cells = [state["must"]] if state.get("must") is not None else [i for i, v in enumerate(b) if _owner(v) == p]
    jumps = [m for i in cells for m in _jumps(b, i, b[i], p)]
    if jumps or state.get("must") is not None:
        return jumps
    return [m for i in cells for m in _steps(b, i, b[i])]


def ck_move(state, who, move):
    i = _who(state, who)
    if state["status"] != "playing" or state["turn"] != i:
        raise GameError("It is not your turn.")
    try:
        frm, to = int(move["from"]), int(move["to"])
    except (KeyError, TypeError, ValueError):
        raise GameError("Invalid move.")
    chosen = next((m for m in ck_legal(state) if m[0] == frm and m[1] == to), None)
    if not chosen:
        raise GameError("That move is not allowed (a jump is mandatory).")
    b = state["board"]
    v = b[frm]
    b[frm], b[to] = 0, v
    became_king = False
    if chosen[2] is not None:
        b[chosen[2]] = 0
    if v == 1 and to // 8 == 0:
        b[to], became_king = 3, True
    if v == 2 and to // 8 == 7:
        b[to], became_king = 4, True
    if chosen[2] is not None and not became_king and _jumps(b, to, b[to], i):
        state["must"] = to                                   # the same piece has to keep jumping
        return
    state["must"] = None
    state["turn"] = 1 - i
    if not ck_legal(state):                                  # the next player can not move: they lose
        _finish(state, i)


def ck_bot(state, level):
    moves = ck_legal(state)
    if not moves:
        return None
    rng = _rng()
    jumps = [m for m in moves if m[2] is not None]
    if level == "easy":
        m = rng.choice(moves)
    elif level == "medium":
        m = rng.choice(jumps or moves)
    else:                                                    # hard/impossible: prefer jumps, kings, safe squares, centre
        def score(m):
            to_r, to_c = divmod(m[1], 8)
            s = (10 if m[2] is not None else 0) + (3 if m[1] // 8 in (0, 7) else 0) + (1 if 2 <= to_c <= 5 else 0)
            s += 0.5 if to_c in (0, 7) else 0                # edge pieces can not be captured
            return s + rng.random() * (0.3 if level == "impossible" else 1.5)
        m = max(moves, key=score)
    return {"from": m[0], "to": m[1]}


def ck_view(state, me):
    out = dict(state)
    out["legal"] = [[m[0], m[1]] for m in ck_legal(state)] if state["status"] == "playing" else []
    return out


# ============================================================================ Chess (rules from the python-chess library)
def ch_new(players, level="easy"):
    import chess
    return {"players": players, "fen": chess.STARTING_FEN, "turn": 0, "status": "playing", "winner": None, "last": None, "check": False}


def _board(state):
    import chess
    return chess.Board(state["fen"])


def _ch_after(state, board, i):
    import chess
    state["fen"] = board.fen()
    state["check"] = board.is_check()
    if board.is_checkmate():
        _finish(state, i)
    elif board.is_game_over(claim_draw=False) or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():
        _finish(state, "draw")
    else:
        state["turn"] = 1 - i


def ch_move(state, who, move):
    import chess
    i = _who(state, who)
    if state["status"] != "playing" or state["turn"] != i:
        raise GameError("It is not your turn.")
    board = _board(state)
    try:
        mv = chess.Move.from_uci(str(move.get("uci", "")))
    except (ValueError, AttributeError):
        raise GameError("Invalid move.")
    if mv not in board.legal_moves:                          # a pawn reaching the last row is promoted to a queen
        q = chess.Move.from_uci(str(move.get("uci", ""))[:4] + "q") if len(str(move.get("uci", ""))) == 4 else None
        if q and q in board.legal_moves:
            mv = q
        else:
            raise GameError("That move is not allowed.")
    board.push(mv)
    state["last"] = mv.uci()
    _ch_after(state, board, i)


def _material(board, color):
    import chess
    vals = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    return sum(vals.get(p.piece_type, 0) * (1 if p.color == color else -1) for p in board.piece_map().values())


_deadline = [0.0]


def _search(board, depth, color, alpha=-999, beta=999):
    import chess
    if _deadline[0] and time.time() > _deadline[0]:
        raise TimeoutError                                   # thinking too long on a slow server: the caller uses a shallower result
    if board.is_checkmate():
        return -500 - depth
    if board.is_game_over():
        return 0
    if depth == 0:
        return _material(board, board.turn)
    best = -999
    for mv in board.legal_moves:
        board.push(mv)
        score = -_search(board, depth - 1, not color, -beta, -alpha)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def ch_bot(state, level):
    board = _board(state)
    moves = list(board.legal_moves)
    if not moves:
        return None
    rng = _rng()
    if level == "easy":
        mv = rng.choice(moves)
    elif level == "medium":                                  # takes pieces when it can, otherwise random
        caps = [m for m in moves if board.is_capture(m)]
        mv = rng.choice(caps or moves)
    else:
        def ranked(depth):
            scored = []
            for m in moves:
                board.push(m)
                try:
                    scored.append((-_search(board, depth - 1, board.turn), rng.random(), m))
                finally:
                    board.pop()
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return scored
        _deadline[0] = 0.0
        scored = ranked(2)
        if level == "impossible":
            _deadline[0] = time.time() + 2.5                 # a deeper look, but never longer than 2.5 seconds
            try:
                scored = ranked(3)
            except TimeoutError:
                pass
            finally:
                _deadline[0] = 0.0
        mv = scored[0][2] if level == "impossible" or rng.random() < 0.8 else rng.choice(scored[:3])[2]
    return {"uci": mv.uci()}


def ch_view(state, me):
    out = dict(state)
    if state["status"] == "playing":
        board = _board(state)
        out["legal"] = [m.uci() for m in board.legal_moves]
    else:
        out["legal"] = []
    return out


# ============================================================================ Memory (2 players, take turns)
SYMBOLS = ["🍎", "🚀", "🎸", "🐙", "🌵", "🍕", "⚽", "🎲", "🦊", "🌈", "🎧", "🍉"]


def mem_new(players, level="easy"):
    pairs = {"easy": 6, "medium": 8, "hard": 10, "impossible": 12}.get(level, 8)
    deck = SYMBOLS[:pairs] * 2
    _rng().shuffle(deck)
    return {"players": players, "deck": deck, "matched": [False] * len(deck), "open": [], "last": [], "scores": [0, 0],
            "turn": 0, "status": "playing", "winner": None, "level": level}


def mem_move(state, who, move):
    i = _who(state, who)
    if state["status"] != "playing" or state["turn"] != i:
        raise GameError("It is not your turn.")
    k = move.get("card") if isinstance(move, dict) else None
    n = len(state["deck"])
    if isinstance(k, bool) or not isinstance(k, int) or not 0 <= k < n or state["matched"][k] or k in state["open"]:
        raise GameError("That card can not be turned.")
    state["last"] = []
    state["open"].append(k)
    if len(state["open"]) < 2:
        return
    a, b = state["open"]
    state["open"] = []
    state["last"] = [a, b]                                    # both cards stay visible until the next move
    if state["deck"][a] == state["deck"][b]:
        state["matched"][a] = state["matched"][b] = True
        state["scores"][i] += 1
        if all(state["matched"]):
            s0, s1 = state["scores"]
            _finish(state, "draw" if s0 == s1 else (0 if s0 > s1 else 1))
    elif len(state["players"]) == 2:
        state["turn"] = 1 - i                                 # alone: you simply go on


def mem_bot(state, level):
    """The computer remembers cards it saw: easy never, medium sometimes, hard/impossible always."""
    rng = _rng()
    free = [k for k in range(len(state["deck"])) if not state["matched"][k] and k not in state["open"]]
    if not free:
        return None
    mem_chance = {"easy": 0.0, "medium": 0.4, "hard": 0.8, "impossible": 1.0}.get(level, 0.4)
    seen = state.setdefault("seen", {})                      # card index -> symbol, only what was turned face up
    if state["open"]:
        first = state["open"][0]
        sym = state["deck"][first]
        if rng.random() < mem_chance:
            for k, s in seen.items():
                if s == sym and int(k) != first and not state["matched"][int(k)]:
                    return {"card": int(k)}
        return {"card": rng.choice([k for k in free if k != first])}
    if rng.random() < mem_chance:
        by = {}
        for k, s in seen.items():
            if not state["matched"][int(k)]:
                by.setdefault(s, []).append(int(k))
        for s, ks in by.items():
            if len(ks) >= 2:
                return {"card": ks[0]}
    unseen = [k for k in free if str(k) not in seen] or free
    return {"card": rng.choice(unseen)}


def mem_view(state, me):
    out = {k: v for k, v in state.items() if k not in ("deck", "seen")}
    shown = set(state["open"]) | set(state["last"])
    out["faces"] = {str(k): state["deck"][k] for k in range(len(state["deck"])) if state["matched"][k] or k in shown}
    out["size"] = len(state["deck"])
    return out


# ============================================================================ Wordle (race: first to find the word wins)
def wd_new(players, level="easy"):
    return {"players": players, "secret": _rng().choice(WORDS), "guesses": [[] for _ in players], "turn": None,
            "status": "playing", "winner": None}


def wd_score(secret, guess):
    res = ["x"] * 5
    left = list(secret)
    for k in range(5):
        if guess[k] == secret[k]:
            res[k] = "g"
            left.remove(guess[k])
    for k in range(5):
        if res[k] == "x" and guess[k] in left:
            res[k] = "y"
            left.remove(guess[k])
    return "".join(res)


def wd_move(state, who, move):
    i = _who(state, who)
    if state["status"] != "playing":
        raise GameError("The game is over.")
    guess = str(move.get("word", "")).lower().strip() if isinstance(move, dict) else ""
    if len(guess) != 5 or not guess.isalpha() or not guess.isascii():
        raise GameError("Type a word with 5 letters (a-z).")
    if len(state["guesses"][i]) >= 6:
        raise GameError("You used all 6 tries.")
    state["guesses"][i].append({"word": guess, "result": wd_score(state["secret"], guess)})
    if guess == state["secret"]:
        _finish(state, i)
    elif all(len(g) >= 6 for g in state["guesses"]):
        _finish(state, "draw")


def wd_bot(state, level):
    return None                                              # Wordle against the computer is a solo game (see below)


def wd_view(state, me):
    out = {k: v for k, v in state.items() if k != "secret"}
    if state["status"] == "done":
        out["secret"] = state["secret"]
    return out


# ============================================================================ Typing duel (who types the sentence faster)
def ty_new(players, level="easy"):
    return {"players": players, "text": _rng().choice(SENTENCES), "started": time.time(), "results": [None, None], "turn": None,
            "status": "playing", "winner": None}


def ty_move(state, who, move):
    i = _who(state, who)
    if state["status"] != "playing" or state["results"][i] is not None:
        raise GameError("You are already done.")
    typed = str(move.get("text", "")) if isinstance(move, dict) else ""
    secs = max(time.time() - state["started"], 0.5)
    target = state["text"]
    correct = sum(1 for a, b in zip(typed, target) if a == b)
    accuracy = correct / max(len(target), 1) if len(typed) == len(target) else correct / max(len(target), 1) * 0.5
    wpm = (len(target) / 5) / (secs / 60)
    ok = typed == target
    state["results"][i] = {"wpm": round(min(wpm, 400), 1), "accuracy": round(accuracy * 100), "ok": ok, "secs": round(secs, 1)}
    if all(r is not None for r in state["results"][: len(state["players"])]):
        res = state["results"][: len(state["players"])]
        score = [r["wpm"] if r["ok"] else 0 for r in res]
        if len(res) == 1 or score[0] == score[-1]:
            _finish(state, "draw" if len(res) > 1 else (0 if res[0]["ok"] else "draw"))
        else:
            _finish(state, score.index(max(score)))


def ty_bot(state, level):
    return None


def ty_view(state, me):
    return dict(state)


def _bot_typing(state, level):
    """The computer has no hands: its result for the typing duel is a speed that depends on the level."""
    wpm = {"easy": 25, "medium": 45, "hard": 70, "impossible": 140}.get(level, 40)
    return {"wpm": wpm, "accuracy": 100, "ok": True, "secs": round(len(state["text"]) / 5 / wpm * 60, 1)}


def _plain_view(state, me):
    return dict(state)


GAMES = {
    "tictactoe": {"new": ttt_new, "move": ttt_move, "bot": ttt_bot, "view": _plain_view, "players": 2},
    "checkers": {"new": ck_new, "move": ck_move, "bot": ck_bot, "view": ck_view, "players": 2},
    "chess": {"new": ch_new, "move": ch_move, "bot": ch_bot, "view": ch_view, "players": 2},
    "memory": {"new": mem_new, "move": mem_move, "bot": mem_bot, "view": mem_view, "players": 2},
    "wordle": {"new": wd_new, "move": wd_move, "bot": wd_bot, "view": wd_view, "players": 2},
    "typing": {"new": ty_new, "move": ty_move, "bot": ty_bot, "view": ty_view, "players": 2},
}
LEVELS = ("easy", "medium", "hard", "impossible")
