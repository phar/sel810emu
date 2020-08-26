import sys
import threading
import select
import socket
import time

sys.path.append("sel810asm")
from sel810dis import *


#
# connect to asr33 console:
# socat - UNIX-CONNECT:/tmp/SEL810_asr33
#
#

class ExternalUnit():
	def __init__(self,name):
		self.name = name
		self.read_buffer = []
		self.write_buffer = []
		self.socketfn = os.path.join("/tmp","SEL810_" + self.name.replace(" ","_"))
		try:
			os.unlink(self.socketfn)
		except OSError:
			if os.path.exists(self.socketfn):
				raise
		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		
		self.sock.bind(self.socketfn)
		self.sock.listen(1)

		x = threading.Thread(target=self.socket_handler, args=(0,))
		x.start()
		
	def socket_handler(self,arg):
		while(1): #fixme
			connection, client_address = self.sock.accept()
			pollerObject = select.poll()
			pollerObject.register(connection, select.POLLIN| select.POLLOUT)

			while(1):
				fdVsEvent = pollerObject.poll(10000)
				for descriptor, Event in fdVsEvent:
					if Event & ~select.POLLOUT:
						if len(self.write_buffer):
							connection.send(struct.pack("B",self.write_buffer[0]))
							self.write_buffer = self.write_buffer[1:]
							
					if Event & ~select.POLLIN:
						self.read_buffer.append(connection.recv(1))

	def unit_command(self,command):
		print("%s command %d" % (self.name,command))

	def unit_test(self,command):
		print("%s test %d" % (self.name,command))
		
	def unit_write(self,data):
		print("%s write %d" % (self.name,data))
		self.write_buffer.append(data)

	def unit_read(self):
		while(len(self.read_buffer) == 0):
			time.sleep(.25)
			
		t = self.read_buffer[0]
		self.read_buffer = self.read_buffer[1:]
		print("%s read" % self.name,t)
		return t


MAX_MEM_SIZE = 0x7fff

def parity_calc(i):
	i = i - ((i >> 1) & 0x55555555)
	i = (i & 0x33333333) + ((i >> 2) & 0x33333333)
	i = (((i + (i >> 4)) & 0x0F0F0F0F) * 0x01010101) >> 24
	return int(i % 2)

class RAM():
	def __init__(self,value=0):
		self.value = 0
		self.prot = False
		self.parity = False

		self.write(value)
		
	def protected(self,state):
		if state:
			self.prot = True
		else:
			self.prot = False
		
	def is_protected(self):
		return self.prot
		
	def read(self):
		return self.value
	
	def write(self,v):
#		if v < 0:
#			val = oparg | ((~abs(v) + 1)  & 0xffff)#its a 16 bit value so to fix the sign bit
#		else:
#			val = oparg | v
		
		self.value = v
		self.parity = parity_calc(self.value)
		return self.value


class SEL810CPU():
	def __init__(self):
		self.ram = [RAM() for x in range(MAX_MEM_SIZE)]

		self.external_units = [ExternalUnit("nulldev"),ExternalUnit("asr33"),ExternalUnit("paper tape"),ExternalUnit("card punch"),ExternalUnit("card reader"),ExternalUnit("line printer"),ExternalUnit("TCU 1"),ExternalUnit("TCU 2"),ExternalUnit("INVALID 1"),ExternalUnit("INVALID 2"),ExternalUnit("typewriter"),ExternalUnit("X-Y plotter"),ExternalUnit("interval timer"),ExternalUnit("movable head disc"),ExternalUnit("CRT"),ExternalUnit("fixed head disc")]
		self.memory_map = []
		self.prog_counter = 0
		self.instr_register = 0
		self.accumulator_a = 0
		self.accumulator_b = 0
		self.t_register = 0
		self.halt_flag = True #start halted
		self.parity_flag = False
		self.IOwait_flag = False
		self.interrupt_flag = False
		self.overflow_flag = False
#		self.switch_runstop = 0

		for borp in range(0, MAX_MEM_SIZE): #memory is filled entirely with ram right now
			self.memory_map.append({"read": lambda x=borp:ram[x].read(), "write": lambda x,y=borp : self.ram[y].write(x)})
			
	def set_program_counter(self, addr):
		self.prog_counter = addr & MAX_MEM_SIZE
		
	def panelswitch_halt(self):
		pass
		
	def panelswitch_clear_t(self):
		pass

	def panelswitch_master_clear(self):
		pass

	def panelswitch_start_stop_toggle(self):
		if self.halt_flag == False:
			self.halt_flag = True
			
		elif self.halt_flag == True:
			self.halt_flag = False

	def panelswitch_single_cycle(self):
		(self.instr_register, mnemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(self.ram[self.prog_counter].read())
		args = args.split(",")

		print("%06o %s" % (self.prog_counter, mnemonic))
		if mnemonic == "CEU":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.IOwait_flag = True
			self.external_units[unit].unit_command(self.ram[self.prog_counter + 1].read())
			self.IOwait_flag = False
			self.prog_counter = self.prog_counter + 2 #second word
			
		if mnemonic == "TEU":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.IOwait_flag = True
			self.accumulator_a = self.external_units[unit].unit_test(self.ram[self.prog_counter+ 1].read())
			self.IOwait_flag = False
			self.prog_counter = self.prog_counter + 2 #second word
			
		elif mnemonic == "AIP":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.IOwait_flag = True
			self.accumulator_a = self.external_units[unit].unit_read()
			self.IOwait_flag = False
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "AOP":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.IOwait_flag = True
			self.external_units[unit].unit_write(self.accumulator_a)
			self.IOwait_flag = False
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "BRU":
			(address,) = args
			address = int(address[1:],8)
			self.set_program_counter(address)

		elif mnemonic == "IBS":
			self.accumulator_b =  (self.accumulator_b + 1) & 0xffff
			if self.accumulator_b  == 0:
				self.prog_counter = self.prog_counter + 2
			else:
				self.prog_counter = self.prog_counter + 1

		elif mnemonic == "NOP":
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "SAP":
			if self.accumulator_a > 0:
				self.set_program_counter(self.prog_counter + 1)
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "SAN":
			if self.accumulator_a < 0:
				self.prog_counter = self.prog_counter + 1
			self.prog_counter = self.prog_counter + 1
				
		elif mnemonic == "SAZ":
			if self.accumulator_a == 0:
				self.prog_counter = self.prog_counter + 1
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "STA":
			(address,) = args
			address = int(address[1:],8)
			self.ram_write(address, self.accumulator_a)
			self.prog_counter = self.prog_counter + 1
		
		elif mnemonic == "STB":
			(address,) = args
			address = int(address[1:],8)
			self.ram_write(address, self.accumulator_b)
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "TBA":
			 self.accumulator_a = self.accumulator_b
			 self.prog_counter = self.prog_counter + 1
			 
		elif mnemonic == "TAB":
			self.accumulator_b = self.accumulator_a
			self.prog_counter = self.prog_counter + 1

		elif mnemonic == "HLT":
			self.halt_flag = True

	def run(self):
		while(not self.halt_flag):
			self.panelswitch_single_cycle()
		return
#	def ram_read(self,addr):
#		return self.ram[addr]
#
#	def ram_write(self,addr,val):
#		self.ram[addr & MAX_MEM_SIZE] = val & 0xffff
#		return self.ram[addr& 0xffff]

	def loadAtAddress(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.memory_map[address+i]["write"](binfile[i])


if __name__ == '__main__':
	file= sys.argv[1]
	
	cpu = SEL810CPU()
	cpu.loadAtAddress(0o6000,file)
	cpu.set_program_counter(0o6000)
	
	cpu.panelswitch_start_stop_toggle()
	
#	while(1):
	cpu.run()
	print("halted")
	
#	for val in  binfile:
#		(opcode, nmemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(val)
#		print(nmemonic)
