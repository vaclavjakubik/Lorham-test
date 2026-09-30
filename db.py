from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL


def get_connection():
    return psycopg.connect(DATABASE_URL)


def fetch_all(sql, params=()):
    # Provede SELECT a vrátí řádky jako slovníky, např. row["name"].
    # Hodnoty z uživatelského vstupu patří vždy do params, nikdy do textu sql.
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@contextmanager
def transaction():
    # Použití: with db.transaction() as cur: ... cur.execute(...)
    # Když blok doběhne bez chyby, všechny zápisy se uloží najednou (commit).
    # Když uvnitř vznikne chyba, zruší se všechny (rollback) a v DB nezůstane nic.
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
