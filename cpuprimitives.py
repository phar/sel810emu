from defs import *
from util import *

class REGISTER_CELL():
	def __init__(self,parent_array=None, width=16):
		self.value = 0
		self.bitwidth = width
		self.parent = parent_array

	def read_signed(self):
		return twoscmplment2dec(self.value)

	def read(self):
		return self.value

	def write(self,v):
		self.value = v & ((2**self.bitwidth) - 1)
		self.parity = parity_calc(self.value)

	def write_signed(self,v):
		self.value = dec2twoscmplment(v & ((2**self.bitwidth) - 1),self.bitwidth)
		self.parity = parity_calc(self.value)

class RAM_CELL(REGISTER_CELL):
	def __init__(self,parent_array, addr, prot,  width=16):
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
	def __init__(self, cpu, backing_file, memmax=0x7fff, options=OPTION_PROT_NONE):
		self.optionsmask = options
		self.memmax = memmax
		self.prot_reg = 0
		self._ram = [] # [RAM_CELL()] * self.memmax
		self.cpu = cpu
		self.backingfile = backing_file

		if self.optionsmask & OPTION_PROT_1B: #its not clear how this option works for various memory sizes
			psize = 1024
		elif self.optionsmask & OPTION_PROT_2B:
			psize = 2048
		else:
			psize = self.memmax

		try:
			binfile = loadProgramBin(self.backingfile)
		except:
			binfile = [0] * MAX_MEM_SIZE

		self.corememfile = open(self.backingfile,"wb")
		for i in range(0, self.memmax, psize):
			for e in range(0,psize):
				cell = RAM_CELL(self,(i*psize) + e, i)
				self._ram.append(cell)
				if len(binfile) > (i*psize) + e:
					cell.write(binfile[(i*psize) + e])
				else:
					cell.write(0)
					
	def _flush_write(self,addr):
		self.corememfile.seek(addr * struct.calcsize("H"))
		self.corememfile.write(struct.pack(">H", self[addr].read()))


#Any priority interrupt will turn ON the protect latch and any instruction within the interrupt subroutine which is not in a protected area will turn OFF the pro- tect latch. To insure that the protect status that was present at the time of the interrupt is returned after the inter- rupt subroutine is completed, the pro- tect latch status is stored as follows: after the interrupt has occurred, when the wired SPB instruction is executed, the status of the protect latch is stored in bit 0 of the effective address defined to store the program counter contents. When the TO! and BRU indirect (or LOB) instructions are executed following the interrupt subroutine, the protect latch is returned to the status present a t the time the interrupt occurred.


	def _write_attempt(self,prot_bit):
		if self.cpu.hwoptions & SEL_OPTION_PROTECT_AND_TRAP_MEM:
			if self.cpu.latch["protect"]: #fixme, needs to be anded with protection mask
				self.cpu.fire_protection_violation_interrupt()
				return False
		return True #will figure out the interrupt logic for this later
		 
	def __setitem__(self, key, item):
		self.__dict__[key] = item

	def __getitem__(self, key):
		return self._ram[key & self.memmax]

	def set_prot_reg(self, regval):
		self.prot_reg = regval
		
	def get_prot_reg(self):
		return self.prot_reg
		
	def shutdown(self):
		self.corememfile.close()

