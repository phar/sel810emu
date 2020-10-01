from SELDeviceDriver import *
import socket


class ASR33ExternalUnit(ExternalUnitHandler):
	ceuevents = {
					"btc_init":			(0x8000,False,None),
					"interrupt_connect":(0x4000,False,None),
					"in":				(0x2000,True,1),
					"out":				(0x1000,True,2),
					"reader mode":		(0x0800,False,None),
					"key mode":			(0x0400,False,None),
					"clear":			(0x0200,False,None),
					"power on":			(0x0100,False,None),
					"power off":		(0x0080,False,None)}

	def update_ceu(self,ceuval):
		#i dont really need to do anything for this update
		pass

	def update_teu(self,teuval):
		#the asr33 does not appear to have any tests, so success
		return True


class ASR33OnTelnetDriver():
	def __init__(self, devicenode, host, port):
		self.devicenode = devicenode
		self.host = host
		self.port = port
		self.thread = threading.Thread(target=self.asr33_server_thread, args=(self.host,self.port))
		self.e = ASR33ExternalUnit(self.devicenode,chardev=True)

	def start(self):
		self.e.start()
		self.thread.start()

	def stop(self):
		self.e.stop()
		self.thread.join()

	def asr33_server_thread(self,host="0.0.0.0",port=9999):
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.bind((host, port))
		s.listen()
		print("started ASR33 7-bit telnet driver on %s:%d" % (host,port))
		spollerrObject = select.poll()
		conn = None
		while(self.e.connected == True):
			spollerrObject.register(s, select.POLLIN)
			sfdVsEvent = spollerrObject.poll(250)
			if len(sfdVsEvent):
				sdescriptor, sEvent = sfdVsEvent[0]
				if sEvent & select.POLLIN:
					conn, addr = s.accept()
					connected=True
					pollerrObject = select.poll()
					self.e.event("on")
					while(self.e.connected and connected==True):
						pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
						fdVsEvent = pollerrObject.poll(10)
						if self.e.pollread():
							self.e.event("out")
							conn.send(struct.pack("B",(self.e.read() ^ 0x80)))
							
						for descriptor, Event in fdVsEvent:
							if Event & (select.POLLERR | select.POLLHUP):
								self.e.event("off")
								conn.close()
								connected=False
								break
								
							if Event & select.POLLIN:
								self.e.event("in")
								self.e.write(ord(conn.recv(1)) | 0x80)
								
		s.close()
		if conn is not None:
			conn.close()


if __name__ == '__main__':
	pass
