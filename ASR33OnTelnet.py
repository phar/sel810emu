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
	def __init__(self,cpu, devicenode, host, port):
		self.thread = threading.Thread(target=self.asr33_server_thread, args=(devicenode,host,port))
		self.cpu = cpu
		
	def start(self):
		self.thread.start()

	def stop(self):
		self.thread.join()

	def asr33_server_thread(self, socketname,host="0.0.0.0",port=9999):
		e = ASR33ExternalUnit(socketname,chardev=True)
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.bind((host, port))
		s.listen()
		print("started ASR33 7-bit telnet driver on %s:%d" % (host,port))
		spollerrObject = select.poll()
		conn = None
		while(self.cpu._shutdown == False):
			spollerrObject.register(s, select.POLLIN)
			sfdVsEvent = spollerrObject.poll(250)
			if len(sfdVsEvent):
				sdescriptor, sEvent = sfdVsEvent[0]
				if sEvent & select.POLLIN:
					conn, addr = s.accept()
					connected=True
					pollerrObject = select.poll()
					e.event("on")
					while(e.connected and self.cpu._shutdown == False and connected==True):
						pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
						fdVsEvent = pollerrObject.poll(1000)
						if e.pollread():
							e.event("out")
							conn.send(struct.pack("B",(e.read() ^ 0x80)))
							
						for descriptor, Event in fdVsEvent:
							if Event & (select.POLLERR | select.POLLHUP):
#								print("socket closed")
								e.event("off")
								conn.close()
								connected=False
								break
								
							if Event & select.POLLIN:
								e.event("in")
								e.write(ord(conn.recv(1)) | 0x80)
								
		s.close()
		if conn is not None:
			conn.close()


if __name__ == '__main__':
	pass
