from defs import *
from util import *

class REGISTER_CELL():
	def __init__(self,parent_array=None, width=16, pwm=False):
		self.value = 0
		self.bitwidth = width
		self.parent = parent_array
		self.pwm = pwm
		self.pwmclear()

	def __pwmupdate(self):
		self.pwmops += 1
		for i in range(self.bitwidth):
			if (1 << i) & self.value:
				self.pwmvals[(self.bitwidth - 1) - i] = (self.pwmvals[(self.bitwidth - 1) - i] + 1.0)
			
	def pwmclear(self):
		self.pwmops = 0
		self.pwmvals = [0.0] * self.bitwidth
	
	
	def get_PWM_vals(self):
		if self.pwmops == 0:
			self.__pwmupdate()
		lst = []
		for i in range(self.bitwidth):
			lst.append(self.pwmvals[i] / self.pwmops)
		return lst
		
	def read_signed(self):
		return twoscmplment2dec(self.value)

	def read(self):
		return self.value

	def write(self,v):
		self.value = v & ((2**self.bitwidth) - 1)
		self.parity = parity_calc(self.value)
		if self.pwm:
			self.__pwmupdate()

	def write_signed(self,v):
		self.value = dec2twoscmplment(v & ((2**self.bitwidth) - 1),self.bitwidth)
		self.parity = parity_calc(self.value)
		if self.pwm:
			self.__pwmupdate()


class RAM_CELL(REGISTER_CELL):
	def __init__(self,parent_array, addr,  width=16):
		self.prot = False
		self.parity = False
		self.addr = addr
		super().__init__(parent_array, width=width)

	def write(self,v):
		if self.parent._write_attempt(self.prot):
			super().write(v)
			self.parent._flush_write(self.addr)

	def write_signed(self,v):
		overflow = False
		if self.parent._write_attempt(self.prot):
			super().write_signed(v)
			self.parent._flush_write(self.addr)
	

class COREMEMORY(list):
	def __init__(self, cpu, backing_file, memmax=0x7fff):
		self.memmax = memmax
		self._ram = []
		self.cpu = cpu
		self.backingfile = backing_file

		try:
			binfile = loadProgramBin(self.backingfile) #fixme should be replaced
		except:
			binfile = [0] * MAX_MEM_SIZE

		self.corememfile = open(self.backingfile,"wb+")

		for i in range(0, self.memmax):
			cell = RAM_CELL(self,i)
			self._ram.append(cell)
			if len(binfile) > i:
				cell.write(binfile[i])
			else:
				cell.write(0)
					
	def _flush_write(self,addr):
		self.corememfile.seek(addr * struct.calcsize("H"))
		self.corememfile.write(struct.pack(">H", self[addr].read()))


#Any priority interrupt will turn ON the protect latch and any instruction within the interrupt subroutine which is not in a protected area will turn OFF the pro- tect latch. To insure that the protect status that was present at the time of the interrupt is returned after the inter- rupt subroutine is completed, the pro- tect latch status is stored as follows: after the interrupt has occurred, when the wired SPB instruction is executed, the status of the protect latch is stored in bit 0 of the effective address defined to store the program counter contents. When the TO! and BRU indirect (or LOB) instructions are executed following the interrupt subroutine, the protect latch is returned to the status present a t the time the interrupt occurred.


	def _write_attempt(self,prot_bit):
		if self.cpu.hwoptions & (SEL_OPTION_PROTECT_1B_AND_TRAP_MEM | SEL_OPTION_PROTECT_2B_AND_TRAP_MEM):
			if (self.cpu.registers["Protect Register"].read() & (1<<prot_bit)) > 0: #fixme, needs to be anded with protection mask
				#If the Program Protect and Instruction Trap option is included (and the computer is in the protected mode), the status of the Protect Latch is also stored in bit 0 of the interrupt routine entry point by the SPB instruction. When the program returns to the point of interrupt, the protect latch returns to the status present at the time of the interrupt.
				self.cpu.fire_protection_violation_interrupt((self.cpu.registers["Protect Register"].read() & (1<<prot_bit)) > 0)
				return False
		return True #will figure out the interrupt logic for this later
		 
	def __setitem__(self, key, item):
		self.__dict__[key] = item

	def __getitem__(self, key):
		return self._ram[key & self.memmax]

	def shutdown(self):
		self.corememfile.close()

