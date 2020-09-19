import sys
import threading,queue
import select
import socket
import time
import cmd
import os
import json
from SELDeviceDriver import *



try:
    import readline
except ImportError:
    readline = None


sys.path.append("sel810asm")
from util import *
from MNEMBLER2 import *



CPU_HERTZ = 572000



class ExternalUnitNotConnected(Exception):
	"""Raised when the external unit is not connected and wait flag is not asserted"""
	pass


class ExternalUnit():
	def __init__(self,cpu, name,chardev=False):
		self.cpu = cpu
		self.name = name
		self.read_buffer = []
		self.write_buffer = []
		self.connected = False
		self.connected_host = None
		self.connected_port = None
		self.shutdown = False
		self.chardev = chardev
		self.socketfn = os.path.join("/tmp","SEL810_" + self.name.replace(" ","_"))
		self.wq = queue.Queue()
		self.rq = queue.Queue()
		self.ceuresp = threading.Event()
		self.teuresp = threading.Event()
		self.rdyresp = threading.Event()
		self.wresp = threading.Event()
		self.rresp = threading.Event()
		self.ceu = 0
		self.teu = 0
		self.w = 0
		self.ready = 0
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
		while(self.shutdown == False):
				self.devsock, client_address = self.sock.accept()
				self.connected = True
				pollerrObject = select.poll()
				pollerrObject.register(self.devsock, select.POLLIN | select.POLLERR | select.POLLHUP)

				while(self.connected == True):
						fdVsEvent = pollerrObject.poll(1)
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
								elif t == 't':
									self.teu = v
									self.teuresp.set()
								elif t == 'w':
									self.w = v
									self.wresp.set()
								elif t == 'r':
									self.rresp.set()
								elif t == '?':
									self.rdyresp.set()
									
						if self.wq.qsize():
							try:
								(t,v) = self.wq.get()
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
		
	def unit_command(self,command):
		self.cpu.IOwait_flag = True
		self.wq.put(("c",command))
		self.ceuresp.wait()
		self.cpu.IOwait_flag = False
		return self.ceu
						
	def unit_test(self,command):
		self.cpu.IOwait_flag = True
		self.wq.put(("t",command))
		self.teuresp.wait()
		self.cpu.IOwait_flag = False
		return self.teu

	def unit_write(self,data):
		self.cpu.IOwait_flag = True
		self.wq.put(("w",data))
		self.wresp.wait()
		self.cpu.IOwait_flag = False

	def unit_ready(self,qry):
		self.cpu.IOwait_flag = True
		self.wq.put(("?",qry))
		self.rdyresp.wait()
		self.cpu.IOwait_flag = False
		return self.ready

	def unit_read(self, wait=False):
		self.cpu.IOwait_flag = True
		self.wq.put(("r",True))
		self.rresp.wait()
#		print("%s read" % self.name,self.w)
		self.cpu.IOwait_flag = False
		return self.w
				
	def _teardown(self):
		print("%s external unit shutting down" % self.name)
		self.shutdown = True
		self.thread.join()


MAX_MEM_SIZE = 0x7fff
		
OPTION_PROT_NONE 	= 0
OPTION_PROT_1B 		= 1
OPTION_PROT_2B		= 2

class RAM_CELL():
	def __init__(self,parent_array=None, prot=None, width=16):
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
		overflow = False
		if v > ((2**self.bitwidth) - 1):
			overflow = True
		self.value = v & ((2**self.bitwidth) - 1)
		self.parity = parity_calc(self.value)
		return overflow

	def write(self,v):
		overflow = False
		if v > ((2**self.bitwidth) - 1):
			overflow = True
			
		if self.parent != None:
			if self.parent._write_attempt(self.prot):
				self.value = dec2twoscmplment(v & ((2**self.bitwidth) - 1),self.bitwidth)
				self.parity = parity_calc(self.value)
		else: #no parent to check with
			self.value = dec2twoscmplment(v & ((2**self.bitwidth) - 1),self.bitwidth)
			self.parity = parity_calc(self.value)

		return overflow
	
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
		self.external_units = {0:ExternalUnit(self,"nulldev"),
							   1:ExternalUnit(self,"asr33",chardev=True),
							   2:ExternalUnit(self,"paper tape",chardev=True),
							   3:ExternalUnit(self,"card punch",chardev=True),
							   4:ExternalUnit(self,"card reader",chardev=True),
							   5:ExternalUnit(self,"line printer",chardev=True),
							   6:ExternalUnit(self,"TCU 1"),
							   7:ExternalUnit(self,"TCU 2"),
							   10:ExternalUnit(self,"typewriter"),
							   11:ExternalUnit(self,"X-Y plotter"),
							   12:ExternalUnit(self,"interval timer"),
							   13:ExternalUnit(self,"movable head disc"),
							   14:ExternalUnit(self,"CRT"),
							   15:ExternalUnit(self,"fixed head disc"),
				
							   32:ExternalUnit(self,"NIXIE Minute Second"),
							   33:ExternalUnit(self,"NIXIE Day Hour"),
							   34:ExternalUnit(self,"NIXIE Months"),
							   35:ExternalUnit(self,"SWITCH0"),
							   36:ExternalUnit(self,"SWITCH1"),
							   37:ExternalUnit(self,"SWITCH2"),
							   38:ExternalUnit(self,"RELAY0"),
							   39:ExternalUnit(self,"RELAY1"),
							   40:ExternalUnit(self,"SENSE0"),
							   50:ExternalUnit(self,"SENSE1"),

}
		
		
		if self.type == SEL810ATYPE:

			b_reg_cell = RAM_CELL()
			self.registers = {
				"Program Counter":RAM_CELL(width=15),
				"Index Register":b_reg_cell,
				"A Register":RAM_CELL(),
				"B Register":b_reg_cell,
				"Protection Register":RAM_CELL(),
				"VBR Register":RAM_CELL(width=6),
				"Control Switches":RAM_CELL(),
			}

		elif self.type == SEL810BTYPE:
			self.registers = {
				"Program Counter":RAM_CELL(width=15),
				"Index Register":RAM_CELL(),
				"A Register":RAM_CELL(),
				"B Register":RAM_CELL(),
				"Protection Register":RAM_CELL(),
				"VBR Register":RAM_CELL(width=6),
				"Control Switches":RAM_CELL(),
			}
		self.cyclecount = 0

		#registers
#		self.prog_counter = 0
#		self.hw_index_register = 0
#		self.accumulator_a = 0
#		self.accumulator_b = 0
#		self.protect_register = 0
#		self.vbr = 0 #6 bit
#		self.control_switches = 0

		self.t_register = 0
		
		#latches
		self.halt_flag = True #start halted
		self.IOwait_flag = False
		self.interrupt_flag = False
		self.overflow_flag = False
		self.index_register_pointer = False

	def set_control_switches(self,val):
		self.control_switches = val & 0xffff
		
	def set_program_counter(self, addr):
#		self.prog_counter = addr & MAX_MEM_SIZE
		self.registers["Program Counter"].raw_write(addr)
		
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
#		self.prog_counter = (self.prog_counter + incrnum ) & MAX_MEM_SIZE
		self.registers["Program Counter"].write_raw(self.registers["Program Counter"].read_raw() + incrnum )

	def _next_pc(self):
		return (self.registers["Program Counter"].read_raw() + 1) & MAX_MEM_SIZE


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
			
			
	def _resolve_indirect_address(self,base,m,i,x):
		#M functions only if the Indirect Flag (bit5)isa "1". Ifbit5andbit6 are both "1" bits the MSB of the program counter is merged with the Indirect Address. If bit 5 is a "1" andbit6isa "0"theMSBofthe Indirect Address is set to a "0". This feature allows the program to be executed in upper memory (MAP 40 or greater) in the same manner as it is executed in lower memory.
		
		if i:
			val =  self.ram[self.ram[(self.registers["Program Counter"].read_raw() & 0x4000) | ((base + (x * self.registers["Index Register"].read())) & MAX_MEM_SIZE)].read()].read()
		else:
			val =  self.ram[(base + (x * self.registers["Index Register"].read())) & MAX_MEM_SIZE].read()
			
		return val
		
	def panelswitch_single_cycle(self):
		op  = SELOPCODE(opcode=self.ram[self.registers["Program Counter"].read_raw()].read())
		if op.nmemonic in SEL810_OPCODES:
		
			if "address" in op.fields:
#				map = op.fields["m"]  #left as a reminder
				address = op.fields["address"]
				if op.fields["i"]:
					address = self.ram[address].read()
				
			if op.nmemonic == "LAA":
				self.registers["A Register"].write_raw(self.ram[(address + (op.fields["x"] * self.registers["Index Register"].read())) & MAX_MEM_SIZE].read_raw())
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "LBA":
				self.registers["B Register"].write_raw(self.ram[(address + (op.fields["x"] * self.registers["Index Register"].read())) & MAX_MEM_SIZE].read())
				self._increment_pc()
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "STA":
				self.ram[address].write_raw(self.registers["A Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "STB":
				self.ram[address].write_raw(self.registers["B Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "AMA":
				if (self.registers["A Register"].read() + self.ram[address].read()) > 0xffff:
					self.overflow_flag = True
				self.registers["A Register"].write (self.registers["A Register"].read() + self.ram[address].read())
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "SMA":
#				if self.accumulator_a - self.ram[address].read() < 0:
#					self.overflow_flag = True
#				self.accumulator_a =  (self.accumulator_a + self.ram[address].read()) & 0xffff
				if (self.registers["A Register"].read() - self.ram[address].read()) < 0:
					self.overflow_flag = True
				self.registers["A Register"].write(self.registers["A Register"].read() - self.ram[address].read())
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "MPY":
#				if self.accumulator_a * self.ram[address].read() < 0:
				if self.registers["A Register"].read() * self.ram[address].read() < 0:
						self.overflow_flag = True
#				self.accumulator_a =  (self.accumulator_a * self.ram[address].read()) & 0xffff
				self.registers["A Register"].write(self.registers["A Register"].read() * self.ram[address].read())
				self._increment_pc()
				self._increment_cycle_count(6)

			elif op.nmemonic == "DIV":
				if  self.ram[address].read() != 0: #fixme
					a = (self.registers["A Register"].read() << 16 | self.registers["B Register"].read()) / self.ram[address].read()
					b = (self.registers["A Register"].read() << 16 | self.registers["B Register"].read()) % self.ram[address].read()
					self.registers["A Register"].write(a)
					self.registers["B Register"].write(b)
				else:
					self.overflow_flag = True
				self._increment_cycle_count(11)
				self._increment_pc()
							
			elif op.nmemonic == "BRU":
#				self.prog_counter = (address + ( op.fields["x"] * self.get_index())) & MAX_MEM_SIZE
				self.registers["Program Counter"].raw_write(address + ( op.fields["x"] * self.registers["Index Register"].read()))
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "SPB":
				self.ram[address].write(self._next_pc())
#				self.prog_counter = address
				self.registers["Program Counter"].raw_write(address)
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "IMS":
				t = (self.ram[address]["read"]() + 1) & 0xffff
				self.ram[address].write(t)
				if t == 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(3)

			elif op.nmemonic == "CMA":
				if self.registers["A Register"].read() == self.ram[address].read():
					self._increment_pc() #the next instruction is skipped.
				elif self.registers["A Register"].read() > self.ram[address].read():
					self._increment_pc(2) #the next two instructions are skipped.
				self._increment_pc()
				self._increment_cycle_count(3)
				
			elif op.nmemonic == "AMB":
				if  (self.registers["B Register"].read() + self.ram[address].read()) > 0x7fff:
					self.overflow_flag = True
				self.registers["B Register"].write(self.registers["B Register"].read() + self.ram[address].read())
				self._increment_cycle_count(2)
				self._increment_pc()
			 			 
			elif op.nmemonic == "CEU":
				if op.fields["i"]:
					addridx = self.ram[self._next_pc()].read()
					addr = addridx & 0x3fff
					i = (0x4000 & addridx) >> 14
					x = (0x8000 & addridx) >> 15
					val = self._resolve_indirect_address(address,op.fields["m"],i,x)
				else:
					val  = self.ram[self._next_pc()].read()
					
				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]
				if eu.unit_ready("r") or op.fields["wait"]:
					eu.unit_command(val)
					self._increment_cycle_count(1)
				else:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "TEU":
				if op.fields["i"]:
					addridx = self.ram[self._next_pc()].read()
					addr = addridx & 0x3fff
					i = (0x4000 & addridx) >> 14
					x = (0x8000 & addridx) >> 15
					val = self._resolve_indirect_address(address,op.fields["m"],i,x)
				else:
					val  = self.ram[self._next_pc()].read()
					
				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]
					
				if eu.unit_ready("r") or op.fields["wait"]:
					eu.unit_test(val)
					self._increment_cycle_count(1)
				else:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "SNS":
				if self.control_switches & (1 << op.fields["unit"]):
					self._increment_pc()
				else: #if switch is NOT set, the next instruction is skipped.
					self._increment_pc(2)
				self._increment_cycle_count(1)

			elif op.nmemonic == "AIP":
				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]

				if eu.unit_ready("r") or op.fields["wait"]:
					if not op.fields["r"]:
						self.registers["A Register"].write(0)
					self._increment_cycle_count(1)
					self.registers["A Register"].write(self.registers["A Register"].read() + eu.unit_read())
					#wait
				else:
					self._increment_pc() #skip
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "AOP":
				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]

				if eu.unit_ready("r") or op.fields["wait"]:
					self._increment_cycle_count(1)
					eu.unit_write(self.registers["A Register"].read())
					#wait
				else:
					self._increment_pc() #skip
				self._increment_pc(1)
				self._increment_cycle_count(4)

			elif op.nmemonic == "MIP":
				self.accumulator_a = ord(self.external_units[op.fields["unit"]].unit_read())
				self._increment_pc()
				self._increment_cycle_count(4)

				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]

				if eu.unit_ready("w") or op.fields["wait"]:
#					if not op.fields["r"]:
##						self.accumulator_a = 0
#						self.registers["A Register"].write(0)
					self._increment_cycle_count(1)
					self.ram[self._next_pc()].write(eu.unit_read())
					#wait
				else:
					self._increment_pc() #skip
				self._increment_pc()
				self._increment_cycle_count(4)

			elif op.nmemonic == "MOP":
				if op.fields["unit"] not in self.external_units:
					eu = self.external_units[0]
				else:
					eu = self.external_units[op.fields["unit"]]

				if eu.unit_ready("w") or op.fields["wait"]:
					self._increment_cycle_count(1)
					eu.unit_write(self.ram[self._next_pc()].read())
					#wait
				else:
					self._increment_pc() #skip
				self._increment_pc(2)
				self._increment_cycle_count(4)

			elif op.nmemonic == "HLT":
				self.halt_flag = True
				self._increment_cycle_count()

			elif op.nmemonic == "RNA":
				if self.registers["B Register"].read_raw() & 0x4000:
					if (self.registers["A Register"].raw_read() + 1) > 0x7fff:
						self.overflow_flag = True
					self.registers["A Register"].write(self.registers["A Register"].read() + 1)
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "NEG": #fixme
				self._increment_pc()
				self._increment_cycle_count()
				
			elif op.nmemonic == "CLA": #fixme
				self._increment_pc()
				self._increment_cycle_count()
				
			elif op.nmemonic == "TBA":
#				 self.accumulator_a = self.accumulator_b
				self.registers["A Register"].write(self.registers["B Register"].read())
				self._increment_cycle_count(1)
				self._increment_pc()
				 
			elif op.nmemonic == "TAB":
#				self.accumulator_b = self.accumulator_a
				self.registers["B Register"].write(self.registers["A Register"].read())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "IAB":
#				t = self.accumulator_a
				t = self.registers["A Register"].read()
#				self.accumulator_a = self.accumulator_b
				self.registers["A Register"].write(self.registers["B Register"].read())
#				self.accumulator_b = t
				self.registers["B Register"].write(t)
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "CSB":
				if self.registers["B Register"].read_raw() & 0x8000:
					self.carry_flag = True
				else:
					self.carry_flag = False
				self.registers["B Register"].write(self.registers["A Register"].raw_read() & 0x7fff)
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "RSA":
#				self.accumulator_a = (accumulator_a & 0x8000) | ((self.accumulator_a & 0xffff) >> op.fields["shifts"]) & 0x7fff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSA":
#				self.accumulator_a = (accumulator_a & 0x8000) | ((self.accumulator_a & 0x7fff) << op.fields["shifts"]) & 0x7fff
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRA":
				self._increment_pc()
				self._shift_cycle_timing(op.fields["shifts"])

			elif op.nmemonic == "FLL":
#				t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"]) & 0xffffffff
#				self.accumulator_a = (t & 0xffff0000) >> 16
#				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRL":
#				t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"])
#				l = (t ^ 0xffffffff) >> (16-op.fields["shifts"])  #uhhh
#				t = t | l
				
#				self.accumulator_a = (t & 0xffff0000) >> 16
#				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "RSL":
#				self.accumulator_a = (self.accumulator_a >> op.fields["shifts"]) & 0xffff
#				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSL":
#				self.accumulator_a = (self.accumulator_a << op.fields["shifts"]) & 0xffff
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() << op.fields["shifts"])
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FLA": #fixme
#				t = ((((self.accumulator_a & 0x7fff) << 15) | (self.accumulator_b & 0x7fff)) << op.fields["shifts"]) & 0xffffffff
#				self.accumulator_a = (t & 0xffff0000) >> 16
#				self.accumulator_b = (t & 0x0000ffff)
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()
				
			elif op.nmemonic == "ASC":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() ^ 0x8000)
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAS":
				if self.registers["A Register"].read() == 0:
					self._increment_pc()
				elif self.registers["A Register"].read()> 0:
					self._increment_pc(2)
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "SAZ":
				if self.registers["A Register"].read() == 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAN":
				if self.registers["A Register"].read() < 0:
					self._increment_pc()
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "SAP":
				if self.registers["A Register"].read() > 0:
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
				self.registers["B Register"].write(self.registers["B Register"].read() + 1)
				if self.registers["B Register"].read()  == 0:
					self._increment_pc(2)
				else:
					self._increment_pc()
				self._increment_cycle_count(1)
					
			elif op.nmemonic == "ABA":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() & self.registers["B Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "OBA":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() | self.registers["B Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "LCS":
				self.registers["A Register"].write_raw(self.registers["Control Panel Switches"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)
			
			elif op.nmemonic == "SNO": #If bit Al does not equal bit AO of the A~Accurnulator, the next instruction is skipped
				if(self.registers["A Register"].read_raw() & 0x0001) != ((self.registers["A Register"].read_raw() * 0x0002) >> 1):
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
				self.registers["Program Counter"].raw_write(self.ram[self._next_pc()])
				self._increment_cycle_count(2)
				self._increment_pc(2)
				
			elif op.nmemonic == "OVS":
				self.overflow_flag = True
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "STX":
				indir = self.ram[self._next_pc()] & 0x4000
				idx = self.ram[self._next_pc()] & 0x8000
				addr = self.ram[self._next_pc()] & 0x3000
				
				if not indir:
					self.ram[addr] = self.registers["Index Register"].read()
					self._increment_cycle_count(2)
				else:
					self.ram[self.ram[addr].read()] = self.registers["Index Register"].read()
					self._increment_cycle_count(3) #GUESSING
				self._increment_pc(2)

			elif op.nmemonic == "TPB":
				self.registers["B Register"].write_raw(self.registers["Protect Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)
					
			elif op.nmemonic == "TBP":
\				self.registers["Protect Register"].write_raw(self.registers["B Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TBV":
				self.registers["VBR Register"].write_raw(self.registers["B Register"].read_raw())
				self._increment_pc()
				self._increment_cycle_count(1)
				
			elif op.nmemonic == "TVB":
				self.registers["B Register"].write_raw(self.registers["VBR Register"].read_raw())
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
				self.ram[address].write(self.registers["B Register"].read())
				self._increment_pc()
				self._increment_cycle_count(2)

			elif op.nmemonic == "IXS":
				if self.registers["Index Register"].read() + 1 > 0x7fff:
					self._increment_pc()
				self.registers["Index Register"].write(self.registers["Index Register"].read() + 1)
								
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TAX":
				self.registers["Index Register"].write(self.registers["A Register"].read())
				self._increment_pc()
				self._increment_cycle_count(1)

			elif op.nmemonic == "TXA":
				self.registers["A Register"].write(self.registers["Index Register"].read())
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
		for n,u in self.external_units.items():
			u._teardown()



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
		self.exit_flag = True
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
		print("program counter:\t0x%04x ('%06o)" % (self.cpu.registers["Program Counter"].read_raw(),self.cpu.registers["Program Counter"].read_raw()))
		print("accumulator a:\t\t0x%04x ('%06o)" % (self.cpu.registers["A Register"].read_raw(),self.cpu.registers["A Register"].read_raw()))
		print("accumulator b:\t\t0x%04x ('%06o)" % (self.cpu.registers["B Register"].read_raw(),self.cpu.registers["B Register"].read_raw()))
		print("\"index\":\t\t0x%04x ('%06o)" % (self.cpu.registers["Index Register"].read_raw(),self.cpu.registers["Index Register"].read_raw()))
		print("\"VBR\":\t\t\t0x%04x ('%06o)" % (self.cpu.registers["VBR Register"].read_raw(), self.cpu.registers["VBR Register"].read_raw()))
		print("\"Control Switches\":\t0x%04x ('%06o)" % (self.cpu.registers["Control Switches"].read_raw(),self.cpu.registers["Control Switches"].read_raw()))
		print("\"HALTED\":\t\t%s" % str(bool(self.cpu.halt_flag)))
		print("\"OVERFLOW\":\t\t%s" % str(bool(self.cpu.overflow_flag)))
		print("\"I\\O HOLD\":\t\t%s" % str(bool(self.cpu.IOwait_flag)))
		print("cyclecount:\t\t%dcycles or %fseconds" % (self.cpu.cyclecount, self.cpu.cyclecount * (1.0/CPU_HERTZ)))



	def postcmd(self,arg,b):
		print("ok (next op:%s)" % SELOPCODE(opcode=self.cpu.ram[self.cpu.registers["Program Counter"].read_raw()].read()).pack_asm()[0] )

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
		
		
		
		
class ASR33ExternalUnit(ExternalUnitHandler):
	power = True
	
	def handle_configure(self, val):
		print("ceu command!")
		if val & 0x0080: #power off
			self.power = False
			
		if val & 0x0100: #power on
			self.power = True
			
		if val & 0x0200: #clear
			pass
			
		if val & 0x0400: #key mode
			pass
			
		if val & 0x0800: #reader mode
			pass
			
		if val & 0x1000: #out
			pass
			
		if val & 0x2000: #in
			pass
			
		if val & 0x4000: #interrupt_connect
			pass
			
		self.wq.put(("c",ret))

	def handle_test(self, val):
		print("teu command!")
		ret = 0x22
		self.wq.put(("t",ret))


	def handle_ready(self, val):
		if self.power == False:
			if val == "r":
				self.wq.put(("?",self.rq.qsize() > 0))
			elif val in  ["w","c","t"]:
				if self.connected:
					self.wq.put(("?",True))
				else:
					self.wq.put(("?",False))
		else:
			self.wq.put(("?",False))
			

def serve_console(shell, socketname,host="0.0.0.0",port=9999):
	e = ASR33ExternalUnit(socketname,chardev=True)
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	s.bind((host, port))
	s.listen()
	print("started ASR33 7-bit telnet driver on %s:%d" % (host,port))
	while(1):
		conn, addr = s.accept()
		pollerrObject = select.poll()
		while(e.connected):
			pollerrObject.register(conn, select.POLLIN | select.POLLERR | select.POLLHUP)
			fdVsEvent = pollerrObject.poll(10)
			if e.pollread():
				conn.send(struct.pack("B",(e.read() ^ 0x80)))
				
			for descriptor, Event in fdVsEvent:
				if Event & (select.POLLERR | select.POLLHUP):
					print("socket closed")
					e.connected = False
					break
					
				if Event & select.POLLIN:
					e.write(ord(conn.recv(1)) | 0x80)


		
if __name__ == '__main__':
#	file= sys.argv[1]

	shell = SEL810Shell()
#while shell.exit_flag == False:
#	print("starting console on port 9999")
#	os.system("python ASR33OnTelnet.py&")
	thread = threading.Thread(target=serve_console, args=(shell, "/tmp/SEL810_asr33","0.0.0.0",9999))
	thread.start()

	print(shell.cmdloop())
