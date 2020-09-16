import sys
import threading
import select
import socket
import time
import cmd
import os
try:
    import readline
except ImportError:
    readline = None


sys.path.append("sel810asm")
#from sel810dis import *
from util import *
from MNEMBLER2 import *

#
# connect to asr33 console:
# socat - UNIX-CONNECT:/tmp/SEL810_asr33
#
#

class ExternalUnitNotConnected(Exception):
	"""Raised when the external unit is not connected and wait flag is not asserted"""
	pass


class ExternalUnit():
	def __init__(self,name,chardev=False):
		self.name = name
		self.read_buffer = []
		self.write_buffer = []
		self.connected = False
		self.shutdown = False
		self.chardev = chardev
		self.socketfn = os.path.join("/tmp","SEL810_" + self.name.replace(" ","_"))
		try:
			os.unlink(self.socketfn)
		except OSError:
			if os.path.exists(self.socketfn):
				raise
		self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		
		self.sock.bind(self.socketfn)
		self.sock.listen(1)

		self.thread = threading.Thread(target=self.socket_handler, args=(0,))
		self.thread.start()
		print("started external unit %s on %s" % (self.name,self.socketfn))
		
	def socket_handler(self,arg):
		serverpollerObject = select.poll()
		serverpollerObject.register(self.sock, select.POLLIN)
		
		while(self.shutdown == False):
			serverfdVsEvent = serverpollerObject.poll(250)
			for adescriptor, aEvent in serverfdVsEvent:
				connection, client_address = self.sock.accept()
				self.connected = True
				
				pollerrObject = select.poll()
				pollerrObject.register(connection, select.POLLIN | select.POLLERR | select.POLLHUP)
				pollerrwObject = select.poll()
				pollerrwObject.register(connection, select.POLLIN | select.POLLOUT | select.POLLERR | select.POLLHUP)
				connection.setblocking(0)
				while(self.shutdown == False):
					if len(self.write_buffer):
						fdVsEvent = pollerrwObject.poll(125)
					else:
						fdVsEvent = pollerrObject.poll(125)

					for descriptor, Event in fdVsEvent:
						if Event & select.POLLOUT:
							if len(self.write_buffer):
								connection.send(struct.pack("B",self.write_buffer[0]))
								self.write_buffer = self.write_buffer[1:]
								
						if Event & (select.POLLERR | select.POLLHUP):
							self.connected = False
							connection.close()
							break
							
						if Event & select.POLLIN:
							print(self.write_buffer)
							self.read_buffer.append(connection.recv(1))

		self.connected = False

	def unit_command(self,command):
		print("%s command %d" % (self.name,command))

	def unit_test(self,command):
		print("%s test %d" % (self.name,command))
		
	def unit_write(self,data,wait=False):
		if wait:
			while(self.connected == 0):
				time.sleep(.25)
				
		if self.connected:
			print("%s write %d" % (self.name,data))
			if self.chardev:
				self.write_buffer.append((data & 0xff00) >> 8)
			else:
				self.write_buffer.append((data & 0xff00) >> 8)
				self.write_buffer.append(data & 0xff)
		else:
			raise ExternalUnitNotConnected
			
	def unit_read(self, wait=False):
		if wait:
			while(self.connected == 0):
				time.sleep(.25)
				
		if self.connected:
			while(len(self.read_buffer) == 0):
				time.sleep(.25)
			t = self.read_buffer[0]
			self.read_buffer = self.read_buffer[1:]
			print("%s read" % self.name,t)
			return ord(t)
		else:
			raise ExternalUnitNotConnected
				
	def unit_shutdown(self):
		print("%s external unit shutting down" % self.name)
		self.shutdown = True
		self.thread.join()

MAX_MEM_SIZE = 0x7fff
		
OPTION_PROT_NONE 	= 0
OPTION_PROT_1B 		= 1
OPTION_PROT_2B		= 2

class RAM_CELL():
	def __init__(self,parent_array, prot=None, width=16):
		self.value = 0
		self.bitwidth = width
		self.prot = False
		self.parity = False
		self.parent = parent_array
		self.write(0x0000)

	def read(self):
		return twoscmplment2dec(self.value)

	def read_raw(self):
		return self.value

	def write_raw(self,v):
		self.value = v & ((2**self.bitwidth) - 1)
		self.parity = parity_calc(self.value)

	def write(self,v):
		if self.parent._write_attempt(self.prot):
			self.value = dec2twoscmplment(v & ((2**self.bitwidth) - 1),self.bitwidth)
			self.parity = parity_calc(self.value)
		return self.value
	
class MEMORY(list):
	def __init__(self, cpu, memmax=0x7fff, options=OPTION_PROT_NONE):
		self.optionsmask = options
		self.memmax = memmax
		self.prot_reg = 0
		self._ram = [] # [RAM_CELL()] * self.memmax
		self.cpu = cpu

		if self.optionsmask & OPTION_PROT_1B: #its not clear how this option works for various memory sizes
			psize = 1024
		elif self.optionsmask & OPTION_PROT_2B:
			psize = 2048
		else:
			psize = self.memmax
			
		for i in range(0, self.memmax, psize):
			for e in range(0,psize):
				self._ram.append(RAM_CELL(self,i))
				
	def _write_attempt(self,prot_bit):
		return 1 #will figure out the interrupt logic for this later
		 
	def __setitem__(self, key, item):
		self.__dict__[key] = item

	def __getitem__(self, key):
		return self._ram[key & self.memmax]

	def set_prot_reg(self, regval):
		self.prot_reg = regval
		
	def get_prot_reg(self):
		return self.prot_reg



class SEL810CPU():
	def __init__(self,type= SEL810ATYPE):
		self.ram = MEMORY(self)
		self.type = SEL810ATYPE
		self.external_units = [ExternalUnit("nulldev"),ExternalUnit("asr33",chardev=True),ExternalUnit("paper tape",chardev=True),ExternalUnit("card punch",chardev=True),ExternalUnit("card reader",chardev=True),ExternalUnit("line printer",chardev=True),ExternalUnit("TCU 1"),ExternalUnit("TCU 2"),ExternalUnit("INVALID 1"),ExternalUnit("INVALID 2"),ExternalUnit("typewriter"),ExternalUnit("X-Y plotter"),ExternalUnit("interval timer"),ExternalUnit("movable head disc"),ExternalUnit("CRT"),ExternalUnit("fixed head disc")]
		
#		self.registers = {
#			"Program Counter":RAM_CELL(),
#			"Instruction Pointer":RAM_CELL(),
#			"Index Register":RAM_CELL(),
#			"A Register":RAM_CELL(),
#			"B Register":RAM_CELL(),
#			"Protection Register":RAM_CELL(),
#			"VBR Register":RAM_CELL(),
#		}
		self.cyclecount = 0

		#registers
		self.prog_counter = 0
		self.instr_register = 0
		self.hw_index_register = 0
		self.accumulator_a = 0
		self.accumulator_b = 0
		self.protect_register = 0
		self.vbr = 0 #6 bit
		self.control_switches = 0

		self.t_register = 0
		
		#latches
		self.halt_flag = True #start halted
		self.IOwait_flag = False
		self.interrupt_flag = False
		self.overflow_flag = False
		self.index_register_pointer = False

	def set_index(self,val):
		if self.type == SEL810ATYPE:
			self.accumulator_b = val & 0xffff
		elif self.type == SEL810BTYPE:
			self.hw_index_register = val & 0xffff

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
			
	def _increment_pc(self,incrnum=1):
		self.prog_counter = (self.prog_counter + incrnum ) & 0x7fff

	def _increment_cycle_count(self,incrnum=1):
		self.cyclecount += incrnum

	def _shift_cycle_timing(self,shifts):
		if 0 > shifts and shifts < 5:
			self._increment_cycle_count(2)
		elif 4 > shifts and shifts < 9:
			self._increment_cycle_count(3)
		elif 8 > shifts and shifts < 13:
			self._increment_cycle_count(4)
		elif 13 > shifts and shifts < 16:
			self._increment_cycle_count(5)

	def panelswitch_single_cycle(self):
		op  = SELOPCODE(opcode=self.ram[self.prog_counter].read())
		if op.nmemonic in SEL810_OPCODES:
		
			if "address" in op.fields:
#				map = op.fields["m"]  #left as a reminder
				address = op.fields["address"]
				if op.fields["i"]:
					address = self.ram[address].read()
				
			if op.nmemonic == "LAA":
				print("foo",(address + (op.fields["x"] * self.get_index())), self.get_index())
				self.accumulator_a = self.ram[(address + (op.fields["x"] * self.get_index())) & 0x7fff].read()
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "LBA":
				self.accumulator_b = self.ram[(address + (op.fields["x"] * self.get_index())) & 0x7fff].read()
				self._increment_pc()
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "STA":
				self.ram[address].write(self.accumulator_a)
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "STB":
				self.ram_write(address, self.accumulator_b)
				self._increment_pc()
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "AMA":
				if self.accumulator_a + self.ram[address].read() > 0xffff:
					self.overflow_flag = True
				self.accumulator_a =  (self.accumulator_a + self.ram[address].read()) & 0xffff
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "SMA":
				if self.accumulator_a - self.ram[address].read() < 0:
					self.overflow_flag = True
				self.accumulator_a =  (self.accumulator_a + self.ram[address].read()) & 0xffff
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "MPY":
				if self.accumulator_a * self.ram[address].read() < 0:
						self.overflow_flag = True
				self.accumulator_a =  (self.accumulator_a * self.ram[address].read()) & 0xffff
				self._increment_pc()
				self._increment_cycle_count(6)

			elif op.nmemonic == "DIV":
				if  self.ram[address].read() != 0: #fixme
					a = (self.accumulator_a << 16 | self.accumulator_b) / self.ram[address].read()
					b = (self.accumulator_a << 16 | self.accumulator_b) % self.ram[address].read()
					self.accumulator_a = a
					self.accumulator_b = b
				else:
					self.overflow_flag = True 
				self._increment_cycle_count(11)
				self._increment_pc()
							
			elif op.nmemonic == "BRU":
				self.prog_counter = (address + ( op.fields["x"] * self.get_index())) & 0x7fff
				self._increment_cycle_count()
				self._increment_cycle_count()
				
			elif op.nmemonic == "SPB":
				self.ram[address].write((self.prog_counter + 1) & 0x7fff)
				self.prog_counter = address
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "IMS":
				t = self.ram[address]["read"]()+1
				self.ram[address].write(t)
				if t == 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(3)

			elif op.nmemonic == "CMA":
				if self.accumulator_a == self.ram[address].read():
					self._increment_pc() #the next instruction is skipped.
				elif self.accumulator_a > self.ram[address].read():
					self._increment_pc(2) #the next two instructions are skipped.
				self._increment_pc()
				self._increment_cycle_count(3)
				
			elif op.nmemonic == "AMB":
				if  (self.accumulator_b + self.ram[address].read()) > 0x7fff:
					self.overflow_flag = True
				self.accumulator_b =  (self.accumulator_b + self.ram[address].read()) & 0xffff
				self._increment_cycle_count(2)
				self._increment_pc()
			 
			elif op.nmemonic == "CEU":
				self.IOwait_flag = True
				self.external_units[op.fields["unit"]].unit_command(self.ram[self.prog_counter + 1].read())
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word
				self._increment_cycle_count(4)

			elif op.nmemonic == "TEU":
				self.IOwait_flag = True
				self.accumulator_a = self.external_units[op.fields["unit"]].unit_test(self.ram[self.prog_counter+ 1].read())
				self.IOwait_flag = False
				self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word
				self._increment_cycle_count(4)

			elif op.nmemonic == "SNS":
				if self.control_switches & (1 << op.fields["unit"]):
					self._increment_pc()
				else: #if switch is NOT set, the next instruction is skipped.
					self._increment_pc(2)
				self._increment_cycle_count(1)

			elif op.nmemonic == "AIP":
				self.IOwait_flag = True
				try:
					self.accumulator_a = (self.accumulator_a *  op.fields["r"]) + self.external_units[op.fields["unit"]].unit_read(wait)
					if not op.fields["wait"]:
						self.prog_counter = (self.prog_counter + 2) & 0x7fff
				except ExternalUnitNotConnected:
					self._increment_pc()
				self.IOwait_flag = False
				self._increment_cycle_count(4)

			elif op.nmemonic == "AOP":
				self.IOwait_flag = True
				self.external_units[op.fields["unit"]].unit_write(self.accumulator_a)
				self.IOwait_flag = False
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "MIP":
				self.IOwait_flag = True
				self.accumulator_a = ord(self.external_units[op.fields["unit"]].unit_read())
				self.IOwait_flag = False
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "MOP":
				self.IOwait_flag = True
				print("mop", self.ram[(self.prog_counter + 1) & 0x7fff].read())
				self.external_units[op.fields["unit"]].unit_write(self.ram[(self.prog_counter + 1) & 0x7fff].read())
				self.IOwait_flag = False
				self._increment_pc(2)
				self._increment_cycle_count(4)

			elif op.nmemonic == "HLT":
				self.halt_flag = True
				self._increment_cycle_count()

			elif op.nmemonic == "RNA":
				if self.accumulator_b & 0x4000:
					if self.accumulator_a + 1 > 0x7fff:
						self.overflow_flag = True
					self.accumulator_a =  (self.accumulator_a + 1) & 0x7fff
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "NEG":
				self._increment_pc()
				self._increment_cycle_count()
				
			elif op.nmemonic == "CLA":
				self._increment_pc()
				self._increment_cycle_count()
				
			elif op.nmemonic == "TBA":
				 self.accumulator_a = self.accumulator_b
				 self._increment_cycle_count(1)
				 self._increment_pc()
				 
			elif op.nmemonic == "TAB":
				self.accumulator_b = self.accumulator_a
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "IAB":
				t = self.accumulator_a
				self.accumulator_a = self.accumulator_b
				self.accumulator_b = t
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "CSB":
				if self.accumulator_b & 0x8000:
					self.carry_flag = True
				else:
					self.carry_flag = False
				self.accumulator_b &= 0x7fff
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "RSA":
				self.accumulator_a = (accumulator_a & 0x8000) | ((self.accumulator_a & 0xffff) >> op.fields["shifts"]) & 0x7fff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSA":
				self.accumulator_a = (accumulator_a & 0x8000) | ((self.accumulator_a & 0x7fff) << op.fields["shifts"]) & 0x7fff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRA":
				self._increment_pc()
				self._shift_cycle_timing(op.fields["shifts"])

			elif op.nmemonic == "FLL":
				t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"]) & 0xffffffff
				self.accumulator_a = (t & 0xffff0000) >> 16
				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRL":
				t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"])
				l = (t ^ 0xffffffff) >> (16-op.fields["shifts"])  #uhhh
				t = t | l
				
				self.accumulator_a = (t & 0xffff0000) >> 16
				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "RSL":
				self.accumulator_a = (self.accumulator_a >> op.fields["shifts"]) & 0xffff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSL":
				self.accumulator_a = (self.accumulator_a << op.fields["shifts"]) & 0xffff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FLA": #fixme
				t = ((((self.accumulator_a & 0x7fff) << 15) | (self.accumulator_b & 0x7fff)) << op.fields["shifts"]) & 0xffffffff
				self.accumulator_a = (t & 0xffff0000) >> 16
				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()
				
			elif op.nmemonic == "ASC":
				self.accumulator_a ^= 0x8000
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAS":
				if self.accumulator_a == 0:
					self._increment_pc()
				elif self.accumulator_a > 0:
					self._increment_pc(2)
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "SAZ":
				if self.accumulator_a == 0:
					self.prog_counter = self.prog_counter + 1
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAN":
				if self.accumulator_a < 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAP":
				if self.accumulator_a > 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "SOF":
				if self.overflow_flag == True:#If the arithmetic overflow latch is set, it is reset and the next instruction is executed;
					self.overflow_flag = False
				else: #if the latch is reset, the next instruction is skipped.
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "IBS":
				self.accumulator_b =  (self.accumulator_b + 1) & 0xffff
				if self.accumulator_b  == 0:
					self.prog_counter = (self.prog_counter + 2) & 0x7fff
				else:
					self._increment_pc()
				self._increment_cycle_count(1)
					
			elif op.nmemonic == "ABA":
				self.accumulator_a =  self.accumulator_a & self.accumulator_b
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "OBA":
				self.accumulator_a =  (self.accumulator_a & self.accumulator_b) & 0xffff
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "LCS":
				self.accumulator_a =  self.control_switches
				self._increment_pc()
				self._increment_cycle_count(1)
			
			elif op.nmemonic == "SNO": #If bit Al does not equal bit AO of the A~Accurnulator, the next instruction is skipped
				if(self.accumulator_a & 0x0001) != ((self.accumulator_a & 0x0002) >> 1):
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "NOP":
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "CNS":
				self._increment_pc()
				self._increment_cycle_count(1)
				#overflow
				
			elif op.nmemonic == "TOI":
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "LOB":
				self.prog_counter = self.ram[self.prog_counter + 1] & 0x7fff
				self._increment_cycle_count(2)
				self._increment_pc(2)
				
			elif op.nmemonic == "OVS":
				self.overflow_flag = True
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "STX":
				indir = self.ram[self.prog_counter + 1] & 0x4000
				idx = self.ram[self.prog_counter + 1] & 0x8000
				addr = self.ram[self.prog_counter + 1] & 0x3000
				
				if not indir:
					self.ram[addr] = self.get_index()
					self._increment_cycle_count(2)
				else:
					self.ram[self.ram[addr].read()] = self.get_index()
					self._increment_cycle_count(3) #GUESSING
				self._increment_pc(2)

			elif op.nmemonic == "TPB":
				self.accumulator_b = self.protect_register
				self._increment_pc()
				self._increment_cycle_count(1)
					
			elif op.nmemonic == "TBP":
				self.protect_register = self.accumulator_b
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TBV":
				self.vbr = self.accumulator_b & 0x2f
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "TVB":
				self.accumulator_b = self.vbr
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "LIX":
				self._increment_cycle_count(2)
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "XPX":
				self.index_register_pointer = True
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "XPB":
				self.index_register_pointer = False
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "STB":
				self.ram[address].write(self.accumulator_b)
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "IXS":
				if self.get_index() + 1 > 0x7fff:
					self._increment_pc()
				self.set_index(self.get_index() + 1)
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TAX":
				self.set_index(self.accumulator_a)
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TXA":
				self.accumulator_a = self.get_index()
				self._increment_pc()
				self._increment_cycle_count()
	
			elif op.nmemonic == "PID":
				self._increment_pc()
				
			elif op.nmemonic == "PIE":
				self._increment_pc()

		else:
			pass
		



	def run(self):
		while(not self.halt_flag):
			self.panelswitch_single_cycle()
		return

	def loadAtAddress(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.ram[address+i].write_raw(binfile[i])
			
	def shutdown(self):
		for u in self.external_units:
#			print(u)
			u.unit_shutdown()



def parse_inputint(val):
	print("test",val)
	try:
		val = val.strip()
		if val[0] == "'": #octal
			return int(val[1:],8)

		elif len(val) > 2 and val[:2] == "0o": #modern octal
			return int(val,8)

		elif len(val) > 2 and val[:2] == "0x": #hex
			return int(val,16)

		elif len(val) > 2 and val[:2] == "0b": #binary
			return int(val,2)

		elif val.isnumeric(): #flat number
			return(int(val))
		else:
			return  None
	except ValueError:
		return None


EXIT_FLAG = False

CPU_HERTZ = 760000

class SEL810Shell(cmd.Cmd):
	intro = 'Welcome to the SEL emulator/debugger. Type help or ? to list commands.\n'
	prompt = '(SEL810x) '
	file = None
	cpu = SEL810CPU()
	exit_flag = False
	histfile = os.path.expanduser('~/.sel810_console_history')
	histfile_size = 1000

	def do_step(self, arg):
		'singlestep the processor'
		self.cpu.panelswitch_single_cycle()

	def do_toggle_run_stop(self, arg):
		'execute until a halt is recieved'
		self.cpu.run()

	def do_load(self, arg):
		'load a binary file into memory at an address load [address] [filename]'
		try:
			(addr,file) = arg.split(" ")
		except ValueError:
			print("not enough arguments provided")
			return False
		addr = parse_inputint(addr) # fixme, should be flexible
		self.cpu.loadAtAddress(addr,file)

	def do_setpc(self,arg):
		'set the program counter to a specific memory location'
		try:
			(progcnt,) = arg.split(" ")
		except ValueError:
			print("not enough arguments provided")
			return False
		
		progcnt = parse_inputint(progcnt) # fixme, should be flexible
		self.cpu.set_program_counter(progcnt)

	def do_quit(self,args):
		'exit the emulator'
		self.cpu.shutdown()
		return True
		
	def do_hexdump(self,arg):
		'hexdump SEL memory, hexdump [offset] [length]'
		try:
			(offset,length) = arg.split(" ")
			offset = parse_inputint(offset)
			length = parse_inputint(length)
		except ValueError:
			print("not enough arguments provided")
			return False

		for i in range(offset,offset+length,8):
			print("0x%04x\t" % i,end='')
			for e in range(8):
				print("0x%04x "% self.cpu.ram[i+e].read_raw(),end="")
			print("")

	def do_octdump(self,arg):
		'octdump SEL memory, octdump [offset] [length]'
		try:
			(offset,length) = arg.split(" ")
			offset = parse_inputint(offset)
			length = parse_inputint(length)
		except ValueError:
			print("not enough arguments provided")
			return False

		for i in range(offset,offset+length,8):
			print("0o%06o\t" % i,end='')
			for e in range(8):
				print("0o%06o "% self.cpu.ram[i+e].read_raw(),end="")
			print("")


	def do_disassemble(self,arg):
		'disassemble SEL memory, disassemble [offset] [length]'
		try:
			(offset,length) = arg.split(" ")
			offset = parse_inputint(offset)
			length = parse_inputint(length)
		except ValueError:
			print("not enough arguments provided")
			return False

		for i in range(offset,offset+length):
			op = SELOPCODE(opcode=self.cpu.ram[i].read_raw())
			print("'%06o" % i, op.pack_asm()[0])
			

	def do_registers(self,args):
		'show the current register contents'
		print("program counter:\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.prog_counter),dec2twoscmplment(self.cpu.prog_counter)))
		print("accumulator a:\t\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.accumulator_a),dec2twoscmplment(self.cpu.accumulator_a)))
		print("accumulator b:\t\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.accumulator_b),dec2twoscmplment(self.cpu.accumulator_b)))
		print("\"index\":\t\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.get_index()), dec2twoscmplment(self.cpu.get_index())))
		if self.cpu.type == SEL810BTYPE:
			print("hardware index register: 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.hw_index_register),dec2twoscmplment(self.cpu.hw_index_register)))
		print("\"VBR\":\t\t\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.vbr), dec2twoscmplment(self.cpu.vbr)))
		print("\"Control Switches\":\t0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.control_switches), dec2twoscmplment(self.cpu.control_switches)))
		print("\"HALTED\":\t\t%s" % str(bool(self.cpu.halt_flag)))
		print("\"OVERFLOW\":\t\t%s" % str(bool(self.cpu.overflow_flag)))
		print("\"I\\O HOLD\":\t\t%s" % str(bool(self.cpu.IOwait_flag)))
		print("cyclecount:\t\t%dcycles or %fseconds" % (self.cpu.cyclecount, self.cpu.cyclecount * (1.0/CPU_HERTZ)))



	def postcmd(self,arg,b):
		print("ok (next op:%s)" % SELOPCODE(opcode=self.cpu.ram[self.cpu.prog_counter].read()).pack_asm()[0] )

#		if self.cpu.halt_flag:
#			print("halted")
		return arg

	def preloop(self):
		if readline and os.path.exists(self.histfile):
			readline.read_history_file(self.histfile)

	def postloop(self):
		if readline:
			readline.set_history_length(self.histfile_size)
			readline.write_history_file(self.histfile)

#	def precmd(self, line):
#		pass

	def close(self):
		pass
		
if __name__ == '__main__':
#	file= sys.argv[1]

	shell = SEL810Shell()
#while shell.exit_flag == False:
	print(shell.cmdloop())
