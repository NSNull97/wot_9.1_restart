"""Verify a clean operator provenance chain for a scene SQLite snapshot."""
import hashlib
from pathlib import Path
try:
    from tools.content0_s5a_stand import json_unique,no_link,read_stable
except ModuleNotFoundError as e:
    if e.name!='tools':raise
    from content0_s5a_stand import json_unique,no_link,read_stable

CLEAN='content0-s5a-clean-operator.v1'
SCENE='content0-s5a-scene-operator.v1'

def sha(raw): return hashlib.sha256(raw).hexdigest()

def verified_owner(stand,game,account,config,allow_legacy_scene=False):
    stand=Path(stand).resolve(strict=True);game=Path(game).resolve(strict=True)
    no_link(game,stand)
    path=game.parent/'receipt.json'
    direct=True
    if not path.exists() and allow_legacy_scene:
        direct=False
        # Existing prepared snapshot: accept only the original signed-by-hash
        # scene receipt and currently pinned DB before creating a new snapshot.
        sp=game.parent/'scene-receipt.json';no_link(sp,stand);scene=json_unique(read_stable(sp))
        if (scene.get('status')!='PREPARED_NOT_RUN' or Path(scene.get('new_database','')).resolve()!=game
            or scene.get('backup',{}).get('sha256')!=config.get('operator_game_db_sha256')
            or sha(read_stable(game))!=config.get('operator_game_db_sha256')
            or scene.get('scene')!=config.get('scene')):raise ValueError('legacy scene provenance mismatch')
        origin=Path(scene['prior_database']).resolve(strict=True);no_link(origin,stand);path=origin.parent/'receipt.json'
        raw=read_stable(path);owner=json_unique(raw)
    else:
        no_link(path,stand);raw=read_stable(path);owner=json_unique(raw)
        if owner.get('schema')==SCENE:
            direct=False
            if (sha(raw)!=config.get('operator_provenance_sha256') or Path(owner.get('game_database','')).resolve()!=game or owner.get('account_id')!=account or owner.get('backup_sha256')!=config.get('operator_game_db_sha256')):
                raise ValueError('scene operator provenance mismatch')
            complete=(owner.get('integrity_check')=='ok' and owner.get('foreign_keys')=='ok' and owner.get('ownership')=='single_verified')
            if not complete:raise ValueError('scene integrity proof missing')
            sp=game.parent/'scene-receipt.json';no_link(sp,stand);sr=read_stable(sp);scene=json_unique(sr)
            if sha(sr)!=owner.get('scene_receipt_sha256') or scene.get('backup',{}).get('sha256')!=owner['backup_sha256'] or Path(scene.get('new_database','')).resolve()!=game:
                raise ValueError('scene receipt mismatch')
            path=Path(owner['clean_receipt']);no_link(path,stand);raw=read_stable(path)
            if sha(raw)!=owner.get('clean_receipt_sha256'):raise ValueError('clean receipt hash mismatch')
            clean=json_unique(raw)
            if clean.get('native_database_id')!=owner.get('native_database_id'):raise ValueError('native provenance mismatch')
            owner=clean
    if (owner.get('schema')!=CLEAN or owner.get('account_id')!=account or type(owner.get('native_database_id')) is not int
        or owner['native_database_id']<1):raise ValueError('operator DB receipt mismatch')
    origin=Path(owner.get('game_database','')).resolve(strict=True);no_link(origin,stand)
    if path.parent.resolve()!=origin.parent:raise ValueError('clean source binding mismatch')
    if direct and origin!=game:raise ValueError('clean database binding mismatch')
    return {'clean_receipt':str(path.resolve()),'clean_receipt_sha256':sha(raw),'native_database_id':owner['native_database_id'],'clean_database':str(origin)}
