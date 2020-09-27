import time
import sys
import threading, queue
import select
import socket
import struct
import json


class ControlPanelClient():
	def __init__(self,devicenode,updatecb):
		self._shutdown = False
		self.devicenode = devicenode
		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.sock.connect(self.devicenode)
		self.updatecb = updatecb
		self.thread = threading.Thread(target=self.packet_hub, args=(self.sock,))

	def start(self):
		self.thread.start()

	def stop(self):
		self.thread.join()
		
	def packet_hub(self,sock):
		pollerObject = select.poll()
		pollerObject.register(sock, select.POLLIN | select.POLLERR | select.POLLHUP)
				
		while self._shutdown == False:
#			try:
				fdVsEvent = pollerObject.poll(250)
				for descriptor, Event in fdVsEvent:
					if Event & select.POLLIN:
						a = self.recv_packet(sock)
						self.updatecb(a)
					
					if Event & (select.POLLERR | select.POLLHUP):
						self._shutdown = True
						print("here")
				print("dfs",self._shutdown)
		print("here2")

#			except:
#				print("here")
#				self._shutdown = True
			
	def send_packet(self,sock,packet):
		try:
			pp = json.dumps(packet).encode("utf-8")
			sock.send(struct.pack(">H",len(pp)))
			sock.send(pp)
		except:
			print("somehting went wrong with the emulator connection")
			self._shutdown = True
			
	def recv_packet(self,sock):
		try:
			buff = b""
			while len(buff) < struct.calcsize(">H"):
				buff += sock.recv( struct.calcsize(">H") - len(buff))
			(s,) = struct.unpack(">H",buff)
			buff = b""
			while len(buff) < s:
				buff += sock.recv(s - len(buff))
			return json.loads(buff)
		except:
			print("somehting went wrong with the emulator connection")
			self._shutdown = True
			
	def shutdown(self):
		self._shutdown = True
		self.thread.join()

	def step(self):
		self.send_packet(self.sock,("s",1))

	def halt(self):
		self.send_packet(self.sock,("h+",None))

	def set_pc(self, pc):
		self.send_packet(self.sock,("u",{"Program Counter":pc}))

	def update_panel(self,panelstruct):
		self.send_packet(self.sock,("u",panelstruct))
	
	def load_file(self,addr,filename):
		self.send_packet(self.sock,("l",(addr,filename)))
		

if __name__ == '__main__':


	def showuypdate(arg):
#		print(arg)
		pass

	a = ControlPanelClient("/tmp/SEL810_control_panel",showuypdate)
	a.start()

	while(a._shutdown == False):
		time.sleep(1)
		print("dfpp",a._shutdown)
#		a.step()
	print("booos")
	a.shutdown()
