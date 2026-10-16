"""Self-contained bounded original #717 PE proof for the full fire property.

No original code is executed. Numeric instructions/addresses are measured facts;
this audit does not depend on ignored historical JSON/disassembly exports.
"""
from pathlib import Path
import re
import struct
import capstone
import pefile
from p06t_shell_catalog import sha,require
from vehicle_physics_profile import no_links

EXE_SHA256="86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed"
INSTRUCTIONS=[
 (0x1683ec0,'push 0x1f85008'),(0x1683ec5,'push 0'),(0x1683ec7,'push 2'),
 (0x1683ec9,'push 0x19b1720'),(0x1684415,'mov dword ptr [0x1f85010], 0xd70fc0'),
 (0x1684429,'mov dword ptr [0x1f85018], 0xd71080'),
 (0xd729c9,'mov edx, ecx'),(0xd729cb,'mov ecx, dword ptr [edx + 0x14]'),
 (0xd729d1,'mov eax, dword ptr [edx + 0x10]'),(0xd729d4,'call eax'),
 (0xd71087,'sub eax, dword ptr [0x2305660]'),(0xd71099,'call dword ptr [edx + 0x30]'),
 (0x5c8a42,'call 0x5c2a00'),(0x5c2a0b,'call 0xdc96b0'),(0x5c2a12,'call 0xdc6e30'),
 (0xdc9719,'push dword ptr [eax + edi*4]'),(0xdc971c,'call 0xdc7e80'),
 (0xdc6e30,'mov ecx, dword ptr [ecx + 0x20]'),(0xdc6e35,'jmp dword ptr [eax + 0x24]'),
 (0xdecd97,'imul eax, dword ptr [esi + 0x18]'),
 (0xdecda2,'mov dword ptr [esi + 0x20], 0xffffffff'),(0xded1f0,'mov eax, dword ptr [ecx + 0x20]'),
 (0xee3486,'cmp byte ptr [esi + 1], 2'),(0xee3498,'call dword ptr [edx + 8]'),
 (0xee349b,'test eax, eax'),(0xee349d,'jns 0xee34ad'),(0xee349f,'neg eax'),
 (0xee34a1,'mov byte ptr [esi + 1], 1'),(0xee34a5,'mov dword ptr [esi + 4], eax'),
 (0xee34d0,'mov eax, dword ptr [ecx + 4]'),(0xee34d3,'inc eax'),
 (0xee369d,'movzx esi, byte ptr [ebx + 1]'),(0xee3535,'mov byte ptr [edx + 1], cl'),
 (0xed2544,'call 0xee3480'),(0xed2550,'call 0xed28c0'),
 (0xed2911,'call 0xee3660'),(0xed2924,'call 0xee34c0'),(0xed2929,'add edi, eax'),
 (0xed296b,'mov ebx, dword ptr [esi + 0x20]'),(0xed2986,'mov word ptr [esi + 8], di'),
 (0xed298a,'mov dword ptr [esi + 0xc], ebx'),
 (0xd70fcc,'sub eax, dword ptr [0x2305660]'),(0xd70fde,'call dword ptr [esi + 0x24]'),
 (0x5c86cb,'call 0x5c2940'),(0x5c2960,'call 0x6194b0'),(0x619528,'call 0x619ab0'),
 (0x619ae5,'call 0xdc96b0'),(0x619b09,'push 0'),(0x619b14,'call 0x6199c0'),
 (0x6199d9,'call dword ptr [eax + 0x20]'),(0xded156,'je 0xded1c0'),
 (0xded1c8,'call 0xdedc50'),(0xdedc90,'push 4'),(0xdedc97,'mov ebx, dword ptr [eax]')]


def audit(original):
    path=no_links(Path(original)/"WorldOfTanks.exe")
    require(path.is_file() and path.stat().st_size<=64*1024*1024,"original PE file bound")
    raw=path.read_bytes();require(sha(raw)==EXE_SHA256,"original PE SHA")
    pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
    require(pe.FILE_HEADER.Machine==0x14c and base==0x400000,"original x86 PE image")
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
    def read(va,count):
        require(base<=va and 0<count<=256,"PE read bound")
        offset=pe.get_offset_from_rva(va-base);value=raw[offset:offset+count]
        require(len(value)==count,"PE read truncation");return value
    def u32(va):return struct.unpack("<I",read(va,4))[0]
    pointers={0x1f85008:0x19b0ca4,0x19b0ca4+8:0xd729c0,0x17ca924+0x24:0x5c8650,0x17ca924+0x30:0x5c89f0,
        0x19b7824+0x20:0xded120,0x19b7824+0x24:0xded1f0,0x19b7384+0x24:0xded1f0,0x19b74dc+0x24:0xded1f0,0xee3768+4:0xee369d,0xee3648:0xee352d}
    for va,value in pointers.items():require(u32(va)==value,"original PE vtable/branch pin")
    checks=[]
    for va,expected in INSTRUCTIONS:
        instruction=next(cs.disasm(read(va,16),va),None)
        require(instruction is not None and instruction.mnemonic+" "+instruction.op_str==expected,"PE instruction differs: "+hex(va))
        checks.append({"va":hex(va),"hex":instruction.bytes.hex(),"instruction":expected})
    require(read(0x19b1720,15)==b"entityProperty\0","PE property registry name")
    counts={0x1f84c2c:0,0x1f84c1c:0};last={};registrations=[]
    for slot in range(0x16f1050,0x16f1284,4):
        va=u32(slot)
        if not 0x1683000<=va<0x1685000:continue
        pushes=[];interface=None;register=False;expand=False
        for instruction in cs.disasm(read(va,64),va):
            if instruction.mnemonic=="push" and re.fullmatch(r"(0x[0-9a-f]+|[0-9]+)",instruction.op_str):pushes.append(int(instruction.op_str,0))
            if instruction.mnemonic=="mov" and instruction.op_str.startswith("ecx, 0x"):
                candidate=int(instruction.op_str[5:],0)
                if candidate in counts:interface=candidate
            if instruction.mnemonic=="call" and instruction.op_str=="0xedf560":register=True
            if instruction.mnemonic=="call" and instruction.op_str=="0xedf620":expand=True
            if instruction.mnemonic=="ret":break
        if interface is None:continue
        entry={"initializer_slot":hex(slot),"initializer":hex(va),"interface":hex(interface)}
        if register:
            require(len(pushes)==4,"PE registry register arguments")
            name=read(pushes[3],128).split(b"\0",1)[0].decode("ascii")
            entry.update(event="register",id=counts[interface],kind=pushes[2],length=pushes[1],name=name)
            counts[interface]+=1;last[interface]=entry
        elif expand:
            require(len(pushes)==1 and pushes[0] in (1,2),"PE registry expand arguments")
            current=counts[interface];end=current+(254-current)//pushes[0]
            entry.update(event="expand",divisor=pushes[0],start=last[interface]["id"],end=end,name=last[interface]["name"]);counts[interface]=end+1
        else:continue
        registrations.append(entry)
    ranges={row["name"]:[row["start"],row["end"]]for row in registrations if row["event"]=="expand"}
    require(ranges["entityMethod"]==[59,157] and ranges["entityProperty"]==[158,254],"original PE method/property registry range")
    return {"schema":"p06t-fire-full-property-pe.v1","status":"PASS_STATIC_PE_ONLY","original_exe_sha256":EXE_SHA256,
        "instruction_assertions":checks,"pointer_assertions":{hex(k):hex(v)for k,v in pointers.items()},"registrations":registrations,
        "ranges":ranges,"sequence_variable_size":-1,"outer_length_bytes":1,"array_count_bytes":4,
        "original_execution":False,"native":"NOT_RUN"}
