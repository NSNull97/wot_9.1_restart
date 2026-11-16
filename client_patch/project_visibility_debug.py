# -*- coding: utf-8 -*-
"""Closed operator spotting overlay, prepared client only; never an authority.

The gateway must separately authorize this account and opt into diagnostics.
This module only consumes bounded, per-session frames containing committed server
facts. It never sends poses or calculates LOS. Rendering is screen projection,
not depth-tested native 3D. Native rendering is NOT_RUN until an owner battle.
"""
import json
import binascii
import hashlib
import hmac
import os
import math
import re
import struct

VERSION = 3
SETTING = 'visibility_debug'
FEATURE = 'sr_visibility_debug_v1'
AUTH_PREFIX = b'sr_visibility_debug_auth_v1:'
CHALLENGE = struct.Struct('<2sBQ16sI32s')
AUTH_DOMAIN = b'wot091:visibility-operator:v1\x00'
FRAGMENT_DOMAIN = b'wot091:visibility-fragment:v3\x00'
TAG_SIZE = 16
ARENA_UPDATE_TYPE = 201
MAGIC = b'VD'
FRAME = struct.Struct('<2sBQ16s16sIBB')
MAX_FRAME = 210
MAX_PARTS = 57
MAX_BODY = 8192
MAX_RAYS = 14
PART_TIMEOUT = 15.0
CHALLENGE_WINDOW = 256
RECOVERY_DELAY = 31.0
RECOVERY_COOLDOWN = 60.0
SNAPSHOT_DEADLINE = 30.0
MAP_NAMES = {'02_malinovka': 'Malinovka', '05_prohorovka': 'Prokhorovka'}
UUID = re.compile(r'\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')
try:
    INTEGER = (int, long)
    TEXT = (str, unicode)
except NameError:
    INTEGER = (int,)
    TEXT = (str,)


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings: raise ValueError('debug setting must be omitted when disabled')
        return False
    if (settings.get('enable_profile13_battle') is not True or type(value) is not dict
            or set(value) not in (set(('observer', 'target', 'run', 'account', 'grant_file')),
                                  set(('observer', 'target', 'run', 'account', 'grant_file', 'pair_hotkeys')))
            or ('pair_hotkeys' in value and value['pair_hotkeys'] is not True)):
        raise ValueError('debug requires explicit profile13 and pair')
    endpoint=settings.get('endpoint')
    if (not isinstance(endpoint,TEXT) or re.match(r'\A127\.0\.0\.1:[0-9]{1,5}\Z',endpoint) is None
            or not 1024<=int(endpoint.rsplit(':',1)[1])<=65535 or settings.get('network_policy') is not None):
        raise ValueError('debug requires an explicit numeric loopback endpoint')
    a, b = value['observer'], value['target']
    if type(a) is not int or type(b) is not int or not (0 <= a < 6 and 0 <= b < 6) or a == b:
        raise ValueError('debug pair invalid')
    if not isinstance(value['run'],TEXT) or UUID.match(value['run']) is None:
        raise ValueError('debug run UUID invalid')
    if not isinstance(value['account'],TEXT) or UUID.match(value['account']) is None:
        raise ValueError('debug account UUID invalid')
    root=settings.get('local_root');path=value['grant_file']
    if not isinstance(root,TEXT) or not isinstance(path,TEXT) or not os.path.isabs(root) or not os.path.isabs(path):
        raise ValueError('debug grant requires absolute local paths')
    root=os.path.normcase(os.path.realpath(root));path=os.path.normcase(os.path.realpath(path))
    if not path.startswith(root+os.sep) or path==root:
        raise ValueError('debug grant escapes local root')
    return True


def read_grant(path):
    with open(path,'rb') as stream: data=stream.read(44)
    if len(data)!=43 or re.match(br'\A[A-Za-z0-9_-]{43}\Z',data) is None:
        raise ValueError('invalid operator grant')
    return data


def answer_challenge(data,expected_run,expected_battle,account,grant):
    if type(data) is not bytes or len(data)!=CHALLENGE.size:raise ValueError('debug challenge size')
    magic,version,battle,run,session,nonce=CHALLENGE.unpack(data)
    _integer(expected_battle,1,2**64-1)
    if (magic!=b'VC' or version!=1 or battle!=expected_battle or session==0
            or not isinstance(expected_run,TEXT) or UUID.match(expected_run) is None
            or not isinstance(account,TEXT) or UUID.match(account) is None
            or type(grant) is not bytes or re.match(br'\A[A-Za-z0-9_-]{43}\Z',grant) is None
            or run!=binascii.unhexlify(expected_run.replace('-','').encode('ascii'))):
        raise ValueError('debug challenge identity')
    body=AUTH_DOMAIN+run+struct.pack('<QI',battle,session)+nonce+account.encode('ascii')
    return (session,nonce,AUTH_PREFIX+hmac.new(grant,body,hashlib.sha256).hexdigest().encode('ascii'))


def _number(value, minimum, maximum):
    if type(value) not in INTEGER + (float,) or not minimum <= value <= maximum or math.isnan(value) or math.isinf(value):
        raise ValueError('debug numeric bound')
    return value


def _integer(value, minimum, maximum):
    if type(value) not in INTEGER or not minimum <= value <= maximum: raise ValueError('debug integer bound')
    return value


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result: raise ValueError('duplicate debug JSON key')
        result[key] = value
    return result


def _json_shape(raw):
    # Bounded nesting before handing bytes to the JSON parser; quoted brackets
    # and escaped quotes are not structure. This also excludes non-ASCII.
    if not raw or len(raw) > MAX_BODY: raise ValueError('debug JSON bytes')
    try: text = raw.decode('ascii')
    except UnicodeError: raise ValueError('debug JSON ASCII')
    level, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in '{[':
            level += 1
            if level > 8: raise ValueError('debug JSON depth')
        elif char in '}]':
            level -= 1
            if level < 0: raise ValueError('debug JSON depth')
    if quoted or level: raise ValueError('debug JSON truncated')
    return text


def decode_snapshot(raw, selected):
    value = json.loads(_json_shape(raw), object_pairs_hook=_pairs,
                       parse_constant=lambda unused: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    if type(value) is not dict or set(value) != set(('schema','run','battle','tick','scan_ms','next_scan_ms','pair','publication','map')):
        raise ValueError('debug snapshot fields')
    if value['schema'] != 'content0-s5a-operator.v1' or type(value['run']) not in TEXT or not UUID.match(value['run']):
        raise ValueError('debug run identity')
    if type(value['battle']) not in TEXT or not value['battle'].isdigit() or len(value['battle']) > 20 or int(value['battle']) <= 0:
        raise ValueError('debug battle identity')
    _integer(value['tick'], 0, 2**32-1)
    _integer(value['scan_ms'], 0, 3600000)
    _integer(value['next_scan_ms'], value['scan_ms'], 3602000)
    p = value['pair']
    required = ('observer','target','distance_m','view_m','base','base_stationary','movement_delta','moving','net','fire_multiplier','fired',
                'effective','net_remaining_ms','threshold_m','direct','reason','rays','unchecked_ray_count','unchecked_rays')
    if type(p) is not dict or set(p) != set(required) or (p['observer'],p['target']) != selected:
        raise ValueError('debug pair identity')
    for key in ('distance_m','view_m','threshold_m'): _number(p[key], 0, 20000)
    for key in ('base','base_stationary','net','fire_multiplier','effective'): _number(p[key], 0, 1)
    _number(p['movement_delta'],-1,1)
    for key in ('moving','fired','direct'):
        if type(p[key]) is not bool: raise ValueError('debug boolean')
    if p['net_remaining_ms'] is not None: _integer(p['net_remaining_ms'], 0, 3000)
    _integer(p['unchecked_ray_count'], 0, MAX_RAYS)
    if p['reason'] not in ('no_clear_ray','proximity','outside_base_threshold','direct_ray','foliage_threshold'):
        raise ValueError('debug reason')
    if type(p['rays']) is not list or len(p['rays']) > MAX_RAYS: raise ValueError('debug rays')
    for ray in p['rays']:
        if type(ray) is not dict or set(ray) != set(('observer_point','target_point','start','end','result','hit_point','foliage','threshold_m')):
            raise ValueError('debug ray fields')
        _integer(ray['observer_point'],0,1); _integer(ray['target_point'],0,6)
        for key in ('start','end'):
            if type(ray[key]) is not list or len(ray[key]) != 3: raise ValueError('debug vector')
            for n in ray[key]: _number(n,-10000,10000)
        if ray['hit_point'] is not None:
            if type(ray['hit_point']) is not list or len(ray['hit_point']) != 3: raise ValueError('debug hit point')
            for n in ray['hit_point']: _number(n,-10000,10000)
        if ray['result'] not in ('clear','terrain','object','coincident'): raise ValueError('debug ray result')
        if ray['foliage'] is not None: _number(ray['foliage'],0,1)
        if ray['threshold_m'] is not None: _number(ray['threshold_m'],0,20000)
    unchecked = p['unchecked_rays']
    if (type(unchecked) is not list or len(unchecked) != p['unchecked_ray_count']
            or len(unchecked) + len(p['rays']) != MAX_RAYS):
        raise ValueError('debug unchecked ray count')
    for ray in unchecked:
        if type(ray) is not dict or set(ray) != set(('observer_point','target_point','start','end','result')) or ray['result'] != 'not_checked':
            raise ValueError('debug unchecked ray')
        _integer(ray['observer_point'],0,1); _integer(ray['target_point'],0,6)
        for key in ('start','end'):
            if type(ray[key]) is not list or len(ray[key]) != 3: raise ValueError('debug vector')
            for n in ray[key]: _number(n,-10000,10000)
    pub = value['publication']
    if type(pub) is not dict or set(pub) != set(('recipient','target','visible','source','spotter')):
        raise ValueError('debug publication')
    if (pub['recipient'], pub['target']) != selected or type(pub['visible']) is not bool:
        raise ValueError('debug publication identity')
    if pub['source'] not in ('direct','team','direct_retained','team_retained','wreck','hidden'):
        raise ValueError('debug publication source')
    if pub['spotter'] is not None: _integer(pub['spotter'],0,5)
    world=value['map']
    if (type(world) is not dict or set(world)!=set(('asset','actors','direct','publications'))
            or type(world['asset']) not in TEXT or world['asset'] not in MAP_NAMES):
        raise ValueError('debug map identity')
    actors=world['actors']
    if type(actors) is not list or not 1<=len(actors)<=6:raise ValueError('debug map actors')
    slots={}
    for actor in actors:
        if type(actor) is not dict or set(actor)!=set(('slot','team','position','vehicle')):raise ValueError('debug map actor')
        slot=_integer(actor['slot'],0,5);team=_integer(actor['team'],1,2)
        if slot in slots:raise ValueError('duplicate debug map actor')
        if type(actor['position']) is not list or len(actor['position'])!=3:raise ValueError('debug map position')
        for coordinate in actor['position']:_number(coordinate,-10000,10000)
        vehicle=actor['vehicle']
        if (not isinstance(vehicle,TEXT) or re.match(r'\A[A-Za-z0-9_:\-]{1,96}\Z',vehicle) is None):
            raise ValueError('debug map vehicle')
        slots[slot]=team
    direct=world['direct'];seen=set()
    if type(direct) is not list or len(direct)>30:raise ValueError('debug map direct count')
    for edge in direct:
        if type(edge) is not list or len(edge)!=2:raise ValueError('debug map edge')
        a,b=(_integer(item,0,5) for item in edge)
        if a not in slots or b not in slots or slots[a]==slots[b] or (a,b) in seen:raise ValueError('debug map edge identity')
        seen.add((a,b))
    publications=world['publications'];seen_pub=set()
    if type(publications) is not list or len(publications)>30:raise ValueError('debug map publications')
    for entry in publications:
        if type(entry) is not dict or set(entry)!=set(('recipient','target','visible','source','spotter')):
            raise ValueError('debug map publication')
        a=_integer(entry['recipient'],0,5);b=_integer(entry['target'],0,5)
        if a not in slots or b not in slots or slots[a]==slots[b] or (a,b) in seen_pub or type(entry['visible']) is not bool:
            raise ValueError('debug map publication identity')
        if entry['source'] not in ('direct','team','direct_retained','team_retained','wreck','hidden'):
            raise ValueError('debug map source')
        if entry['spotter'] is not None:_integer(entry['spotter'],0,5)
        seen_pub.add((a,b))
    return value



def _tag_equal(actual,expected):
    """Compare fixed-size tags without early exit on Python 2.7.3 as well."""
    if len(actual)!=TAG_SIZE or len(expected)!=TAG_SIZE:return False
    compare=getattr(hmac,'compare_digest',None)
    if callable(compare):return compare(actual,expected)
    difference=0
    for left,right in zip(bytearray(actual),bytearray(expected)):
        difference |= left ^ right
    return difference==0


class Reassembler(object):
    """One bounded in-flight snapshot; never combines epochs or old parts."""
    def __init__(self, selected, run, grant, epoch=None):
        if type(grant) is not bytes or len(grant)!=43:
            raise ValueError('debug authenticated fragment verifier unavailable')
        self.grant=grant;self.epoch=epoch
        if epoch is not None and (type(epoch) is not bytes or len(epoch)!=16):raise ValueError('debug epoch')
        self.selected, self.sequence, self.parts, self.started, self.count = selected, None, {}, 0., 0
        if not isinstance(run,TEXT) or UUID.match(run) is None:raise ValueError('debug expected run')
        self.run=run;self.run_bytes=binascii.unhexlify(run.replace('-','').encode('ascii'))
        self.battle=None
        self.last_sequence = None

    def clear(self):
        self.sequence, self.parts, self.count, self.started = None, {}, 0, 0.

    def reset(self):
        self.clear(); self.last_sequence = None; self.battle=None;self.epoch=None

    def set_epoch(self,epoch,battle):
        if type(epoch) is not bytes or len(epoch)!=16:raise ValueError('debug epoch')
        _integer(battle,1,2**64-1)
        self.reset();self.epoch=epoch;self.battle=battle

    def feed(self, data, now, battle):
        if type(data) is not bytes or not FRAME.size+TAG_SIZE < len(data) <= MAX_FRAME: raise ValueError('debug frame size')
        header=data[:FRAME.size];tag=data[FRAME.size:FRAME.size+TAG_SIZE];body=data[FRAME.size+TAG_SIZE:]
        expected=hmac.new(self.grant,FRAGMENT_DOMAIN+header+body,hashlib.sha256).digest()[:TAG_SIZE]
        if not _tag_equal(tag,expected):raise ValueError('debug fragment authentication')
        magic, version, frame_battle, frame_run, frame_epoch, sequence, index, count = FRAME.unpack(data[:FRAME.size])
        _integer(battle,1,2**64-1)
        if self.battle is not None and self.battle!=battle:
            self.reset();raise ValueError('debug battle changed')
        if (magic != MAGIC or version != VERSION or frame_battle!=battle or frame_run!=self.run_bytes
                or self.epoch is None or frame_epoch!=self.epoch
                or not 1 <= count <= MAX_PARTS or index >= count):
            raise ValueError('debug frame header')
        if self.battle is None:self.battle=battle
        if self.sequence is not None and now - self.started > PART_TIMEOUT: self.clear()
        if self.last_sequence is not None and sequence <= self.last_sequence: return None
        if self.sequence != sequence:
            if self.sequence is not None and sequence < self.sequence: return None
            self.clear(); self.sequence, self.count, self.started = sequence, count, now
        if count != self.count or index in self.parts: raise ValueError('debug frame duplicate or mismatch')
        self.parts[index] = body
        if sum(map(len,self.parts.values())) > MAX_BODY: self.clear(); raise ValueError('debug assembled bytes')
        if len(self.parts) != self.count: return None
        raw = b''.join(self.parts[i] for i in range(self.count))
        try:
            result = decode_snapshot(raw,self.selected)
            if result['run']!=self.run or result['battle']!=str(battle):raise ValueError('debug snapshot epoch mismatch')
        except (ValueError, TypeError, KeyError, OverflowError):
            self.clear()
            raise ValueError('debug snapshot rejected')
        self.last_sequence = sequence; self.clear()
        return result

# The panel displays the base effective value separately from per-ray foliage.
# UNKNOWN/unexamined rays are grey; no ray is recomputed locally.
COLORS = {'terrain':0xff6666,'object':0xffa040,'clear':0x60e080,'coincident':0x60e080,'not_checked':0x808080}
CALL_CLEAR, CALL_LINE, CALL_PANEL, CALL_MARKER = 'ProjectVisibility.clear', 'ProjectVisibility.line', 'ProjectVisibility.panel', 'ProjectVisibility.marker'
CALL_LAMP = 'ProjectVisibility.lamp'
# Six-seat entity layout in shared/wire.rs. The active avatar exposes its own vehicle ID.
VEHICLE_SLOTS = {0x09100003: 0, 0x09100005: 1, 0x09110003: 2,
                 0x09110005: 3, 0x09110007: 4, 0x09110009: 5}
LIVE_SPOTTING_SOURCES = ('direct', 'team', 'direct_retained', 'team_retained')


def own_spotting(snapshot, vehicle_id):
    if type(vehicle_id) not in INTEGER:
        return None
    own_slot = VEHICLE_SLOTS.get(vehicle_id)
    world = snapshot['map']
    if not any(actor['slot'] == own_slot for actor in world['actors']):
        return None
    return any(row['target'] == own_slot and row['visible'] and row['source'] in LIVE_SPOTTING_SOURCES
               for row in world['publications'])
CAMERA_CONTRACT = ('scripts/client/AvatarInputHandler/cameras.py', 'getViewProjectionMatrix', 173, (),
                   'b9ff840c934e586fc4a9a4315bcf99c51db5762600def73723fb83c4e760acf1')
_installed = None


def _clip(x0,y0,x1,y1,width,height):
    dx,dy=x1-x0,y1-y0
    low,high=0.,1.
    for p,q in ((-dx,x0),(dx,width-x0),(-dy,y0),(dy,height-y0)):
        if p==0:
            if q<0: return None
        else:
            t=q/p
            if p<0: low=max(low,t)
            else: high=min(high,t)
            if low>high:return None
    return [int(x0+low*dx),int(y0+low*dy),int(x0+high*dx),int(y0+high*dy)]


def _clip_point(matrix, Math, point):
    p=matrix.applyV4Point(Math.Vector4(point[0],point[1],point[2],1.))
    if not all(math.isfinite(float(v)) if hasattr(math,'isfinite') else not (math.isnan(v) or math.isinf(v))
               for v in (p.x,p.y,p.w)):
        return None
    return [float(p.x),float(p.y),float(p.w)]


def _project_segment(matrix, Math, start, end, width, height):
    """Project one authoritative segment, clipping at camera w and viewport.

    This is an overlay, not a depth test; no world-space ray is recomputed.
    """
    a,b=_clip_point(matrix,Math,start),_clip_point(matrix,Math,end)
    if a is None or b is None:return None
    epsilon=1e-5
    if a[2]<=epsilon and b[2]<=epsilon:return None
    if a[2]<=epsilon:
        t=(epsilon-a[2])/(b[2]-a[2]);a=[a[i]+t*(b[i]-a[i]) for i in range(3)]
    elif b[2]<=epsilon:
        t=(epsilon-a[2])/(b[2]-a[2]);b=[a[i]+t*(b[i]-a[i]) for i in range(3)]
    xy=[]
    for p in (a,b):
        x=(p[0]/p[2]+1.)*width/2.;y=(1.-p[1]/p[2])*height/2.
        if not all(not (math.isnan(v) or math.isinf(v)) and abs(v)<=1e9 for v in (x,y)):return None
        xy.extend((x,y))
    return _clip(xy[0],xy[1],xy[2],xy[3],width,height)


def panel(snapshot):
    pair=snapshot['pair']; pub=snapshot['publication']
    tested=[r for r in pair['rays'] if r['foliage'] is not None]
    selected=tested[-1] if tested else None
    final=('%.3f' % min(1.,pair['effective']+selected['foliage'])) if selected else 'unknown'
    bush=('%.3f' % selected['foliage']) if selected else 'unknown'
    ray_threshold=('%.1f' % selected['threshold_m']) if selected and selected['threshold_m'] is not None else 'unknown'
    return [
        'VIS DEBUG run %s battle %s tick %s' % (snapshot['run'],snapshot['battle'],snapshot['tick']),
        'pair %s -> %s  distance %.1fm  view %.1fm' % (pair['observer'],pair['target'],pair['distance_m'],pair['view_m']),
        'still %.3f  move %+.3f (%s)  net +%.3f' % (pair['base_stationary'],pair['movement_delta'],pair['moving'],pair['net']),
        'shot %s  factor %.3f  effective before foliage %.3f' % (pair['fired'],pair['fire_multiplier'],pair['effective']),
        'last clear ray bush %s  total %s  threshold %sm' % (bush,final,ray_threshold),
        'base threshold %.1fm  net wait %s ms  next scan at %s ms' % (pair['threshold_m'],pair['net_remaining_ms'],snapshot['next_scan_ms']),
        'direct %s  reason %s  team %s via %s' % (pair['direct'],pair['reason'],pub['source'],pub['spotter']),
        'tested %s / 14  grey = not checked; blocked: red terrain / orange object' % len(pair['rays'])]


def map_overlay(snapshot,width):
    """Project coordinate plot, not the native minimap or an inferred sighting."""
    world=snapshot['map'];size=260.;left=width-size-16.;top=180.
    if left<0:return [],[]
    def xy(pos):return left+(pos[0]+600.)/1200.*size,top+(600.-pos[2])/1200.*size
    lines=[(left,top,left+size,top,0xbababa),(left+size,top,left+size,top+size,0xbababa),
           (left+size,top+size,left,top+size,0xbababa),(left,top+size,left,top,0xbababa)]
    locations={};markers=[];occupied=[]
    for actor in world['actors']:
        x,y=xy(actor['position'])
        if not (left<=x<=left+size and top<=y<=top+size):continue
        locations[actor['slot']]=(x,y)
        colour=0x91cd4a if actor['team']==1 else 0xf07870
        lines.extend(((x-3,y,x+3,y,colour),(x,y-3,x,y+3,colour)))
        # Keep point labels inside the plot and separate them from one another.
        offsets=sorted(((dx*26,dy*15) for dx in range(-5,6) for dy in range(-5,6)),
                       key=lambda point:abs(point[0])+abs(point[1]))
        for ox,oy in offsets:
            px=max(left,min(left+size-26,x+ox));py=max(top,min(top+size-15,y+oy))
            if all(px+26<=ax or ax+26<=px or py+15<=ay or ay+15<=py for ax,ay in occupied):
                occupied.append((px,py))
                markers.append((actor['slot'],int(px),int(py),'#%s' % actor['slot'],colour))
                break
        label=actor['vehicle'].split(':')[-1]
        if len(label)>27:label=label[:24]+'...'
        markers.append((6+actor['slot'],int(left+3),int(top+size+8+actor['slot']*16),
                        '#%s %s' % (actor['slot'],label),colour))
    for a,b in world['direct']:
        if a not in locations or b not in locations:continue
        x0,y0=locations[a];x1,y1=locations[b];dx=x1-x0;dy=y1-y0;length=math.sqrt(dx*dx+dy*dy)
        if length<1.:continue
        ux,uy=dx/length,dy/length;endx=x1-5*ux;endy=y1-5*uy;colour=0x80cfff
        lines.extend(((x0,y0,endx,endy,colour),
                      (endx,endy,endx-7*ux+3*uy,endy-7*uy-3*ux,colour),
                      (endx,endy,endx-7*ux-3*uy,endy-7*uy+3*ux,colour)))
    markers.append((12,int(left),int(top-18),MAP_NAMES[world['asset']]+' plot: direct sight ->',0xffffff))
    return lines,markers


class Runtime(object):
    def __init__(self, settings, engine, Math, GUI, cameras, record, grant):
        self.settings,self.engine,self.Math,self.GUI,self.cameras,self.record=settings,engine,Math,GUI,cameras,record
        self.decoder=Reassembler((settings['observer'],settings['target']),settings['run'],grant)
        self.grant=grant;self.challenges=set();self.challenge_battle=None;self.responded=False;self.hello_pending=False
        self.retry=None;self.recover_tick=None;self.auth_at=None
        self.selection_world=None;self.awaiting_since=None
        self.battle,self.snapshot,self.received,self.active,self.timer,self.run=None,None,0.,True,None,None
        self.rendered=None;self.keys_down=set()
        self.spotting_lamp = None
    def attach(self,window): self.battle=window
    def detach(self):
        if self.battle is not None:
            try:
                self.set_spotting_lamp(None)
            except Exception as error:
                self.record('visibility_debug_lamp_clear_failed', error_type=type(error).__name__)
            try:self.battle.call(CALL_CLEAR,[False])
            except Exception as error:self.record('visibility_debug_clear_failed',error_type=type(error).__name__)
        self.spotting_lamp = None
        self.battle=None;self.decoder.reset();self.snapshot=None;self.run=None;self.rendered=None;self.selection_world=None;self.awaiting_since=None;self.auth_at=None
    def ready(self): self.decoder.reset();self.snapshot=None;self.run=None;self.rendered=None;self.responded=False;self.hello_pending=False;self.selection_world=None;self.awaiting_since=None;self.auth_at=None;self.keys_down.clear()
    def frame(self,data):
        try:
            player=self.engine.player()
            battle=getattr(player,'arenaUniqueID',None)
            _integer(battle,1,2**64-1)
            if self.snapshot is not None and self.snapshot['battle']!=str(battle):self.ready()
            if type(data) is bytes and data.startswith(b'VC'):
                if not self.hello_pending:raise ValueError('debug unexpected challenge')
                session,nonce,feature=answer_challenge(data,self.settings['run'],battle,self.settings['account'],self.grant)
                if self.challenge_battle!=battle:
                    self.challenges.clear();self.challenge_battle=battle
                key=(battle,session,nonce)
                if key in self.challenges or len(self.challenges)>=CHALLENGE_WINDOW:
                    raise ValueError('debug repeated challenge or battle challenge limit')
                self.challenges.add(key)
                player.base.setDevelopmentFeature(feature,(self.settings['observer']<<8)|self.settings['target'])
                self.decoder.set_epoch(hashlib.sha256(nonce).digest()[:16],battle)
                self.snapshot=None;self.rendered=None;self.run=None
                if self.battle is not None:self.battle.call(CALL_CLEAR,[False])
                self.responded=True;self.hello_pending=False;self.auth_at=self.engine.time()
                self.record('visibility_debug_challenge_answered')
                return
            if not self.responded:raise ValueError('debug frame before authorization response')
            value=self.decoder.feed(data,self.engine.time(),battle)
            if value is None:return
            if self.run is not None and self.run!=value['run']:raise ValueError('debug run changed in battle')
            self.run=value['run'];self.snapshot=value;self.received=self.engine.time();self.selection_world=value;self.awaiting_since=None;self.auth_at=None
            self.record('visibility_debug_snapshot', snapshot=value)
        except (ValueError,TypeError,KeyError,OverflowError):
            self.decoder.clear();self.record('visibility_debug_frame_rejected')
    def expire_snapshot(self):
        if self.snapshot is not None and self.engine.time()-self.received>15.:
            self.selection_world=self.snapshot;self.snapshot=None;self.rendered=None;self.run=None
            self.awaiting_since=self.received;self.responded=False;self.hello_pending=False;self.auth_at=None;self.decoder.reset()
            if self.retry is not None:self.retry()
            return True
        return False
    def set_spotting_lamp(self, state, tick=None):
        if state == self.spotting_lamp:
            return
        mode = 'native' if state is None else 'spotted' if state else 'hidden'
        self.battle.call(CALL_LAMP, [mode])
        self.spotting_lamp = state
        self.record('visibility_debug_lamp', spotted=state, tick=tick)
    def draw(self):
        if self.battle is None:return
        player=self.engine.player()
        current=getattr(player,'arenaUniqueID',None)
        if self.snapshot is not None and (type(current) not in INTEGER or str(current)!=self.snapshot['battle']):
            self.ready()
        self.expire_snapshot()
        # The map's own-vehicle publications remain relevant while changing the displayed pair.
        lamp_snapshot = self.snapshot or self.selection_world
        if (lamp_snapshot is not None and str(current) == lamp_snapshot['battle']
                and self.engine.time() - self.received <= 15.):
            self.set_spotting_lamp(own_spotting(lamp_snapshot, getattr(player, 'playerVehicleID', None)),
                                   lamp_snapshot['tick'])
        else:
            self.set_spotting_lamp(None)
        if self.snapshot is None:
            if self.recover_tick is not None:self.recover_tick()
            self.battle.call(CALL_CLEAR,[False]);return
        self.battle.call(CALL_CLEAR,[True])
        width,height=self.GUI.screenResolution()
        if not (1<=width<=16384 and 1<=height<=16384):raise ValueError('screen size')
        matrix=self.cameras.getViewProjectionMatrix()
        pair=self.snapshot['pair']
        for ray in pair['rays']+pair['unchecked_rays']:
            end=ray.get('hit_point') or ray['end']
            clipped=_project_segment(matrix,self.Math,ray['start'],end,width,height)
            if clipped is None:continue
            colour=0xffde60 if ray['result']=='clear' and ray.get('foliage',0)>0 else COLORS[ray['result']]
            self.battle.call(CALL_LINE,clipped+[colour])
        map_lines,map_markers=map_overlay(self.snapshot,width)
        for line in map_lines:self.battle.call(CALL_LINE,[int(v) for v in line])
        for slot in range(13):self.battle.call(CALL_MARKER,[slot,0,0,'',0xffffff])
        for marker in map_markers:self.battle.call(CALL_MARKER,list(marker))
        self.battle.call(CALL_PANEL,panel(self.snapshot))
        self.rendered={'battle':self.snapshot['battle'],'run':self.snapshot['run'],'tick':self.snapshot['tick']}


def rendered_snapshot():
    """Only the currently bound, fresh snapshot already sent to the movie."""
    if _installed is None:return None
    runtime=_installed[7]
    value=runtime.snapshot;rendered=runtime.rendered
    if (not runtime.active or runtime.battle is None or value is None or rendered is None
            or runtime.engine.time()-runtime.received>15.0
            or rendered != {'battle':value['battle'],'run':value['run'],'tick':value['tick']}
            or str(getattr(runtime.engine.player(),'arenaUniqueID',None))!=value['battle']):
        return None
    return dict(rendered)



def select_pair(observer, target):
    """Reauthorize a pair in an already established operator session.

    Caller is a locally installed operator control; ordinary clients never
    install this module or hold the grant. Selection does not assert sight.
    """
    if type(observer) is not int or type(target) is not int or not (0<=observer<6 and 0<=target<6) or observer==target:
        raise ValueError('debug pair invalid')
    if _installed is None:raise RuntimeError('debug channel not installed')
    runtime=_installed[7];engine=_installed[8];state=_installed[9];hello=_installed[10]
    player=engine.player()
    if runtime.expire_snapshot() and runtime.battle is not None:runtime.battle.call(CALL_CLEAR,[False])
    world=runtime.snapshot if runtime.snapshot is not None else runtime.selection_world
    if not runtime.active or runtime.battle is None or world is None or str(getattr(player,'arenaUniqueID',None))!=world['battle']:
        raise RuntimeError('debug channel not established')
    if runtime.snapshot is not None:
        if not runtime.responded or engine.time()-runtime.received>15.:
            raise RuntimeError('debug channel not established')
    else:
        # A selected actor may disappear after the last committed scan. Wait for
        # any server-side pending challenge to expire before allowing recovery.
        last_sent=state.get('last_sent')
        if (runtime.awaiting_since is None or engine.time()-runtime.awaiting_since<RECOVERY_DELAY
                or (last_sent is not None and engine.time()-last_sent<RECOVERY_DELAY)):
            raise RuntimeError('debug pair recovery pending')
    teams={actor['slot']:actor['team'] for actor in world['map']['actors']}
    if observer not in teams or target not in teams or teams[observer]==teams[target]:
        raise ValueError('debug pair must contain known opposing actors')
    if (observer,target)==(runtime.settings['observer'],runtime.settings['target']):return False
    if len(runtime.challenges)>=CHALLENGE_WINDOW:
        raise RuntimeError('debug battle challenge limit')
    # Revoke rendered data before requesting a new pair. A stale VD fragment
    # can never complete against the new decoder's expected pair.
    runtime.battle.call(CALL_CLEAR,[False])
    if state['callback'] is not None:engine.cancelCallback(state['callback'])
    runtime.selection_world=world;runtime.awaiting_since=engine.time()
    runtime.settings['observer']=observer;runtime.settings['target']=target
    runtime.decoder=Reassembler((observer,target),runtime.settings['run'],runtime.grant)
    runtime.snapshot=None;runtime.rendered=None;runtime.run=None;runtime.responded=False;runtime.hello_pending=False;runtime.auth_at=None
    state['attempts']=0;state['callback']=engine.callback(1.,hello)
    runtime.record('visibility_debug_pair_requested',observer=observer,target=target)
    return True



def handle_operator_key(event):
    """Observe an explicitly enabled shortcut; never consume native input."""
    if _installed is None:return
    runtime=_installed[7]
    if runtime.settings.get('pair_hotkeys') is not True:return
    import Keys
    key=event.key
    bindings={Keys.KEY_LEFTARROW:(0,-1),Keys.KEY_RIGHTARROW:(0,1),
              Keys.KEY_UPARROW:(1,1),Keys.KEY_DOWNARROW:(1,-1)}
    if key not in bindings:return
    if not event.isKeyDown():
        runtime.keys_down.discard(key);return
    if key in runtime.keys_down:return
    runtime.keys_down.add(key)
    down=runtime.engine.isKeyDown
    if not ((down(Keys.KEY_LCONTROL) or down(Keys.KEY_RCONTROL)) and
            (down(Keys.KEY_LALT) or down(Keys.KEY_RALT))):return
    axis,step=bindings[key]
    observer,target=runtime.settings['observer'],runtime.settings['target']
    world=runtime.snapshot if runtime.snapshot is not None else runtime.selection_world
    if world is None:return
    teams={actor['slot']:actor['team'] for actor in world['map']['actors']}
    fixed=target if axis==0 else observer
    if fixed not in teams:return
    eligible=sorted(slot for slot in teams if teams[slot]!=teams[fixed])
    current=observer if axis==0 else target
    if current not in eligible or len(eligible)<2:return
    chosen=eligible[(eligible.index(current)+step)%len(eligible)]
    if axis==0:observer=chosen
    else:target=chosen
    try:select_pair(observer,target)
    except RuntimeError:runtime.record('visibility_debug_pair_key_refused',reason='channel_not_ready')


def install(record, settings):
    """Bind the prepared native callback and existing battle host; reversible."""
    global _installed
    if _installed is not None:raise RuntimeError('visibility debug already installed')
    import BigWorld, GUI, Math, ClientArena
    from AvatarInputHandler import cameras
    from PlayerEvents import g_playerEvents
    from gui.WindowsManager import g_windowsManager
    import project_battle_feed, project_hit_indicator
    original=ClientArena.ClientArena.__dict__.get('update')
    from native_contract import check
    check(cameras.getViewProjectionMatrix,*(CAMERA_CONTRACT+('visibility projection',)))
    if project_hit_indicator.policy() is None:
        check(original,*(tuple(project_hit_indicator.ARENA_CONTRACT)+('visibility debug',)))
    runtime=Runtime(settings,BigWorld,Math,GUI,cameras,record,read_grant(settings['grant_file']))
    hello_state={'callback':None,'attempts':0,'last_sent':None,'last_attempt':None,'battle':None,'scene':False}
    def update(self,kind,payload):
        if kind==ARENA_UPDATE_TYPE:
            try:runtime.frame(payload)
            except Exception as error:
                runtime.active=False;runtime.detach();record('visibility_debug_channel_failed',error_type=type(error).__name__)
            return None
        return original(self,kind,payload)
    def hello():
        hello_state['callback']=None
        if not runtime.active or not hello_state['scene'] or runtime.responded or hello_state['attempts']>=5:return
        hello_state['attempts']+=1;hello_state['last_attempt']=BigWorld.time()
        player=BigWorld.player()
        if hasattr(player,'base') and hasattr(player,'arena'):
            battle=getattr(player,'arenaUniqueID',None)
            if type(battle) not in INTEGER or not 1<=battle<2**64:
                hello_state['callback']=BigWorld.callback(2.,hello);return
            hello_state['battle']=battle;hello_state['last_sent']=BigWorld.time()
            player.base.setDevelopmentFeature(FEATURE,(settings['observer']<<8)|settings['target'])
            runtime.hello_pending=True
        hello_state['callback']=BigWorld.callback(2.,hello)
    def retry():
        # A previously established pair went stale. Retry once with the usual
        # bounded five hello attempts; do not wait for an alternative pair.
        if not runtime.active or not hello_state['scene']:return
        battle=getattr(BigWorld.player(),'arenaUniqueID',None)
        if len(runtime.challenges)>=CHALLENGE_WINDOW and (
                type(battle) not in INTEGER or not 1<=battle<2**64 or battle==runtime.challenge_battle):return
        if hello_state['callback'] is not None:BigWorld.cancelCallback(hello_state['callback'])
        hello_state['attempts']=0
        hello_state['callback']=BigWorld.callback(1.,hello)
        record('visibility_debug_stale_reauthorization_requested')
    runtime.retry=retry
    def recover_tick():
        # Handles initial hello loss, stalled authenticated snapshots, and
        # previously active channels. Each burst is bounded and rate-limited.
        if not runtime.active or not hello_state['scene'] or runtime.battle is None or runtime.snapshot is not None:return
        player=BigWorld.player();battle=getattr(player,'arenaUniqueID',None)
        known=hello_state['battle']
        if known is not None and battle!=known:return
        if runtime.auth_at is not None and BigWorld.time()-runtime.auth_at>=SNAPSHOT_DEADLINE:
            runtime.auth_at=None;runtime.responded=False;runtime.hello_pending=False;runtime.decoder.reset()
            if hello_state['callback'] is not None:BigWorld.cancelCallback(hello_state['callback'])
            hello_state['callback']=None;hello_state['attempts']=5
            record('visibility_debug_snapshot_deadline')
        last=hello_state['last_attempt']
        if (hello_state['attempts']<5 or hello_state['callback'] is not None or last is None
                or BigWorld.time()-last<RECOVERY_COOLDOWN):return
        retry()
    runtime.recover_tick=recover_tick
    def ready():
        runtime.ready();hello_state['attempts']=0;hello_state['last_attempt']=None;hello_state['last_sent']=None;hello_state['battle']=None;hello_state['scene']=True
        if hello_state['callback'] is not None:BigWorld.cancelCallback(hello_state['callback'])
        hello_state['callback']=BigWorld.callback(1.,hello)
    def leave():
        hello_state['scene']=False;runtime.ready()
        if hello_state['callback'] is not None:BigWorld.cancelCallback(hello_state['callback'])
        hello_state['callback']=None
    def draw():
        if not runtime.active:return
        try:runtime.draw()
        except Exception as error:
            runtime.active=False;runtime.detach();record('visibility_debug_render_failed',error_type=type(error).__name__)
            return
        runtime.timer=BigWorld.callback(0.1,draw)
    host=project_battle_feed.BATTLE
    ready_added=leave_added=False
    try:
        ClientArena.ClientArena.update=update
        g_playerEvents.onAvatarReady += ready
        ready_added=True
        g_playerEvents.onAvatarBecomeNonPlayer += leave
        leave_added=True
        host.add(runtime.attach,runtime.detach,g_windowsManager)
        runtime.timer=BigWorld.callback(0.1,draw)
    except Exception:
        runtime.active=False
        # add() can attach immediately and raise after registering the listener.
        # Attempt every independent undo even if one native cleanup fails.
        try:
            if runtime.timer is not None: BigWorld.cancelCallback(runtime.timer)
        except Exception as error:
            record('visibility_debug_rollback_failed',error_type=type(error).__name__)
        try:
            if (runtime.attach,runtime.detach) in host.listeners:
                host.remove(runtime.attach,runtime.detach)
        except Exception as error:
            record('visibility_debug_rollback_failed',error_type=type(error).__name__)
        try:
            if leave_added: g_playerEvents.onAvatarBecomeNonPlayer -= leave
        except Exception as error:
            record('visibility_debug_rollback_failed',error_type=type(error).__name__)
        try:
            if ready_added: g_playerEvents.onAvatarReady -= ready
        except Exception as error:
            record('visibility_debug_rollback_failed',error_type=type(error).__name__)
        if ClientArena.ClientArena.__dict__.get('update') is update:
            ClientArena.ClientArena.update=original
        raise
    _installed=(ClientArena.ClientArena,original,update,g_playerEvents,ready,leave,project_battle_feed.BATTLE,runtime,BigWorld,hello_state,hello)
    record('visibility_debug_installed',observer=settings['observer'],target=settings['target'])


def restore(record):
    global _installed
    if _installed is None:return
    arena,original,wrapper,events,ready,leave,host,runtime,engine,hello_state,hello=_installed
    runtime.active=False
    if runtime.timer is not None:engine.cancelCallback(runtime.timer)
    if hello_state['callback'] is not None:engine.cancelCallback(hello_state['callback'])
    host.remove(runtime.attach,runtime.detach)
    events.onAvatarReady -= ready
    events.onAvatarBecomeNonPlayer -= leave
    if arena.__dict__.get('update') is not wrapper:raise RuntimeError('visibility debug callback changed')
    arena.update=original;_installed=None
    record('visibility_debug_restored')
