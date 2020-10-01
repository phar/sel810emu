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
	def __init__(self,cpu, name,btc=None, iogroup=0,chardev=False):
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
		self.devq = queue.Queue()
		self.ceuresp = threading.Event()
		self.teuresp = threading.Event()
		self.rdyresp = threading.Event()
		self.wresp = threading.Event()
		self.rresp = threading.Event()
		self.ceu = 0
		self.teu = 0
		self.w = 0
		self.r = 0
		self.ready = 0
		self.btc = False
		self.iodelay = 1
		self.iogroup=iogroup
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
				sfdVsEvent = servpoller.poll(250)
				if len(sfdVsEvent):
					descriptor, sEvent = sfdVsEvent[0]
					if sEvent & select.POLLIN:
						self.devsock, client_address = self.sock.accept()
						self.connected = True
						pollerrObject = select.poll()
						pollerrObject.register(self.devsock, select.POLLIN | select.POLLERR | select.POLLHUP)
						while(self.connected == True and self.cpu._shutdown == False and self._shutdown == False):
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
										if t == '*':#time response
											pass
										elif t == 't':
											self.teu = v
											self.teuresp.set()
										elif t == 'w':
											self.w = v
											self.wresp.set()
										elif t == 'r':
											self.r = v
											self.rresp.set()
										elif t == '?':
											self.ready = v
											self.rdyresp.set()
										elif t == 'i': #interrupt
											if ((self.cpu.registers["Interrupt"].read() &  0x7000) >> 8) == self.iogroup:
												self.cpu.fire_priority_interrupt(self.iogroup, v)


								if self.devq.qsize():
									try:
										(t,v) = self.devq.get()
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
		if self.connected:
			self.cpu.latch["iowait"] = True
			while not event.isSet() and self.cpu.latch["io_hold_release"] == False: #probably where i need to clear the wait
				event.wait(.1)  #this value ay need tweaking
				if not event.isSet(): #a bit more forgiving on timing if it happens on the first timeout
					self.cpu._increment_cycle_count(self.iodelay)
			self.cpu.latch["iowait"] = False
			return True
		else:
			return False

	def unit_command(self,command):
		self.devq.put(("c",command))
		self.ceuresp.clear()
		self._wait_on_event(self.ceuresp)
		if (self.ceu & 0x8000) and (self.btc == True):
			self.btc_cwa = self.cpu.ram[0o1060 + (self.btc * 2)].read()
			self.cpu.cpu_increment_cycle_count()
			self.btc_wc = self.cpu.ram[0o1060 + (self.btc * 2) + 1].read()
			self.cpu.cpu_increment_cycle_count()
		return self.ceu
						
	def unit_test(self,command):
		self.devq.put(("t",command))
		self.teuresp.clear()
		self._wait_on_event(self.teuresp)
		return self.teu


	def unit_tick(self,data):
		if self.connected:
			self.devq.put(("*",data))
		
	def unit_write(self,data):
		self.devq.put(("w",data))
		self.wresp.clear()
		self._wait_on_event(self.wresp)
		return self.w

	def unit_ready(self,qry):
		self.devq.put(("?",qry))
		self.rdyresp.clear()
		self.rdyresp.wait(.1)  #this value ay need tweaking
		if not self.rdyresp.isSet(): #if we're not connected, we're not ready but we should wait to se if the device has a character either
			self.ready = False
		return self.ready

	def unit_read(self, wait=False):
		self.rresp.clear()
		self.devq.put(("r",True))
		self._wait_on_event(self.rresp)
		return self.r
				
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
		self.rq = queue.Queue()
		self.devq = queue.Queue()
		self.wq = queue.Queue()
		self.ceu = 0

	def start(self):
		self.thread = threading.Thread(target=self.socket_handler, args=(0,))
		self.thread.start()

	def stop(self):
		self.connected = False
		self.thread.join()

	def socket_handler(self,arg):
		pollerObject = select.poll()
		pollerObject.register(self.sock, select.POLLIN | select.POLLERR | select.POLLHUP)

		while(self.connected):
			if self.devq.qsize():
				self.send_packet(self.devq.get())
				
			fdVsEvent = pollerObject.poll(10)

			for descriptor, Event in fdVsEvent:
				if Event & (select.POLLERR | select.POLLHUP):
					print("the emulator connection failed (socket)")
					self.connected = False
					self.sock.close()
					break

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
					elif t == "*":
						self.handle_time(v)
							
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
		if (self.ceu & INTERRUPT_CONNECT) and (event,interrupable,level) in self.ceuevents:
			if (self.ceu & selc.ceuevents[event]) and  interrupable:
				self.devq.put(("i", level))

	def update_ceu(self,ceu):
		'''left to the driver to handle'''
		pass
		
	def update_teu(self,ceu):
		'''left to the driver to handle'''
		return True
		
	def update_time(self,ceu):
		'''left to the driver to handle'''
		pass

	def handle_time(self, val):
		self.update_time(val)

	def handle_configure(self, val):
		self.ceu = val
		self.update_ceu(self.ceu)
		self.devq.put(("c",self.ceu))

	def handle_test(self, val):
		ret = True
		if self.update_teu(val) == True:
			self.devq.put(("t",True))
		else:
			self.devq.put(("t",False))

	
#----- these are from the emulators perspective
	def handle_write(self, val):
		self.rq.put(val)
		self.devq.put(("w", True))

	def handle_read(self, val):
		self.devq.put(("r",self.wq.get()))

	def handle_ready(self, val):
		if val == "r":
			self.devq.put(("?",self.wq.qsize() > 0))

		elif val in  ["w","c","t"]:
			if self.connected:
				self.devq.put(("?",True))
			else:
				self.devq.put(("?",False))
		self.devq.put(("?",True)) #catch all
		
#----these are from the client perspective
	def write(self,d):
		self.wq.put(d)
		
	def read(self,plen=1):
		if self.chardev:
			t = self.rq.get()
			return ((t &  0xff00) >> 8)
		else:
			return t

	def pollwrite(self):
		if self.wq.qsize(): 
			return self.wq.qsize()
		else:
			return False

	def pollread(self):
		if self.rq.qsize():
			return self.rq.qsize()
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
