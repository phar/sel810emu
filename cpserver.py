import time
import sys
import threading, queue
import select
import socket
import struct
import json
import os
from defs import * 
#class dummy_cpu():
#	def __init__(self):
#		self.cpcmdqueue = queue.Queue()
#		self._shutdown = False
#
#	def get_cpu_state(self):
#		return {"a":"ds","b":5,"more":44}
#
#	def set_cpu_state(self,state):
#		print(state)
#


class ControlPanelDriver():
	def __init__(self,cpu, devicenode):
		self.thread = threading.Thread(target=self.control_panel_thread, args=(devicenode,))
		self.cpu = cpu
		self.devnode = devicenode
		try:
			os.unlink(self.devnode)
		except OSError:
			if os.path.exists(self.devnode):
				raise

		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.sock.bind(self.devnode)
		self.sock.listen(1)

	def start(self):
		self.thread.start()

	def stop(self):
		self.thread.join()

	def control_panel_thread(self, socketname):
		print("started Control panel server on %s" % (self.devnode))
		spollerrObject = select.poll()
		conn = None
		last_state = {}
		last_time = 0
		while(self.cpu._shutdown == False):
			spollerrObject.register(self.sock, select.POLLIN | select.POLLERR | select.POLLHUP)
			sfdVsEvent = spollerrObject.poll(250)
			if len(sfdVsEvent):
				sdescriptor, sEvent = sfdVsEvent[0]
				if sEvent & select.POLLIN:
					conn, addr = self.sock.accept()
					last_state = {}
					pollerrObject = select.poll()
					while(self.cpu._shutdown == False):
						pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
						fdVsEvent = pollerrObject.poll(IDLE_UPDATE_MILLISECONDS) #this is basically our refresh rate
						for descriptor, Event in fdVsEvent:
							if Event & (select.POLLERR | select.POLLHUP):
#								print("socket closed")
								conn.close()
								break
								
							if Event & select.POLLIN:
								try:
									a = self.recv_packet(conn)
									self.cpu.cpcmdqueue.put(a)
								except:
									conn.close()
									break
#						try:
						state = self.cpu.get_cpu_state()
						if state != last_state or (last_time + 1) < time.time():
							self.send_packet(conn,state)
							last_time = time.time()

						last_state = state
#						except:
#							conn.close()
#							break
		self.sock.close()
		if conn is not None:
			conn.close()

	def send_packet(self,sock, packet):
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



#cpu = dummy_cpu()
#
#f  = ControlPanelDriver(cpu,"/tmp/control_panel")
#f.start()
#while 1:
#	time.sleep(1)
