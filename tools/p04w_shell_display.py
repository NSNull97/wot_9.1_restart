"""Display references for six source-qualified #717 stock shell IDs only.

No inventory, purchase, price charged, sale, ammunition or revision is mutated.
The original Shop iterator requires itemPrices even for Warehouse enumeration;
notInShopItems hides purchasing rows while the Warehouse inventory filter uses
the actual independently projected inventoryCount. Source prices are client XML
reference facts, not a claim about historical server financial transactions.
"""
from copy import deepcopy
import hashlib

SOURCE_PATH='res/scripts/item_defs/vehicles/ussr/components/shells.xml'
SOURCE_BYTES=20468
SOURCE_SHA256='ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96'
# CD, exact XML resource, original source ID, credit/gold display reference.
SOURCE_ROWS=(
 (2570,'_37mm_UBRT1',10,(0,0)),
 (2826,'_37mm_BPT1',11,(0,1)),
 (3082,'_37mm_UOT1',12,(8,0)),
 (14602,'_130mm_UBR-482',57,(1118,0)),
 (14858,'_130mm_UBR-482P',58,(0,12)),
 (15114,'_130mm_UOF-482',59,(978,0)),
)

def verified_source_prices(raw):
    """Read-only reproducible static audit; never executes client bytecode."""
    if type(raw)is not bytes or len(raw)!=SOURCE_BYTES or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('P04W_EXACT_ORIGINAL_SHELL_SOURCE_REQUIRED')
    from packed_xml import decode,walk
    values=dict(walk(decode(raw,max_bytes=SOURCE_BYTES,max_depth=32,max_nodes=30000)))
    result={}
    for cd,resource,source_id,expected in SOURCE_ROWS:
        base='/'+resource+'[1]'
        actual_id=values[base+'/id[1]'];amount=values[base+'/price[1]']
        if type(actual_id)is not int or actual_id!=source_id or cd!=(actual_id<<8)+10:
            raise ValueError('P04W_SHELL_ID_NATION_TYPE_CHANGED')
        if type(amount)is not int or not 0<=amount<=2**31-1:
            raise ValueError('P04W_SOURCE_PRICE_NOT_BOUNDED_INTEGER')
        gold=base+'/price[1]/gold[1]'in values
        price=(0,amount)if gold else(amount,0)
        if price!=expected:raise ValueError('P04W_SOURCE_PRICE_CHANGED')
        result[cd]=price
    return result

def add_shell_display_references(shop):
    """Only six pinned hidden reference rows; quantities come from inventory10.

    Trusted projection output only. No client value or mutable catalogue is a
    source of a price. A conflicting preexisting row refuses publication.
    """
    if type(shop)is not dict or type(shop.get('items'))is not dict:
        raise ValueError('P04W_SHOP_STRUCTURE')
    items=shop['items'];prices=items.get('itemPrices');hidden=items.get('notInShopItems')
    if type(prices)is not dict or type(hidden)is not list or len(prices)>8192 or len(hidden)>8192:
        raise ValueError('P04W_REFERENCE_CATALOGUE_BOUND')
    if any(type(cd)is not int or not 0<cd<=0xffffff for cd in prices):
        raise ValueError('P04W_REFERENCE_CD')
    if any(type(cd)is not int or not 0<cd<=0xffffff for cd in hidden)or len(set(hidden))!=len(hidden):
        raise ValueError('P04W_HIDDEN_REFERENCE_CD')
    result=deepcopy(shop);items=result['items'];prices=items['itemPrices'];hidden=items['notInShopItems']
    for cd,resource,source_id,reference in SOURCE_ROWS:
        if cd in prices:
            old=prices[cd]
            if type(old)not in(tuple,list)or len(old)!=2 or any(type(n)is not int for n in old)or tuple(old)!=reference:
                raise ValueError('P04W_CONFLICTING_SOURCE_PRICE')
        prices[cd]=reference
        if cd not in hidden:hidden.append(cd)
    return result
