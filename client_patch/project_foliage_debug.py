# -*- coding: utf-8 -*-
"""Optional preview of calibrated foliage in the native #717 battle movie."""
import hashlib
import json
import math
import os
import re


SETTING = 'foliage_debug'
MAP = '05_prohorovka'
FILE = 'sr_foliage_debug.json'
SCHEMA = 'project-foliage-preview.v1'
CLEAR = 'ProjectFoliage.clear'
POLYGON = 'ProjectFoliage.polygon'
MAX_BYTES = 2 * 1024 * 1024
MAX_POLYGONS = 40
RADIUS_M = 100.
DRAW_INTERVAL_S = .10
TREE_REFRESH_S = .50
POINTS = 16
SCREEN_DIRECTIONS = tuple((math.cos(i * math.pi / 8.), math.sin(i * math.pi / 8.)) for i in range(POINTS))
BOX_CORNERS = tuple((x, y, z) for x in (-1., 1.) for y in (-1., 1.) for z in (-1., 1.))
DIGEST = re.compile(r'\A[0-9a-f]{64}\Z')
CAMERA_CONTRACT = ('scripts/client/AvatarInputHandler/cameras.py', 'getViewProjectionMatrix', 173, (),
                   'b9ff840c934e586fc4a9a4315bcf99c51db5762600def73723fb83c4e760acf1')
try:
    TEXT = (str, unicode)
    INTEGER = (int, long)
except NameError:
    TEXT = (str,)
    INTEGER = (int,)


def _sha(value):
    return isinstance(value, TEXT) and DIGEST.match(value) is not None


def validate_settings(settings):
    if SETTING not in settings:
        return False
    value = settings[SETTING]
    endpoint = settings.get('endpoint')
    if (settings.get('enable_profile13_battle') is not True or settings.get('network_policy') is not None
            or not isinstance(endpoint, TEXT) or re.match(r'\A127\.0\.0\.1:[0-9]{1,5}\Z', endpoint) is None
            or not 1024 <= int(endpoint.rsplit(':', 1)[1]) <= 65535):
        raise ValueError('foliage preview requires local profile13')
    if (type(value) is not dict or set(value) != set(('map', 'file', 'sha256'))
            or value['map'] != MAP or value['file'] != FILE or not _sha(value['sha256'])):
        raise ValueError('foliage preview setting')
    return True


def _number(value, minimum, maximum):
    if type(value) not in INTEGER + (float,) or not minimum <= value <= maximum:
        raise ValueError('foliage preview number')
    return float(value)


def _vector(value, limit):
    if type(value) is not list or len(value) != 3:
        raise ValueError('foliage preview vector')
    return tuple(_number(axis, -limit, limit) for axis in value)


def _basis(value):
    if type(value) is not list or len(value) != 3:
        raise ValueError('foliage preview basis')
    return tuple(_vector(row, 1000.) for row in value)


def _colour(coefficient):
    red, yellow, green = (237, 69, 76), (255, 226, 61), (48, 219, 106)
    start, end, delta = ((red, yellow, coefficient * 4.) if coefficient < .25
                         else (yellow, green, min(1., (coefficient - .25) * 4.)))
    channels = [int(a + (b - a) * delta + .5) for a, b in zip(start, end)]
    return (channels[0] << 16) | (channels[1] << 8) | channels[2]


def read_geometry(settings):
    path = os.path.realpath(settings['file'])
    if os.path.normcase(os.path.dirname(path)) != os.path.normcase(os.path.realpath(os.getcwd())):
        raise ValueError('foliage preview file outside client copy')
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != settings['sha256']:
        raise ValueError('foliage preview bytes/hash')
    data = json.loads(raw.decode('ascii'))
    if (type(data) is not dict or data.get('schema') != SCHEMA or data.get('map') != MAP
            or not _sha(data.get('source_sha256')) or not _sha(data.get('calibration_sha256'))):
        raise ValueError('foliage preview document')
    instances, crowns = data.get('instances'), data.get('fallen_trees')
    if type(instances) is not list or not 1 <= len(instances) <= 3000 or type(crowns) is not list or len(crowns) > 1000:
        raise ValueError('foliage preview count')
    shrubs, trees = [], {}
    for row in instances:
        shape = row.get('shape', 'ellipsoid')
        if shape not in ('ellipsoid', 'box'):
            raise ValueError('foliage preview shrub shape')
        shrubs.append((_vector(row['center_world'], 10000.), _basis(row['basis_world_rows']),
                       _colour(_number(row['concealment_additive'], 0., 1.)), shape))
    for row in crowns:
        chunk, index = row['chunk_id'], row['native_index']
        if (type(chunk) not in INTEGER or not 0 <= chunk <= 65535 or type(index) not in INTEGER
                or not 0 <= index <= 255 or (chunk, index) in trees):
            raise ValueError('foliage preview native tree identity')
        trees[chunk, index] = (_vector(row['root_world'], 10000.), _vector(row['center_from_root_world'], 1000.),
                               _basis(row['basis_world_rows']), _colour(_number(row['concealment_additive'], 0., 1.)))
    return shrubs, trees, data['source_sha256']


def fallen_geometry(tree, packed):
    root, offset, basis, colour = tree
    yaw = ((packed >> 18) & 63) * math.pi / 32. - math.pi
    pitch = (packed & 65535) * math.pi / 32768. - math.pi
    sin_yaw, cos_yaw = math.sin(yaw), math.cos(yaw)
    sin_pitch, cos_pitch = math.sin(pitch), math.cos(pitch)

    def rotate(axis):
        x, y, z = axis
        forward = x * sin_yaw + z * cos_yaw
        delta = forward * (cos_pitch - 1.) + y * sin_pitch
        return (x + delta * sin_yaw, y * cos_pitch - forward * sin_pitch, z + delta * cos_yaw)

    return (tuple(x + dx for x, dx in zip(root, rotate(offset))), tuple(rotate(row) for row in basis), colour,
            'ellipsoid')


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _viewport(points, width, height):
    for axis, bound, sign in ((0, 0., 1), (0, width, -1), (1, 0., 1), (1, height, -1)):
        if not points:
            return []
        clipped = []
        start = points[-1]
        sd = (start[axis] - bound) * sign
        for end in points:
            ed = (end[axis] - bound) * sign
            if (sd >= 0.) != (ed >= 0.):
                t = sd / (sd - ed)
                clipped.append(tuple(a + t * (b - a) for a, b in zip(start, end)))
            if ed >= 0.:
                clipped.append(end)
            start, sd = end, ed
        points = clipped
    return points


def _projected_basis(matrix, math_api, center, basis):
    def clip(row, w):
        value = matrix.applyV4Point(math_api.Vector4(row[0], row[1], row[2], w))
        return value.x, value.y, value.w

    return clip(center, 1.), tuple(zip(*(clip(row, 0.) for row in basis)))


def project(matrix, math_api, center, basis, width, height):
    # In homogeneous coordinates each projected silhouette support point is
    # the maximum of a linear numerator divided by the positive camera w.
    # Solve that quadratic for 16 directions around the projected ellipsoid.
    (cx, cy, cw), (bx, by, bw) = _projected_basis(matrix, math_api, center, basis)
    norm_w = math.sqrt(_dot(bw, bw))
    # Suppress a projection that cuts across the camera plane, including
    # sniper views with the camera inside a bush.
    if not cw - norm_w > 1e-4:
        return []
    for coord, axes in ((cx, bx), (cy, by)):
        for sign in (-1, 1):
            extent = tuple(w + sign * v for w, v in zip(bw, axes))
            if cw + sign * coord + math.sqrt(_dot(extent, extent)) < 0.:
                return []

    quadratic = cw * cw - norm_w * norm_w
    points = []
    for ux, uy in SCREEN_DIRECTIONS:
        n = cx * ux + cy * uy
        axis = tuple(x * ux + y * uy for x, y in zip(bx, by))
        half = n * cw - _dot(axis, bw)
        disc = half * half - quadratic * (n * n - _dot(axis, axis))
        support = (half + math.sqrt(max(0., disc))) / quadratic
        normal = tuple(x - support * w for x, w in zip(axis, bw))
        length = math.sqrt(_dot(normal, normal))
        if not length > 0.:
            return []
        point = tuple(x / length for x in normal)
        w = cw + _dot(bw, point)
        points.append(((1. + (cx + _dot(bx, point)) / w) * width / 2.,
                       (1. - (cy + _dot(by, point)) / w) * height / 2.))
    points = _viewport(points, width, height)
    if len(points) > POINTS:
        points = [points[i * len(points) // POINTS] for i in range(POINTS)]
    return points


def _convex_hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        return []

    def half(ordered):
        hull = []
        for point in ordered:
            x, y = point
            while len(hull) >= 2:
                a, b = hull[-2], hull[-1]
                if (b[0] - a[0]) * (y - a[1]) > (b[1] - a[1]) * (x - a[0]):
                    break
                hull.pop()
            hull.append(point)
        return hull[:-1]

    return half(points) + half(reversed(points))


def project_box(matrix, math_api, center, basis, width, height):
    (cx, cy, cw), (bx, by, bw) = _projected_basis(matrix, math_api, center, basis)
    # Match the ellipsoid preview when the volume straddles the camera plane.
    if not cw - sum(abs(axis) for axis in bw) > 1e-4:
        return []
    points = []
    for corner in BOX_CORNERS:
        w = cw + _dot(bw, corner)
        x = (1. + (cx + _dot(bx, corner)) / w) * width / 2.
        y = (1. - (cy + _dot(by, corner)) / w) * height / 2.
        if math.isnan(x) or math.isinf(x) or math.isnan(y) or math.isinf(y):
            return []
        points.append((x, y))
    return _viewport(_convex_hull(points), width, height)


class Preview(object):
    def __init__(self, engine, math_api, gui, cameras, tree_type, record, geometry):
        self.engine, self.math, self.gui, self.cameras = engine, math_api, gui, cameras
        self.tree_type, self.record = tree_type, record
        self.shrubs, self.crowns, self.source = geometry
        self.window, self.timer, self.space = None, None, None
        self.enabled, self.visible, self.pressed, self.active = False, False, False, True
        self.fallen, self.tree_refresh = [], None
        self.first_draw = True

    def attach(self, window):
        self.window = window
        self.first_draw = True
        self.schedule()

    def detach(self):
        try:
            self.cancel()
            self.clear()
        finally:
            self.window, self.space, self.tree_refresh = None, None, None
            self.fallen = []
            self.pressed = False

    def cancel(self):
        if self.timer is not None:
            self.engine.cancelCallback(self.timer)
            self.timer = None

    def clear(self):
        if self.window is not None and self.visible:
            self.visible = False
            try:
                self.window.call(CLEAR, [False])
            except Exception as error:
                self.record('foliage_debug_clear_failed', error_type=type(error).__name__)

    def schedule(self):
        if self.enabled and self.active and self.window is not None and self.timer is None:
            self.timer = self.engine.callback(DRAW_INTERVAL_S, self.tick)

    def toggle(self):
        if self.window is None or self.player() is None:
            return
        self.enabled = not self.enabled
        if self.enabled:
            self.schedule()
        else:
            self.cancel()
            self.clear()
        self.record('foliage_debug_toggled', enabled=self.enabled, map=MAP)

    def player(self):
        player = self.engine.player()
        arena_type = getattr(getattr(player, 'arena', None), 'arenaType', None)
        if getattr(arena_type, 'geometryName', None) != MAP:
            return None
        return player

    def nearby_fallen(self, player):
        now = self.engine.time()
        if self.space == player.spaceID and self.tree_refresh is not None and now < self.tree_refresh:
            return self.fallen
        fallen = {}
        for entity in self.engine.entities.values():
            if type(entity) is not self.tree_type or getattr(entity, 'spaceID', None) != player.spaceID:
                continue
            chunk = getattr(entity, '_AreaDestructibles__chunkID', None)
            for index, packed in enumerate(getattr(entity, 'fallenTrees', ())):
                if index >= 62:
                    break
                if type(packed) in INTEGER and 0 <= packed <= 0xffffffff:
                    key = (chunk, packed >> 24)
                    if key in self.crowns:
                        fallen[key] = fallen_geometry(self.crowns[key], packed)
        self.space, self.tree_refresh = player.spaceID, now + TREE_REFRESH_S
        self.fallen = list(fallen.values())
        return self.fallen

    def draw(self):
        player = self.player()
        vehicle_id = getattr(player, 'playerVehicleID', None)
        vehicle = self.engine.entity(vehicle_id) if vehicle_id else None
        if vehicle is None or not vehicle.inWorld:
            self.clear()
            return
        vector = vehicle.position
        position = (vector.x, vector.y, vector.z)
        nearby = []
        for volume in self.shrubs + self.nearby_fallen(player):
            center = volume[0]
            distance = sum((a - b) ** 2 for a, b in zip(center, position))
            if distance <= RADIUS_M ** 2:
                nearby.append((distance, volume))
        nearby.sort(key=lambda pair: pair[0])
        width, height = self.gui.screenResolution()
        if not 1 <= width <= 16384 or not 1 <= height <= 16384:
            return
        matrix = self.cameras.getViewProjectionMatrix()
        polygons = []
        boxes = 0
        for _, (center, basis, colour, shape) in nearby:
            draw_shape = project_box if shape == 'box' else project
            points = draw_shape(matrix, self.math, center, basis, width, height)
            if len(points) >= 3:
                coordinates = [int(round(value)) for point in points for value in point]
                polygons.append([colour, 27, len(points)] + coordinates + [0] * (POINTS * 2 - len(coordinates)))
                boxes += int(shape == 'box')
                if len(polygons) == MAX_POLYGONS:
                    break
        self.window.call(CLEAR, [True])
        self.visible = True
        for polygon in reversed(polygons):
            self.window.call(POLYGON, polygon)
        if polygons and self.first_draw:
            self.first_draw = False
            self.record('foliage_debug_rendered', map=MAP, polygons=len(polygons), box_polygons=boxes,
                        native_fallen=len(self.fallen), source_sha256=self.source, projection='screen_space')

    def tick(self):
        self.timer = None
        try:
            self.draw()
        except Exception as error:
            self.active = False
            self.record('foliage_debug_render_failed', error_type=type(error).__name__)
            self.clear()
            return
        self.schedule()


_installed = None


def install(record, settings):
    global _installed
    if _installed is not None:
        raise RuntimeError('foliage preview already installed')
    import BigWorld
    import GUI
    import Math
    from AreaDestructibles import AreaDestructibles
    from AvatarInputHandler import cameras
    from gui.WindowsManager import g_windowsManager
    from project_battle_feed import BATTLE
    from native_contract import check

    check(cameras.getViewProjectionMatrix, *(CAMERA_CONTRACT + ('foliage projection',)))
    geometry = read_geometry(settings)
    preview = Preview(BigWorld, Math, GUI, cameras, AreaDestructibles, record, geometry)
    BATTLE.add(preview.attach, preview.detach, g_windowsManager)
    _installed = (BATTLE, preview)
    record('foliage_debug_installed', map=MAP, shrubs=len(preview.shrubs), crowns=len(preview.crowns),
           source_sha256=preview.source, hotkey='Ctrl+Alt+F')


def handle_key(event):
    if _installed is None:
        return
    import Keys
    preview = _installed[1]
    if event.key != Keys.KEY_F:
        return
    if not event.isKeyDown():
        preview.pressed = False
        return
    if preview.pressed:
        return
    preview.pressed = True
    down = preview.engine.isKeyDown
    if (down(Keys.KEY_LCONTROL) or down(Keys.KEY_RCONTROL)) and (down(Keys.KEY_LALT) or down(Keys.KEY_RALT)):
        preview.toggle()


def restore(record):
    global _installed
    if _installed is None:
        return
    host, preview = _installed
    _installed = None
    preview.active = False
    host.remove(preview.attach, preview.detach)
    record('foliage_debug_restored')
