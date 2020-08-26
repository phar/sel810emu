import sys
import threading
import select
import socket
import struct

baud_rate = 300

byte_time = 1 / (baud_rate * 9)
sys.path.append("sel810asm")
from rs227 import *

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

sock.connect("/tmp/SEL810_paper tape")
tape = RS227(sys.argv[1])
tapedata = tape.read_contents()
for w in tapedata:
	bb = struct.pack("BB", ((w & 0xff) >> 8), (w & 0xff))
	sock.send(bytes(bb[0]))
	time.sleep(byte_time)
	sock.send(bytes(bb[1]))
	time.sleep(byte_time)
print("sent %d words" % len(tapedata))
