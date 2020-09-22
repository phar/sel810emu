import time
import sys
import threading, queue
import select
import socket
import struct
import json
import os

INTERRUPT_CONNECT = 0x4000


class SELBTCDriver():
	def __init__(self, cpu, baseaddr):
		self.current_word_address;
		self.word_count
		self.baseaddr = baseaddr
		self.cpu = cpu

	def update_from_memory(self):
		self.current_word_address = self.cpu.ram[self.baseaddr].read()
		self.word_count = self.cell0[self.baseaddr+1].read()

	def transfer(self):
		pass
		
		
class ExternalUnitNotConnected(Exception):
	"""Raised when the external unit is not connected and wait flag is not asserted"""
	pass


class ExternalUnit():
	def __init__(self,cpu, name,chardev=False):
		self.cpu = cpu
		self.name = name
		self.read_buffer = []
		self.write_buffer = []
		self.connected = False
		self.connected_host = None
		self.connected_port = None
		self._shutdown = False
		self.chardev = chardev
		self.socketfn = os.path.join("/tmp","SEL810_" + self.name.replace(" ","_"))
		self.wq = queue.Queue()
		self.rq = queue.Queue()
		self.ceuresp = threading.Event()
		self.teuresp = threading.Event()
		self.rdyresp = threading.Event()
		self.wresp = threading.Event()
		self.rresp = threading.Event()
		self.ceu = 0
		self.teu = 0
		self.w = 0
		self.ready = 0
		self.iodelay = 1
		try:
			os.unlink(self.socketfn)
		except OSError:
			if os.path.exists(self.socketfn):
				raise
				
		self.devsock = None
		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.sock.bind(self.socketfn)
		self.sock.listen(1)

		self.thread = threading.Thread(target=self.socket_handler, args=(0,))
		self.thread.start()
		print("started external unit %s on %s" % (self.name,self.socketfn))
		
	def socket_handler(self,arg):
		servpoller = select.poll()
		servpoller.register(self.sock, select.POLLIN )
		while(self.cpu._shutdown == False and self._shutdown == False):
				sfdVsEvent = servpoller.poll(1)
				if len(sfdVsEvent):
					descriptor, sEvent = sfdVsEvent[0]
					if sEvent & select.POLLIN:
						self.devsock, client_address = self.sock.accept()
						self.connected = True
						pollerrObject = select.poll()
						pollerrObject.register(self.devsock, select.POLLIN | select.POLLERR | select.POLLHUP)
						while(self.connected == True and self._shutdown == False and self._shutdown == False):
								fdVsEvent = pollerrObject.poll(10)
								for descriptor, Event in fdVsEvent:
									if Event & (select.POLLERR | select.POLLHUP):
											self.connected = False
											self.devsock.close()
											break
										
									if Event & select.POLLIN:
										try:
											(t,v) = self.recv_packet()
										except:
											self.connected = False
											self.devsock.close()
										if t == 'c':
											self.ceu = v
											self.ceuresp.set()
										elif t == 't':
											self.teu = v
											self.teuresp.set()
										elif t == 'w':
											self.w = v
											self.wresp.set()
										elif t == 'r':
											self.rresp.set()
										elif t == '?':
											self.rdyresp.set()
										elif t == 'i': #interrupt
											pass

								if self.wq.qsize():
									try:
										(t,v) = self.wq.get()
										self.send_packet((t,v))
									except:
										self.connected = False
										self.devsock.close()

		self.connected = False

	def send_packet(self,packet):
		pp = json.dumps(packet)
		self.devsock.send(struct.pack("B",len(pp)))
		self.devsock.send(bytes(pp,"utf-8"))
		
	def recv_packet(self):
		buff = b""
		while len(buff) < struct.calcsize("B"):
			buff += self.devsock.recv( struct.calcsize("B") - len(buff))
			
		(s,) = struct.unpack("B",buff)

		buff = b""
		while len(buff) < s:
			buff += self.devsock.recv(s - len(buff))
		return json.loads(buff)
		
	def _wait_on_event(self,event):
		while not event.isSet():
			event.wait(.1)  #this value ay need tweaking
			if not event.isSet(): #a bit more forgiving on timing if it happens on the first timeout
				self._increment_cycle_count(self.iodelay)

	def unit_command(self,command):
		self.cpu.IOwait_flag = True
		self.wq.put(("c",command))
		self._wait_on_event(self.ceuresp)
		self.cpu.IOwait_flag = False
		return self.ceu
						
	def unit_test(self,command):
		self.cpu.IOwait_flag = True
		self.wq.put(("t",command))
		self._wait_on_event(self.teuresp)
		self.cpu.IOwait_flag = False
		return self.teu

	def unit_write(self,data):
		self.cpu.IOwait_flag = True
		self.wq.put(("w",data))
		self._wait_on_event(self.wresp)
		self.cpu.IOwait_flag = False

	def unit_ready(self,qry):
		self.cpu.IOwait_flag = True
		self.wq.put(("?",qry))
		self._wait_on_event(self.rdyresp)

		self.cpu.IOwait_flag = False
		return self.ready

	def unit_read(self, wait=False):
		self.cpu.IOwait_flag = True
		self.wq.put(("r",True))
		self._wait_on_event(self.rresp)
		self.cpu.IOwait_flag = False
		return self.w
				
	def _teardown(self):
		print("%s external unit shutting down" % self.name)
		self._shutdown = True
		self.thread.join()
		
		
		

class ExternalUnitHandler():
	def __init__(self, devicenode, chardev=False):
		self.devicenode = devicenode
		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.sock.connect(self.devicenode)
		self.connected = True
		self.chardev = chardev
		self.thread = threading.Thread(target=self.socket_handler, args=(0,))
		self.rq = queue.Queue()
		self.wq = queue.Queue()
		self.ceu = 0
#		self.ceuevents = {} #drivers must overide this
		self.thread.start()

	def socket_handler(self,arg):
		pollerObject = select.poll()
		pollerObject.register(self.sock, select.POLLIN | select.POLLERR | select.POLLHUP)

		while(self.connected):
			if self.wq.qsize():
				(t,v) = self.wq.get()
				self.send_packet((t,v))
			fdVsEvent = pollerObject.poll(10)

			for descriptor, Event in fdVsEvent:
				if Event & select.POLLIN:
					(t,v) = self.recv_packet()
					if t == "c":
						self.handle_configure(v)
					elif t == "t":
						self.handle_test(v)
					elif t == "w":
						self.handle_write(v)
					elif t == "r":
						self.handle_read(v)
					elif t == "?":
						self.handle_ready(v)
						
				if Event & (select.POLLERR | select.POLLHUP):
					print("the emulator connection failed (socket)")
					self.connected = False
					self.sock.close()
					break
							
	def send_packet(self,packet):
		pp = json.dumps(packet).encode("utf-8")
		self.sock.send(struct.pack("B",len(pp)))
		self.sock.send(pp)
		
	def recv_packet(self):
		buff = b""
		while len(buff) < struct.calcsize("B"):
			buff += self.sock.recv( struct.calcsize("B") - len(buff))
		(s,) = struct.unpack("B",buff)
		buff = b""
		while len(buff) < s:
			buff += self.sock.recv(s - len(buff))
		return json.loads(buff)

	def event(self,event):
		if (self.ceu & INTERRUPT_CONNECT) and event in self.ceuevents:
			if self.ceu & selc.ceuevents[event]:
				self.wq.put(("i", self.ceu & self.ceuevents[event]))

	def update_ceu(self,ceu):
		'''left to the driver to handle'''
		pass
		
	def update_teu(self,ceu):
		'''left to the driver to handle'''
		return True
		
	def handle_configure(self, val):
		self.ceu = val
		self.update_ceu(self.ceu)
		self.wq.put(("c",self.ceu))

	def handle_test(self, val):
		ret = True
		if self.update_teu(val) == True:
			self.wq.put(("t",True))
		else:
			self.wq.put(("t",False))

	
#----- these are from the emulators perspective
	def handle_write(self, val):
		self.rq.put(val)
		self.wq.put(("w", True))

	def handle_read(self, val):
		self.wq.put(("r",self.rq.get()))

	def handle_ready(self, val):
		if val == "r":
			self.wq.put(("?",self.rq.qsize() > 0))
		elif val in  ["w","c","t"]:
			if self.connected:
				self.wq.put(("?",True))
			else:
				self.wq.put(("?",False))
				
#----these are from the client perspective
	def write(self,d):
		self.wq.put(("w", d))
		
	def read(self,plen=1):
		if self.chardev:
			t = self.rq.get()
			return ((t &  0xff00) >> 8)
		else:
			return self.rq.get()

	def pollread(self):
		if self.rq.qsize():
			return True
		else:
			return False


#if __name__ == '__main__':
#	e = ExternalUnitHandler("/tmp/SEL810_asr33")
#
#	HOST = "0.0.0.0"
#	PORT = 9999
#
#	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#	s.bind((HOST, PORT))
#	s.listen()
#	conn, addr = s.accept()
#
#	pollerrObject = select.poll()
#	while(e.connected):
#
#		pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
#		if e.pollread():
#			conn.send(e.read() ^ 0x80)
#
#		for descriptor, Event in fdVsEvent:
#			if Event & (select.POLLERR | select.POLLHUP):
#				pass
#
#			if Event & select.POLLIN:
#				e.write(bytes(int(conn.recv(1)) | 0x80))
