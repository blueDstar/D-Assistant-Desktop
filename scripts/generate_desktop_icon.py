"""Code-drawn icon matching the monochrome robot; PNG/ICO using only stdlib."""
import struct
import zlib
from pathlib import Path

def rounded(x,y,box,r):
    left,top,right,bottom=box
    if not(left<=x<right and top<=y<bottom):return False
    cx=max(left+r,min(x,right-r));cy=max(top+r,min(y,bottom-r))
    return (x-cx)**2+(y-cy)**2<=r*r

def build():
    rows=[]
    for y in range(256):
        row=bytearray([0])
        for x in range(256):
            color=(0,0,0,0)
            if rounded(x,y,(20,28,236,224),55):color=(48,48,48,255)
            if rounded(x,y,(26,34,230,218),49):color=(243,240,233,255)
            if rounded(x,y,(40,53,216,185),38):color=(20,20,20,255)
            if any(rounded(x,y,box,13) for box in [(65,85,91,135),(165,85,191,135)]):color=(243,240,233,255)
            if 111<=x<146 and 152<=y<156:color=(185,183,178,255)
            row.extend(color)
        rows.append(row)
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',256,256,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
    folder=Path(__file__).resolve().parents[1]/'desktop'
    (folder/'icon.png').write_bytes(png)
    (folder/'icon.ico').write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',0,0,0,0,1,32,len(png),22)+png)

if __name__=='__main__':build()
