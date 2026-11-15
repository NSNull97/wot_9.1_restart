from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib,sqlite3,unittest
from contextlib import closing
from tools.content0_s5a_bind_clean_db import verify_clean_db
class CleanDbTests(unittest.TestCase):
    def test_one_owner_integrity_and_hash_are_required(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/'game.sqlite'
            with closing(sqlite3.connect(db)) as c:c.execute('create table game_snapshot(account_id text)');c.execute("insert into game_snapshot values ('operator')");c.commit()
            pin=hashlib.sha256(db.read_bytes()).hexdigest();verify_clean_db(db,'operator',pin)
            with self.assertRaises(ValueError):verify_clean_db(db,'other',pin)
            with self.assertRaises(ValueError):verify_clean_db(db,'operator','0'*64)
            with closing(sqlite3.connect(db)) as c:c.execute("insert into game_snapshot values ('foreign')");c.commit()
            pin=hashlib.sha256(db.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):verify_clean_db(db,'operator',pin)
