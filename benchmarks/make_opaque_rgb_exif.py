"""Acrescenta EXIF6 a uma fixture RGB sem recodificar seus pixels PNG."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autorip.imaging import Image


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cases=json.loads((args.fixtures/'cases.json').read_text())
    base=next(c for c in cases if c['name']=='rgb_icc_90mp')
    source=Path(base['path'])
    assert sha(source)==base['source_sha256']
    args.output.mkdir(parents=True,exist_ok=False)
    destination=args.output/'rgb_exif_icc_90mp.png'
    exif=Image.Exif();exif[274]=6
    payload=exif.tobytes()[6:]
    inserted=False
    with source.open('rb') as incoming,destination.open('wb') as outgoing:
        signature=incoming.read(8);assert signature==b'\x89PNG\r\n\x1a\n'
        outgoing.write(signature)
        while True:
            header=incoming.read(8)
            if not header:break
            assert len(header)==8
            length,kind=struct.unpack('>I4s',header)
            data=incoming.read(length+4);assert len(data)==length+4
            if kind==b'eXIf':continue
            if kind==b'IDAT' and not inserted:
                outgoing.write(struct.pack('>I4s',len(payload),b'eXIf'))
                outgoing.write(payload)
                outgoing.write(struct.pack('>I',zlib.crc32(b'eXIf'+payload)&0xffffffff))
                inserted=True
            outgoing.write(header);outgoing.write(data)
    assert inserted and sha(source)==base['source_sha256']
    with Image.open(destination) as image:
        assert image.mode=='RGB' and image.getexif()[274]==6
    cases.append(dict(base,name='rgb_exif_icc_90mp',path=str(destination.resolve()),
                      source_bytes=destination.stat().st_size,source_sha256=sha(destination),phases=['job']))
    (args.output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    print(json.dumps(cases[-1]))


if __name__=='__main__':main()
