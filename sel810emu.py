import sys

sys.path.append("sel810asm")
from sel810dis import *

class ExternalUnit():
	def __init__(self,name):
		self.name = name
		self.read_buffer = [ord("h"),ord("e"),ord("l"),ord("l"),ord("o"),ord("w"),ord("o"),ord("r"),ord("l"),ord("d")]
		self.write_buffer = []

	def unit_command(self,command):
		print("%s command %d" % (self.name,command))

	def unit_test(self,command):
		print("%s test %d" % (self.name,command))


	def unit_write(self,data):
		print("%s write %d" % (self.name,data))
		self.write_buffer.append(data)

	def unit_read(self):
		t = self.read_buffer[0]
		self.read_buffer = self.read_buffer[1:]
		print("%s read %d" % (self.name,t))
		return t


class SEL810CPU():
	def __init__(self):
		self.ram = [0] *  0xffff  #im just going to make this a 1:1 mapping even though most locations wont get used
		self.external_units = [ExternalUnit("nulldev"),ExternalUnit("asr33"),ExternalUnit("paper tape"),ExternalUnit("card punch"),ExternalUnit("card reader"),ExternalUnit("line printer"),ExternalUnit("TCU 1"),ExternalUnit("TCU 2"),ExternalUnit("INVALID 1"),ExternalUnit("INVALID 2"),ExternalUnit("typewriter"),ExternalUnit("X-Y plotter"),ExternalUnit("interval timer"),ExternalUnit("movable head disc"),ExternalUnit("CRT"),ExternalUnit("fixed head disc")]
		self.memory_map = []
		self.prog_counter = 0
		self.instr_register = 0
		self.accumulator_a = 0
		self.accumulator_b = 0
		self.t_register = 0
		
		self.switch_runstop = 0

		for borp in range(0, 0xffff): #memory is filled entirely with ram right now
			self.memory_map.append({"read": lambda x:ram_read(x), "write": lambda x,y=borp: self.ram_write(y,x)})
			
	def set_program_counter(self, addr):
		self.prog_counter = addr & 0xffff
		
	def panelswitch_halt(self):
		pass
		
	def panelswitch_clear_t(self):
		pass

	def panelswitch_master_clear(self):
		pass

	def panelswitch_start_stop(self,state):
		if state:
			self.switch_runstop = True
		else:
			self.switch_runstop = False


	def panelswitch_single_cycle(self):
		(opcode, mnemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(self.ram_read(self.prog_counter))
		args = args.split(",")

		print("%06o %s" % (self.prog_counter, mnemonic))
		if mnemonic == "CEU":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.external_units[unit].unit_command(self.ram_read(self.prog_counter + 1))
			self.set_program_counter(self.prog_counter + 2) #second word
			
		if mnemonic == "TEU":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.accumulator_a = self.external_units[unit].unit_test(self.ram_read(self.prog_counter + 1))
			self.set_program_counter(self.prog_counter + 2) #second word
			
		elif mnemonic == "AIP":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.accumulator_a = self.external_units[unit].unit_read()
			self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "AOP":
			(unit,wait) = args #assuming all the number we produce are octal sames time
			unit = int(unit[1:],8)
			self.external_units[unit].unit_write(self.accumulator_a)
			self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "BRU":
			(address,) = args
			address = int(address[1:],8)
			self.set_program_counter(address)
#			self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "IBS":
			self.accumulator_b =  (self.accumulator_b + 1) & 0xffff
			if self.accumulator_b  == 0:
				self.set_program_counter(self.prog_counter + 2)
			else:
				self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "NOP":
			self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "SAP":
			if self.accumulator_a > 0:
				self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "SAN":
			if self.accumulator_a < 0:
				self.set_program_counter(self.prog_counter + 1)
				
		elif mnemonic == "SAZ":
			if self.accumulator_a == 0:
				self.set_program_counter(self.prog_counter + 1)
			self.set_program_counter(self.prog_counter + 1)

		elif mnemonic == "STA":
			(address,) = args
			address = int(address[1:],8)
			self.ram_write(address, self.accumulator_a)
		
		elif mnemonic == "STB":
			(address,) = args
			address = int(address[1:],8)
			self.ram_write(address, self.accumulator_b)

		elif mnemonic == "TBA":
			 self.accumulator_a = self.accumulator_b
			 
		elif mnemonic == "TAB":
			self.accumulator_b = self.accumulator_a

	def run(self):
		while(self.switch_runstop):
			self.panelswitch_single_cycle()
		
	def ram_read(self,addr):
		return self.ram[addr]
	
	def ram_write(self,addr,val):
		self.ram[addr & 0xffff] = val & 0xffff
		return self.ram[addr& 0xffff]

	def loadAtAddress(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.memory_map[address+i]["write"](binfile[i])


if __name__ == '__main__':
	file= sys.argv[1]
	
	cpu = SEL810CPU()
	cpu.loadAtAddress(0o6000,file)
	cpu.set_program_counter(0o6000)
	cpu.panelswitch_start_stop(True)
	
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
	cpu.panelswitch_single_cycle()
#	cpu.run()
	
#	for val in  binfile:
#		(opcode, nmemonic, indir,  args, comment, second_word, second_word_hint) = SELDISASM(val)
#		print(nmemonic)
