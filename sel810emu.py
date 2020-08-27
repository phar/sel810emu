import sys
import threading
import select
import socket
import time

sys.path.append("sel810asm")
from sel810dis import *
from util import *

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
		return twoscmplment2dec(self.value)
	
	def write(self,v):
		self.value = dec2twoscmplment(v)
		self.parity = parity_calc(self.value)
		return self.value

SEL810ATYPE = 0
SEL810BTYPE = 1

class SEL810CPU():
	def __init__(self,type= SEL810ATYPE):
		self.ram = [RAM() for x in range(MAX_MEM_SIZE)]
		self.type = SEL810ATYPE
		self.external_units = [ExternalUnit("nulldev"),ExternalUnit("asr33"),ExternalUnit("paper tape"),ExternalUnit("card punch"),ExternalUnit("card reader"),ExternalUnit("line printer"),ExternalUnit("TCU 1"),ExternalUnit("TCU 2"),ExternalUnit("INVALID 1"),ExternalUnit("INVALID 2"),ExternalUnit("typewriter"),ExternalUnit("X-Y plotter"),ExternalUnit("interval timer"),ExternalUnit("movable head disc"),ExternalUnit("CRT"),ExternalUnit("fixed head disc")]
		self.memory_map = []
		self.prog_counter = 0
		self.instr_register = 0
		self.hw_index_register = 0
		self.accumulator_a = 0
		self.accumulator_b = 0
		self.t_register = 0
		self.halt_flag = True #start halted
		self.parity_flag = False
		self.IOwait_flag = False
		self.interrupt_flag = False
		self.overflow_flag = False
		self.control_switches = 0

		for borp in range(0, MAX_MEM_SIZE): #memory is filled entirely with ram right now
			self.memory_map.append({"read": lambda x=borp:ram[x].read(), "write": lambda x,y=borp : self.ram[y].write(x)})

	def get_index(self):
		if self.type == SEL810ATYPE:
			return self.accumulator_b
		elif self.type == SEL810BTYPE:
			return self.hw_index_register
	
	def set_control_switches(self,val):
		self.control_switches = val & 0xffff
		
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
		
		print("%06o %s %s" % (self.prog_counter, mnemonic, ",".join(args)))

		if mnemonic in MREF_OPCODES:
			idx = False
			if len(args) == 1:
				(address,) = args
			elif len(args) == 2:
				(address,idx) = args

			address = int(address[1:],8)

#			print("\"%s\"" % indir)
			if indir == "*":
				print("-> %d"% self.ram[address].read())
				address = self.ram[address].read()
				
			if mnemonic == "BRU":
				self.set_program_counter(self.ram[address].read())
			
			elif mnemonic == "STA":
				self.ram_write(address, self.accumulator_a)
				self.prog_counter = (self.prog_counter + 1) & 0x7fff
			
			elif mnemonic == "STB":
				self.ram_write(address, self.accumulator_b)
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "AMB":
				self.accumulator_b =  self.accumulator_b + self.ram[address]["read"]()
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "SPB":
				self.ram[address].write((self.prog_counter + 1) & 0x7fff)
				self.prog_counter = (address + 1) & 0x7fff
		
			elif mnemonic == "ABA":
				self.accumulator_a =  self.accumulator_a & self.accumulator_b
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "AMA":
				self.accumulator_a =  self.accumulator_a + self.ram[address]["read"]()
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

				
		elif mnemonic in IO_OPCODES:
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
		
			if mnemonic == "CEU":
				self.IOwait_flag = True
				self.external_units[unit].unit_command(self.ram[self.prog_counter + 1].read())
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word
				
			if mnemonic == "TEU":
				self.IOwait_flag = True
				self.accumulator_a = self.external_units[unit].unit_test(self.ram[self.prog_counter+ 1].read())
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word

			elif mnemonic == "AIP":
				self.IOwait_flag = True
				self.accumulator_a = self.external_units[unit].unit_read()
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "AOP":
				self.IOwait_flag = True
				self.external_units[unit].unit_write(self.accumulator_a)
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "MIP":
				self.IOwait_flag = True
				self.accumulator_a = self.external_units[unit].unit_read()
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "MOP":
				self.IOwait_flag = True
				self.external_units[unit].unit_write(self.ram[self.prog_counter + 1].read())
				self.IOwait_flag = False
			self.prog_counter = (self.prog_counter + 2) & 0x7fff
			
		elif mnemonic in AUGMENTED_OPCODES:

			if mnemonic == "IBS":
				self.accumulator_b =  (self.accumulator_b + 1) & 0xffff
				if self.accumulator_b  == 0:
					self.prog_counter = (self.prog_counter + 2) & 0x7fff
				else:
					sself.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "NOP":
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "SAP":
				if self.accumulator_a > 0:
					self.prog_counter = (self.prog_counter + 1) & 0x7fff
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "SAN":
				if self.accumulator_a < 0:
					self.prog_counter = (self.prog_counter + 1) & 0x7fff
				self.prog_counter = (self.prog_counter + 1) & 0x7fff
					
			elif mnemonic == "SAZ":
				if self.accumulator_a == 0:
					self.prog_counter = self.prog_counter + 1
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "TBA":
				 self.accumulator_a = self.accumulator_b
				 self.prog_counter = (self.prog_counter + 1) & 0x7fff
				 
			elif mnemonic == "TAB":
				self.accumulator_b = self.accumulator_a
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "IMS":
				(address,) = args
				address = int(address[1:],8)
				t = self.ram[address]["read"]()+1
				self.ram[address].write(t)
				if t == 0:
					self.prog_counter = (self.prog_counter + 1) & 0x7fff
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "LCS":
				self.accumulator_a =  self.control_switches
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "TXA":
				self.accumulator_a =  self.hw_index_register
				self.prog_counter = (self.prog_counter + 1) & 0x7fff
				
			elif mnemonic == "TAX":
				self.hw_index_register = self.accumulator_a
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "HLT":
				self.halt_flag = True

		elif mnemonic in INT_OPCODES:
			pass

	def run(self):
		while(not self.halt_flag):
			self.panelswitch_single_cycle()
		return

	def loadAtAddress(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.memory_map[address+i]["write"](binfile[i])


if __name__ == '__main__':
	file= sys.argv[1]
	
	cpu = SEL810CPU()
	cpu.loadAtAddress(0o0000,file)
	cpu.set_program_counter(0o0000)
	
	cpu.panelswitch_start_stop_toggle()
	
#	while(1):
	for i in range(20):
		cpu.panelswitch_single_cycle()
#	cpu.run()
	print("halted")
	
#	for val in  binfile:
#		(opcode, nmemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(val)
#		print(nmemonic)
