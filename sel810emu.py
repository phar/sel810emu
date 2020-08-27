import sys
import threading
import select
import socket
import time
import cmd
try:
    import readline
except ImportError:
    readline = None


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
		self.shutdown = False
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
			for descriptor, Event in serverfdVsEvent:
				connection, client_address = descriptor.accept()
				pollerObject = select.poll()
				pollerObject.register(connection, select.POLLIN| select.POLLOUT)

				while(1):#fixme
					try:
						fdVsEvent = pollerObject.poll(250)
						for descriptor, Event in fdVsEvent:
							if Event & ~select.POLLOUT:
								if len(self.write_buffer):
									connection.send(struct.pack("B",self.write_buffer[0]))
									self.write_buffer = self.write_buffer[1:]
									
							if Event & ~select.POLLIN:
								self.read_buffer.append(connection.recv(1))
					except:
						connection.close()
						break

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

	def unit_shutdown(self):
		print("%s external unit shutting down" % self.name)
		self.shutdown = True
		self.thread.join()

MAX_MEM_SIZE = 0x7fff


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
	
	def read_raw(self):
		return self.value

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
		
		print("%08d %s %s" % (self.prog_counter, mnemonic, ",".join(args)))

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
				self.prog_counter = address
			
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

			elif mnemonic == "LAA":
				self.accumulator_a =   self.ram[address]["read"]()
				self.prog_counter = (self.prog_counter + 1) & 0x7fff

			elif mnemonic == "LBA":
				self.accumulator_b =  self.ram[address]["read"]()
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
			for e in range(i,i+8 if (i+8)<=length else i + (length-i)):
				print("0x%04x "% self.cpu.ram[e].read_raw(),end="")
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
			for e in range(i,i+8 if (i+8)<=length else i + (length-i)):
				print("0o%06o "% self.cpu.ram[e].read_raw(),end="")
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
				(opcode, mnemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(self.cpu.ram[e].read_raw())
				print("0x%04x\t %s%s\t%s" % (e,mnemonic,indir,args))
			

	def do_registers(self,args):
		'show the current register contents'
		print("program counter: %s" % self.cpu.prog_counter)
		print("accumulator a: %s" % self.cpu.accumulator_a)
		print("accumulator b: %s" % self.cpu.accumulator_b)
		print("\"index\": %s" % self.cpu.get_index())
		if self.cpu.type == SEL810BTYPE:
			print("hardware index register: %s" % self.cpu.hw_index_register)



	def postcmd(self,arg,b):
		print("ok")

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
	file= sys.argv[1]

shell = SEL810Shell()
#while shell.exit_flag == False:
print(shell.cmdloop())
