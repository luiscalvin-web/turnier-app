from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
from pathlib import Path
import math
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "turnier-app-dev-secret")

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "tournament.db"

app.secret_key = os.environ.get("SECRET_KEY", "turnier-app-dev-secret")

FAMILY_PASSWORD = os.environ.get("FAMILY_PASSWORD", "familie123")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

DISCIPLINE_CONFIG = {
    "Billard": {"key": "billiard", "default_target": 8, "default_sets": 1},
    "Dart": {"key": "dart", "default_target": 501, "default_sets": 1},
    "Kicker": {"key": "kicker", "default_target": 10, "default_sets": 1},
    "Tischtennis": {"key": "table_tennis", "default_target": 11, "default_sets": 1},
    "Cornhole": {"key": "cornhole", "default_target": 21, "default_sets": 1},
    "Bogenschießen": {"key": "archery", "default_target": 30, "default_sets": 1},
}

PHASES = {"groups", "waiting_for_knockout", "knockout", "finished"}


def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_admin():
    return session.get("is_admin", False)


def ensure_column(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cursor.fetchall()}
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_size INTEGER NOT NULL,
            billiard INTEGER DEFAULT 0,
            dart INTEGER DEFAULT 0,
            kicker INTEGER DEFAULT 0,
            table_tennis INTEGER DEFAULT 0,
            cornhole INTEGER DEFAULT 0,
            archery INTEGER DEFAULT 0,
            billiard_target INTEGER DEFAULT 8,
            billiard_sets INTEGER DEFAULT 1,
            dart_target INTEGER DEFAULT 501,
            dart_sets INTEGER DEFAULT 1,
            kicker_target INTEGER DEFAULT 10,
            kicker_sets INTEGER DEFAULT 1,
            table_tennis_target INTEGER DEFAULT 11,
            table_tennis_sets INTEGER DEFAULT 1,
            cornhole_target INTEGER DEFAULT 21,
            cornhole_sets INTEGER DEFAULT 1,
            archery_target INTEGER DEFAULT 30,
            archery_sets INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            phase TEXT NOT NULL DEFAULT 'groups'
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO tournament_meta (id, phase) VALUES (1, 'groups')")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            discipline TEXT NOT NULL,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            score1 INTEGER DEFAULT 0,
            score2 INTEGER DEFAULT 0,
            sets_won_1 INTEGER DEFAULT 0,
            sets_won_2 INTEGER DEFAULT 0,
            winner_id INTEGER,
            status TEXT DEFAULT 'offen',
            FOREIGN KEY (player1_id) REFERENCES players(id),
            FOREIGN KEY (player2_id) REFERENCES players(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            set_number INTEGER NOT NULL,
            score1 INTEGER NOT NULL,
            score2 INTEGER NOT NULL,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            wins INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            sets_for INTEGER DEFAULT 0,
            sets_against INTEGER DEFAULT 0,
            sets_diff INTEGER DEFAULT 0,
            score_for INTEGER DEFAULT 0,
            score_against INTEGER DEFAULT 0,
            score_diff INTEGER DEFAULT 0,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knockout_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discipline TEXT NOT NULL,
            round_name TEXT NOT NULL,
            round_order INTEGER NOT NULL DEFAULT 0,
            match_order INTEGER NOT NULL DEFAULT 0,
            player1_id INTEGER,
            player2_id INTEGER,
            player1_label TEXT,
            player2_label TEXT,
            score1 INTEGER DEFAULT 0,
            score2 INTEGER DEFAULT 0,
            sets_won_1 INTEGER DEFAULT 0,
            sets_won_2 INTEGER DEFAULT 0,
            winner_id INTEGER,
            status TEXT DEFAULT 'offen',
            source_match1_id INTEGER,
            source_match2_id INTEGER,
            FOREIGN KEY (player1_id) REFERENCES players(id),
            FOREIGN KEY (player2_id) REFERENCES players(id),
            FOREIGN KEY (source_match1_id) REFERENCES knockout_matches(id),
            FOREIGN KEY (source_match2_id) REFERENCES knockout_matches(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knockout_match_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            set_number INTEGER NOT NULL,
            score1 INTEGER NOT NULL,
            score2 INTEGER NOT NULL,
            FOREIGN KEY (match_id) REFERENCES knockout_matches(id)
        )
    """)

    for col, definition in [
        ("sets_for", "INTEGER DEFAULT 0"),
        ("sets_against", "INTEGER DEFAULT 0"),
        ("sets_diff", "INTEGER DEFAULT 0"),
        ("score_for", "INTEGER DEFAULT 0"),
        ("score_against", "INTEGER DEFAULT 0"),
        ("score_diff", "INTEGER DEFAULT 0"),
    ]:
        ensure_column(cursor, "standings", col, definition)

    for col, definition in [
        ("archery", "INTEGER DEFAULT 0"),
        ("archery_target", "INTEGER DEFAULT 30"),
        ("archery_sets", "INTEGER DEFAULT 1"),
    ]:
        ensure_column(cursor, "tournament_settings", col, definition)

    for col, definition in [
        ("round_order", "INTEGER DEFAULT 0"),
        ("match_order", "INTEGER DEFAULT 0"),
        ("player1_label", "TEXT"),
        ("player2_label", "TEXT"),
        ("sets_won_1", "INTEGER DEFAULT 0"),
        ("sets_won_2", "INTEGER DEFAULT 0"),
        ("source_match1_id", "INTEGER"),
        ("source_match2_id", "INTEGER"),
    ]:
        ensure_column(cursor, "knockout_matches", col, definition)

    conn.commit()
    conn.close()


init_db()


def current_phase():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phase FROM tournament_meta WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    phase = row["phase"] if row else "groups"
    return phase if phase in PHASES else "groups"


def set_phase(new_phase):
    if new_phase not in PHASES:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tournament_meta SET phase = ? WHERE id = 1", (new_phase,))
    conn.commit()
    conn.close()


def get_latest_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tournament_settings ORDER BY id DESC LIMIT 1")
    settings = cursor.fetchone()
    conn.close()
    return settings


def get_player_name(conn, player_id):
    if player_id is None:
        return None
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    return row["name"] if row else None


def selected_disciplines_from_settings(row):
    if not row:
        return []
    disciplines = []
    if row["billiard"]:
        disciplines.append("Billard")
    if row["dart"]:
        disciplines.append("Dart")
    if row["kicker"]:
        disciplines.append("Kicker")
    if row["table_tennis"]:
        disciplines.append("Tischtennis")
    if row["cornhole"]:
        disciplines.append("Cornhole")
    if row["archery"]:
        disciplines.append("Bogenschießen")
    return disciplines


def settings_to_discipline_cards(row):
    cards = []
    if not row:
        return cards
    mapping = [
        ("Billard", "billiard", "billiard_target", "billiard_sets"),
        ("Dart", "dart", "dart_target", "dart_sets"),
        ("Kicker", "kicker", "kicker_target", "kicker_sets"),
        ("Tischtennis", "table_tennis", "table_tennis_target", "table_tennis_sets"),
        ("Cornhole", "cornhole", "cornhole_target", "cornhole_sets"),
        ("Bogenschießen", "archery", "archery_target", "archery_sets"),
    ]
    for label, active_key, target_key, sets_key in mapping:
        if row[active_key]:
            cards.append({"label": label, "target": row[target_key], "sets": row[sets_key]})
    return cards


def get_discipline_settings(discipline):
    settings = get_latest_settings()
    if not settings:
        cfg = DISCIPLINE_CONFIG[discipline]
        return {"target": cfg["default_target"], "sets": cfg["default_sets"]}
    mapping = {
        "Billard": ("billiard_target", "billiard_sets"),
        "Dart": ("dart_target", "dart_sets"),
        "Kicker": ("kicker_target", "kicker_sets"),
        "Tischtennis": ("table_tennis_target", "table_tennis_sets"),
        "Cornhole": ("cornhole_target", "cornhole_sets"),
        "Bogenschießen": ("archery_target", "archery_sets"),
    }
    target_key, sets_key = mapping[discipline]
    return {"target": settings[target_key], "sets": settings[sets_key]}


def validate_set_score(discipline, target, score1, score2):
    if score1 < 0 or score2 < 0:
        return False, "Negative Werte sind nicht erlaubt."
    if discipline == "Dart":
        if score1 == score2:
            return False, "Bei Dart kann ein Leg nicht unentschieden enden."
        if score1 == 0 and score2 > 0:
            return True, ""
        if score2 == 0 and score1 > 0:
            return True, ""
        return False, "Bei Dart muss genau ein Spieler 0 Restpunkte haben."
    if discipline == "Bogenschießen":
        if score1 > 30 or score2 > 30:
            return False, "Beim Bogenschießen sind pro Satz maximal 30 Punkte möglich."
        return True, ""
    if discipline == "Tischtennis":
        if score1 == score2:
            return False, "Ein Satz darf nicht unentschieden enden."
        winner = max(score1, score2)
        loser = min(score1, score2)
        if winner < target:
            return False, f"Tischtennis-Satz endet erst ab {target} Punkten."
        if winner == target and loser > target - 2:
            return False, "Bei Tischtennis braucht der Gewinner mindestens 2 Punkte Vorsprung."
        if winner > target and winner - loser != 2:
            return False, "Verlängerung im Tischtennis braucht genau 2 Punkte Vorsprung."
        return True, ""
    if discipline in ("Billard", "Kicker", "Cornhole"):
        if score1 == score2:
            return False, "Ein Satz darf nicht unentschieden enden."
        winner = max(score1, score2)
        loser = min(score1, score2)
        if winner != target:
            return False, f"Der Gewinner muss genau {target} erreichen."
        if loser >= target:
            return False, "Der Verlierer darf das Ziel nicht ebenfalls erreichen."
        return True, ""
    return True, ""


def calculate_match_result(discipline, set_scores, sets_to_play, allow_draw=False):
    wins1 = 0
    wins2 = 0
    for s1, s2 in set_scores:
        if discipline == "Dart":
            if s1 == 0 and s2 > 0:
                wins1 += 1
            elif s2 == 0 and s1 > 0:
                wins2 += 1
        else:
            if s1 > s2:
                wins1 += 1
            elif s2 > s1:
                wins2 += 1
    needed = sets_to_play // 2 + 1
    winner = None
    status = "offen"
    if wins1 >= needed:
        winner = 1
        status = "abgeschlossen"
    elif wins2 >= needed:
        winner = 2
        status = "abgeschlossen"
    elif allow_draw and len(set_scores) == sets_to_play:
        status = "abgeschlossen"
    return {"sets_won_1": wins1, "sets_won_2": wins2, "winner_side": winner, "status": status}


def save_match_sets(table_name, match_id, set_scores):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table_name} WHERE match_id = ?", (match_id,))
    for idx, (score1, score2) in enumerate(set_scores, start=1):
        cursor.execute(
            f"INSERT INTO {table_name} (match_id, set_number, score1, score2) VALUES (?, ?, ?, ?)",
            (match_id, idx, score1, score2),
        )
    conn.commit()
    conn.close()


def load_match_sets(table_name, match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT set_number, score1, score2 FROM {table_name} WHERE match_id = ? ORDER BY set_number",
        (match_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def create_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_size FROM tournament_settings ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    if not result:
        conn.close()
        return
    desired_group_size = result["group_size"]
    cursor.execute("SELECT id, name, age FROM players ORDER BY age ASC, name ASC")
    players = cursor.fetchall()
    cursor.execute("DELETE FROM groups")
    if not players:
        conn.commit()
        conn.close()
        return
    num_players = len(players)
    num_groups = max(1, math.ceil(num_players / desired_group_size))
    base_size = num_players // num_groups
    remainder = num_players % num_groups
    group_sizes = [base_size + (1 if i < remainder else 0) for i in range(num_groups)]
    group_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    start = 0
    for idx, size in enumerate(group_sizes):
        group_name = f"Gruppe {group_letters[idx]}"
        chunk = players[start:start + size]
        for player in chunk:
            cursor.execute("INSERT INTO groups (group_name, player_id) VALUES (?, ?)", (group_name, player["id"]))
        start += size
    conn.commit()
    conn.close()


def create_matches():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matches")
    cursor.execute("DELETE FROM match_sets")
    settings = get_latest_settings()
    disciplines = selected_disciplines_from_settings(settings)
    if not disciplines:
        conn.commit()
        conn.close()
        return
    cursor.execute("SELECT DISTINCT group_name FROM groups ORDER BY group_name")
    groups = cursor.fetchall()
    for group in groups:
        group_name = group["group_name"]
        cursor.execute("SELECT player_id FROM groups WHERE group_name = ? ORDER BY player_id", (group_name,))
        player_ids = [row["player_id"] for row in cursor.fetchall()]
        for discipline in disciplines:
            for i in range(len(player_ids)):
                for j in range(i + 1, len(player_ids)):
                    cursor.execute(
                        "INSERT INTO matches (group_name, discipline, player1_id, player2_id) VALUES (?, ?, ?, ?)",
                        (group_name, discipline, player_ids[i], player_ids[j]),
                    )
    conn.commit()
    conn.close()


def update_standings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM standings")
    cursor.execute("SELECT DISTINCT group_name FROM groups ORDER BY group_name")
    groups = cursor.fetchall()
    for group in groups:
        group_name = group["group_name"]
        cursor.execute("SELECT player_id FROM groups WHERE group_name = ?", (group_name,))
        players = cursor.fetchall()
        for player in players:
            player_id = player["player_id"]
            wins = draws = losses = points = 0
            sets_for = sets_against = 0
            score_for = score_against = 0
            cursor.execute(
                """
                SELECT id, player1_id, player2_id, winner_id, status
                FROM matches
                WHERE group_name = ? AND status = 'abgeschlossen' AND (player1_id = ? OR player2_id = ?)
                """,
                (group_name, player_id, player_id),
            )
            played_matches = cursor.fetchall()
            for match in played_matches:
                match_id = match["id"]
                is_p1 = player_id == match["player1_id"]
                winner_id = match["winner_id"]
                cursor.execute("SELECT score1, score2 FROM match_sets WHERE match_id = ? ORDER BY set_number", (match_id,))
                set_rows = cursor.fetchall()
                local_sets_for = local_sets_against = 0
                local_score_for = local_score_against = 0
                for set_row in set_rows:
                    s1, s2 = set_row["score1"], set_row["score2"]
                    if is_p1:
                        local_score_for += s1
                        local_score_against += s2
                        if s1 > s2:
                            local_sets_for += 1
                        elif s2 > s1:
                            local_sets_against += 1
                    else:
                        local_score_for += s2
                        local_score_against += s1
                        if s2 > s1:
                            local_sets_for += 1
                        elif s1 > s2:
                            local_sets_against += 1
                sets_for += local_sets_for
                sets_against += local_sets_against
                score_for += local_score_for
                score_against += local_score_against
                if winner_id is None:
                    draws += 1
                    points += 1
                elif winner_id == player_id:
                    wins += 1
                    points += 3
                else:
                    losses += 1
            cursor.execute(
                """
                INSERT INTO standings (
                    group_name, player_id, wins, draws, losses, points,
                    sets_for, sets_against, sets_diff,
                    score_for, score_against, score_diff
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_name, player_id, wins, draws, losses, points,
                    sets_for, sets_against, sets_for - sets_against,
                    score_for, score_against, score_for - score_against,
                ),
            )
    conn.commit()
    conn.close()


def power_of_two_bracket_size(n):
    size = 1
    while size < n:
        size *= 2
    return size


def round_name_from_size(size):
    mapping = {2: "Finale", 4: "Halbfinale", 8: "Viertelfinale", 16: "Achtelfinale", 32: "Sechzehntelfinale"}
    return mapping.get(size, f"Runde der letzten {size}")


def propagate_knockout_winner(conn, match_id):
    cursor = conn.cursor()
    cursor.execute("SELECT id, winner_id FROM knockout_matches WHERE id = ?", (match_id,))
    finished_match = cursor.fetchone()
    if not finished_match or not finished_match["winner_id"]:
        return
    winner_id = finished_match["winner_id"]
    winner_name = get_player_name(conn, winner_id)
    cursor.execute(
        """
        SELECT id, source_match1_id, source_match2_id, player1_id, player2_id
        FROM knockout_matches
        WHERE source_match1_id = ? OR source_match2_id = ?
        """,
        (match_id, match_id),
    )
    next_matches = cursor.fetchall()
    for next_match in next_matches:
        if next_match["source_match1_id"] == match_id and next_match["player1_id"] is None:
            cursor.execute(
                """
                UPDATE knockout_matches
                SET player1_id = ?, player1_label = ?, status = CASE WHEN player2_id IS NULL THEN 'wartet' ELSE 'offen' END
                WHERE id = ?
                """,
                (winner_id, winner_name, next_match["id"]),
            )
        elif next_match["source_match2_id"] == match_id and next_match["player2_id"] is None:
            cursor.execute(
                """
                UPDATE knockout_matches
                SET player2_id = ?, player2_label = ?, status = CASE WHEN player1_id IS NULL THEN 'wartet' ELSE 'offen' END
                WHERE id = ?
                """,
                (winner_id, winner_name, next_match["id"]),
            )
        cursor.execute("SELECT player1_id, player2_id, winner_id FROM knockout_matches WHERE id = ?", (next_match["id"],))
        refreshed = cursor.fetchone()
        if refreshed["winner_id"] is None:
            if refreshed["player1_id"] and not refreshed["player2_id"]:
                cursor.execute("UPDATE knockout_matches SET winner_id = ?, status = 'abgeschlossen' WHERE id = ?", (refreshed["player1_id"], next_match["id"]))
                conn.commit()
                propagate_knockout_winner(conn, next_match["id"])
            elif refreshed["player2_id"] and not refreshed["player1_id"]:
                cursor.execute("UPDATE knockout_matches SET winner_id = ?, status = 'abgeschlossen' WHERE id = ?", (refreshed["player2_id"], next_match["id"]))
                conn.commit()
                propagate_knockout_winner(conn, next_match["id"])
    conn.commit()


def create_knockout_matches():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM knockout_matches")
    cursor.execute("DELETE FROM knockout_match_sets")
    settings = get_latest_settings()
    disciplines = selected_disciplines_from_settings(settings)
    for discipline in disciplines:
        cursor.execute("SELECT DISTINCT group_name FROM groups ORDER BY group_name")
        group_names = cursor.fetchall()
        qualified_players = []
        for group in group_names:
            group_name = group["group_name"]
            cursor.execute(
                """
                SELECT p.id, COUNT(*) AS wins_in_discipline,
                       COALESCE(SUM(CASE
                           WHEN p.id = m.player1_id THEN m.score1 - m.score2
                           WHEN p.id = m.player2_id THEN m.score2 - m.score1
                           ELSE 0 END), 0) AS diff_value
                FROM matches m
                JOIN players p ON (
                    (p.id = m.player1_id AND m.winner_id = m.player1_id)
                    OR (p.id = m.player2_id AND m.winner_id = m.player2_id)
                )
                WHERE m.group_name = ? AND m.discipline = ? AND m.status = 'abgeschlossen'
                GROUP BY p.id
                ORDER BY wins_in_discipline DESC, diff_value DESC, p.id ASC
                LIMIT 1
                """,
                (group_name, discipline),
            )
            best_player = cursor.fetchone()
            if best_player:
                qualified_players.append(best_player["id"])
        if len(qualified_players) < 2:
            continue
        bracket_size = power_of_two_bracket_size(len(qualified_players))
        slots = qualified_players + [None] * (bracket_size - len(qualified_players))
        round_order = 1
        current_round_ids = []
        current_size = bracket_size
        current_round_name = round_name_from_size(current_size)
        match_number = 1
        for i in range(0, len(slots), 2):
            p1, p2 = slots[i], slots[i + 1]
            p1_label = get_player_name(conn, p1) if p1 else "Freilos"
            p2_label = get_player_name(conn, p2) if p2 else "Freilos"
            status = "offen"
            winner_id = None
            if p1 and not p2:
                winner_id = p1
                status = "abgeschlossen"
            elif p2 and not p1:
                winner_id = p2
                status = "abgeschlossen"
            cursor.execute(
                """
                INSERT INTO knockout_matches (
                    discipline, round_name, round_order, match_order,
                    player1_id, player2_id, player1_label, player2_label,
                    winner_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (discipline, current_round_name, round_order, match_number, p1, p2, p1_label, p2_label, winner_id, status),
            )
            current_round_ids.append(cursor.lastrowid)
            match_number += 1
        conn.commit()
        while current_size > 2:
            next_round_ids = []
            next_size = current_size // 2
            next_round_name = round_name_from_size(next_size)
            prev_round_name = round_name_from_size(current_size)
            round_order += 1
            pair_counter = 1
            for i in range(0, len(current_round_ids), 2):
                source1, source2 = current_round_ids[i], current_round_ids[i + 1]
                cursor.execute(
                    """
                    INSERT INTO knockout_matches (
                        discipline, round_name, round_order, match_order,
                        player1_label, player2_label,
                        source_match1_id, source_match2_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'wartet')
                    """,
                    (discipline, next_round_name, round_order, pair_counter, f"Gewinner {prev_round_name} {i + 1}", f"Gewinner {prev_round_name} {i + 2}", source1, source2),
                )
                next_round_ids.append(cursor.lastrowid)
                pair_counter += 1
            current_round_ids = next_round_ids
            current_size = next_size
            conn.commit()
        cursor.execute("SELECT id FROM knockout_matches WHERE discipline = ? AND winner_id IS NOT NULL ORDER BY id", (discipline,))
        for row in cursor.fetchall():
            propagate_knockout_winner(conn, row["id"])
    conn.commit()
    conn.close()


def compute_overall_rankings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM players ORDER BY name")
    players = cursor.fetchall()
    rankings = []
    for player in players:
        player_id = player["id"]
        name = player["name"]
        wins = draws = losses = points = 0
        sets_for = sets_against = 0
        score_for = score_against = 0
        cursor.execute("SELECT id, player1_id, player2_id, winner_id FROM matches WHERE status = 'abgeschlossen' AND (player1_id = ? OR player2_id = ?)", (player_id, player_id))
        for match in cursor.fetchall():
            is_p1 = player_id == match["player1_id"]
            winner_id = match["winner_id"]
            cursor.execute("SELECT score1, score2 FROM match_sets WHERE match_id = ? ORDER BY set_number", (match["id"],))
            for s in cursor.fetchall():
                a, b = s["score1"], s["score2"]
                if is_p1:
                    score_for += a
                    score_against += b
                    sets_for += 1 if a > b else 0
                    sets_against += 1 if b > a else 0
                else:
                    score_for += b
                    score_against += a
                    sets_for += 1 if b > a else 0
                    sets_against += 1 if a > b else 0
            if winner_id is None:
                draws += 1
                points += 1
            elif winner_id == player_id:
                wins += 1
                points += 3
            else:
                losses += 1
        cursor.execute("SELECT id, player1_id, player2_id, winner_id FROM knockout_matches WHERE status = 'abgeschlossen' AND (player1_id = ? OR player2_id = ?)", (player_id, player_id))
        for match in cursor.fetchall():
            is_p1 = player_id == match["player1_id"]
            winner_id = match["winner_id"]
            cursor.execute("SELECT score1, score2 FROM knockout_match_sets WHERE match_id = ? ORDER BY set_number", (match["id"],))
            for s in cursor.fetchall():
                a, b = s["score1"], s["score2"]
                if is_p1:
                    score_for += a
                    score_against += b
                    sets_for += 1 if a > b else 0
                    sets_against += 1 if b > a else 0
                else:
                    score_for += b
                    score_against += a
                    sets_for += 1 if b > a else 0
                    sets_against += 1 if a > b else 0
            if winner_id == player_id:
                wins += 1
                points += 3
            elif winner_id is None:
                draws += 1
                points += 1
            else:
                losses += 1
        rankings.append({
            "player_id": player_id,
            "name": name,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "points": points,
            "sets_for": sets_for,
            "sets_against": sets_against,
            "sets_diff": sets_for - sets_against,
            "score_for": score_for,
            "score_against": score_against,
            "score_diff": score_for - score_against,
        })
    rankings.sort(key=lambda x: (-x["points"], -x["sets_diff"], -x["score_diff"], -x["score_for"], x["name"].lower()))
    conn.close()
    return rankings


def compute_discipline_results():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT discipline FROM knockout_matches ORDER BY discipline")
    disciplines = [row["discipline"] for row in cursor.fetchall()]
    results = []
    for discipline in disciplines:
        cursor.execute("SELECT * FROM knockout_matches WHERE discipline = ? ORDER BY round_order DESC, match_order ASC LIMIT 1", (discipline,))
        final_match = cursor.fetchone()
        if not final_match or final_match["status"] != "abgeschlossen" or not final_match["winner_id"]:
            continue
        winner_id = final_match["winner_id"]
        second_id = final_match["player2_id"] if final_match["player1_id"] == winner_id else final_match["player1_id"]
        results.append({
            "discipline": discipline,
            "winner": get_player_name(conn, winner_id),
            "second": get_player_name(conn, second_id) if second_id else "Freilos",
            "final_round": final_match["round_name"],
        })
    conn.close()
    return results


@app.route("/")
def home():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM players")
    player_count = cursor.fetchone()["count"]
    settings = get_latest_settings()
    discipline_cards = settings_to_discipline_cards(settings)
    phase = current_phase()
    conn.close()
    return render_template("index.html", player_count=player_count, discipline_cards=discipline_cards, phase=phase)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        age = request.form["age"].strip()
        if not name or not age:
            flash("Bitte Name und Alter eingeben.")
            return redirect(url_for("register"))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO players (name, age) VALUES (?, ?)", (name, int(age)))
        conn.commit()
        conn.close()
        flash("Spieler wurde erfolgreich angemeldet.")
        return redirect(url_for("groups_overview"))
    return render_template("register.html")


@app.route("/groups")
def groups_overview():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT group_name FROM groups ORDER BY group_name")
    groups = cursor.fetchall()
    cursor.execute("SELECT group_name, COUNT(*) AS player_count FROM groups GROUP BY group_name ORDER BY group_name")
    group_counts = {row["group_name"]: row["player_count"] for row in cursor.fetchall()}
    phase = current_phase()
    conn.close()
    return render_template("groups_overview.html", groups=groups, group_counts=group_counts, phase=phase)


@app.route("/group/<group_name>")
def group_view(group_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.group_name, p.name, p.age
        FROM groups g
        JOIN players p ON g.player_id = p.id
        WHERE g.group_name = ?
        ORDER BY p.age, p.name
    """, (group_name,))
    players = cursor.fetchall()
    cursor.execute("""
        SELECT m.id, m.group_name, m.discipline, p1.name AS player1_name, p2.name AS player2_name,
               m.status, m.score1, m.score2, m.sets_won_1, m.sets_won_2
        FROM matches m
        JOIN players p1 ON m.player1_id = p1.id
        JOIN players p2 ON m.player2_id = p2.id
        WHERE m.group_name = ?
        ORDER BY m.discipline, m.id
    """, (group_name,))
    matches = cursor.fetchall()
    cursor.execute("""
        SELECT s.group_name, p.name, s.wins, s.draws, s.losses, s.points,
               s.sets_for, s.sets_against, s.sets_diff, s.score_for, s.score_against, s.score_diff
        FROM standings s
        JOIN players p ON s.player_id = p.id
        WHERE s.group_name = ?
        ORDER BY s.points DESC, s.sets_diff DESC, s.score_diff DESC, s.score_for DESC, p.name ASC
    """, (group_name,))
    standings = cursor.fetchall()
    phase = current_phase()
    conn.close()
    return render_template("group_view.html", group_name=group_name, players=players, matches=matches, standings=standings, phase=phase)


@app.route("/knockout")
def knockout_view():
    conn = get_connection()
    cursor = conn.cursor()
    phase = current_phase()
    cursor.execute("""
        SELECT discipline, round_name, round_order, match_order,
               COALESCE(player1_label, 'Noch offen') AS player1_label,
               COALESCE(player2_label, 'Noch offen') AS player2_label,
               score1, score2, sets_won_1, sets_won_2, status, winner_id, id
        FROM knockout_matches
        ORDER BY discipline, round_order DESC, match_order
    """)
    knockout_matches = cursor.fetchall()
    conn.close()
    return render_template("knockout.html", phase=phase, knockout_matches=knockout_matches)


@app.route("/results")
def results_view():
    phase = current_phase()
    discipline_results = compute_discipline_results()
    overall_rankings = compute_overall_rankings()
    return render_template("results.html", phase=phase, discipline_results=discipline_results, overall_rankings=overall_rankings)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form["password"]
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("Falsches Passwort.")
        return redirect(url_for("admin"))
    if not is_admin():
        return render_template("admin_login.html")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players ORDER BY age ASC, name ASC")
    players = cursor.fetchall()
    cursor.execute("""
        SELECT g.group_name, p.name, p.age
        FROM groups g
        JOIN players p ON g.player_id = p.id
        ORDER BY g.group_name, p.age, p.name
    """)
    groups = cursor.fetchall()
    cursor.execute("""
        SELECT m.group_name, m.discipline, p1.name AS player1_name, p2.name AS player2_name,
               m.status, m.id, m.score1, m.score2, m.sets_won_1, m.sets_won_2
        FROM matches m
        JOIN players p1 ON m.player1_id = p1.id
        JOIN players p2 ON m.player2_id = p2.id
        ORDER BY m.group_name, m.discipline, m.id
    """)
    matches = cursor.fetchall()
    cursor.execute("""
        SELECT s.group_name, p.name, s.wins, s.draws, s.losses, s.points,
               s.sets_for, s.sets_against, s.sets_diff, s.score_for, s.score_against, s.score_diff
        FROM standings s
        JOIN players p ON s.player_id = p.id
        ORDER BY s.group_name, s.points DESC, s.sets_diff DESC, s.score_diff DESC, s.score_for DESC, p.name ASC
    """)
    standings = cursor.fetchall()
    cursor.execute("""
        SELECT k.discipline, k.round_name, k.round_order, k.match_order,
               COALESCE(k.player1_label, 'Noch offen') AS player1_label,
               COALESCE(k.player2_label, 'Noch offen') AS player2_label,
               k.status, k.id, k.score1, k.score2, k.sets_won_1, k.sets_won_2
        FROM knockout_matches k
        ORDER BY k.discipline, k.round_order DESC, k.match_order
    """)
    knockout_matches = cursor.fetchall()
    settings = get_latest_settings()
    phase = current_phase()
    cursor.execute("SELECT COUNT(*) AS cnt FROM knockout_matches WHERE status != 'abgeschlossen'")
    open_ko = cursor.fetchone()["cnt"]
    conn.close()
    return render_template(
        "admin_dashboard.html",
        players=players,
        groups=groups,
        matches=matches,
        standings=standings,
        knockout_matches=knockout_matches,
        settings=settings,
        discipline_cards=settings_to_discipline_cards(settings),
        phase=phase,
        can_finish=(phase == "knockout" and open_ko == 0 and len(knockout_matches) > 0),
    )


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin wurde abgemeldet.")
    return redirect(url_for("admin"))


@app.route("/delete_player/<int:player_id>")
def delete_player(player_id):
    if not is_admin():
        return redirect(url_for("admin"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE player_id = ?", (player_id,))
    cursor.execute("DELETE FROM standings WHERE player_id = ?", (player_id,))
    cursor.execute("DELETE FROM players WHERE id = ?", (player_id,))
    conn.commit()
    conn.close()
    flash("Spieler wurde gelöscht.")
    return redirect(url_for("admin"))


@app.route("/edit_player/<int:player_id>", methods=["GET", "POST"])
def edit_player(player_id):
    if not is_admin():
        return redirect(url_for("admin"))
    conn = get_connection()
    cursor = conn.cursor()
    if request.method == "POST":
        name = request.form["name"].strip()
        age = request.form["age"].strip()
        cursor.execute("UPDATE players SET name = ?, age = ? WHERE id = ?", (name, int(age), player_id))
        conn.commit()
        conn.close()
        flash("Spieler wurde aktualisiert.")
        return redirect(url_for("admin"))
    cursor.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    conn.close()
    return render_template("edit_player.html", player=player)


@app.route("/create_tournament", methods=["GET", "POST"])
def create_tournament():
    if not is_admin():
        return redirect(url_for("admin"))
    if request.method == "POST":
        group_size = int(request.form["group_size"])
        billiard = 1 if "billiard" in request.form else 0
        dart = 1 if "dart" in request.form else 0
        kicker = 1 if "kicker" in request.form else 0
        table_tennis = 1 if "table_tennis" in request.form else 0
        cornhole = 1 if "cornhole" in request.form else 0
        archery = 1 if "archery" in request.form else 0
        billiard_target = int(request.form.get("billiard_target", 8))
        billiard_sets = int(request.form.get("billiard_sets", 1))
        dart_target = int(request.form.get("dart_target", 501))
        dart_sets = int(request.form.get("dart_sets", 1))
        kicker_target = int(request.form.get("kicker_target", 10))
        kicker_sets = int(request.form.get("kicker_sets", 1))
        table_tennis_target = int(request.form.get("table_tennis_target", 11))
        table_tennis_sets = int(request.form.get("table_tennis_sets", 1))
        cornhole_target = int(request.form.get("cornhole_target", 21))
        cornhole_sets = int(request.form.get("cornhole_sets", 1))
        archery_target = 30
        archery_sets = int(request.form.get("archery_sets", 1))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tournament_settings")
        cursor.execute("DELETE FROM groups")
        cursor.execute("DELETE FROM matches")
        cursor.execute("DELETE FROM match_sets")
        cursor.execute("DELETE FROM standings")
        cursor.execute("DELETE FROM knockout_matches")
        cursor.execute("DELETE FROM knockout_match_sets")
        cursor.execute("""
            INSERT INTO tournament_settings (
                group_size, billiard, dart, kicker, table_tennis, cornhole, archery,
                billiard_target, billiard_sets, dart_target, dart_sets, kicker_target, kicker_sets,
                table_tennis_target, table_tennis_sets, cornhole_target, cornhole_sets, archery_target, archery_sets
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group_size, billiard, dart, kicker, table_tennis, cornhole, archery,
            billiard_target, billiard_sets, dart_target, dart_sets, kicker_target, kicker_sets,
            table_tennis_target, table_tennis_sets, cornhole_target, cornhole_sets, archery_target, archery_sets,
        ))
        cursor.execute("UPDATE tournament_meta SET phase = 'groups' WHERE id = 1")
        conn.commit()
        conn.close()
        create_groups()
        create_matches()
        update_standings()
        flash("Turnier wurde erstellt.")
        return redirect(url_for("admin"))
    return render_template("create_tournament.html")


@app.route("/prepare_knockout")
def prepare_knockout():
    if not is_admin():
        return redirect(url_for("admin"))
    create_knockout_matches()
    set_phase("waiting_for_knockout")
    flash("KO-Feld wurde berechnet. Spieler sehen jetzt: Warten auf Adminfreigabe.")
    return redirect(url_for("admin"))


@app.route("/start_knockout")
def start_knockout():
    if not is_admin():
        return redirect(url_for("admin"))
    set_phase("knockout")
    flash("KO-Phase wurde gestartet.")
    return redirect(url_for("admin"))


@app.route("/finish_tournament")
def finish_tournament():
    if not is_admin():
        return redirect(url_for("admin"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS cnt FROM knockout_matches")
    total_ko = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) AS cnt FROM knockout_matches WHERE status != 'abgeschlossen'")
    open_ko = cursor.fetchone()["cnt"]
    conn.close()
    if total_ko == 0 or open_ko > 0:
        flash("Turnier kann erst beendet werden, wenn alle KO-Spiele abgeschlossen sind.")
        return redirect(url_for("admin"))
    set_phase("finished")
    flash("Turnier wurde beendet. Die Auswertung ist jetzt verfügbar.")
    return redirect(url_for("results_view"))


@app.route("/update_match/<int:match_id>", methods=["GET", "POST"])
def update_match(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.id, m.group_name, m.discipline, p1.name AS player1_name, p2.name AS player2_name,
               m.score1, m.score2, m.sets_won_1, m.sets_won_2, m.status
        FROM matches m
        JOIN players p1 ON m.player1_id = p1.id
        JOIN players p2 ON m.player2_id = p2.id
        WHERE m.id = ?
    """, (match_id,))
    match = cursor.fetchone()
    if not match:
        conn.close()
        flash("Spiel nicht gefunden.")
        return redirect(url_for("groups_overview"))
    phase = current_phase()
    if not is_admin():
        if phase != "groups":
            conn.close()
            flash("Ergebnisse können nur während der Gruppenphase eingetragen werden.")
            return redirect(url_for("group_view", group_name=match["group_name"]))
        if match["status"] == "abgeschlossen":
            conn.close()
            flash("Dieses Spiel ist bereits abgeschlossen. Änderungen nur durch Admin.")
            return redirect(url_for("group_view", group_name=match["group_name"]))
    settings = get_discipline_settings(match["discipline"])
    sets_rows = load_match_sets("match_sets", match_id)
    sets_values = [{"set_number": r["set_number"], "score1": r["score1"], "score2": r["score2"]} for r in sets_rows]
    if request.method == "POST":
        set_scores = []
        error_message = None
        for i in range(1, settings["sets"] + 1):
            raw1 = request.form.get(f"set_{i}_score1", "").strip()
            raw2 = request.form.get(f"set_{i}_score2", "").strip()
            if not raw1 and not raw2:
                continue
            if not raw1 or not raw2:
                error_message = f"Satz {i} ist unvollständig."
                break
            score1 = int(raw1)
            score2 = int(raw2)
            valid, msg = validate_set_score(match["discipline"], settings["target"], score1, score2)
            if not valid:
                error_message = f"Satz {i}: {msg}"
                break
            set_scores.append((score1, score2))
        if error_message:
            flash(error_message)
            conn.close()
            return render_template("update_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values, is_admin=is_admin())
        if not set_scores:
            flash("Bitte mindestens einen Satz eintragen.")
            conn.close()
            return render_template("update_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values, is_admin=is_admin())
        result = calculate_match_result(match["discipline"], set_scores, settings["sets"], allow_draw=True)
        if result["winner_side"] is None and len(set_scores) < settings["sets"]:
            flash("Das Match ist noch nicht entschieden. Bitte vollständige Sätze eintragen.")
            conn.close()
            return render_template("update_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values, is_admin=is_admin())
        final_score1 = sum(s[0] for s in set_scores)
        final_score2 = sum(s[1] for s in set_scores)
        cursor.execute("SELECT player1_id, player2_id FROM matches WHERE id = ?", (match_id,))
        ids = cursor.fetchone()
        winner_id = ids["player1_id"] if result["winner_side"] == 1 else ids["player2_id"] if result["winner_side"] == 2 else None
        cursor.execute("""
            UPDATE matches
            SET score1 = ?, score2 = ?, sets_won_1 = ?, sets_won_2 = ?, winner_id = ?, status = 'abgeschlossen'
            WHERE id = ?
        """, (final_score1, final_score2, result["sets_won_1"], result["sets_won_2"], winner_id, match_id))
        conn.commit()
        conn.close()
        save_match_sets("match_sets", match_id, set_scores)
        update_standings()
        flash("Gruppenspiel wurde gespeichert.")
        if is_admin():
            return redirect(url_for("admin"))
        return redirect(url_for("group_view", group_name=match["group_name"]))
    conn.close()
    return render_template("update_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values, is_admin=is_admin())


@app.route("/update_knockout_match/<int:match_id>", methods=["GET", "POST"])
def update_knockout_match(match_id):
    if not is_admin():
        return redirect(url_for("admin"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT k.id, k.discipline, k.round_name, k.player1_label AS player1_name, k.player2_label AS player2_name,
               k.player1_id, k.player2_id, k.score1, k.score2, k.sets_won_1, k.sets_won_2
        FROM knockout_matches k
        WHERE k.id = ?
    """, (match_id,))
    match = cursor.fetchone()
    settings = get_discipline_settings(match["discipline"])
    sets_rows = load_match_sets("knockout_match_sets", match_id)
    sets_values = [{"set_number": r["set_number"], "score1": r["score1"], "score2": r["score2"]} for r in sets_rows]
    if request.method == "POST":
        set_scores = []
        error_message = None
        for i in range(1, settings["sets"] + 1):
            raw1 = request.form.get(f"set_{i}_score1", "").strip()
            raw2 = request.form.get(f"set_{i}_score2", "").strip()
            if not raw1 and not raw2:
                continue
            if not raw1 or not raw2:
                error_message = f"Satz {i} ist unvollständig."
                break
            score1 = int(raw1)
            score2 = int(raw2)
            valid, msg = validate_set_score(match["discipline"], settings["target"], score1, score2)
            if not valid:
                error_message = f"Satz {i}: {msg}"
                break
            set_scores.append((score1, score2))
        if error_message:
            flash(error_message)
            conn.close()
            return render_template("update_knockout_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values)
        if not set_scores:
            flash("Bitte mindestens einen Satz eintragen.")
            conn.close()
            return render_template("update_knockout_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values)
        result = calculate_match_result(match["discipline"], set_scores, settings["sets"], allow_draw=False)
        if result["winner_side"] is None:
            flash("KO-Spiel braucht eine eindeutige Entscheidung. Bitte Ergebnis prüfen oder Entscheidungssatz eintragen.")
            conn.close()
            return render_template("update_knockout_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values)
        final_score1 = sum(s[0] for s in set_scores)
        final_score2 = sum(s[1] for s in set_scores)
        winner_id = match["player1_id"] if result["winner_side"] == 1 else match["player2_id"]
        cursor.execute("""
            UPDATE knockout_matches
            SET score1 = ?, score2 = ?, sets_won_1 = ?, sets_won_2 = ?, winner_id = ?, status = 'abgeschlossen'
            WHERE id = ?
        """, (final_score1, final_score2, result["sets_won_1"], result["sets_won_2"], winner_id, match_id))
        conn.commit()
        propagate_knockout_winner(conn, match_id)
        conn.close()
        save_match_sets("knockout_match_sets", match_id, set_scores)
        flash("KO-Spiel wurde gespeichert.")
        return redirect(url_for("admin"))
    conn.close()
    return render_template("update_knockout_match.html", match=match, settings=settings, set_rows=range(1, settings["sets"] + 1), sets_values=sets_values)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
