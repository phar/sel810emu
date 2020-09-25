import re
import os
import struct

from math import floor, log10

def fexp(f):
    return int(floor(log10(abs(f)))) if f != 0 else 0

def fman(f):
    return f/10**fexp(f)
    

def dec2twoscmplment(val):
	if val < 0:
	#	val = ((~abs(v) + 1)  & 0xffff)#its a 16 bit value so to fix the sign bit
		val = val + 2**16
	return val


def twoscmplment2dec(val):
	if val & 0x8000:
		val = val - (2**16)
	return val
	

def parity_calc(i):
	i = i - ((i >> 1) & 0x55555555)
	i = (i & 0x33333333) + ((i >> 2) & 0x33333333)
	i = (((i + (i >> 4)) & 0x0F0F0F0F) * 0x01010101) >> 24
	return int(i % 2)
	

def loadProgramBin(filename):
	size = os.path.getsize(filename)
	f = open(filename,"rb")
	b = f.read(size)
	binfile = struct.unpack(">%dH" % (size/2), b)
	return binfile


def storeProgramBin(filename,data):
	f = open(filename,"wb")
	size = len(data)
	binfile = struct.pack(">%dH" % size, *data)
	f.write(binfile)
	f.close()




