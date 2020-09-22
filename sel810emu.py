import sys
import threading,queue
import select
import socket
import time
import cmd
import os
import json
from SELDeviceDriver import *
from ASR33OnTelnet import *
from cpserver import *
#
#TODO
#  interrupts
#  variable base register
#  BTC block transfer controller
#
#Maximum Number of BTC's per Computer  8
#Maximum Number of CGP's per Computer   6
#Maximum Number of Peripheral Devices per BTC  16
#RAM should save out to a non-volatile file since the core memory is
#join threads on exit
#
#


try:
    import readline
except ImportError:
    readline = None


sys.path.append("sel810asm")
from util import *
from MNEMBLER2 import *



CPU_HERTZ = 572000



class SELBTCDriver():
	def __init__(self, cpu, baseaddr):
		self.current_word_address;
		self.word_count
		self.baseaddr = baseaddr
		self.cpu = cpu

	def update_from_memory(self):
		self.current_word_address = self.cpu.ram[self.baseaddr].read()
		self.word_count = self.cell0[self.baseaddr+1].read()

	def transfer(self):
		pass
		

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
		self._shutdown = False
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
		servpoller = select.poll()
		servpoller.register(self.sock, select.POLLIN )
		while(self.cpu._shutdown == False and self._shutdown == False):
				sfdVsEvent = servpoller.poll(1)
				if len(sfdVsEvent):
					descriptor, sEvent = sfdVsEvent[0]
					if sEvent & select.POLLIN:
						self.devsock, client_address = self.sock.accept()
						self.connected = True
						pollerrObject = select.poll()
						pollerrObject.register(self.devsock, select.POLLIN | select.POLLERR | select.POLLHUP)
						while(self.connected == True and self._shutdown == False and self._shutdown == False):
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
										elif t == 'i': #interrupt
											pass

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
		self.cpu.IOwait_flag = False
		return self.w
				
	def _teardown(self):
		print("%s external unit shutting down" % self.name)
		self._shutdown = True
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
		self.cpcmdqueue = queue.Queue()
		self._shutdown = False

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
				"Instruction":RAM_CELL(),
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

		self.t_register = 0
	
		self.latch = {	"halt":True,#start halted
						"iowait":False,
						"overflow":False,
						"index_pointer":False}
		
		self.load_core_memory()
		
		
		self.cpthread = threading.Thread(target=control_panel_backend, args=(self,))
		self.cpthread.start()

		
	def store_core_memory(self):
		coredata = []
		for i in range(MAX_MEM_SIZE):
			coredata.append(self.ram[i].read_raw())
		storeProgramBin("sel810.coremem",coredata)

	def load_core_memory(self):
		try:
			self.loadAtAddress(0,"sel810.coremem")
		except: #if we cant load the file, no worries
			pass

	def _increment_pc(self,incrnum=1):
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
	
	def fire_pf_restore_interrupt(self):
		self._SPB_indir_opcode(0o1000, True)
		
	def fire_stall_interrupt(self):
		self._SPB_indir_opcode(0o1001, True)

	def fire_priority_interrupt(self,group,channel):
		self._SPB_indir_opcode(0o1002 + (group * 12) + channel, True)
		
	def _SPB_indir_opcode(self,address): #fixme
		#fixme
		address = self.ram[address].read()

		self.ram[address].write(self._next_pc())
		self.registers["Program Counter"].write_raw(address)
		self._increment_cycle_count(2)
		self._increment_pc()


	def panelswitch_step_neg_edge(self):
		self.registers["Instruction"].write_raw(self.ram[self.registers["Program Counter"].read_raw()].read_raw())



	def panelswitch_step_pos_edge(self):
		op  = SELOPCODE(opcode=self.registers["Instruction"].read_raw())
		if op.nmemonic in SEL810_OPCODES:
		
			if "address" in op.fields:
#				map = op.fields["m"]  #left as a reminder
				address = op.fields["address"]
				if op.fields["i"]:
					address = self.ram[address].read()
				
			if op.nmemonic == "LAA":
				self.registers["A Register"].write_raw(self.ram[(address + (op.fields["x"] * self.registers["Index Register"].read())) & MAX_MEM_SIZE].read_raw())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "LBA":
				self.registers["B Register"].write_raw(self.ram[(address + (op.fields["x"] * self.registers["Index Register"].read())) & MAX_MEM_SIZE].read())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "STA":
				self.ram[address].write_raw(self.registers["A Register"].read_raw())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "STB":
				self.ram[address].write_raw(self.registers["B Register"].read_raw())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "AMA": ##CARRY
				if (self.registers["A Register"].read() + self.ram[address].read()) > 0xffff:
					self.latch["overflow"] = True
				self.registers["A Register"].write (self.registers["A Register"].read() + self.ram[address].read())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "SMA": #CARRY
				if (self.registers["A Register"].read() - self.ram[address].read()) < 0:
					self.latch["overflow"] = True
				self.registers["A Register"].write(self.registers["A Register"].read() - self.ram[address].read())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "MPY":
				if self.registers["A Register"].read() * self.ram[address].read() < 0:
					self.latch["overflow"] = True
				self.registers["A Register"].write(self.registers["A Register"].read() * self.ram[address].read())
				self._increment_cycle_count(6)
				self._increment_pc()

			elif op.nmemonic == "DIV":
				if  self.ram[address].read() != 0: #fixme overflow is wrong
					a = (self.registers["A Register"].read() << 16 | self.registers["B Register"].read()) / self.ram[address].read()
					b = (self.registers["A Register"].read() << 16 | self.registers["B Register"].read()) % self.ram[address].read()
					self.registers["A Register"].write(a)
					self.registers["B Register"].write(b)
				else:
					self.latch["overflow"] = True
				self._increment_cycle_count(11)
				self._increment_pc()
							
			elif op.nmemonic == "BRU":
				self.registers["Program Counter"].write_raw(address + ( op.fields["x"] * self.registers["Index Register"].read()))
				self._increment_cycle_count(2)
				
			elif op.nmemonic == "SPB":
				self.ram[address].write(self._next_pc())
				self.registers["Program Counter"].write_raw(address)
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "IMS":
				t = (self.ram[address]["read"]() + 1) & 0xffff
				self.ram[address].write(t)
				if t == 0:
					self._increment_pc()
				self._increment_cycle_count(3)
				self._increment_pc()

			elif op.nmemonic == "CMA":
				if self.registers["A Register"].read() == self.ram[address].read():
					self._increment_pc() #the next instruction is skipped.
				elif self.registers["A Register"].read() > self.ram[address].read():
					self._increment_pc(2) #the next two instructions are skipped.
				self._increment_cycle_count(3)
				self._increment_pc()

			elif op.nmemonic == "AMB":
				if  (self.registers["B Register"].read() + self.ram[address].read()) > 0x7fff:
					self.latch["overflow"] = True
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
				self._increment_cycle_count(4)
				self._increment_pc()

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
				self._increment_cycle_count(4)
				self._increment_pc()

			elif op.nmemonic == "SNS":
				if self.registers["Control Switches"].read() & (1 << op.fields["unit"]):
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
				self._increment_cycle_count(4)
				self._increment_pc()

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
				self._increment_cycle_count(4)
				self._increment_pc()

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
				self._increment_cycle_count(4)
				self._increment_pc()

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
				self._increment_cycle_count(4)
				self._increment_pc(2)

			elif op.nmemonic == "HLT":
				self.latch["halt"] = True
				self._increment_cycle_count()

			elif op.nmemonic == "RNA":
				if self.registers["B Register"].read_raw() & 0x4000:
					if (self.registers["A Register"].raw_read() + 1) > 0x7fff:
						self.latch["overflow"] = True
					self.registers["A Register"].write(self.registers["A Register"].read() + 1)
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "NEG": #fixme
				self.registers["A Register"].write(self.registers["B Register"].raw_read()) #twoscomplement applied on write()
				self._increment_cycle_count()
				self._increment_pc()

			elif op.nmemonic == "CLA":
				self.registers["A Register"].write(0)
				self._increment_cycle_count()
				self._increment_pc()

			elif op.nmemonic == "TBA":
				self.registers["A Register"].write(self.registers["B Register"].read())
				self._increment_cycle_count(1)
				self._increment_pc()
				 
			elif op.nmemonic == "TAB":
				self.registers["B Register"].write(self.registers["A Register"].read())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "IAB":
				t = self.registers["A Register"].read()
				self.registers["A Register"].write(self.registers["B Register"].read())
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
				s  = self.registers["A Register"].read_raw() & 0x8000
				for i in op.fields["shifts"]:
					self.registers["A Register"].write_raw(s | (self.registers["A Register"].read_raw() >> 1))
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSA":
				s  = self.registers["A Register"].read_raw() & 0x8000
				self.registers["A Register"].write_raw(s | ((self.registers["A Register"].read_raw() << op.fields["shifts"]) & 0x7fff))
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRA":
				s1  = self.registers["A Register"].read_raw() & 0x8000
				s2  = self.registers["B Register"].read_raw() & 0x8000
				r = ((self.registers["A Register"].read_raw() & 0x7fff) << 15) | (self.registers["B Register"].read_raw() & 0x7fff)
				for i in op.fields["shifts"]:
					r = s1 | (r >> 1)
				self.registers["A Register"].write_raw(s1 | ((r >> 15) & 0x7fff))
				self.registers["B Register"].write_raw(s2 | (r & 0x7fff))
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FLL":
				t = (((self.registers["A Register"].read_raw() << 16) | self.registers["B Register"].read_raw()) << op.fields["shifts"]) & 0xffffffff
				self.registers["A Register"].write_raw((t  >> 16) & 0xffff)
				self.registers["B Register"].write_raw((t & 0xffff))
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FRL":
				for i in range(op.fields["shifts"]):
					t = (((self.registers["A Register"].read_raw() << 16) | self.registers["B Register"].read_raw()) << 1)
					b = t & (0x10000) >> 16
					t = t | b
				self.registers["A Register"].write_raw((t  >> 16) & 0xffff)
				self.registers["B Register"].write_raw((t & 0xffff))
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "RSL":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() >> op.fields["shifts"])
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "LSL":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() << op.fields["shifts"])
				self._shift_cycle_timing(op.fields["shifts"])
				self._increment_pc()

			elif op.nmemonic == "FLA": #fixme
				s1  = self.registers["A Register"].read_raw() & 0x8000
				s2  = self.registers["B Register"].read_raw() & 0x8000
				r = ((((self.registers["A Register"].read_raw() & 0x7fff) << 15) | (self.registers["B Register"].read_raw() & 0x7fff))  << op.fields["shifts"]) & 0xffffffff
				self.registers["A Register"].write_raw(s1 | ((r >> 15) & 0x7fff))
				self.registers["B Register"].write_raw(s2 | (r & 0x7fff))
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
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "SAN":
				if self.registers["A Register"].read() < 0:
					self._increment_pc()
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "SAP":
				if self.registers["A Register"].read() > 0:
					self._increment_pc()
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "SOF":
				if self.latch["overflow"] == True:#If the arithmetic overflow latch is set, it is reset and the next instruction is executed;
					self.latch["overflow"] = False
				else: #if the latch is reset, the next instruction is skipped.
					self._increment_pc()
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "IBS":
				self.registers["B Register"].write(self.registers["B Register"].read() + 1)
				if self.registers["B Register"].read()  == 0:
					self._increment_pc(2)
				else:
					self._increment_pc()
				self._increment_cycle_count(1)
					
			elif op.nmemonic == "ABA":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() & self.registers["B Register"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "OBA":
				self.registers["A Register"].write_raw(self.registers["A Register"].read_raw() | self.registers["B Register"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "LCS":
				self.registers["A Register"].write_raw(self.registers["Control Panel Switches"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "SNO": #If bit Al does not equal bit AO of the A~Accurnulator, the next instruction is skipped
				if(self.registers["A Register"].read_raw() & 0x0001) != ((self.registers["A Register"].read_raw() * 0x0002) >> 1):
					self._increment_pc()
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "NOP":
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "CNS":
				self._increment_cycle_count(1)
				self._increment_pc()
				
			elif op.nmemonic == "TOI":
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "LOB":
				self.registers["Program Counter"].write_raw(self.ram[self._next_pc()])
				self._increment_cycle_count(2)
				self._increment_pc(2)
				
			elif op.nmemonic == "OVS":
				self.latch["overflow"] = True
				self._increment_cycle_count(1)
				self._increment_pc()

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
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "TBP":
				self.registers["Protect Register"].write_raw(self.registers["B Register"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "TBV":
				self.registers["VBR Register"].write_raw(self.registers["B Register"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "TVB":
				self.registers["B Register"].write_raw(self.registers["VBR Register"].read_raw())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "LIX": #fixme
				self._increment_cycle_count(2)
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "XPX":
				self.latch["index_pointer"] = True
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "XPB":
				self.latch["index_pointer"] = False
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "SXB":
				self.ram[address].write(self.registers["B Register"].read())
				self._increment_cycle_count(2)
				self._increment_pc()

			elif op.nmemonic == "IXS":
				if self.registers["Index Register"].read() + 1 > 0x7fff:
					self._increment_pc()
				self.registers["Index Register"].write(self.registers["Index Register"].read() + 1)
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "TAX":
				self.registers["Index Register"].write(self.registers["A Register"].read())
				self._increment_cycle_count(1)
				self._increment_pc()

			elif op.nmemonic == "TXA":
				self.registers["A Register"].write(self.registers["Index Register"].read())
				self._increment_cycle_count()
				self._increment_pc()

			elif op.nmemonic == "PID":
				self._increment_pc()
				
			elif op.nmemonic == "PIE":
				self._increment_pc()
		else:
			pass
			
			
	def get_cpu_state(self):
		state_struct = {}
		for n,v in self.registers.items():
			state_struct[n] = v.read_raw()
		for n,v in self.latch.items():
			state_struct[n] = v
		state_struct["cyclecount"] = self.cyclecount
		return state_struct


	def set_cpu_state(self,state_struct):
		for n,v in self.registers.items():
			if n in state_struct:
				self.registers[n].write_raw(state_struct[n])
				
		for n,v in self.latch.items():
			if n in state_struct:
				self.latch[n].write_raw (state_struct[n])

	def loadAtAddress(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.ram[address+i].write_raw(binfile[i])
			
	def shutdown(self):
		self._shutdown = True
		self.cpthread.join()
		for n,u in self.external_units.items():
			u._teardown()
		self.store_core_memory()



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

def control_panel_backend(cpu):
	while cpu._shutdown == False:
		if cpu.cpcmdqueue.qsize():
			(c, data) = cpu.cpcmdqueue.get()
			if c == "s":
				for i in range(data):
					cpu.panelswitch_step_neg_edge()
					cpu.panelswitch_step_pos_edge()
					print("(next op:%s)" % SELOPCODE(opcode=cpu.ram[cpu.registers["Program Counter"].read_raw()].read()).pack_asm()[0] ) #probably not the way to do this anymore

			elif c == "u":
				cpu.set_cpu_state(data)
				
			elif c == "l":
				(addr,file) = data
				cpu.loadAtAddress(addr,file)
				
			elif c == "h+":
				cpu.latch["halt"] = True

			elif c == "h-":
				cpu.latch["halt"] = False

			elif c == "q":
				running = False
				
		if not cpu.latch["halt"]:
			cpu.panelswitch_step_neg_edge()
			cpu.panelswitch_step_pos_edge()
			
		else:
			time.sleep(.1)
		

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
		if len(arg.split(" ")) > 1:
			steps = parse_inputint(arg.split(" ")[0])
		else:
			if arg != "":
				steps = parse_inputint(arg)
			else:
				steps = 1
		
		self.cpu.cpcmdqueue.put(("s",steps))

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
		self.cpu.cpcmdqueue.put(("l",(addr,file)))


	def do_setpc(self,arg):
		'set the program counter to a specific memory location'
		try:
			(progcnt,) = arg.split(" ")
		except ValueError:
			print("not enough arguments provided")
			return False
		
		progcnt = parse_inputint(progcnt) # fixme, should be flexible
		self.cpu.cpcmdqueue.put(("u",{"Program Counter":33}))

	def do_quit(self,args):
		'exit the emulator'
		self.exit_flag = True
		self.cpu.cpcmdqueue.put(("q",None))
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

	def do_halt(self,arg):
		'halt running cpu'
		self.cpu.cpcmdqueue.put(("h+",None))
		
		
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


	shell = SEL810Shell()
	
	telnet = ASR33OnTelnetDriver(shell.cpu, "/tmp/SEL810_asr33","0.0.0.0",9999)
	cp  = ControlPanelDriver(shell.cpu,"/tmp/control_panel")
	cp.start()
	telnet.start()
	shell.cmdloop()

	telnet.stop()
	cp.stop()
