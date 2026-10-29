# -*- coding: utf-8 -*-
"""NET-01 diagnostic, not original 0.9.1: what this client shows, 10 times a second.

Read-only. While the player is the native Avatar, every 0.1 s one event
records BigWorld.time(), BigWorld.serverTime() and the position every native
Vehicle entity currently has (the own vehicle flagged). It calls no game
command and assigns no Entity/filter/UI state. With the gateway's
SHARED_SNAPSHOT (server positions per tick) it measures display lag directly;
the 1 Hz shared_native_snapshot was too coarse (NET-01 battle 2026-10-29).

Bounded: at most MAX_SAMPLES events and MAX_VEHICLES rows per event.
Enabled only by the explicit prepare option --trace-pose-10hz; omit the option
and re-prepare to roll back. Pure Python 2.7 at import time.
"""
import math

VERSION = 1
SETTING = 'trace_pose_10hz'
EVENT = 'native_pose_sample'
PERIOD = 0.1
MAX_SAMPLES = 20 * 60 * 10
MAX_VEHICLES = 40
_state = None


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('pose trace setting must be omitted when disabled')
        return False
    if value is not True or settings.get('enable_profile13_battle') is not True:
        raise ValueError('pose trace requires explicit true and profile13 battle')
    return True


def _coordinate(value):
    value = float(value)
    if math.isnan(value) or math.isinf(value) or abs(value) > 4096:
        raise ValueError('native vehicle position is not bounded')
    return round(value, 3)


def sample(engine, avatar_class, vehicle_class):
    """One row set, or None when the native player is not the battle Avatar."""
    player = engine.player()
    if type(player) is not avatar_class:
        return None
    own = player.playerVehicleID
    rows = []
    for entity in engine.entities.values():
        if type(entity) is not vehicle_class:
            continue
        if len(rows) >= MAX_VEHICLES:
            raise ValueError('pose trace vehicle bound')
        p = entity.position
        rows.append([entity.id, _coordinate(p.x), _coordinate(p.y), _coordinate(p.z), entity.id == own])
    rows.sort(key=lambda row: row[0])
    return dict(native_time=float(engine.time()), server_time=float(engine.serverTime()),
                arena_unique_id=player.arenaUniqueID, player_vehicle_id=own, vehicles=rows,
                observer_mutated_gameplay=False)


def install(record):
    global _state
    if _state is not None:
        raise RuntimeError('pose trace already installed')
    if not callable(record):
        raise ValueError('diagnostic record function required')
    import BigWorld
    import Avatar
    import Vehicle
    _state = dict(record=record, samples=0, active=True)

    def tick():
        state = _state
        if state is None or not state['active']:
            return
        try:
            row = sample(BigWorld, Avatar.PlayerAvatar, Vehicle.Vehicle)
            if row is not None:
                state['samples'] += 1
                state['record'](EVENT, sample=state['samples'], **row)
        except Exception as error:
            # A failed sample stops the trace; the game itself is untouched.
            state['active'] = False
            state['record']('native_pose_trace_stopped', error_type=type(error).__name__,
                            error=str(error)[:200], samples=state['samples'])
            return
        if state['samples'] >= MAX_SAMPLES:
            state['active'] = False
            state['record']('native_pose_trace_stopped', reason='sample bound', samples=state['samples'])
            return
        BigWorld.callback(PERIOD, tick)

    record('native_pose_trace_installed', version=VERSION, period_s=PERIOD, max_samples=MAX_SAMPLES)
    BigWorld.callback(PERIOD, tick)


def restore(record):
    global _state
    if _state is not None:
        _state['active'] = False
        record('native_pose_trace_restored', samples=_state['samples'])
    _state = None
