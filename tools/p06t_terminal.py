"""Staged terminal DTO validator; configured lab policy is mandatory.

Device maxima/indices are not guessed here. The authoritative damage component
must supply a separately pinned, versioned policy document. No historical hit
volume, damage chance or native behaviour is implied by this generic validator.
The writer records this terminal snapshot atomically with per-stack spending.
"""
from copy import deepcopy
import json
import re
from pathlib import Path

from p09d_ammo_store import require,sha
from p09d_ammo_projection import canonical
from p09e_research_store import _json
from p08b_battle_store import _integer, MAX_PARTICIPANTS
from content0_equipment_catalog import (CO2_FUEL_TANK, CYCLONE_FILTER, ENHANCED_SUSPENSIONS, RPM_LIMITER,
                                       SUSPENSION_TRACK_HEALTH_PERCENT, WET_AMMO_RACKS)

POLICY_SCHEMA="p06t-terminal-policy.v1"
MANIFEST_SHA256="cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717"
SOURCE_CAPS_SHA256="3c4219c2adda799677dea310e84765bbfebca6edfa06aa3db450a7ddfb4875b5"
FIELDS={"policy_revision","roster_size","crew_active","crew","devices","fire","death"}


def fitted_device_maxima(devices, frozen):
    fitted = frozen.get("artefacts", {}).get("optional_devices", ())
    factors = {26: 150 if CYCLONE_FILTER in fitted else 100,
               27: 150 if any(item in WET_AMMO_RACKS for item in fitted) else 100,
               28: 150 if CO2_FUEL_TANK in fitted else 100}
    if any(item in ENHANCED_SUSPENSIONS for item in fitted):
        factors.update({30: SUSPENSION_TRACK_HEALTH_PERCENT, 31: SUSPENSION_TRACK_HEALTH_PERCENT})
    for device in devices:
        extra, maximum = device["extra_index"], device["max_health"]
        yield extra, min(65535, (maximum * factors.get(extra, 100) + 50) // 100)


class TerminalPolicy:
    def __init__(self,document,*,expected_sha256,generated=frozenset()):
        require(type(document) is dict and set(document)=={"schema","policy_revision","profiles"}
            and document["schema"]==POLICY_SCHEMA and type(expected_sha256)is str
            and re.fullmatch(r"[0-9a-f]{64}",expected_sha256) and sha(canonical(document))==expected_sha256,"P06T_TERMINAL_POLICY_REQUIRED")
        revision=document["policy_revision"]
        require(type(revision)is str and re.fullmatch(r"test_lab\.[A-Za-z0-9_.-]{1,80}\.v[1-9][0-9]{0,2}",revision),"P06T_TERMINAL_POLICY_REQUIRED")
        profiles=document["profiles"]
        # BATTLE-ANY: extra kinds only as explicitly generated rows beside a pinned legacy set.
        require(type(profiles)is dict and type(generated)is frozenset and generated<=set(profiles)
            and set(profiles)-generated in ({"ms1","is7"},{"ms1","is7","t26","t34","t3485"}),"P06T_TERMINAL_POLICY_REQUIRED")
        for kind,profile in profiles.items():
            require(type(profile)is dict and set(profile)=={"max_hp","crew_count","devices"} and type(profile["devices"])is list
                and 1<=len(profile["devices"])<=16,"P06T_TERMINAL_POLICY_REQUIRED")
            _integer(profile["max_hp"],1,10000,"P06T_TERMINAL_POLICY_REQUIRED");_integer(profile["crew_count"],1,6,"P06T_TERMINAL_POLICY_REQUIRED")
            seen=set()
            for row in profile["devices"]:
                require(type(row)is dict and set(row)=={"extra_index","max_health"},"P06T_TERMINAL_POLICY_REQUIRED")
                _integer(row["extra_index"],0,255,"P06T_TERMINAL_POLICY_REQUIRED");_integer(row["max_health"],1,60000,"P06T_TERMINAL_POLICY_REQUIRED")
                require(row["extra_index"] not in seen,"P06T_TERMINAL_POLICY_REQUIRED");seen.add(row["extra_index"])
        require(len(canonical(document))<=8192+1024*len(generated),"P06T_TERMINAL_POLICY_REQUIRED")
        self.document=deepcopy(document);self.sha256=expected_sha256;self.generated=generated

    def with_generated(self,rows):
        """New policy with BATTLE-ANY kinds from verified generated table rows
        (vehicle max HP, crew seats, ordered device maxima); legacy rows unchanged."""
        profiles=dict(self.document["profiles"])
        for kind,row in rows.items():
            require(kind not in profiles,"P06T_TERMINAL_POLICY_REQUIRED")
            profiles[kind]=dict(max_hp=row["identity"]["max_hp"],crew_count=len(row["crew_seats"]),
                devices=[{"extra_index":d["extra_index"],"max_health":d["max_health"]}for d in row["devices"]])
        document=dict(self.document,profiles=profiles)
        return TerminalPolicy(document,expected_sha256=sha(canonical(document)),generated=self.generated|frozenset(rows))

    def with_builds(self,rows):
        """CONTENT-0 3.3/4: rows of the generated builds (label -> max HP, crew count, ordered (extra index, device
        max health)) from the pinned build table; a frozen build kind is its label. Stock rows unchanged."""
        profiles=dict(self.document["profiles"])
        for kind,(max_hp,crew_count,devices) in rows.items():
            require(kind not in profiles and "--" in kind,"P06T_TERMINAL_POLICY_REQUIRED")
            profiles[kind]=dict(max_hp=max_hp,crew_count=crew_count,devices=[{"extra_index":i,"max_health":h}for i,h in devices])
        document=dict(self.document,profiles=profiles)
        return TerminalPolicy(document,expected_sha256=sha(canonical(document)),generated=self.generated|frozenset(rows))

    @classmethod
    def from_manifest(cls,path):
        # Caller supplies a trusted configured path, never an incoming request.
        # Exact verified bytes pin both static #717 maxima and explicit lab
        # semantics; a future policy update needs a new contract/pin.
        path=Path(path);require(path.is_file() and path.stat().st_size<=32768,"P06T_TERMINAL_POLICY_REQUIRED")
        with path.open("rb")as stream:raw=stream.read(32769)
        require(sha(raw)==MANIFEST_SHA256,"P06T_TERMINAL_POLICY_REQUIRED")
        data=json.loads(raw)
        require(data["schema"]=="p06t-device-policy.v1" and data["source_caps_sha256"]==SOURCE_CAPS_SHA256
            and data["policy_revision"]=="test_lab.p06t.devices-proxy-fire.v1","P06T_TERMINAL_POLICY_REQUIRED")
        document=dict(schema=POLICY_SCHEMA,policy_revision=data["policy_revision"],profiles={r["kind"]:dict(max_hp=r["vehicle_max_health"],
            crew_count=len(r["crew"]),devices=[{k:v[k]for k in ("extra_index","max_health")}for v in r["devices"]])for r in data["profiles"]})
        return cls(document,expected_sha256=sha(canonical(document)))

    def validate(self,raw,*,frozen,terminal_hp,results=None):
        require(type(raw)is str and len(raw.encode("utf8"))<=8192,"INVALID_TERMINAL_STATE")
        value=_json(raw)
        if "consumables_used" in value:
            slots=value["consumables_used"]
            fitted=frozen.get("artefacts",{}).get("consumables",[0,0,0])
            require(type(slots) is list and 1<=len(slots)<=3
                and all(type(slot) is int and 0<=slot<3 and fitted[slot] not in (0, RPM_LIMITER) for slot in slots)
                and slots==sorted(set(slots)), "INVALID_TERMINAL_STATE")
        require(set(value)-{"consumables_used"}==FIELDS and value["policy_revision"]==self.document["policy_revision"]
            and frozen["kind"] in self.document["profiles"] and type(value["crew_active"])is bool,"INVALID_TERMINAL_STATE")
        profile=self.document["profiles"][frozen["kind"]]
        require(frozen["max_hp"]==profile["max_hp"] and len(frozen["crew_ids"])==profile["crew_count"],"INVALID_TERMINAL_STATE")
        _integer(terminal_hp,0,frozen["max_hp"],"INVALID_TERMINAL_STATE");_integer(value["roster_size"],0,MAX_PARTICIPANTS,"INVALID_TERMINAL_STATE")
        crew=value["crew"]
        require(type(crew)is list and len(crew)==len(frozen["crew_ids"]),"INVALID_TERMINAL_STATE")
        for row,identity in zip(crew,frozen["crew_ids"]):
            require(type(row)is dict and set(row)=={"crew_id","alive"} and row["crew_id"]==identity
                and type(row["alive"])is bool,"INVALID_TERMINAL_STATE")
        require(value["crew_active"]==any(row["alive"]for row in crew),"INVALID_TERMINAL_STATE")
        devices=value["devices"];policy=self.document["profiles"][frozen["kind"]]["devices"]
        require(type(devices)is list and len(devices)==len(policy),"INVALID_TERMINAL_STATE")
        for row,(extra,maximum) in zip(devices,fitted_device_maxima(policy,frozen)):
            require(type(row)is dict and set(row)=={"extra_index","health","max_health"}
                and type(row["extra_index"])is int and row["extra_index"]==extra
                and type(row["max_health"])is int and row["max_health"]==maximum,"INVALID_TERMINAL_STATE")
            _integer(row["health"],0,row["max_health"],"INVALID_TERMINAL_STATE")
        fire=value["fire"];death=value["death"]
        require(type(fire)is dict and set(fire)=={"active","ticks","damage"} and type(fire["active"])is bool
            and type(death)is dict and set(death)=={"reason","killer_slot","tick"},"INVALID_TERMINAL_STATE")
        _integer(fire["ticks"],0,216000,"INVALID_TERMINAL_STATE");_integer(fire["damage"],0,60000,"INVALID_TERMINAL_STATE")
        _integer(death["reason"],-1,10,"INVALID_TERMINAL_STATE");_integer(death["tick"],0,216000,"INVALID_TERMINAL_STATE")
        if death["killer_slot"]is not None:_integer(death["killer_slot"],0,value["roster_size"]-1,"INVALID_TERMINAL_STATE")
        if terminal_hp>0 and value["crew_active"]:require(death["reason"]==-1 and death["killer_slot"]is None,"INVALID_TERMINAL_STATE")
        if terminal_hp==0 or not value["crew_active"]:require(death["reason"]>=0,"INVALID_TERMINAL_STATE")
        if results is not None:require(value["roster_size"]==len(results["participants"]),"INVALID_TERMINAL_STATE")
        return deepcopy(value)
