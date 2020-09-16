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
			serverfdVsEvent = serverpollerObject.poll(10000)
			for adescriptor, aEvent in serverfdVsEvent:
				connection, client_address = self.sock.accept()
				self.connected = True
				pollerObject = select.poll()
				pollerObject.register(connection, select.POLLIN | select.POLLOUT | select.POLLERR | select.POLLHUP)
				connection.setblocking(0)
				while(1):#fixme
#					try:
					fdVsEvent = pollerObject.poll(10000)
					for descriptor, Event in fdVsEvent:
						if Event & select.POLLOUT:
#								print("SS")
							if len(self.write_buffer):
#								print("pollout")
								connection.send(struct.pack("B",self.write_buffer[0]))
								self.write_buffer = self.write_buffer[1:]
								
						if Event & (select.POLLERR | select.POLLHUP):
							self.connected = False
#							print("werre")
							connection.close()
							break
							
						if Event & select.POLLIN:
#							print("pollin")
							print(self.write_buffer)
							self.read_buffer.append(connection.recv(1))
#					except:
#						self.connected = False
#						connection.close()
#						break
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


class RAM_CELL():
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
	
	def read_raw(self):
		return self.value

	def write_raw(self,v):
		self.value = v
		self.parity = parity_calc(self.value)
	
	def write(self,v):
		self.value = dec2twoscmplment(v)
		self.parity = parity_calc(self.value)
		return self.value
		
	

SEL810ATYPE = 0
SEL810BTYPE = 1

class SEL810CPU():
	def __init__(self,type= SEL810ATYPE):
		self.ram = [RAM_CELL() for x in range(MAX_MEM_SIZE)]
		self.type = SEL810ATYPE
		self.external_units = [ExternalUnit("nulldev"),ExternalUnit("asr33",chardev=True),ExternalUnit("paper tape",chardev=True),ExternalUnit("card punch",chardev=True),ExternalUnit("card reader",chardev=True),ExternalUnit("line printer",chardev=True),ExternalUnit("TCU 1"),ExternalUnit("TCU 2"),ExternalUnit("INVALID 1"),ExternalUnit("INVALID 2"),ExternalUnit("typewriter"),ExternalUnit("X-Y plotter"),ExternalUnit("interval timer"),ExternalUnit("movable head disc"),ExternalUnit("CRT"),ExternalUnit("fixed head disc")]
		
		self.prog_counter = 0
		self.instr_register = 0
		self.hw_index_register = 0
		self.accumulator_a = 0
		self.accumulator_b = 0
		self.protect_register = 0
		self.vbr = 0
		
		self.t_register = 0
		
		self.halt_flag = True #start halted
		self.IOwait_flag = False
		self.interrupt_flag = False
		self.overflow_flag = False
		self.control_switches = 0
		self.cyclecount = 0

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
			
	def _increment_pc(self):
		self.prog_counter = (self.prog_counter + 1 ) & 0x7fff

	def panelswitch_single_cycle(self):
		op  = SELOPCODE(opcode=self.ram[self.prog_counter].read())
		if op.nmemonic in SEL810_OPCODES:
			if SEL810_OPCODES[op.nmemonic][0] == SEL810_MREF_OPCODE:
				indir = op.fields["i"]
				map = op.fields["m"]
				address = op.fields["address"]

				if indir:
					print("-> %d"% self.ram[address].read_raw())
					address = self.ram[address].read()
				
				if op.nmemonic == "LAA":
					print("foo",(address + (op.fields["x"] * self.get_index())), self.get_index())
					self.accumulator_a = self.ram[(address + (op.fields["x"] * self.get_index())) & 0x7fff].read()
					self._increment_pc()

				elif op.nmemonic == "LBA":
					self.accumulator_b = self.ram[(address + (op.fields["x"] * self.get_index())) & 0x7fff].read()
					self._increment_pc()
					
				elif op.nmemonic == "STA":
					self.ram[address].write(self.accumulator_a)
					self._increment_pc()

				elif op.nmemonic == "STB":
					self.ram_write(address, self.accumulator_b)
					self._increment_pc()
					
				elif op.nmemonic == "AMA":
					if self.accumulator_a + self.ram[address].read() > 0xffff:
						self.overflow_flag = True
					self.accumulator_a =  (self.accumulator_a + self.ram[address].read()) & 0xffff
					self._increment_pc()
					self.cyclecount += 2

				elif op.nmemonic == "SMA":
					if self.accumulator_a - self.ram[address].read() < 0:
						self.overflow_flag = True
					self.accumulator_a =  (self.accumulator_a + self.ram[address].read()) & 0xffff
					self._increment_pc()
					self.cyclecount += 2

				elif op.nmemonic == "MPY":
					if self.accumulator_a * self.ram[address].read() < 0:
							self.overflow_flag = True
						self.accumulator_a =  (self.accumulator_a * self.ram[address].read()) & 0xffff
						self._increment_pc()
						self.cyclecount += 6

				elif op.nmemonic == "DIV": #fixme
					self._increment_pc()
								
				elif op.nmemonic == "BRU":
					self.prog_counter = (address + ( op.fields["x"] * self.get_index())) & 0x7fff
					self.cyclecount += 1
					
				elif op.nmemonic == "SPB":
					self.ram[address].write((self.prog_counter + 1) & 0x7fff)
					self.prog_counter = address
					self._increment_pc()
					self.cyclecount +=2

				elif op.nmemonic == "IMS":
					t = self.ram[address]["read"]()+1
					self.ram[address].write(t)
					if t == 0:
						self._increment_pc()
					self._increment_pc()
					self.cyclecount += 3

				elif op.nmemonic == "CMA":
					if self.accumulator_a == self.ram[address].read():
						self._increment_pc() #the next instruction is skipped.
					elif self.accumulator_a > self.ram[address].read():
						self._increment_pc() #the next two instructions are skipped.
						self._increment_pc()
					self._increment_pc()
					self.cyclecount += 3

				elif op.nmemonic == "AMB":
					self.accumulator_b =  self.accumulator_b + self.ram[address].read()
					self._increment_pc()
		
			elif SEL810_OPCODES[op.nmemonic][0] == SEL810_IO_OPCODE:
				merge = op.fields["r"]
				wait = op.fields["wait"]
		 
				if op.nmemonic == "CEU":
					self.IOwait_flag = True
					self.external_units[op.fields["unit"]].unit_command(self.ram[self.prog_counter + 1].read())
					self.IOwait_flag = False
					self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word
					self.cyclecount += 4

				elif op.nmemonic == "TEU":
					self.IOwait_flag = True
					self.accumulator_a = self.external_units[op.fields["unit"]].unit_test(self.ram[self.prog_counter+ 1].read())
					self.IOwait_flag = False
					self.prog_counter = (self.prog_counter + 2) & 0x7fff #second word
					self.cyclecount += 4


				elif op.nmemonic == "SNS":
					if self.control_switches & (1 << op.fields["unit"]):
						self._increment_pc()
					else: #if switch is NOT set, the next instruction is skipped.
						self._increment_pc()
						self._increment_pc()
					self.cyclecount += 1
	
				elif op.nmemonic == "AIP":
					self.IOwait_flag = True
					try:
						self.accumulator_a = (self.accumulator_a * merge) + self.external_units[op.fields["unit"]].unit_read(wait)
						if not wait:
							self.prog_counter = (self.prog_counter + 2) & 0x7fff
					except ExternalUnitNotConnected:
						self._increment_pc()
					self.IOwait_flag = False
					self.cyclecount += 4

				elif op.nmemonic == "AOP":
					self.IOwait_flag = True
					self.external_units[op.fields["unit"]].unit_write(self.accumulator_a)
					self.IOwait_flag = False
					self._increment_pc()
					self.cyclecount += 4

				elif op.nmemonic == "MIP":
					self.IOwait_flag = True
					self.accumulator_a = ord(self.external_units[op.fields["unit"]].unit_read())
					self.IOwait_flag = False
					self._increment_pc()
					self.cyclecount += 4

				elif op.nmemonic == "MOP":
					self.IOwait_flag = True
					print("mop", self.ram[(self.prog_counter + 1) & 0x7fff].read())
					self.external_units[op.fields["unit"]].unit_write(self.ram[(self.prog_counter + 1) & 0x7fff].read())
					self.IOwait_flag = False
					self._increment_pc()
					self._increment_pc()
					self.cyclecount += 4
			
			elif SEL810_OPCODES[op.nmemonic][0] == SEL810_AUGMENTED_OPCODE:

				augmentcode = op.fields["augmentcode"]

				if op.nmemonic == "HLT":
					pass
				elif op.nmemonic == "RNA":
					if self.accumulator_b & 0x4000:
						if self.accumulator_a + 1 > 0x7fff:
							self.overflow_flag = True
						self.accumulator_a =  (self.accumulator_a + 1) & 0x7fff
					self._increment_pc()
					self.cyclecount += 1
					
				elif op.nmemonic == "NEG":
					self._increment_pc()
					
				elif op.nmemonic == "CLA":
					self._increment_pc()
					
				elif op.nmemonic == "TBA":
					 self.accumulator_a = self.accumulator_b
					 self.cyclecount += 1
					 self._increment_pc()
					 
				elif op.nmemonic == "TAB":
					self.accumulator_b = self.accumulator_a
					self.cyclecount += 1
					self._increment_pc()

				elif op.nmemonic == "IAB":
					t = self.accumulator_a
					self.accumulator_a = self.accumulator_b
					self.accumulator_b = t
					self._increment_pc()
					self.cyclecount += 1
					
				elif op.nmemonic == "CSB":
					if self.accumulator_b & 0x8000:
						self.carry_flag = True
					else:
						self.carry_flag = False
					self.accumulator_b &= 0x7fff
					self._increment_pc()
					self.cyclecount += 1
					
				elif op.nmemonic == "RSA":
					self._increment_pc()
					
				elif op.nmemonic == "LSA":
					self._increment_pc()
					
				elif op.nmemonic == "FRA":
					self._increment_pc()
					
				elif op.nmemonic == "FLL":
					t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"]) & 0xffffffff
					self.accumulator_a = (t & 0xffff0000) >> 16
					self.accumulator_b = (t & 0x0000ffff)
					if 0 > op.fields["shifts"] and op.fields["shifts"] < 5:
						self.cyclecount += 2
					elif 4 > op.fields["shifts"] and op.fields["shifts"] < 9:
						self.cyclecount += 3
					elif 8 > op.fields["shifts"] and op.fields["shifts"] < 13:
						self.cyclecount += 4
					elif 13 > op.fields["shifts"] and op.fields["shifts"] < 16:
						self.cyclecount += 5
					self._increment_pc()
					
				elif op.nmemonic == "FRL":
					t = (((self.accumulator_a << 16) | self.accumulator_b) << op.fields["shifts"])
					l = (t ^ 0xffffffff) >> (16-op.fields["shifts"])  #uhhh
					t = t | l
					
					self.accumulator_a = (t & 0xffff0000) >> 16
					self.accumulator_b = (t & 0x0000ffff)
					if 0 > op.fields["shifts"] and op.fields["shifts"] < 5:
						self.cyclecount += 2
					elif 4 > op.fields["shifts"] and op.fields["shifts"] < 9:
						self.cyclecount += 3
					elif 8 > op.fields["shifts"] and op.fields["shifts"] < 13:
						self.cyclecount += 4
					elif 13 > op.fields["shifts"] and op.fields["shifts"] < 16:
						self.cyclecount += 5
					self._increment_pc()
					
				elif op.nmemonic == "RSL":
					self.accumulator_a = (self.accumulator_a >> op.fields["shifts"]) & 0xffff
					if 0 > op.fields["shifts"] and op.fields["shifts"] < 5:
						self.cyclecount += 2
					elif 4 > op.fields["shifts"] and op.fields["shifts"] < 9:
						self.cyclecount += 3
					elif 8 > op.fields["shifts"] and op.fields["shifts"] < 13:
						self.cyclecount += 4
					elif 13 > op.fields["shifts"] and op.fields["shifts"] < 16:
						self.cyclecount += 5
					self._increment_pc()
					
				elif op.nmemonic == "LSL":
					self.accumulator_a = (self.accumulator_a << op.fields["shifts"]) & 0xffff
					if 0 > op.fields["shifts"] and op.fields["shifts"] < 5:
						self.cyclecount += 2
					elif 4 > op.fields["shifts"] and op.fields["shifts"] < 9:
						self.cyclecount += 3
					elif 8 > op.fields["shifts"] and op.fields["shifts"] < 13:
						self.cyclecount += 4
					elif 13 > op.fields["shifts"] and op.fields["shifts"] < 16:
						self.cyclecount += 5
					self._increment_pc()
					
				elif op.nmemonic == "FLA": #fixme
					t = ((((self.accumulator_a & 0x7fff) << 15) | (self.accumulator_b & 0x7fff)) << op.fields["shifts"]) & 0xffffffff
					self.accumulator_a = (t & 0xffff0000) >> 16
					self.accumulator_b = (t & 0x0000ffff)
					if 0 > op.fields["shifts"] and op.fields["shifts"] < 5:
						self.cyclecount += 2
					elif 4 > op.fields["shifts"] and op.fields["shifts"] < 9:
						self.cyclecount += 3
					elif 8 > op.fields["shifts"] and op.fields["shifts"] < 13:
						self.cyclecount += 4
					elif 13 > op.fields["shifts"] and op.fields["shifts"] < 16:
						self.cyclecount += 5
					self._increment_pc()
					
				elif op.nmemonic == "ASC":
					self.accumulator_a ^= 0x8000
					self._increment_pc()
					
				elif op.nmemonic == "SAS":
					if self.accumulator_a == 0:
						self._increment_pc()
					elif self.accumulator_a > 0:
						self._increment_pc()
						self._increment_pc()
					self._increment_pc()

				elif op.nmemonic == "SAZ":
					if self.accumulator_a == 0:
						self.prog_counter = self.prog_counter + 1
					self._increment_pc()
					
				elif op.nmemonic == "SAN":
					if self.accumulator_a < 0:
						self._increment_pc()
					self._increment_pc()
					
				elif op.nmemonic == "SAP":
					if self.accumulator_a > 0:
						self._increment_pc()
					self._increment_pc()

				elif op.nmemonic == "SOF":
					if self.overflow_flag == True:#If the arithmetic overflow latch is set, it is reset and the next instruction is executed;
						self.overflow_flag = False
					else: #if the latch is reset, the next instruction is skipped.
						self._increment_pc()
					self._increment_pc()
					self.cyclecount += 1

				elif op.nmemonic == "IBS":
					self.accumulator_b =  (self.accumulator_b + 1) & 0xffff
					if self.accumulator_b  == 0:
						self.prog_counter = (self.prog_counter + 2) & 0x7fff
					else:
						self._increment_pc()
						
				elif op.nmemonic == "ABA":
					self.accumulator_a =  self.accumulator_a & self.accumulator_b
					self._increment_pc()

				elif op.nmemonic == "OBA":
					self.accumulator_a =  (self.accumulator_a & self.accumulator_b) & 0xffff
					self._increment_pc()
					
				elif op.nmemonic == "LCS":
					self.accumulator_a =  self.control_switches
					self._increment_pc()
				
				elif op.nmemonic == "SNO": #If bit Al does not equal bit AO of the A~Accurnulator, the next instruction is skipped
					if(self.accumulator_a & 0x0001) != ((self.accumulator_a & 0x0002) >> 1):
						self._increment_pc()
					self._increment_pc()
					self.cyclecount += 1
	
				elif op.nmemonic == "NOP":
					self._increment_pc()
					self.cyclecount += 1
					
				elif op.nmemonic == "CNS":
					self._increment_pc()
					
				elif op.nmemonic == "TOI":
					self._increment_pc()
					
				elif op.nmemonic == "LOB":
					self._increment_pc()
					
				elif op.nmemonic == "OVS":
					self._increment_pc()
					
				elif op.nmemonic == "STX":
					self.cyclecount += 1
					self._increment_pc()
										
				elif op.nmemonic == "TPB":
					self.accumulator_b = self.protect_register
					self._increment_pc()
					self.cyclecount += 1
						
				elif op.nmemonic == "TBP":
					self.protect_register = self.accumulator_b
					self._increment_pc()
					self.cyclecount += 1

				elif op.nmemonic == "TBV":
					self.vbr =  self.accumulator_b
					self._increment_pc()
					self.cyclecount += 1
					
				elif op.nmemonic == "TVB":
					self.accumulator_b = self.vbr
					self._increment_pc()
					self.cyclecount += 1

				elif op.nmemonic == "LIX":
					self.cyclecount += 2
					self._increment_pc()
					
				elif op.nmemonic == "XPX":
					self._increment_pc()
				elif op.nmemonic == "XPB":
					self._increment_pc()
					
				elif op.nmemonic == "STB":
					self.ram[address].write(self.accumulator_b)
					self._increment_pc()
					self.cyclecount += 2

				elif op.nmemonic == "ISX":
					self._increment_pc()
					
				elif op.nmemonic == "TAZ":
					self._increment_pc()
					
				elif op.nmemonic == "TXA":
					self.accumulator_a = self.hw_index_register
					self._increment_pc()
	

	
			elif SEL810_OPCODES[op.nmemonic][0] == SEL810_INT_OPCODES:
				print(args)

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
		addr = int(addr) # fixme, should be flexible
		self.cpu.loadAtAddress(addr,file)

	def do_setpc(self,arg):
		'set the program counter to a specific memory location'
		try:
			(progcnt,) = arg.split(" ")
		except ValueError:
			print("not enough arguments provided")
			return False
		
		progcnt = int(progcnt) # fixme, should be flexible
		self.cpu.set_program_counter(progcnt)

	def do_quit(self,args):
		'exit the emulator'
		self.cpu.shutdown()
		return True
		
	def do_hexdump(self,arg):
		'hexdump SEL memory, hexdump [offset] [length]'
		try:
			(offset,length) = arg.split(" ")
			offset = int(offset)
			length = int(length)
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
			offset = int(offset)
			length = int(length)
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
			offset = int(offset)
			length = int(length)
		except ValueError:
			print("not enough arguments provided")
			return False

		for i in range(offset,offset+length,8):
			for e in range(i,i+8 if (i+8)<=length else i + (length-i)):
				op = SELOPCODE(opcode=self.cpu.ram[e].read_raw())
#				(opcode, mnemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(self.cpu.ram[e].read_raw())
#				print("0x%04x\t %s%s\t%s" % (e,mnemonic,indir,args))
				print("'%06o" % e, op.pack_asm()[0])
			

	def do_registers(self,args):
		'show the current register contents'
		print("program counter: 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.prog_counter),dec2twoscmplment(self.cpu.prog_counter)))
		print("accumulator a: 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.accumulator_a),dec2twoscmplment(self.cpu.accumulator_a)))
		print("accumulator b: 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.accumulator_b),dec2twoscmplment(self.cpu.accumulator_b)))
		print("\"index\": 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.get_index()), dec2twoscmplment(self.cpu.get_index())))
		if self.cpu.type == SEL810BTYPE:
			print("hardware index register: 0x%04x ('%06o)" % (dec2twoscmplment(self.cpu.hw_index_register),dec2twoscmplment(self.cpu.hw_index_register)))



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
