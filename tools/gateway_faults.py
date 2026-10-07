"""Explicit loopback packet delivery controls; received bytes are never fabricated."""
import struct
from cryptography.hazmat.primitives import serialization
from verify_redirect_capture import login_plaintext
from verify_baseapp_capture import packet_clear

class Faults:
    def __init__(self, mode, private_path):
        self.mode=mode
        self.private=serialization.load_pem_private_key(private_path.read_bytes(),None)
        self.key=None;self.first=None;self.used=False

    def copies(self, direction, data, elapsed):
        if direction=='client_to_server':
            plain=login_plaintext(data,self.private);pos=1
            for _ in range(2):pos+=1+plain[pos]
            length=plain[pos];self.key=plain[pos+1:pos+1+length]
            if len(self.key)!=16:raise ValueError('fault controller key size')
        if not direction.startswith('base_') or len(data)%8 or self.key is None:return 1
        clear=packet_clear(data,self.key)
        if direction=='base_client_to_server' and len(clear)==16 and clear[:2]==b'\x58\x04' and self.first is None:
            self.first=elapsed
            if self.mode=='duplicate-client-first':self.used=True;return 2
        if self.mode=='blackhole' and self.first is not None and elapsed-self.first>=2:
            return 0
        if self.used:return 1
        if self.mode=='drop-server-sync' and direction=='base_server_to_client' and clear[:4]==b'\x58\x04\x13\x4d' and struct.unpack_from('<I',clear,len(clear)-8)[0]==2:
            self.used=True;return 0
        if self.mode=='duplicate-client-sync' and direction=='base_client_to_server' and clear[:3]==b'\x58\x04\x01' and clear[7:10]==b'\x8e\x14\x00':
            self.used=True;return 2
        # Same measured seq0/ACK1 envelope; an Account creation may carry a body.
        if self.mode=='drop-server-first' and direction=='base_server_to_client' and 10<=len(clear)<=522 and clear[:2]==b'\x58\x04' and clear[-8:]==bytes.fromhex('0000000001000000'):
            self.used=True;return 0
        if self.mode=='drop-client-ack' and direction=='base_client_to_server' and clear[:2] in (b'\x48\x04',b'\x4c\x04') and struct.unpack_from('<I',clear,len(clear)-4)[0]>0:
            self.used=True;return 0
        return 1
