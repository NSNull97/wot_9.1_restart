"""Non-blocking local stand coordination for launcher and offline scene update."""
import msvcrt,os,stat
from tools.content0_s5a_stand import no_link
class StandLock:
    def __init__(self,stand):self.root=stand;self.path=stand/'.s5a-operation.lock';self.handle=None
    def __enter__(self):
        no_link(self.path,self.root)
        try:self.handle=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);created=True
        except FileExistsError:self.handle=os.open(self.path,os.O_RDWR);created=False
        try:
            meta=os.fstat(self.handle)
            if not stat.S_ISREG(meta.st_mode) or meta.st_nlink!=1:raise ValueError('unsafe stand lock')
            if created:os.write(self.handle,b'0')
            elif meta.st_size!=1:raise ValueError('invalid stand lock')
            os.lseek(self.handle,0,os.SEEK_SET);msvcrt.locking(self.handle,msvcrt.LK_NBLCK,1)
        except BaseException:
            os.close(self.handle);self.handle=None;raise
        return self
    def __exit__(self,*_):
        if self.handle is not None:
            os.lseek(self.handle,0,os.SEEK_SET);msvcrt.locking(self.handle,msvcrt.LK_UNLCK,1);os.close(self.handle);self.handle=None
