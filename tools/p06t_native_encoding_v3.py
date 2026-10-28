"""Candidate native-only #717 nation encoding overlay; never a store or grant.

The immutable legacy semantic catalogue/hash stays authoritative for ownership,
assembly compatibility and prices. This object has a different, explicit SHA.
No old command, catalogue pin, projection or database is modified by this module.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict,dataclass
import hashlib,json
from pathlib import Path
from types import MappingProxyType

from p09e_research_catalog import Catalog,load_catalog,NATIONS as LEGACY_NATIONS
from p09e_research_store import assembly
from game_profile_tx import TransactionError
from p09e_native_research_audit import make_int_cd,split_int_cd,plain_vehicle_descriptor
from py27_static import parse_pyc,records
from vehicle_physics_profile import no_links

SCHEMA='native-item-encoding.717.v2'
SEMANTIC_SHA256='1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80'
NATIONS=('ussr','germany','usa','china','france','uk','japan')
TYPES={'vehicle':1,'chassis':2,'turret':3,'gun':4,'engine':5,'fuelTank':6,'radio':7}
MODULE_ORDER=('chassis','engine','fuelTank','radio','turret','gun')
SOURCE_PINS={
 'res/scripts/common/nations.pyc':(565,'34392915b0d2a70a3df0b8151e0fdbb9cb58aad6a708ffc85843c45c596a4562'),
 'res/scripts/common/items/__init__.pyc':(4303,'587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176'),
 'res/scripts/common/items/vehicles.pyc':(125668,'805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'),
}
METHOD_SHA256='00d04a6b4859de88a86d352887866a0947dfe6d6b35a105c2d6f17e71a484ee8'
MAX_ITEMS=16384
MAX_DOCUMENT=1024*1024

class EncodingError(ValueError):pass
def require(value,reason):
    if not value:raise EncodingError(reason)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def verify_sources(payloads):
    require(type(payloads)is dict and set(payloads)==set(SOURCE_PINS),'exact source files required')
    for name,(size,digest)in SOURCE_PINS.items():
        raw=payloads[name];require(type(raw)is bytes and len(raw)==size and sha(raw)==digest,'source pin mismatch')
    nation=parse_pyc(payloads['res/scripts/common/nations.pyc'])
    require([n.encode('ascii')for n in NATIONS]in nation['consts'] and b'NAMES'in nation['names'],'source nation order')
    items=parse_pyc(payloads['res/scripts/common/items/__init__.pyc'])
    names=[b'reserved',b'vehicle',b'vehicleChassis',b'vehicleTurret',b'vehicleGun',b'vehicleEngine',b'vehicleFuelTank',b'vehicleRadio',b'tankman',b'optionalDevice',b'shell',b'equipment']
    require(names in items['consts'],'source native item type ordering')
    matches=[code for name,code in records(parse_pyc(payloads['res/scripts/common/items/vehicles.pyc']))if name=='<module>.makeIntCompactDescrByID']
    require(len(matches)==1 and sha(matches[0]['code'])==METHOD_SHA256,'source integer descriptor algorithm')

@dataclass(frozen=True)
class Item:
    resource_id:str
    kind:str
    nation:str
    nation_id:int
    item_id:int
    native_cd:int
    legacy_cd:int

class NativeEncodingV2:
    """Closed source mapping; resource IDs are stable, native integers are not.

    The caller must bind this encoding to an explicit owner contract and cache
    generation. An integer alone cannot reveal whether an old client meant UK
    or a new client meant France; this object never claims such discrimination.
    """
    def __init__(self,catalog,payloads):
        verify_sources(payloads)
        require(isinstance(catalog,Catalog)and catalog.sha256==SEMANTIC_SHA256,'frozen semantic catalogue required')
        self._domain=Catalog(deepcopy(catalog.document))
        before=canonical(catalog.document);forward={};reverse={}
        records_by_id={**self._domain.vehicles,**self._domain.modules}
        require(1<=len(records_by_id)<=MAX_ITEMS,'bounded semantic items')
        for key,row in records_by_id.items():
            parts=key.split(':');vehicle=key in self._domain.vehicles
            require((vehicle and len(parts)==3 and parts[0]=='vehicle')or(not vehicle and len(parts)==4 and parts[0]=='module'),'semantic resource ID shape')
            nation=parts[1];kind='vehicle'if vehicle else parts[2]
            require(nation in NATIONS and kind in TYPES and row.get('resource_name')==parts[-1],'semantic source kind/name')
            old=row['native_compact_id'];item_type,old_nation,item_id=split_int_cd(old)
            require(item_type==TYPES[kind]and old_nation==LEGACY_NATIONS.index(nation),'legacy native type/nation mismatch')
            if vehicle:require(item_id<=255 and row['nation']==nation and row['nation_id']==old_nation,'vehicle byte/source nation')
            require(make_int_cd(TYPES[kind],old_nation,item_id)==old,'legacy source compact ID layout')
            native=make_int_cd(TYPES[kind],NATIONS.index(nation),item_id)
            require(native not in reverse,'source native compact ID collision')
            item=Item(key,kind,nation,NATIONS.index(nation),item_id,native,old)
            forward[key]=item;reverse[native]=item
        require(canonical(catalog.document)==before and catalog.sha256==SEMANTIC_SHA256,'input catalogue mutated')
        self.items=MappingProxyType(forward);self.reverse=MappingProxyType(reverse)
        document=dict(schema=SCHEMA,semantic_catalog_sha256=SEMANTIC_SHA256,original_nations=list(NATIONS),
            source_pins={k:dict(bytes=v[0],sha256=v[1])for k,v in SOURCE_PINS.items()},
            integer_method_sha256=METHOD_SHA256,items=[asdict(forward[k])for k in sorted(forward)])
        self._raw=canonical(document);require(len(self._raw)<=MAX_DOCUMENT,'bounded encoding document')
        self.sha256=sha(self._raw)
        self.semantic_catalog_sha256=SEMANTIC_SHA256

    @classmethod
    def from_original(cls,original_root,catalog=None):
        root=no_links(Path(original_root)).resolve(strict=True);require(root.is_dir(),'original directory required')
        payloads={}
        for name,(size,_)in SOURCE_PINS.items():
            path=no_links(root/name);require(path.resolve(strict=True).is_relative_to(root)and path.stat().st_size==size,'source path/size')
            with path.open('rb')as stream:payloads[name]=stream.read(size+1)
        return cls(load_catalog(root)if catalog is None else catalog,payloads)

    def document(self):return json.loads(self._raw)

    def encode(self,resource_id,*,expected_kind=None):
        require(type(resource_id)is str and resource_id in self.items,'unknown semantic resource ID')
        row=self.items[resource_id]
        require(expected_kind is None or expected_kind==row.kind,'native source kind mismatch')
        return row.native_cd

    def decode(self,native_cd,*,expected_kind=None,expected_nation=None):
        require(type(native_cd)is int,'native integer type required')
        item_type,nation,item_id=split_int_cd(native_cd)
        require(nation<len(NATIONS)and item_type in TYPES.values()and native_cd in self.reverse,'unregistered native source ID')
        row=self.reverse[native_cd]
        require(row.item_id==item_id and TYPES[row.kind]==item_type and row.nation_id==nation,'native mapping corruption')
        require(expected_kind is None or expected_kind==row.kind,'native source kind mismatch')
        require(expected_nation is None or expected_nation==row.nation,'native source nation mismatch')
        return row.resource_id

    def encode_assembly(self,vehicle_id,modules):
        """Representation/compatibility only: no ownership or admission proof."""
        require(type(modules)is dict and set(modules)==set(MODULE_ORDER),'exact six mounted modules')
        try:assembly(self._domain,vehicle_id,modules)
        except TransactionError as error:raise EncodingError(error.code)from error
        cd=lambda role:self.encode(modules[role],expected_kind=role)
        return plain_vehicle_descriptor(self.encode(vehicle_id,expected_kind='vehicle'),cd('chassis'),cd('engine'),
            cd('fuelTank'),cd('radio'),[(cd('turret'),cd('gun'))])
