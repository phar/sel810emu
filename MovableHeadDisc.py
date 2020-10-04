from SELDeviceDriver import *
import socket
import os
import sys

#1536000, 16-bit words   3072000bytes

#The head can be moved to any of 100 tracks. Each track contains 16 sectors.

#Each sector will store 96 words, thus each track of a recording surface will store 1,536 words and an entire recording surface will store 153,600 words.

#16 sectors per track

#The Disc Control Unit accepts a total of five com- mands from the computer which define all permiss- able disc operations. These commands are:
"""
Data Seek Mode:
	a) Seek Track Zero
	b) Seek N Tracks Forward
	c) Seek N Tracks Reverse
	
Disc Data Mode:
	d) Write Sector I, Head J
	e) Read Sector I, Head J
"""

#Considering a disc pack as 100 cylinders, 15,360 words can be written/read in each cylinder without moving the head assembly.

#The disc rotates at 2400 RPM. This gives a maxi- mum latency time of 25 milliseconds. Figure 6-6 shows the time required to move the head "n" posi- tions. The data transfer rate of the disc system is 78.125 KHz, or one word every 12.8 microseconds.

class MovableHeadDiscEUH(ExternalUnitHandler):
	def __init__(self, devnode, discfile):
		super().__init__(devnode)
		self.discfile = discfile
		#fixme super
		self.ceuevents = {	"btc_init":					(0x8000,False,None),
						"interrupt_connect":		(0x4000,False,None),
						"seek error":				(0x2000,True,1),
						"seek complete":			(0x1000,True,2),
						"seek_or_data":				(0x0080,False,None)}

		self.ceuevents_seek = {	"btc_init":					(0x8000,False,None),
							"interrupt_connect":		(0x4000,False,None),
							"seek_error":				(0x2000,True,1),
							"seek_complete":			(0x1000,True,2),
							"tracks":					(0x03f0,False,None),
							"current word address in":	(0x0400,False,None),
							"forward":					(0x0002,False,None),
							"reverse":					(0x0001,False,None)}
								
		#The Systems Engineering Laboratories printer logic is designed to accept simultaneous commands as long as they are not in mechanical or logical con- flict.
		self.ceuevents_data = {	"btc_init":					(0x8000,False,None),
							"interrupt_connect":		(0x4000,False,None),
							"seek_error":				(0x2000,True,1),
							"seek_complete":			(0x1000,True,2),
							"sector":					(0x0f00,False,None),
							"head":						(0x00f0,False,None),
							"current word address in":	(0x0400,False,None),
							"write":					(0x0002,False,None),
							"read":						(0x0001,False,None)}
							
		self.teuevents = {	"skip_if_seek_complete":		(0x0800),
						"skip_if_no_seek_error":		(0x0400),
						"skip_on_begining_of_disc":		(0x0200),
						"skip_on_begining_of_sector":	(0x0100),
						"skip_if_pack_online":			(0x0080),
						"skip_if_no_read_overflow":		(0x0040),
						"skip_if_no_write_overflow":	(0x0020),
						"skip_if_no_checksum_error":	(0x0010),
						"skip_if_no_file_unsafe":		(0x0008),
						"skip_if_dcu_ready":			(0x0004),
						"skip_if_not_busy":				(0x0002)}

		
		self.mhd = MovableHeadDisc(self, self.discfile)

	def update_ceu(self,ceuval):
	#The CEU instruction is used to command the DCU. There are two tyPes of CEU second word formats, DISC SEEK and DISC DATA.
		if (ceuval & selc.ceuevents["seek_or_data"]):
			#seek
			if ((ceuval & selc.ceuevents_seek["forward"]) and not (ceuval & selc.ceuevents_seek["reverse"])):
				self.mhd.seek_forward((ceuval & selc.ceuevents_seek["tracks"]) >> 4)
				
			if ((ceuval & selc.ceuevents_seek["reverse"]) and not (ceuval & selc.ceuevents_seek["forward"])):
				self.mhd.seek_reverse((ceuval & selc.ceuevents_seek["tracks"]) >> 4)
				
			if ((ceuval & selc.ceuevents_seek["reverse"]) and (ceuval & selc.ceuevents_seek["forward"])):
				self.ceuval |= selc.ceuevents_seek["seek_error"]
		else:
			#data
			if ((ceuval & selc.ceuevents_data["read"]) and not (ceuval & selc.ceuevents_data["write"])):
				self.mhd.read_sector((ceuval & selc.ceuevents_data["sector"]) >> 8,(ceuval & selc.ceuevents_data["head"]) >> 4)
				
			if ((ceuval & selc.ceuevents_seek["write"]) and not (ceuval & selc.ceuevents_seek["read"])):
				self.mhd.write_sector((ceuval & selc.ceuevents_data["sector"]) >> 8,(ceuval & selc.ceuevents_data["head"]) >> 4)

			if ((ceuval & selc.ceuevents_seek["read"]) and (ceuval & selc.ceuevents_seek["write"])):
				self.ceuval |= selc.ceuevents_seek["seek_error"]

	def update_teu(self,teuval):
		return True

	def update_time(self,ticks):
		pass
		
		
class MovableHeadDisc():
	def __init__(self,euh, filename):
		self.filename = filename
		self.euh = euh
		self.file = open(self.filename,"wb+")
		self.curr_track = 0
		self.max_track = 100
		self.sector = 0
		self.head=0
		
	def step_time(self):
		self.sector += 1
		if self.sector > 15:
			self.sector = 0
		
	def seek_zero(self):
		self.curr_track = 0

	def seek_forward(self, dist):
		self.curr_track += dist
		if self.curr_track > self.max_track:
			self.curr_track = self.max_track
			self.euh.ceuval |= selc.ceuevents_seek["seek_error"]
			self.euh.teuval |= selc.ceuevents_seek["skip_if_seek_error"]
		else:
			self.euh.ceuval |= selc.ceuevents_seek["seek_complete"]
			self.euh.teuval |= selc.ceuevents_seek["skip_if_seek_complete"]

	def seek_reverse(self, dist):
		self.curr_track -= dist
		if self.curr_track < 0:
			self.curr_track = 0
			self.euh.ceuval |= selc.ceuevents_seek["seek_error"]
		else:
			self.euh.ceuval |= selc.ceuevents_seek["seek_complete"]
			self.euh.teuval |= selc.ceuevents_seek["skip_if_seek_complete"]

	def write_sector(self, ival, jval):
		pass
		
	def read_sector(self, ival, jval):
		pass



class MovableHeadDiscDriver():
	def __init__(self, devicenode, storagefile="default.mhd"):
		self.done = False
		self.storagefile = storagefile
		self.devnode = devicenode
		self.peripheral = MovableHeadDiscEUH(self.devnode, self.storagefile)


	def start(self):
		self.peripheral.start()
		self.done = False

	def stop(self):
		self.peripheral.stop()


if __name__ == '__main__':

	a = MovableHeadDiscDriver("/tmp/SEL810_movable_head_disc")
	a.start()
	while(not a.done):
		time.sleep(5)
	a.stop()
