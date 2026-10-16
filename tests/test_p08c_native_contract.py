"""#717 lifecycle consumers inspected as inert marshal data, never imported."""
import hashlib
import os
from pathlib import Path
import re
import unittest

from tools import py27_static

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path(os.environ.get("P08C_ORIGINAL_CLIENT", "C:/WoT_0.9.1_RU_0717_original"))
PINS = {
    "common/constants.pyc": "1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd",
    "common/battle_results_shared.pyc": "9fc1ef0d8b5593107426bd2308d7f235f162d331268840168fc7536b471e0f6a",
    "common/streamids.pyc": "737bd163fbba40822e6c8e3493b39a62c944c7af320692c75889679cb4ce3f29",
    "common/arenatype.pyc": "9b1255ac3cd08f23b429570c229337c80286253b4a97b5bf82c3c6f3744adfa0",
    "client/account_helpers/battleresultscache.pyc": "8f8184063abcdfc750ab3cb577add40096b1127d370be57d604cf5ecb4b17347",
    "client/avatar.pyc": "c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e",
    "client/musiccontroller.pyc": "77b52fd049119c893d64f7385561e835598e64a4337c00a78e81765a75c7a84e",
    "client/tutorial/control/battle/context.pyc": "3b737bd8a6f362b511e58ad29c20b748ee0b8bffd9f9c2434892e27cae435292",
}


class NativeLifecycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all((ORIGINAL / "res/scripts" / path).is_file() for path in PINS):
            raise unittest.SkipTest("NOT_RUN: pinned original #717 client unavailable")
        opcode = ROOT / "local/vendor/cpython-2.7.3/opcode.py"
        if not opcode.is_file():
            raise unittest.SkipTest("NOT_RUN: pinned CPython2 opcode declaration unavailable")
        raw = opcode.read_bytes()
        if hashlib.sha256(raw).hexdigest() != "acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884":
            raise AssertionError("opcode declaration changed")
        table = py27_static.opcode_table(raw.decode("utf8"))
        cls.sources = {}
        for path, digest in PINS.items():
            data = (ORIGINAL / "res/scripts" / path).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise AssertionError("pinned source changed: " + path)
            cls.sources[path] = py27_static.inspect(data, table)

    def method(self, path, qualified):
        return next(row for row in self.sources[path] if row["qualified_name"] == qualified)

    def test_result_encoder_field_order_is_the_original_full_81_schema(self):
        module = self.sources["common/battle_results_shared.pyc"][0]["instructions"]
        literals = {row["value"]: module[index - 1].get("value")
                    for index, row in enumerate(module) if row["opname"] == "STORE_NAME"}
        rust = (ROOT / "server/gateway/src/shared/lifecycle_wire.rs").read_text(encoding="utf8")
        def fields(name):
            text = re.search(r"const " + name + r":[^=]+?=\[(.*?)\];", rust, re.S).group(1)
            return re.findall(r'"([^"\n]+)"', text)
        public = literals["_VEH_CELL_RESULTS_PUBLIC"] + literals["_VEH_BASE_RESULTS_PUBLIC"]
        private = literals["_VEH_CELL_RESULTS_PRIVATE"] + literals["_VEH_BASE_RESULTS_PRIVATE"]
        self.assertEqual(fields("PUBLIC_FIELDS"), public)
        self.assertEqual(fields("PRIVATE_FIELDS"), private)
        self.assertEqual(fields("UPDATE_FIELDS"), literals["VEH_FULL_RESULTS_UPDATE"])
        self.assertEqual(fields("FINAL_FIELDS"), literals["_VEH_FULL_RESULTS_PRIVATE"])
        self.assertEqual(sum(map(len, (public, private, fields("UPDATE_FIELDS"), fields("FINAL_FIELDS")))), 81)
        self.assertEqual(literals["PLAYER_INFO"], ["name", "clanDBID", "clanAbbrev", "prebattleID", "team", "igrType"])
        self.assertEqual(literals["COMMON_RESULTS"], ["arenaTypeID", "arenaCreateTime", "winnerTeam", "finishReason", "duration", "bonusType", "guiType", "vehLockMode", "sortieDivision"])

    def test_period_update_and_finish_numeric_values_are_original(self):
        for name, expected in {
            "ARENA_PERIOD": {"WAITING": 1, "PREBATTLE": 2, "BATTLE": 3, "AFTERBATTLE": 4},
            "ARENA_UPDATE": {"PERIOD": 3, "VEHICLE_KILLED": 6, "BASE_POINTS": 8, "BASE_CAPTURED": 9},
            "FINISH_REASON": {"EXTERMINATION": 1, "BASE": 2, "TIMEOUT": 3, "FAILURE": 4, "TECHNICAL": 5},
        }.items():
            rows = self.method("common/constants.pyc", "<module>." + name)["instructions"]
            actual = {row["value"]: rows[index - 1].get("value") for index, row in enumerate(rows)
                      if row["opname"] == "STORE_NAME"}
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    def test_afterbattle_information_indexes_have_native_winner_and_reason_semantics(self):
        music = self.method("client/musiccontroller.pyc", "<module>.MusicController.__onArenaStateChanged")
        self.assertIn("periodAdditionalInfo", music["names"])
        self.assertEqual([(x["opname"], x.get("value")) for x in music["instructions"]
                          if 162 <= x["offset"] <= 172], [
            ("LOAD_FAST", "arena"), ("LOAD_ATTR", "periodAdditionalInfo"),
            ("LOAD_CONST", 0), ("BINARY_SUBSCR", None), ("STORE_FAST", "winnerTeam")])
        context = self.method("client/tutorial/control/battle/context.pyc", "<module>.ExtendedBattleClientCtx.fetch")
        semantic_keys = [row["value"] for row in context["instructions"]
                         if row["opname"] == "LOAD_CONST" and 124 <= row["offset"] <= 151]
        self.assertEqual(semantic_keys, [0, "winnerTeam", 1, "finishReason"])

    def test_avatar_push_results_and_account_cache_fetch_use_distinct_native_streams(self):
        stream = self.sources["common/streamids.pyc"][0]["instructions"]
        assigned = {row["value"]: stream[index - 1].get("value") for index, row in enumerate(stream)
                    if row["opname"] == "STORE_NAME"}
        self.assertEqual(assigned["STREAM_ID_AVATAR_BATTLE_RESULS"], 100)
        avatar = self.method("client/avatar.pyc", "<module>.PlayerAvatar.receiveBattleResults")
        self.assertTrue({"decompress", "loads", "save", "convertToFullForm", "onBattleResultsReceived",
                         "confirmBattleResultsReceiving"} <= set(avatar["names"]))
        cache = self.method("client/account_helpers/battleresultscache.pyc", "<module>.BattleResultsCache.__onGetResponse")
        self.assertEqual(cache["varnames"], ["self", "callback", "requestID", "resultID", "errorStr", "ext"])
        self.assertIn("_subscribeForStream", cache["names"])
        self.assertIn("RES_STREAM", cache["names"])
        complete = self.method("client/account_helpers/battleresultscache.pyc", "<module>.BattleResultsCache.__onStreamComplete")
        self.assertIn("CMD_BATTLE_RESULTS_RECEIVED", complete["names"])

    def test_base_id_is_original_position_suffix_and_is_not_zero_based(self):
        reader = self.method("common/arenatype.pyc", "<module>.__readTeamBasePositions")
        self.assertEqual(reader["firstlineno"], 491)
        self.assertEqual([(x["opname"], x.get("value")) for x in reader["instructions"]
                          if 129 <= x["offset"] <= 145], [
            ("LOAD_GLOBAL", "int"), ("LOAD_FAST", "s"), ("LOAD_ATTR", "name"),
            ("LOAD_CONST", 8), ("SLICE+1", None), ("CALL_FUNCTION", None), ("STORE_FAST", "id")])
        self.assertEqual([(x["opname"], x.get("value")) for x in reader["instructions"]
                          if 181 <= x["offset"] <= 197], [
            ("LOAD_FAST", "s"), ("LOAD_ATTR", "asVector2"), ("LOAD_FAST", "teamBases"),
            ("LOAD_FAST", "teamIdx"), ("BINARY_SUBSCR", None), ("LOAD_FAST", "id"), ("STORE_SUBSCR", None)])


    def test_autoaim_loss_restores_native_mouse_rotator_without_recursive_command(self):
        # Inert original source only: no producer encoder/decoder round trip.
        lost = self.method("client/avatar.pyc", "<module>.PlayerAvatar.onAutoAimVehicleLost")
        self.assertEqual(lost["firstlineno"], 1126)
        ops = {row["offset"]: row for row in lost["instructions"]}
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (9, 12, 15)], [
            ("LOAD_CONST", 0), ("LOAD_FAST", "self"), ("STORE_ATTR", "_PlayerAvatar__autoAimVehID")])
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (24, 27, 30, 33, 36)], [
            ("LOAD_ATTR", "setAimingMode"), ("LOAD_GLOBAL", "False"),
            ("LOAD_GLOBAL", "AIMING_MODE"), ("LOAD_ATTR", "TARGET_LOCK"), ("CALL_FUNCTION", None)])
        self.assertEqual(ops[36]["arg"], 2)
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (40, 43, 46, 49)], [
            ("LOAD_GLOBAL", "True"), ("LOAD_FAST", "self"),
            ("LOAD_ATTR", "gunRotator"), ("STORE_ATTR", "clientMode")])
        self.assertFalse({"cell", "autoAim"} & set(lost["names"]))
        auto = self.method("client/avatar.pyc", "<module>.PlayerAvatar.autoAim")
        ops = {row["offset"]: row for row in auto["instructions"]}
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (163, 166, 169, 172)], [
            ("LOAD_ATTR", "cell"), ("LOAD_ATTR", "autoAim"), ("LOAD_FAST", "vehID"), ("CALL_FUNCTION", None)])
        self.assertEqual(ops[172]["arg"], 1)
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (250, 253, 256, 259)], [
            ("LOAD_GLOBAL", "False"), ("LOAD_FAST", "self"),
            ("LOAD_ATTR", "gunRotator"), ("STORE_ATTR", "clientMode")])
        # Native autoAim(None/invalid/dead/same-target) sets vehID0 and restores
        # mouse mode locally; no server callback echo is needed for cancel0.
        self.assertEqual([(ops[n]["opname"], ops[n].get("value")) for n in (315, 318, 321, 324)], [
            ("LOAD_GLOBAL", "False"), ("LOAD_GLOBAL", "AIMING_MODE"),
            ("LOAD_ATTR", "TARGET_LOCK"), ("CALL_FUNCTION", None)])
        self.assertEqual(ops[324]["arg"], 2)
        self.assertEqual((ops[328]["value"], ops[337]["value"]), ("True", "clientMode"))

    def test_autoaim_fixed_zero_loss_method_has_original_native_rank_zero(self):
        from tools.packed_xml import decode
        def children(node):
            return node.get("children", []) if isinstance(node, dict) else []
        schemas = {}
        for path, pin in {
            "entity_defs/avatar.def": "38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d",
            "entity_defs/interfaces/chat.def": "3f8f0f6d14e21ece8db54af467235110eaf495b04ab404434fd69eaf66270f3d",
            "entity_defs/alias.xml": "14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746",
        }.items():
            source = ORIGINAL / "res/scripts" / path
            if not source.is_file():
                self.skipTest("NOT_RUN: pinned original entity declarations unavailable")
            raw = source.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pin)
            schemas[path] = decode(raw)
        avatar = {row["name"]: row["data"] for row in children(schemas["entity_defs/avatar.def"])}
        self.assertEqual([(row["name"], row["data"]) for row in children(avatar["Implements"])], [("Interface", {"base64": "Chat"})])
        rows = []
        # Original interface declarations precede Avatar declarations.
        for schema in (schemas["entity_defs/interfaces/chat.def"], schemas["entity_defs/avatar.def"]):
            for group in children(schema):
                if group["name"] == "ClientMethods":
                    rows.extend(children(group["data"]))
        fixed_zero = [row["name"] for row in rows
                      if not any(arg["name"] == "Arg" for arg in children(row["data"]))]
        self.assertEqual(fixed_zero, ["onAutoAimVehicleLost"])
        native = next(row for row in rows if row["name"] == "onAutoAimVehicleLost")
        self.assertEqual(native["data"], "")  # no args, FIXED0, no VAR1 length
        aliases = {row["name"]: row["data"] for row in children(schemas["entity_defs/alias.xml"])}
        self.assertEqual(aliases["OBJECT_ID"], "INT32")
        cell = next(row for row in children(avatar["CellMethods"]) if row["name"] == "autoAim")
        self.assertEqual([(row["name"], row["data"]) for row in children(cell["data"])],
                         [("Exposed", "OWN_CLIENT"), ("Arg", "OBJECT_ID")])
        # The reviewed #717 PE establishes stable ascending fixed-width sort
        # (dd2b70/dd3100), variable last, and entityMethod range starts0x3b.
        # This newly checks actual ORIGINAL bytes, not ignored generated tables.
        exe = ORIGINAL / "WorldOfTanks.exe"
        if not exe.is_file():
            self.skipTest("NOT_RUN: pinned original #717 PE unavailable")
        self.assertEqual(hashlib.sha256(exe.read_bytes()).hexdigest(),
                         "86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed")
        # Only FIXED0 occupies the minimum rank. Source/PE-derived literal body:
        # select current player0x13 + entityMethod(0x3b+rank0), no payload bytes.
        rank = fixed_zero.index("onAutoAimVehicleLost")
        self.assertEqual(bytes((0x13, 0x3b + rank)), b"\x13\x3b")

if __name__ == "__main__":
    unittest.main()
