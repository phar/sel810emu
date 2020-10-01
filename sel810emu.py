import sys
import threading,queue
import select
import socket
import time
import cmd
import os
import json
import signal
from SELDeviceDriver import *
from ASR33OnTelnet import *
from cpserver import *
from cpuprimitives import *

#
#TODO
# interrupts not quite right
# badopcode on invalid instructions
# 60hz interrupt location unknown
# invalid opcode execution behavior
# branch instruction interaction with interrupts
# protect features not done
# notify hardware of the passage pf time in  12.8 microsecond increments?


try:
    import readline
except ImportError:
    readline = None

from util import *
from MNEMBLER2 import *
from defs import *

class SEL810CPU():
	def __init__(self,options=0, corememfile="sel810.coremem"):
		self.cpcmdqueue = queue.Queue()
		self._shutdown = False
		driver_positive_edge_tasks = []
		driver_negative_edge_tasks = []
		self.hwoptions = options

		self.external_units = {0:ExternalUnit(self,"nulldev",iogroup=0),
							   1:ExternalUnit(self,"asr33",btc=0,iogroup=0,chardev=True),
							   2:ExternalUnit(self,"paper tape",btc=1,iogroup=0,chardev=True),
							   3:ExternalUnit(self,"card punch",btc=2,iogroup=0,chardev=True),
							   4:ExternalUnit(self,"card reader",btc=3,iogroup=0,chardev=True),
							   5:ExternalUnit(self,"line printer",btc=4,iogroup=0,chardev=True),
							   6:ExternalUnit(self,"TCU 1",btc=5,iogroup=0),
							   7:ExternalUnit(self,"TCU 2",btc=6,iogroup=0),
							   10:ExternalUnit(self,"typewriter",btc=7,iogroup=0),
							   11:ExternalUnit(self,"X-Y plotter",btc=8,iogroup=0),
							   12:ExternalUnit(self,"interval timer",btc=0,iogroup=0),
							   13:ExternalUnit(self,"movable head disc",btc=10,iogroup=0),
							   14:ExternalUnit(self,"CRT",btc=11,iogroup=0),
							   15:ExternalUnit(self,"fixed head disc",btc=12,iogroup=0),
							   32:ExternalUnit(self,"NIXIE Minute Second",iogroup=0),
							   33:ExternalUnit(self,"NIXIE Day Hour",iogroup=0),
							   34:ExternalUnit(self,"NIXIE Months",iogroup=0),
							   35:ExternalUnit(self,"SWITCH0",iogroup=0),
							   36:ExternalUnit(self,"SWITCH1",iogroup=0),
							   37:ExternalUnit(self,"SWITCH2",iogroup=0),
							   38:ExternalUnit(self,"RELAY0",iogroup=0),
							   39:ExternalUnit(self,"RELAY1",iogroup=0),
							   40:ExternalUnit(self,"SENSE0",iogroup=0),
							   50:ExternalUnit(self,"SENSE1",iogroup=0),

}
		
		self.registers = {
			"Program Counter":REGISTER_CELL(width=15,pwm=True),
			"A Register":REGISTER_CELL(pwm=True),
			"B Register":REGISTER_CELL(pwm=True),
			"Control Switches":REGISTER_CELL(),
			"Instruction":REGISTER_CELL(pwm=True),
			"Interrupt Register":REGISTER_CELL(),
			"Transfer Register":REGISTER_CELL(pwm=True)}


		self.latch = {	"halt":True,#start halted
						"iowait":False,
						"overflow":False,
						"master_clear":False,
						"parity":False,
						"display":False,
						"enter":False,
						"step":False,
						"io_hold_release":False,
						"cold_boot":True,
						"carry":False}


		if self.hwoptions & (SEL_OPTION_PROTECT_1B_AND_TRAP_MEM | SEL_OPTION_PROTECT_2B_AND_TRAP_MEM):
			self.latch["protect"] = False
			self.latch["mode_key"] = False
			self.registers["Protect Register"] = REGISTER_CELL()

		if self.hwoptions & SEL_OPTION_VBR:
			self.registers["VBR Register"] = REGISTER_CELL(width=6)

		if self.hwoptions & SEL_OPTION_HW_INDEX:
			self.registers["Index Register"] = REGISTER_CELL()
			self.latch["index_pointer"]  = False
		else:
			self.registers["Index Register"] = self.registers["B Register"]

		if self.hwoptions & SEL_OPTION_STALL_ALARM:
			self.registers["Stall Counter"] = REGISTER_CELL(width=6)
			self.latch["stall"] = False

			
		self.sim_ticks = 0

		self.corememfile = corememfile
		self.ram = COREMEMORY(self,self.corememfile)

		self.cpthread = threading.Thread(target=control_panel_backend, args=(self,))
		self.cpthread.start()

	def _increment_pc(self,incrnum=1):
		self.registers["Program Counter"].write(self.registers["Program Counter"].read() + incrnum )
	
	def _next_pc(self):
		return (self.registers["Program Counter"].read() + 1) & MAX_MEM_SIZE

	def _increment_cycle_count(self,incrnum=1):
		for i in range(incrnum):
			self.sim_ticks += 1

			if self.hwoptions & SEL_OPTION_60HZ_RTC:
				if (self.sim_ticks % CPU_HERTZ) == 0:
						self.fire_60_hz_interrupt()
				
			if (self.sim_ticks % int(CPU_HERTZ / .0000128)) == 0:
				for n, unit in self.external_units.items():
					unit.unit_tick(.0000128)
	

	def _shift_cycle_timing(self,shifts):
		if 0 > shifts and shifts < 5:
			self._increment_cycle_count(2)
		elif 4 > shifts and shifts < 9:
			self._increment_cycle_count(3)
		elif 8 > shifts and shifts < 13:
			self._increment_cycle_count(4)
		elif 13 > shifts and shifts < 16:
			self._increment_cycle_count(5)
			
			
	def _priority_interrupt_notice(self):
		#Any priority interrupt will turn ON the protect latch
		if self.latch["mode_key"] == True:
			self.latch["protect"] = True

	def fire_protection_violation_interrupt(self,protflag):
		self._SPB_indir_opcode( + protflag, True)
		pass #fixme i have no idea where this fires


	def fire_60_hz_interrupt(self):
		pass #fixme i have no idea where this fires
	
	def fire_pf_restore_interrupt(self):
		self._SPB_indir_opcode(0o1000, True)
		
	def fire_stall_interrupt(self):
		self._SPB_indir_opcode(0o1001, True)

	def fire_priority_interrupt(self,group,channel):
		self._priority_interrupt_notice()
		self._SPB_indir_opcode(0o1002 + (group * 12) + channel, True)
		
	def _SPB_indir_opcode(self,address): #fixme
		#fixme is this wrong
		#when the wired SPB instruction is executed, the status of the protect latch is stored in bit 0 of the effective address defined to store the program counter contents.
        # Execution of this instruction is modified when caused by a priority interrupt in that the contents of the program counter are unchanged when transferred to the effective memory address. If the Program Protect and Instruction Trap option is included (and the Protect Mode switch is ON), when the SPB indirect instruction is caused by a priority interrupt' the status of the Protect Latch at the time of the interrupt is stored in bit 0 of the effective memory address.
		address = self.ram[address].read()
		
	#	if self.hwoptions & (SEL_OPTION_PROTECT_1B_AND_TRAP_MEM | SEL_OPTION_PROTECT_2B_AND_TRAP_MEM):
			#If the Program Protect and Instruction Trap option is included (and the computer is in the protected mode), the status of the Protect Latch is also stored in bit 0 of the interrupt routine entry point by the SPB instruction.
			
		self.ram[address].write(self._next_pc())
		self.registers["Program Counter"].write(address)
		self._increment_cycle_count(2)
		self._increment_pc()


	def panelswitch_step_neg_edge(self):
		self.registers["Instruction"].write(self.ram[self.registers["Program Counter"].read()].read())
		self.latch["parity"] = self.registers["Instruction"].parity #bit of a hack but results in the correct behavior.. cannot set parity from control panel
			
	def _stall_counter_task(self,cpu):
		if self.hwoptions & SEL_OPTION_STALL_ALARM: #probably doesnt belong here but no one calls this yet
			if cpu.registers["Program Counter"].read() == self.stall_ptr: #i think this whole construct assumes time ticks as peripherals wait..
				cpu.registers["Stall Counter"].write(cpu.registers["Stall Counter"].read() + 1)
				
			if cpu.registers["Stall Counter"] == STALL_TICKER_COUNT:
				self.latch["stall"] = True
		
	def get_current_map_addr(self):
		return  self.registers["Program Counter"].read() & 0xfc00
	
	
	def _resolve_second_word_address(self,map):
		indir = (self.ram[self._next_pc()].read() & 0x4000) > 0
		idx = (self.ram[self._next_pc()].read() & 0x8000) > 0
		addr = (self.ram[self._next_pc()].read() & 0x3fff)

#		if indir: #address
		return self._resolve_address(addr,map,indir,idx)
#		else: #immediate
#			return self._resolve_address(addr,map,0,0)
	
	def _resolve_address(self,base,map=0,indir=False,index=0):
		if map:
			base = base + self.get_current_map_addr()
	
		if index:
			if self.latch["index_pointer"]:
				base = base + self.registers["Index Register"].read()
			else:
				base = base + self.registers["B Register"].read()
				
		elif not map and self.hwoptions & SEL_OPTION_VBR: # Whenever the MAP and index bits of an instruction are set to logical zero, the contents of the VBR are treated as the most significant bits of, and appended to, the nine-bit operand address.
			base = base | self.registers["VBR Register"].read() << 9

		if indir:
			base = self.ram[base].read()

		return base & MAX_MEM_SIZE

			
	def panelswitch_step_pos_edge(self):
		op  = SELOPCODE(opcode=self.registers["Instruction"].read())
		if (SEL810_OPCODES[op.nmemonic][5] & SEL_OPTION_HW_INDEX) == SEL810_OPCODES[op.nmemonic][5]:
			if op.nmemonic in SEL810_OPCODES:
				if "address" in op.fields:
					address = self._resolve_address(op.fields["address"], op.fields["m"],op.fields["i"],op.fields["x"])
				
				if op.nmemonic == "LAA":
					self.registers["A Register"].write(self.ram[address].read())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "LBA":
					self.registers["B Register"].write(self.ram[address].read())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "STA":
					self.ram[address].write(self.registers["A Register"].read())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "STB":
					self.ram[address].write(self.registers["B Register"].read())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "AMA": ##CARRY
					if (self.registers["A Register"].read_signed() + self.ram[address].read_signed() + self.latch["carry"]) > 0x7fff:
						self.latch["overflow"] = True
					self.registers["A Register"].write (self.registers["A Register"].read_signed() + self.ram[address].read_signed())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "SMA": #CARRY
					if (self.registers["A Register"].read_signed() - self.ram[address].read_signed()) < 0:
						self.latch["overflow"] = True
					self.registers["A Register"].write_signed(self.registers["A Register"].read_signed() - self.ram[address].read_signed() - self.latch["carry"])
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "MPY":
					if self.registers["A Register"].read_signed() * self.ram[address].read_signed() < 0:
						self.latch["overflow"] = True
					self.registers["A Register"].write_signed(self.registers["A Register"].read_signed() * self.ram[address].read_signed())
					self._increment_cycle_count(6)
					self._increment_pc()

				elif op.nmemonic == "DIV": #"OVERFLOW if the divisor is the portion of the dividend"
					if  self.ram[address].read_signed() != 0: #fixme this is just my guess to overflow on divide by zero
						a = (self.registers["A Register"].read_signed() << 16 | self.registers["B Register"].read_signed()) / self.ram[address].read_signed()
						b = (self.registers["A Register"].read_signed() << 16 | self.registers["B Register"].read_signed()) % self.ram[address].read_signed()
						self.registers["A Register"].write_signed(int(a))
						self.registers["B Register"].write_signed(b)
					else:
						self.latch["overflow"] = True
					self._increment_cycle_count(11)
					self._increment_pc()
								
				elif op.nmemonic == "BRU":
					#fixme When the TOI and BRU indirect (or LOB) instructions are executed following the interrupt subroutine, the protect latch is returned to the status present a t the time the interrupt occurred.
					#If the Program Protect and Instruction Trap option is in- cluded (and the Protect Mode switch is ON), when the BRU indirect instruction is executed following a TOI instruction to exit from a priority interrupt routine, bits 2 through 15 of the effective address replace the contents of program counter, and the Protect Latch is set to the state of bit "0" of the effec- tive address.
					self.registers["Program Counter"].write(address)
					self._increment_cycle_count(2)
					
				elif op.nmemonic == "SPB":
					self.ram[address].write_signed(self._next_pc())
					self.registers["Program Counter"].write(address)
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "IMS":
					t = (self.ram[address]["read"]() + 1) & 0xffff
					self.ram[address].write_signed(t)
					if t == 0:
						self._increment_pc()
					self._increment_cycle_count(3)
					self._increment_pc()

				elif op.nmemonic == "CMA":
					if self.registers["A Register"].read_signed() == self.ram[address].read_signed():
						self._increment_pc() #the next instruction is skipped.
					elif self.registers["A Register"].read_signed() > self.ram[address].read_signed():
						self._increment_pc(2) #the next two instructions are skipped.
					self._increment_cycle_count(3)
					self._increment_pc()

				elif op.nmemonic == "AMB":
					if  (self.registers["B Register"].read_signed() + self.ram[address].read_signed()) > 0x7fff:
						self.latch["overflow"] = True
					self.registers["B Register"].write_signed(self.registers["B Register"].read_signed() + self.ram[address].read_signed())
					self._increment_cycle_count(2)
					self._increment_pc()
							 
				elif op.nmemonic == "CEU":
					if op.fields["i"]:
						val = self._resolve_second_word_address(op.fields["m"])
					else:
						val  = self.ram[self._next_pc()].read_signed()
						
					if op.fields["unit"] not in self.external_units:
						eu = self.external_units[0]
					else:
						eu = self.external_units[op.fields["unit"]]
								
					if eu.unit_ready("c") or op.fields["wait"]:
						eu.unit_command(val)
						self._increment_cycle_count(1)
					else:
						self._increment_pc()
					self._increment_cycle_count(4)
					self._increment_pc(2)

				elif op.nmemonic == "TEU":
					if op.fields["i"]:
						val = self._resolve_second_word_address(op.fields["m"])
					else:
						val  = self.ram[self._next_pc()].read_signed()
						
					if op.fields["unit"] not in self.external_units:
						eu = self.external_units[0]
					else:
						eu = self.external_units[op.fields["unit"]]
						
					if eu.unit_ready("t") or op.fields["wait"]:
						eu.unit_test(val)
						self._increment_cycle_count(1)
					else:
						self._increment_pc()
					self._increment_cycle_count(4)
					self._increment_pc(2)

				elif op.nmemonic == "SNS":
					if self.registers["Control Switches"].read_signed() & (1 << op.fields["unit"]):
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
							self.registers["A Register"].write_signed(0)
						self._increment_cycle_count(1)
						self.registers["A Register"].write_signed(self.registers["A Register"].read_signed() + eu.unit_read())
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

					if eu.unit_ready("w") or op.fields["wait"]:
						self._increment_cycle_count(1)
						eu.unit_write(self.registers["A Register"].read_signed())
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

					if eu.unit_ready("r") or op.fields["wait"]:
						self._increment_cycle_count()
						self.ram[self._resolve_second_word_address(op.fields["m"])].write(eu.unit_read())
						
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

						if op.fields["i"]: #address
							eu.unit_write(self.ram[self._resolve_second_word_address(op.fields["m"])].read())
							self._increment_cycle_count()
						else: #immediate
							eu.unit_write(self.ram[self._next_pc()].read())

						self._increment_cycle_count()
					else:
						self._increment_pc() #skip
					self._increment_cycle_count(4)
					self._increment_pc(2)

				elif op.nmemonic == "HLT":
					self.latch["halt"] = True
					self._increment_cycle_count()

				elif op.nmemonic == "RNA":
					if self.registers["B Register"].read() & 0x4000:
						if (self.registers["A Register"].raw_read() + 1) > 0x7fff:
							self.latch["overflow"] = True
						self.registers["A Register"].write_signed(self.registers["A Register"].read_signed() + 1)
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "NEG": #fixme "carry"
					self.registers["A Register"].write_signed(self.registers["A Register"].read()) #twoscomplement applied on write()
					if self.registers["A Register"].read_signed() == MINUS_FULL_SCALE: #"minus full scale"
						self.latch["overflow"] = True
					self._increment_cycle_count()
					self._increment_pc()

				elif op.nmemonic == "CLA":
					self.registers["A Register"].write(0)
					self._increment_cycle_count()
					self._increment_pc()

				elif op.nmemonic == "TBA":
					self.registers["A Register"].write(self.registers["B Register"].read())
					self._increment_cycle_count()
					self._increment_pc()
					 
				elif op.nmemonic == "TAB":
					self.registers["B Register"].write(self.registers["A Register"].read())
					self._increment_cycle_count()
					self._increment_pc()

				elif op.nmemonic == "IAB":
					t = self.registers["A Register"].read()
					self.registers["A Register"].write(self.registers["B Register"].read())
					self.registers["B Register"].write(t)
					self._increment_pc()
					self._increment_cycle_count()
					
				elif op.nmemonic == "CSB":
					if self.registers["B Register"].read() & 0x8000:
						self.latch["carry"]  = True
					else:
						self.latch["carry"]  = False
					self.registers["B Register"].write_signed(self.registers["A Register"].raw_read() & 0x7fff)
					self._increment_pc()
					self._increment_cycle_count()
					
				elif op.nmemonic == "RSA":
					s  = self.registers["A Register"].read() & 0x8000
					for i in op.fields["shifts"]:
						self.registers["A Register"].write(s | (self.registers["A Register"].read() >> 1))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "LSA":
					s  = self.registers["A Register"].read() & 0x8000
					self.registers["A Register"].write(s | ((self.registers["A Register"].read() << op.fields["shifts"]) & 0x7fff))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "FRA":
					s1  = self.registers["A Register"].read() & 0x8000
					s2  = self.registers["B Register"].read() & 0x8000
					r = ((self.registers["A Register"].read() & 0x7fff) << 15) | (self.registers["B Register"].read() & 0x7fff)
					for i in op.fields["shifts"]:
						r = s1 | (r >> 1)
					self.registers["A Register"].write(s1 | ((r >> 15) & 0x7fff))
					self.registers["B Register"].write(s2 | (r & 0x7fff))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "FLL":
					t = (((self.registers["A Register"].read() << 16) | self.registers["B Register"].read()) << op.fields["shifts"]) & 0xffffffff
					self.registers["A Register"].write((t  >> 16) & 0xffff)
					self.registers["B Register"].write((t & 0xffff))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "FRL":
					for i in range(op.fields["shifts"]):
						t = (((self.registers["A Register"].read() << 16) | self.registers["B Register"].read()) << 1)
						b = t & (0x10000) >> 16
						t = t | b
					self.registers["A Register"].write((t  >> 16) & 0xffff)
					self.registers["B Register"].write((t & 0xffff))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "RSL":
					self.registers["A Register"].write(self.registers["A Register"].read() >> op.fields["shifts"])
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "LSL":
					self.registers["A Register"].write(self.registers["A Register"].read() << op.fields["shifts"])
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()

				elif op.nmemonic == "FLA":
					s1  = self.registers["A Register"].read() & 0x8000
					s2  = self.registers["B Register"].read() & 0x8000
					r = ((((self.registers["A Register"].read() & 0x7fff) << 15) | (self.registers["B Register"].read() & 0x7fff))  << op.fields["shifts"]) & 0xffffffff
					self.registers["A Register"].write(s1 | ((r >> 15) & 0x7fff))
					self.registers["B Register"].write(s2 | (r & 0x7fff))
					self._shift_cycle_timing(op.fields["shifts"])
					self._increment_pc()
					
				elif op.nmemonic == "ASC":
					self.registers["A Register"].write(self.registers["A Register"].read() ^ 0x8000)
					self._increment_pc()
					self._increment_cycle_count(1)
					
				elif op.nmemonic == "SAS":
					if self.registers["A Register"].read_signed() == 0:
						self._increment_pc()
					elif self.registers["A Register"].read_signed() > 0:
						self._increment_pc(2)
					self._increment_pc()
					self._increment_cycle_count(1)

				elif op.nmemonic == "SAZ":
					if self.registers["A Register"].read_signed() == 0:
						self._increment_pc()
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "SAN":
					if self.registers["A Register"].read_signed() < 0:
						self._increment_pc()
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "SAP":
					if self.registers["A Register"].read_signed() > 0:
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
					self.registers["B Register"].write_signed(self.registers["B Register"].read_signed() + 1)
					if self.registers["B Register"].read_signed()  >= 0:
						self._increment_pc(2)
					else:
						self._increment_pc()
					self._increment_cycle_count(1)
						
				elif op.nmemonic == "ABA":
					self.registers["A Register"].write(self.registers["A Register"].read() & self.registers["B Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "OBA":
					self.registers["A Register"].write(self.registers["A Register"].read() | self.registers["B Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "LCS":
					self.registers["A Register"].write(self.registers["Control Panel Switches"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "SNO": #If bit Al does not equal bit AO of the A~Accurnulator, the next instruction is skipped
					if(self.registers["A Register"].read() & 0x0001) != ((self.registers["A Register"].read() * 0x0002) >> 1):
						self._increment_pc()
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "NOP":
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "CNS":
					t =self.registers["A Register"].read()
					tc = dec2twoscmplment(t & 0x7fff) |  (t & 0x8000)
					self.registers["A Register"].write(tc)
					if self.registers["A Register"].read_signed() == MINUS_FULL_SCALE: #"minus full scale"
						self.latch["overflow"] = True
					self._increment_cycle_count(1)
					self._increment_pc()
					
				elif op.nmemonic == "TOI": #fixme"
					#fixme When the TOI and BRU indirect (or LOB) instructions are executed following the interrupt subroutine, the protect latch is returned to the status present a t the time the interrupt occurred.
					#The TOI instruction inhibits servicing the interrupt for one instruction to allow the BRU* to be executed at the exit of the interrupt routines. This is to insure that the proper active latch (A) is reset.
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "LOB":
					#fixme When the TOI and BRU indirect (or LOB) instructions are executed following the interrupt subroutine, the protect latch is returned to the status present a t the time the interrupt occurred.
					#f the Program Pro- tect and Instruction Trap option is included (and the Protect Mode switch is ON), when the LOB instruction is used fol- lowing a TOI instruction to exit from a priority interrupt rou- tine, the Protect Latch is set to the state of bit "0" of the effective address.
					self.registers["Program Counter"].write(self.ram[self._next_pc()].read())
					self._increment_cycle_count(2)
					self._increment_pc(2)
					
				elif op.nmemonic == "OVS":
					self.latch["overflow"] = True
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "STX": #
					if op.fields["i"]: #address
						self.ram[self._resolve_second_word_address(op.fields["m"])].write(self.registers["Index Register"])
						self._increment_cycle_count()
					else: #immediate
						self.ram[self._next_pc()].write(self.registers["Index Register"])
					self._increment_cycle_count(2)
					self._increment_pc(2)
						
				elif op.nmemonic == "TPB":
					self.registers["B Register"].write(self.registers["Protect Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TBP":
					self.registers["Protect Register"].write(self.registers["B Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TPA": #lost instuction
					self.registers["Protect Register"].write(self.registers["A Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TAP": #lost instruction
					self.registers["A Register"].write(self.registers["Protect Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TBV":
					self.registers["VBR Register"].write(self.registers["B Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TVB":
					self.registers["B Register"].write(self.registers["VBR Register"].read())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "LIX":
					if op.fields["i"]: #address
						self.registers["Index Register"].write(self.ram[self._resolve_second_word_address(op.fields["m"])].read())
						self._increment_cycle_count()
					else: #immediate
						self.registers["Index Register"] = self.ram[self._next_pc()].read()
					self._increment_cycle_count(2)
					self._increment_pc(2)

				elif op.nmemonic == "XPX":
					self.latch["index_pointer"] = True
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "XPB":
					self.latch["index_pointer"] = False
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "SXB":
					self.ram[address].write_signed(self.registers["B Register"].read_signed())
					self._increment_cycle_count(2)
					self._increment_pc()

				elif op.nmemonic == "IXS": #fixme hidden featuress
					n = (self.registers["Instruction"].read() & 0x03c0) >> 6
					if (self.registers["Index Register"].read_signed() + n) > 0:
						self._increment_pc()
					self.registers["Index Register"].write_signed(self.registers["Index Register"].read_signed() + n)
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TAX":
					self.registers["Index Register"].write_signed(self.registers["A Register"].read_signed())
					self._increment_cycle_count(1)
					self._increment_pc()

				elif op.nmemonic == "TXA":
					self.registers["A Register"].write_signed(self.registers["Index Register"].read_signed())
					self._increment_cycle_count()
					self._increment_pc()

				elif op.nmemonic == "PID":
					self.registers["Interrupt"].write(self.registers["Interrupt"].read() ^ self.ram[self._next_pc()].read())
					self._increment_pc(2)
					
				elif op.nmemonic == "PIE":
					self.registers["Interrupt"].write( self.registers["Interrupt"].read() | self.ram[self._next_pc()].read())
					self._increment_pc(2)
					
				else: #badopcode However, execution of any legal instruction in an unprotected area causes the protect latch tobe turned OFF.
					self.latch["protect"]  = False #fixme
									
									
				if op.nmemonic != "CSB": #the carry latch is reset at the end of the execution of all instructions except CSB
					self.latch["carry"]  = False
		else:
			pass #this is an invalid opcode for this platform
			
	def get_cpu_state(self):
		state_struct = {}
		for n,v in self.registers.items():
			state_struct[n] = v.read()
			
		for n,v in self.latch.items():
			state_struct[n] = v


		state_struct["assembler"] = SELOPCODE(opcode=self.ram[self.registers["Program Counter"].read()].read_signed()).pack_asm()[0].strip()
		return state_struct


	def set_cpu_state(self,state_struct):
		for n,v in self.registers.items():
			if n in state_struct:
				self.registers[n].write(state_struct[n])
				
		for n,v in self.latch.items():
			if n in state_struct:
				self.latch[n] = state_struct[n]
				
		if "assembler" in state_struct:
			try:
				self.registers["Transfer Register"].write(SELOPCODE((" "*5) +  state_struct["assembler"].strip()).pack_abs(self.registers["Program Counter"].read(),{})[0])
			except:
				print("error parsing provided assembler")

	def load_at_address(self,address,file):
		binfile = loadProgramBin(file)
		for i in range(0,len(binfile)):
			self.ram[address+i].write(binfile[i])
			
	def shutdown(self):
		self._shutdown = True
		self.cpthread.join()
		for n,u in self.external_units.items():
			u._teardown()
		self.ram.shutdown()
#		self.store_core_memory()
		
	def step(self):
		#finish up a coldboot sequence by setting the flag and firing the interrupt (FIXME this wouldnt be configured from pid/pie)
		if self.latch["cold_boot"] == True:
			self.latch["cold_boot"] = False
			self._increment_cycle_count(32)
			self.cpu.fire_pf_restore_interrupt()

		#BTC emulation, there might be more nuance missing here to how different devices interleve actual traffic on the bus
		for id, unit in self.external_units.items():
			if (unit.ceu & 0x8000) and (self.btc == True) and unit.unit_ready() and (unit.btc_wc > 0):
				self.ram[unit.btc_cwa] = unit.unit_read()#this isnt right
				unit.btc_wc = (unit.btc_wc - 1)
				unit.btc_cwa = (unit.btc_cwa + 1) & 0xffff
				self._increment_cycle_count(2)
				break;
				
		#alright.. state machine go brrr
		self.panelswitch_step_neg_edge()
		self.panelswitch_step_pos_edge()
		
		self.latch["step"] = False
		self.latch["io_hold_release"] = False




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



def control_panel_backend(cpu):
	stepctr = 0
	cpu.latch["cold_boot"] = True
	running = True
	while cpu._shutdown == False and running:

		if cpu.cpcmdqueue.qsize():
			(c, data) = cpu.cpcmdqueue.get()
			if c == "s":
				stepctr = data
			elif c == "u":
				cpu.set_cpu_state(data)
			elif c == "l":
				(addr,file) = data
				cpu.load_at_address(addr,file)
			elif c == "h+":
				cpu.latch["halt"] = True
			elif c == "h-":
				cpu.latch["halt"] = False
			elif c == "q":
				running = False

		if stepctr > 0: #note, this conflicts with master_clear, setting a step with master clear asserted will clear the step flag
			cpu.latch["step"] = True
			stepctr -= 1

		#power fail feature
		if cpu.latch["cold_boot"] == True:
			cpu.latch["master_clear"] = True

		if cpu.latch["enter"]:
			cpu.ram[cpu.registers["Program Counter"].read()].write(cpu.registers["Transfer Register"].read())
			cpu.latch["enter"] = False

		if cpu.latch["display"]:
			cpu.registers["Transfer Register"].write(cpu.ram[cpu.registers["Program Counter"].read()].read())
			cpu.latch["display"] = False

		#because its the first boot, or someone asserted master clear, we clear registers and latches
		if cpu.latch["master_clear"] == True:
			for n,v in cpu.registers.items():
				cpu.registers[n].write(0)
			for n,v in cpu.latch.items():
				cpu.latch[n] = False
			cpu.latch["halt"] = True
			cpu.latch["master_clear"] = False

		if not cpu.latch["halt"] or cpu.latch["step"]:
			cpu.step()
			cpu.sim_ticks += 1
		else:
			cpu.sim_ticks += 1
			time.sleep(.1)


class SEL810Shell(cmd.Cmd):
	intro = 'Welcome to the SEL emulator/debugger. Type help or ? to list commands.\n'
	prompt = '(SEL810x) '
	histfile = os.path.expanduser(CONSOLE_HISTORY_FILE)
	histfile_size = 1000
	
	def __init__(self):
		super().__init__()
		self.file = None
		self.cpu = SEL810CPU(SEL_OPTION_PROTECT_2B_AND_TRAP_MEM | SEL_OPTION_VBR | SEL_OPTION_HW_INDEX | SEL_OPTION_STALL_ALARM | SEL_OPTION_AUTO_START | SEL_OPTION_IO_PARITY | SEL_OPTION_60HZ_RTC
	,corememfile=CORE_MEMORY_FILE)
		self.exit_flag = False

		signal.signal(signal.SIGINT, lambda x,y  : self.onecmd("quit\n"))

	def do_step(self, arg):
		'singlestep the processor'
		if len(arg.split(" ")) > 1:
			steps = parse_inputint(arg.split(" ")[0])
		else:
			if arg != "":
				steps = parse_inputint(arg)
			else:
				steps = 1

		if not self.cpu.latch["iowait"]:
			self.cpu.cpcmdqueue.put(("s",steps))
			print("(op:%s)" % self.cpu.get_cpu_state()["assembler"]) #probably not the way to do this anymore
		else:
			print("cannot step while in io-wait")

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
		
		progcnt = parse_inputint(progcnt)
		self.cpu.cpcmdqueue.put(("u",{"Program Counter":progcnt}))

	def do_quit(self,args):
		'exit the emulator'
		if self.exit_flag == False:
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
				print("0x%04x "% self.cpu.ram[i+e].read(),end="")
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
				print("0o%06o "% self.cpu.ram[i+e].read(),end="")
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
			op = SELOPCODE(opcode=self.cpu.ram[i].read())
			print("'%06o" % i, op.pack_asm()[0])
			

	def do_registers(self,args):
		'show the current register contents'
		for n,v in self.cpu.get_cpu_state().items():
			if n in self.cpu.registers:
				print("%s0x%04x ('%06o)" % (("%s:"%n).ljust(25) ,v,v))
			elif n in self.cpu.latch:
				print("%s%s" % (("%s:"%n).ljust(25) ,str(v)))

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
	
	telnet = ASR33OnTelnetDriver("/tmp/SEL810_asr33","127.0.0.1",9999)
	cp  = ControlPanelDriver(shell.cpu,"/tmp/SEL810_control_panel")
	cp.start()
	telnet.start()
	shell.cmdloop()
	telnet.stop()
	cp.stop()

