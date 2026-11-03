"""UI-01: native IntUserSettings of one account, outside its revisioned profile.

#717 keeps GAME, GRAPHICS, SOUND, CONTROLS, key bindings, AIM and MARKERS as
{int: int} on the server (IntSettingsRequester.SETTINGS keys 0..56). They carry
no game value, so they stay out of the profile aggregate, its revision and its
immutable fixtures: a table of their own, read at login and merged by the
gateway into the outgoing Account state. An older build ignores the table.
"""
import json
import sqlite3

MAX_KEY = 56
# constants.USER_SERVER_SETTINGS.HIDE_MARKS_ON_GUN, sent with the first-login defaults.
MARKS_ON_GUN = 500
MAX_CHANGES = 64
INT32 = (-2**31, 2**31 - 1)
SCHEMA = """CREATE TABLE IF NOT EXISTS project_int_user_setting(
    account_id TEXT NOT NULL, key INTEGER NOT NULL, value INTEGER NOT NULL, PRIMARY KEY(account_id, key)) WITHOUT ROWID"""


def _int(value):
    return type(value) is int and INT32[0] <= value <= INT32[1]


def _key(value):
    return type(value) is int and (0 <= value <= MAX_KEY or value == MARKS_ON_GUN)


def validate(request):
    """-> (pairs, keys) of a request; ValueError on anything out of the closed shape."""
    if type(request) is not dict or set(request) != {"account_id", "native_database_id", "set", "delete"}:
        raise ValueError("int settings request fields")
    pairs, keys = request["set"], request["delete"]
    if type(pairs) is not list or type(keys) is not list or len(pairs) + len(keys) > MAX_CHANGES:
        raise ValueError("int settings request shape")
    for pair in pairs:
        if type(pair) is not list or len(pair) != 2 or not _key(pair[0]) or not _int(pair[1]):
            raise ValueError("int settings pair")
    # The version key belongs to the client's migration; only its value may change.
    if not all(_key(key) and key != 0 for key in keys):
        raise ValueError("int settings delete key")
    touched = [pair[0] for pair in pairs] + keys
    if len(set(touched)) != len(touched):
        raise ValueError("int settings repeated key")
    return [tuple(pair) for pair in pairs], keys


def execute(database, account_id, body, *, timeout=5.0):
    """Apply one change atomically and return the account's whole map."""
    request = json.loads(body)
    pairs, keys = validate(request)
    if request["account_id"] != account_id:
        raise ValueError("int settings account")
    connection = sqlite3.connect(database, timeout=timeout, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(SCHEMA)
            for key, value in pairs:
                connection.execute("INSERT INTO project_int_user_setting(account_id,key,value) VALUES(?,?,?) "
                                   "ON CONFLICT(account_id,key) DO UPDATE SET value=excluded.value", (account_id, key, value))
            for key in keys:
                connection.execute("DELETE FROM project_int_user_setting WHERE account_id=? AND key=?", (account_id, key))
            rows = connection.execute("SELECT key,value FROM project_int_user_setting WHERE account_id=? ORDER BY key",
                                      (account_id,)).fetchall()
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
    return {"account_id": account_id, "settings": [list(row) for row in rows]}
