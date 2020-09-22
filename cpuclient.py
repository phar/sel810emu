import time
import sys
import threading, queue
import select
import socket
import struct
import json


class ControlPanelClient():
	def __init__(self,devicenode,updatecb):
		self.shutdown = False
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
		while self.shutdown == False:
			a = self.recv_packet(sock)
			self.updatecb(a)
			
	def send_packet(self,sock,packet):
		pp = json.dumps(packet).encode("utf-8")
		sock.send(struct.pack(">H",len(pp)))
		sock.send(pp)
		
	def recv_packet(self,sock):
		buff = b""
		while len(buff) < struct.calcsize(">H"):
			buff += sock.recv( struct.calcsize(">H") - len(buff))
		(s,) = struct.unpack(">H",buff)
		buff = b""
		while len(buff) < s:
			buff += sock.recv(s - len(buff))
		return json.loads(buff)

	def step(self):
		self.send_packet(self.sock,("s",1))

	def halt(self):
		self.send_packet(self.sock,("h+",None))

	def set_pc(self, pc):
		self.send_packet.put(self.sock,("u",{"Program Counter":pc}))

	def update_panel(self,panelstruct):
		self.send_packet.put(self.sock,("u",panelstruct))
		

if __name__ == '__main__':


	def showuypdate(arg):
		print(arg)

	a = ControlPanelClient("/tmp/SEL810_control_panel",showuypdate)
	a.start()

	while(1):
		time.sleep(1)
#		a.step()
