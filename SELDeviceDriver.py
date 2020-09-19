import time
import sys
import threading, queue
import select
import socket
import struct
import json


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
		self.thread.start()

	def socket_handler(self,arg):
		pollerObject = select.poll()
		pollerObject.register(self.sock, select.POLLIN | select.POLLERR | select.POLLHUP)

		while(self.connected):
			if self.wq.qsize():
				(t,v) = self.wq.get()
				self.send_packet((t,v))
			fdVsEvent = pollerObject.poll(1)

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

	def handle_configure(self, val):
		print("ceu command!")
		ret = 0x11
		self.wq.put(("c",ret))

	def handle_test(self, val):
		print("teu command!")
		ret = 0x22
		self.wq.put(("t",ret))

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


if __name__ == '__main__':
	e = ExternalUnitHandler("/tmp/SEL810_asr33")

	HOST = "0.0.0.0"
	PORT = 9999

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((HOST, PORT))
	s.listen()
	conn, addr = s.accept()

	pollerrObject = select.poll()
	while(e.connected):

		pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
		if e.pollread():
			conn.send(e.read() ^ 0x80)

		for descriptor, Event in fdVsEvent:
			if Event & (select.POLLERR | select.POLLHUP):
				pass
				
			if Event & select.POLLIN:
				e.write(bytes(int(conn.recv(1)) | 0x80))
