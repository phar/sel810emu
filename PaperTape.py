from SELDeviceDriver import *
import socket
import os
import sys


class PaperTapeReaderPunch(ExternalUnitHandler):
	ceuevents = {
					"btc_init":			(0x8000,False,None),
					"interrupt_connect":(0x4000,False,None),
					"in":				(0x2000,True,1),
					"out":				(0x1000,True,2),
					"Punch Pwr On":		(0x0800,False,None),
					"Punch Pwr Off":	(0x0400,False,None),
					"Reader Enable":	(0x0200,False,None),
					"Reader Disable":	(0x0100,False,None)}

	def update_ceu(self,ceuval):
		pass

	def update_teu(self,teuval):
		return True


class PaperTapeDriver():
	def __init__(self, devicenode, input_tape=None,output_tape=None):
		self.thread = threading.Thread(target=self.paper_tape_thread, args=(devicenode,input_tape))
		self.done = False
		self.ifile = None
		self.ofile = None
		self.input_tape = input_tape
		self.output_tape = output_tape

		if self.input_tape:
			self.ifilesize = os.path.getsize(self.input_tape)
			self.ifile = open(self.input_tape,"rb")

		if self.output_tape:
			self.ofile = open(self.output_tape,"wb")

		self.bytesdone = 0
		self.peripheral = PaperTapeReaderPunch(devicenode,chardev=True)


	def start(self):
		self.peripheral.start()
		self.done = False
		self.thread.start()

	def stop(self):
		self.peripheral.stop()
		self.thread.join()
		self.ifile.close()
		self.ofile.close()

	def paper_tape_thread(self, socketname, filename):
		print("started paper tape driver with file %s" % filename)

		while self.peripheral.connected:
			if not self.peripheral.pollwrite(): #throttle the data so we dont just dump the file into the fifo
				if self.input_tape:
					self.peripheral.event("in")
					self.peripheral.write(ord(self.ifile.read(1)))
					self.bytesdone += 1
					if self.bytesdone == self.ifilesize: #exit when the last byte is sent
						self.done = True
						
			if self.peripheral.pollread(): #it wrote data to us
				if self.output_tape:
					self.peripheral.event("out")
					self.ofile.write(e.read())
								
								

if __name__ == '__main__':
	try:
		(infile,outfile) = sys.argv[1:3]
	except:
		print("papertape <intape> <outtape>")
		sys.exit()
		
	a = PaperTapeDriver("/tmp/SEL810_paper_tape",infile,outfile)
	a.start()
	while(not a.done):
		print("%.2f percent complete" % ((a.bytesdone/ a.ifilesize) * 100))
		time.sleep(5)
		
	self.peripheral.connected = False
	a.stop()
