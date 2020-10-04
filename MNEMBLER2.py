from collections import *
import re
import pickle
import struct
from util import *
from defs import *
	
SEL810NONETYPE	= 0
SEL810ATYPE 	= 1
SEL810BTYPE 	= 2



SEL810_PEEK_OPCODE 			= 0
SEL810_MREF_OPCODE 			= 1
SEL810_AUGMENTED_OPCODE		= 2
SEL810_IO_OPCODE			= 3
SEL810_INT_OPCODES 			= 4
SEL810_BARE_VALUE			= 5
SEL810_DAC_VALUE 			= 6
SEL810_ZZZ_OPCODE 			= 7
SEL810_SENSE_SWITCHES			= 8

SEL810_PSEUDO_OPCODE 		= -1


OBJOP_DIRECT_LOAD 			= 0
OBJOP_MEMREF_LOAD 			= 1
OBJOP_SUBCALL_LOAD 			= 2
OBJOP_LITERAL_LOAD 			= 3
OBJOP_SPECIAL_LOAD 			= 4

OBJOP_NONE_DUMMY 			= -1


OBJ_SPECIAL_LOAD_POINT		= 0
OBJ_SPECIAL_END_JUMP		= 1
OBJ_SPECIAL_STRING			= 2
OBJ_SPECIAL_9_BIT_ADD_TO	= 3
OBJ_SPECIAL_14_BIT_ADD_TO	= 4
OBJ_SPECIAL_15_BIT_ADD_TO	= 5
OBJ_SPECIAL_SET_CHAIN_FLAG	= 6
OBJ_SPECIAL_SET_LOAD_FLAG	= 7
OBJ_SPECIAL_END_JOB			= 8


FLAG_ADDRESS_MODE_ABSOLUTE	= 0
FLAG_ADDRESS_MODE_RELATIVE	= 1

#                         (type,					,decompose, 		opcode,	augmentcode, second_word, a\b)
SEL810_OPCODES = {	"LAA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o01,	0,		False,	SEL_OPTION_NONE),
					"LBA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o02,	0,		False,	SEL_OPTION_NONE),
					"STA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o03,	0,		False,	SEL_OPTION_NONE),
					"STB":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o04,	0,		False,	SEL_OPTION_NONE),
					"AMA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o05,	0,		False,	SEL_OPTION_NONE),
					"SMA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o06,	0,		False,	SEL_OPTION_NONE),
					"MPY":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o07,	0,		False,	SEL_OPTION_NONE),
					"DIV":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o10,	0,		False,	SEL_OPTION_NONE),
					"BRU":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o11,	0,		False,	SEL_OPTION_NONE),
					"SPB":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o12,	0,		False,	SEL_OPTION_NONE),
					"IMS":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o14,	0,		False,	SEL_OPTION_NONE),

					"CMA":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o15,	0,		False,	SEL_OPTION_NONE),
					"AMB":(SEL810_MREF_OPCODE,		OBJOP_MEMREF_LOAD,	0o16,	0,		False,	SEL_OPTION_NONE),
					"HLT":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o00,	False,	SEL_OPTION_NONE),
					"RNA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o01,	False,	SEL_OPTION_NONE),
					"NEG":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o02,	False,	SEL_OPTION_NONE),
					"CLA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o03,	False,	SEL_OPTION_NONE),
					"TBA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o04,	False,	SEL_OPTION_NONE),
					"TAB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o05,	False,	SEL_OPTION_NONE),
					"IAB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o06,	False,	SEL_OPTION_NONE),
					"CSB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o07,	False,	SEL_OPTION_NONE),
					"RSA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o10,	False,	SEL_OPTION_NONE),
					"LSA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o11,	False,	SEL_OPTION_NONE),
					"FRA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o12,	False,	SEL_OPTION_NONE),
					"FLL":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o13,	False,	SEL_OPTION_NONE),
					"FRL":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o14,	False,	SEL_OPTION_NONE),
					"RSL":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o15,	False,	SEL_OPTION_NONE),
					"LSL":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o16,	False,	SEL_OPTION_NONE),
					"FLA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o17,	False,	SEL_OPTION_NONE),
					"ASC":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o20,	False,	SEL_OPTION_NONE),
					"SAS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o21,	False,	SEL_OPTION_NONE),
					"SAZ":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o22,	False,	SEL_OPTION_NONE),
					"SAN":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o23,	False,	SEL_OPTION_NONE),
					"SAP":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o24,	False,	SEL_OPTION_NONE),
					"SOF":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o25,	False,	SEL_OPTION_NONE),
					"IBS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o26,	False,	SEL_OPTION_NONE),
					"ABA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o27,	False,	SEL_OPTION_NONE),
					"OBA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o30,	False,	SEL_OPTION_NONE),
					"LCS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o31,	False,	SEL_OPTION_NONE),
					"SNO":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o32,	False,	SEL_OPTION_NONE),
					"NOP":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o33,	False,	SEL_OPTION_NONE),
					"CNS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o34,	False,	SEL_OPTION_NONE),
					"TOI":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o35,	False,	SEL_OPTION_NONE),
					"LOB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o36,	True,	SEL_OPTION_NONE),
					"OVS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o37,	False,	SEL_OPTION_HW_INDEX),
					"TBP":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o40,	False,	SEL_OPTION_PROTECT_1B_AND_TRAP_MEM),
					"TPB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o41,	False,	SEL_OPTION_PROTECT_1B_AND_TRAP_MEM),
					"TBV":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o42,	False,	SEL_OPTION_VBR),
					"TVB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o43,	False,	SEL_OPTION_VBR),
					"STX":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o44,	True,	SEL_OPTION_HW_INDEX),
					"LIX":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o45,	True,	SEL_OPTION_HW_INDEX),
					"XPX":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o46,	False,	SEL_OPTION_HW_INDEX),
					"XPB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o47,	False,	SEL_OPTION_HW_INDEX),
					"SXB":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o50,	False,	SEL_OPTION_HW_INDEX),
					"IXS":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o51,	False,	SEL_OPTION_NONE),
					"TAX":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o52,	False,	SEL_OPTION_HW_INDEX),
					"TXA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0o53,	False,	SEL_OPTION_HW_INDEX),
#Table 3-2. SEL BlOB Mnemonic Instructions SEL reference manual.. lost instructions.. the docs say B-accumulator,but the instruction naming suggest A was intended since a working B instruction exists
#					"TPA":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0oxx,	False,	SEL_OPTION_PROTECT_AND_TRAP_MEM), #Transfer B-Accumulator to Protect Register
#					"TAP":(SEL810_AUGMENTED_OPCODE,	OBJOP_DIRECT_LOAD,	0,		0oxx,	False,	SEL_OPTION_PROTECT_AND_TRAP_MEM | SEL_OPTION_VBR), #Transfer Protect Register to B-Accurnulator
					"CEU":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o13,	0o00,	True,	SEL_OPTION_NONE),
					"TEU":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o13,	0o01,	True,	SEL_OPTION_NONE),
					"SNS":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o13,	0o04,	False,	SEL_OPTION_NONE),
					"AIP":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o17,	0o01,	False,	SEL_OPTION_NONE),
					"MOP":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o17,	0o02,	True,	SEL_OPTION_NONE),
					"MIP":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o17,	0o03,	False,	SEL_OPTION_NONE),
					"AOP":(SEL810_IO_OPCODE,		OBJOP_DIRECT_LOAD,	0o17,	0o00,	False,	SEL_OPTION_NONE),
					"PID":(SEL810_INT_OPCODES,		OBJOP_DIRECT_LOAD,	0o13,	0o0601,	True,	SEL_OPTION_NONE), #fixme
					"PIE":(SEL810_INT_OPCODES,		OBJOP_DIRECT_LOAD,	0o13,	0o0600,	True,	SEL_OPTION_NONE)}#fixme


PSEUDO_OPCODES = {	"ABS": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"REL": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"ORG": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"EQU": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"DAC": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"EAC": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"DATA":(SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"END": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"FORM":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"FDAT":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"BSS": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"BES": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"CALL":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"MOR": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"NAME":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"END": (SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"LIST":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"NOLS":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"MACR":(SEL810_PSEUDO_OPCODE,	OBJOP_NONE_DUMMY),
					"EMAC":(SEL810_PSEUDO_OPCODE, 	OBJOP_NONE_DUMMY),
					"***": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD),
					"ZZZ": (SEL810_PSEUDO_OPCODE,	OBJOP_DIRECT_LOAD)}




DECOMPOSE_OBJ_STYLE = [	OrderedDict([("objop",(0,2)),
									("zeros",(2,7)),
									("data",(7,24))]),

						OrderedDict([("objop",(0,2)),
									("reloc",(2,3)),
									("opcode",(3,7)),
									("x",(7,8)),
									("i",(8,9)),
									("address",(9,24)),]),

						OrderedDict([("objop",(0,2)),
								   ("reloc",(4,5)),
								   ("opcode",(5,8)),
								   ("x",(8,9)),
								   ("i",(9,10)),
								   ("addresslen",(10,24))]),

						OrderedDict([("objop",(0,2)),
								   ("reloc",(2,3)),
								   ("opcode",(3,7)),
								   ("special_literal",(7,8)),
								   ("literal",(8,24))]),

						OrderedDict([("objop",(0,2)),
								   ("reloc",(2,3)),
								   ("code",(3,7)),#not a typo
								   ("special_literal",(7,8)),
						#		   ("n",(8,9)), # i think this "negation bit" is just... negative numbers
								   ("address",(8,24))])]




DECOMPOSE_BIN_STYLE = [
						#SEL810_PEEK_OPCODE 			= 0
						OrderedDict([("opcode",(0,4))]),
						#SEL810_MREF_OPCODE 			= 1
						OrderedDict([("opcode",(0,4)),
									("x",(4,5)),
									("i",(5,6)),
									("m",(6,7)),
									("address",(7,16))]),
						#SEL810_AUGMENTED_OPCODE		= 2
						OrderedDict([("opcode",(0,4)),
									("zeros",(4,6)),
									("shifts",(6,10)),
									("augmentcode",(10,16))]),
						#SEL810_IO_OPCODE			= 3
						OrderedDict([("opcode",(0,4)),
									("r",(4,5)),
									("i",(5,6)),
									("m",(6,7)),
									("augmentcode",(7,9)),
									("wait",(9,10)),
									("unit",(10,16))]),
						#SEL810_INT_OPCODES 			= 4
						OrderedDict([("opcode",(0,4)),
									("zeros",(4,7)),
									("augmentcode",(7,16))]),
						#SEL810_BARE_VALUE			= 5
						OrderedDict([("operand",(0,16))]),
						#SEL810_DAC_VALUE 			= 6
						OrderedDict([("x",(0,1)),
									("i",(1,2)),
									("operand",(2,16))]),
						#SEL810_ZZZ_OPCODE 			= 7
						OrderedDict([("opcode",(0,4)),
									("discard",(4,5)),
									("i",(5,6)),
									("operand",(6,16))]),

						#SEL810_SENSE_SWITCHES
						OrderedDict([("opcode",(0,10)),
									("switches",(10,16))])]




def parse_arg(arg,curr_addr=0,symbols={}):
	total = lambda ca,s:0
	mth = lambda ca,s,x,y : x(ca,s)+y(ca,s)
	if arg[0] == "=":
		return  parse_arg2(arg,curr_addr,symbols)
	else:
		if arg[:2] == "''":
			return  parse_arg2(arg,curr_addr,symbols)
		if  any(ele in arg for ele in ["+","-"]):
			argparts = re.split("(\+|\-)",arg)
			for i in range(len(argparts)):
				if argparts[i] != "":
					if argparts[i] in ["+","-"]:
						if argparts[i] == "-":
							mth = lambda ca,s,x,y: x(ca,s)-y(ca,s)
						else:
							mth = lambda ca,s,x,y: x(ca,s)+y(ca,s)
					else:
						total = lambda s,ca, x=total, y = lambda b,ca, a=argparts[i]: parse_arg2(a,ca,b)(b,ca), z=mth: z(s,ca, x, y)
			return  total
		else:
			return  parse_arg2(arg,curr_addr,symbols)
		
def parse_arg2(arg,curr_addr=0,symbols={}):
	if arg[0] == "\'":
		if arg[1] == "\'":
			pack1 =  lambda ca,x,y=arg : [ord(x) | 0x80 for x in y[2:-2]]  + ([0] * (len(y) % 2))
			zzz = pack1(0,{}) #...this is giving me a headache.. fine for now
			g = lambda ca,x,n=iter(zzz) :  [x<<8|next(n)  for x in n]
			return lambda ca,x,n=iter(zzz) :  [x<<8|next(n)  for x in n]
		else:
			return  lambda ca,s,y=arg[1:] :int(y,8) & 0xffff
	elif arg[0] == "*":
		return  lambda ca,s,y=arg : ca
	elif arg.isnumeric():
		return  lambda ca,s,y=arg: int(y) & 0xffff
	else:
		return  lambda ca,s,y=arg : s[y]


def decompose_asm(l):
	l = list(l.replace("\n",""))
	ismacroinst = False
	had_quotes = False
	if len(l):
		if l[0] == "*":
			return {"label":None,"ismacro":ismacroinst,"nmemonic":None, "indirect":None, "args":[], "comment":None}
			
		if len(l) > 5:
			if l[4] == "M":
				ismacroinst = True
			l[4] = "\0"
		if len(l) > 10:
			l[9] = "\0"
			
		in_quotes = False
		qc = 0
		for i in range(0, len(l)): #this matches the manual much better, doesnt actually mention quotes
			if in_quotes:
				if l[i] == "'":
					qc -= 1
				if qc == 0:
					in_quotes = False
			else:
				if l[i] == "'":
					qc += 1
				if qc == 2:
					in_quotes = True
					had_quotes = True
					
			if in_quotes == 0 and l[i] == " " and (i > 13):
				l[i] = "\0"
				break
					
		(label, op, addridx, comment) = (None,None,None,None)
		
		chunkdat = [x for x in "".join(l).split("\00")]
		if len(chunkdat) == 4:
			(label, op, addridx, comment) = chunkdat
		elif  len(chunkdat) == 3:
			(label, op, addridx) = chunkdat
		elif  len(chunkdat) == 2:
			(label, op) = chunkdat
		elif  len(chunkdat) == 1:
			(label,) = chunkdat
		
		if label.strip() == '':
			label = None
		else:
			label = label.strip()
		if comment:
			comment = comment.lstrip()
		indirect_bit = False
		if op != None:
			op = op.strip()
			if op.strip() != "":
				if op[-1] == "*":
					op = op[:-1]     #indirect instruction
					indirect_bit = True
		if addridx:
			addridx = addridx.strip()
		else:
			addridx = ""
		
		if had_quotes:
			return {"label":label,"ismacro":ismacroinst,"nmemonic":op, "indirect":indirect_bit, "args":[addridx], "comment":comment}
		else:
			return {"label":label,"ismacro":ismacroinst,"nmemonic":op, "indirect":indirect_bit, "args":addridx.split(","), "comment":comment}
	else:
		return {"label":None,"ismacro":ismacroinst,"nmemonic":None, "indirect":None, "args":[], "comment":None}

class SELOPCODE(dict):
	def __init__(self,asm=None, opcode=None, flags = {}):
		self.label =  None
		self.nmemonic = ""
		self.ispseudo_opcode = True
		self.data = None
		self.symbols = {}
		self.constants = {}
		self.comment = None
		self.comment_space = 30
		self.operand_is_constant = False
		self.field_spec =  DECOMPOSE_BIN_STYLE[SEL810_BARE_VALUE]
		self.flags = flags.copy()
		self.asmline = asm
		self.asmparse = None
		
		if asm != None:
			self.set_asm(asm)
			
		elif opcode != None:
			self.set_opcode(opcode)

	def get_symbols(self):
		return self.symbols
		
	def add_symbol(self,symbol,val):
		self.symbols[symbol] = val

	def get_constants(self):
		return self.constants
		
	def add_constant(self,constant,val):
		self.constants[constant] = val

	def set_opcode(self,opcode):
		bits = bin(opcode & 0xffff)[2:].zfill(16)

		peekdict = {}
		for n,v in DECOMPOSE_BIN_STYLE[SEL810_PEEK_OPCODE].items():
			if n in ["operand"]:
				peekdict[n] = twoscmplment2dec(int(bits[v[0]:v[1]],2),  v[1] - v[0])
			else:
				peekdict[n] = int(bits[v[0]:v[1]],2)

		tempnmemonic = self._get_nmemonic(peekdict["opcode"])
	
		if "augmentcode" in  DECOMPOSE_BIN_STYLE[SEL810_OPCODES[tempnmemonic][0]]: #catches opcodes that are different based on their augment code
			peekdict = {}
			for n,v in DECOMPOSE_BIN_STYLE[SEL810_OPCODES[tempnmemonic][0]].items():
				peekdict[n] = int(bits[v[0]:v[1]],2)

			self.nmemonic = self._get_nmemonic(peekdict["opcode"],peekdict["augmentcode"])
		else:
			self.nmemonic = self._get_nmemonic(peekdict["opcode"])

		if self.nmemonic != None:
			try:
				self.field_spec =  DECOMPOSE_BIN_STYLE[SEL810_OPCODES[self.nmemonic][1]]
				self.set_nmemonic(self.nmemonic)
			except:
				print("FAIL",self.nmemonic,peekdict["opcode"])
		
		
			self.fields = self._populate_fields_from_spec(self.field_spec)
			for n,v in DECOMPOSE_BIN_STYLE[SEL810_OPCODES[self.nmemonic][0]].items():
				if n in ["operand"]:
					self.fields[n] = twoscmplment2dec(int(bits[v[0]:v[1]],2),  v[1] - v[0])
				else:
					self.fields[n] = int(bits[v[0]:v[1]],2)
			self.ispseudo_opcode = False

	def set_nmemonic(self,nmemonic):
		self.nmemonic = nmemonic
		self.fields = self._populate_fields_from_spec(self.field_spec)
		
		if ("opcode" in self.fields) and (nmemonic not in PSEUDO_OPCODES):
			self.fields["opcode"] = SEL810_OPCODES[nmemonic][2]

	def set_asm(self,asmline):
		self.asmparse = decompose_asm(asmline)
#		print(asmline,self.asmparse)
		self._update_from_asm(self.asmparse)
		
	def _update_from_asm(self,ret):
		self.label = ret["label"]
		self.add_symbol(self.label, parse_arg("*")) #will set the label to the current instruction
		self.comment = ret["comment"]
		self.operand_is_constant = False
		
		if not ret["ismacro"]:
			if ret["args"][0].strip() != "":
				arg0 = parse_arg(ret["args"][0])
			else:
				arg0 = None

			self.set_nmemonic(ret["nmemonic"])
			
			if ret["nmemonic"] in PSEUDO_OPCODES:
				self.ispseudo_opcode = True

				if self.nmemonic == "EQU":
					self.add_symbol(self.label, arg0)
				elif self.nmemonic == "DATA":
					if ret["args"][0][:2] == "\'\'":
						self.data = parse_arg(ret["args"][0])(0,{}) #special case of a string never being symbolic, and gets me out of the corner i painted myself into'
						self.comment = ret["args"][0]
					else:
						self.data = [parse_arg(x) for x in ret["args"][0].split(",")]
						if len(ret["args"]) > 1:
							if self.comment == None:
								self.comment = "*"+",".join(ret["args"])
						else:
							if self.comment == None:
								self.comment = ret["args"][0]
								
				elif self.nmemonic == "ABS":
					self.flags["address_mode"] = FLAG_ADDRESS_MODE_ABSOLUTE
					
				elif self.nmemonic == "REL":
					self.flags["address_mode"] = FLAG_ADDRESS_MODE_RELATIVE
					
				elif self.nmemonic == "ORG":
					self.flags["org_address"] = self._resolve_to_value(arg0,0,{})
					self.field_spec =  DECOMPOSE_OBJ_STYLE[OBJOP_SPECIAL_LOAD]
					self.fields = self._populate_fields_from_spec(self.field_spec)
					self.fields["special_literal"] = False
					self.fields["address"] = arg0
					self.fields["objop"] = OBJOP_LITERAL_LOAD
					self.fields["code"] = OBJ_SPECIAL_LOAD_POINT
					self.fields["reloc"] = True
					
				elif self.nmemonic == "END":
					self.flags["has_end_opcode"] = True
				elif self.nmemonic == "NOLS":
					self.flags["supress_output"] = True
				elif self.nmemonic == "LIST":
					self.flags["supress_output"] = False
				elif self.nmemonic == "MACR":
					self.flags["in_macro_def"] = True
				elif self.nmemonic == "EMAC":
					self.flags["in_macro_def"] = False
					print("confirmed")
				elif self.nmemonic == "DAC":
					self.field_spec =  DECOMPOSE_BIN_STYLE[SEL810_DAC_VALUE]
					self.fields = self._populate_fields_from_spec(self.field_spec)
					self.set_nmemonic(ret["nmemonic"]) #hhacky
					if "x" in self.fields:
						if "1" in ret["args"]:
							self.fields["x"] = 1
					if "i" in self.fields:
						self.fields["i"] = ret["indirect"]
					if "operand" in self.fields:
						if arg0 is not None:
							self.fields["operand"] = arg0
							
				elif self.nmemonic == "EAC":
					self.data = [arg0]
					
				elif self.nmemonic == "BSS":
					self.data = [0] * self._resolve_to_value(arg0,0,{})
					
				elif self.nmemonic == "BES":
					self.data = [0] * self._resolve_to_value(arg0,0,{})
					pass #fixme ... label

				elif self.nmemonic == "ZZZ":
					self.field_spec =  DECOMPOSE_BIN_STYLE[SEL810_ZZZ_OPCODE]
					self.fields = self._populate_fields_from_spec(self.field_spec)
					self.set_nmemonic(ret["nmemonic"]) #hhacky
					self.fields["opcode"] = 0
					self.fields["i"] = ret["indirect"]
							
				elif self.nmemonic == "***":
					self.field_spec =  DECOMPOSE_BIN_STYLE[SEL810_ZZZ_OPCODE]
					self.fields = self._populate_fields_from_spec(self.field_spec)
					self.set_nmemonic(ret["nmemonic"]) #hhacky
					self.fields["opcode"] = 0
					self.fields["i"] = ret["indirect"]
				else:
					print("unhandled", self.nmemonic)
				
			else:
				self.ispseudo_opcode = False
				self.field_spec = DECOMPOSE_BIN_STYLE[SEL810_OPCODES[self.nmemonic][0]]
				self.fields = self._populate_fields_from_spec(self.field_spec)
				self.set_nmemonic(ret["nmemonic"])
				
				if ret["args"][0].strip() != "" and ret["args"][0].strip()[0] == "=":
					arg0 = parse_arg(ret["args"][0][1:])
					self.add_constant(arg0,0)
					self.operand_is_constant = True
					self.fields["special_literal"] = True
					self.fields["reloc"] = False
				else:
					self.fields["reloc"] = True

				if "i" in self.fields:
					self.fields["i"] = ret["indirect"]
				if "augmentcode" in self.fields:
					self.fields["augmentcode"] = SEL810_OPCODES[self.nmemonic][3]
				if "operand" in self.fields and arg0 is not None:
						self.fields["operand"] = arg0
				if "address" in self.fields and arg0 is not None:
						self.fields["m"] = True
						self.fields["address"] = arg0
				if "unit" in self.fields and arg0 is not None:
						self.fields["unit"] = arg0
				if "shifts" in self.fields:
						self.fields["shifts"] = arg0
				if "wait" in self.fields and "W" in ret["args"]:
						self.fields["wait"] = True
				if "x" in self.fields and  "1" in ret["args"]:
						self.fields["x"] = True
				if "r" in self.fields and "R" in ret["args"]:
						self.fields["r"] = True
						
				if "special_literal" in self.fields and self.fields["special_literal"]: #this probably belongs elsewhere
					self.fields["objop"] = OBJOP_LITERAL_LOAD
					for field in ["operand","address","unit"]:
						if field in self.fields:
							self.fields["literal"] = self.fields[field]
				else:
					self.fields["objop"] = SEL810_OPCODES[self.nmemonic][1]
		else:
			self.flags["in_macro_inst"] = True
			self.set_nmemonic(ret["nmemonic"])
#			print("yup")

	def _resolve_to_value(self,a, current_addr, symbols={}):
		if callable(a):
			t = a(current_addr,symbols)
			if t:
				return t
			else:
				return 0
		else:
			if a is not None:
				return a
			else:
				return 0

	def _populate_fields_from_spec(self,field_spec,infields=OrderedDict()):
		fields = {}
		for n, (s,e) in field_spec.items():
			bits = e - s
			if n in infields:
				fields[n] = infields[n]
			else:
				fields[n] = 0
		return fields

	def pack_abs(self, current_addr, symbols={}):
		binary = []
		if not self.ispseudo_opcode:
			if "address" in self.fields:  #hack for map0
				if (current_addr  > 512) and self._resolve_to_value( self.fields["address"], current_addr, symbols) < 512: #map0 if we're not in map0 but the address is
					self.fields["m"] = False

			for n, (s,e) in self.field_spec.items():
				bits = e - s
				if self.operand_is_constant and n == "address":
					binary.append(bin(symbols["='%06o" % self._resolve_to_value(self.fields[n], current_addr, symbols)])[2:].zfill(bits))
				else:
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n], current_addr, symbols)))[2:].zfill(bits))

			return[(int("".join(binary),2))]
			
		else:
			if self.nmemonic == "DATA":
				retarry = []
				for i in self.data:
					retarry.append(dec2twoscmplment(self._resolve_to_value(i,current_addr,symbols)))
				return retarry
					
			elif self.nmemonic == "DAC":
				binary = []
				for n, (s,e) in self.field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n], current_addr, symbols)))[2:].zfill(bits))
				return[(int("".join(binary),2))]
				
			elif self.nmemonic == "END":
					return [0]
					
			elif self.nmemonic == "***":
				binary = []
				for n, (s,e) in self.field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n], current_addr, symbols)))[2:].zfill(bits))
				return[(int("".join(binary),2))]
				return []
			
			elif self.nmemonic == "BSS":
				pass #fixme
				
			elif self.nmemonic == "BES":
				pass #fixme

	def pack_rel(self,curr_addr=0,symbols={}):
		if not self.ispseudo_opcode:

			field_spec = DECOMPOSE_OBJ_STYLE[self.fields["objop"]]
			fields = self._populate_fields_from_spec(field_spec, self.fields)

			if SEL810_OPCODES[self.nmemonic][1] == OBJOP_DIRECT_LOAD:
				fields["data"] = self.pack_abs(curr_addr,symbols)[0]

			binary = []
			for n, (s,e) in field_spec.items():
				bits = e - s
				if  n in fields:
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(fields[n],curr_addr,symbols),bits))[2:].zfill(bits)) #ugly hack for a bug i dont get
				else:
					binary.append(bin(dec2twoscmplment(0,bits))[2:].zfill(bits))
			return[(int("".join(binary),2))]
		else:
			if self.nmemonic in ["DATA","BSS"]:
				field_spec = DECOMPOSE_OBJ_STYLE[OBJOP_DIRECT_LOAD]
				fields = self._populate_fields_from_spec(field_spec, self.fields)
				fields["objop"] = OBJOP_DIRECT_LOAD
					
				if "r" in fields: #reloc flag
					fields["r"] = True

				retbuff = []
				for d in self.data:
					fields["data"] = self._resolve_to_value(d,curr_addr,symbols)
					binary = []
					for n, (s,e) in field_spec.items():
						bits = e - s
						binary.append(bin(dec2twoscmplment(self._resolve_to_value(fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
					retbuff.append((int("".join(binary),2)))
				return retbuff
				
			elif self.nmemonic == "***":
				field_spec = DECOMPOSE_OBJ_STYLE[OBJOP_DIRECT_LOAD]
				fields = self._populate_fields_from_spec(field_spec, self.fields)
						
				fields["objop"] = OBJOP_DIRECT_LOAD
				fields["data"] = self.pack_abs(curr_addr,symbols)[0]
				retbuff = []
				binary = []
				for n, (s,e) in field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
				retbuff.append((int("".join(binary),2)))
				return retbuff
				
			elif self.nmemonic == "ORG":
				retbuff = []
				binary = []
				for n, (s,e) in self.field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
				retbuff.append((int("".join(binary),2)))
				return retbuff
				
			elif self.nmemonic == "DAC":
				retbuff = []
				binary = []
				for n, (s,e) in self.field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
				retbuff.append((int("".join(binary),2)))
				return retbuff
				
			elif self.nmemonic == "EAC":
				retbuff = []
				binary = []
				for n, (s,e) in self.field_spec.items():
					bits = e - s
					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
				retbuff.append((int("".join(binary),2)))
				return retbuff
				
			elif self.nmemonic == "END":
#				retbuff = []
#				binary = []
#				for n, (s,e) in self.field_spec.items():
#					bits = e - s
#					binary.append(bin(dec2twoscmplment(self._resolve_to_value(self.fields[n],curr_addr,symbols),bits))[2:].zfill(bits))
#				retbuff.append((int("".join(binary),2)))
				return [0o70400000] #fixme
				
				
				
				
	def pack_asm(self,curr_addr=0,symbols={}):
		if self.nmemonic != None:
			l = "     "
			if self.label:
				if curr_addr == symbols[self.label]:
					l = self.label.ljust(5)
				else:
					if self.label:
						l = "*" + self.label + "   %d" % curr_addr + "   %d" %  symbols[self.label]
					
			args = []
			if not self.ispseudo_opcode:
				indir = " "
				if self.nmemonic not in ["PID","PIE"]:
					for field in ["operand","address","unit"]:
						if field in self.fields:
							if self.operand_is_constant:
								args.append("='%o" % self._resolve_to_value(self.fields[field] ,curr_addr,symbols)) #fixme, could be a flat value
							else:
								args.append("'%o" % self._resolve_to_value(self.fields[field] ,curr_addr,symbols))
								
					if "i" in self.fields and self.fields["i"]:
							indir = "*"
					if "wait" in self.fields and  self.fields["wait"]:
							args.append("W")
					if "r" in self.fields and self.fields["r"]:
							args.append("R")
					if "x" in self.fields and self.fields["x"]:
							args.append("1")
					if "shifts" in self.fields:
						if self.fields["shifts"]:
							args.append("%d" % self._resolve_to_value( self.fields["shifts"],curr_addr,symbols))

				str = "%s%s%s %s" % (l,self.nmemonic,indir, ",".join(args))
				if self.comment:
					str += (" " * (self.comment_space - len(str)))
					str += "*" + self.comment
			else:
				if self.nmemonic == "DATA":
					lines = []
					if not self.operand_is_constant:
						if self.data:
							for d in  self.data:
								args = []
								dd =  self._resolve_to_value(d,curr_addr,symbols)
								args.append("'%o" % dd)
								str = ""
								if not len(lines):
									str += "%s" % l.ljust(5)
								else:
									str += "     "
								str += "%s  %s" % (self.nmemonic, ",".join(args))

								if self.comment and not len(lines):
									str += (" " * (self.comment_space - len(str)))
									str += "*" + self.comment
								else:
									pass
								lines.append(str)
							return(lines)
							
				elif self.nmemonic == "***":
					indir = " "
					if "i" in self.fields:
						if self.fields["i"]:
							indir = "*"
					str = "%s%s%s  %s" % (l,self.nmemonic,indir, ",".join(args))
				elif self.nmemonic == "ORG":
					args.append("'%o" % self._resolve_to_value(self.fields["address"],curr_addr,symbols))
					str = "%s%s  %s" % (l,self.nmemonic, ",".join(args))
				elif self.nmemonic == "DAC":
					args.append("'%o" % self._resolve_to_value(self.fields["operand"],curr_addr,symbols))
					if "x" in self.fields and self.fields["x"]:
							args.append("1")
					str = "%s%s  %s" % (l,self.nmemonic, ",".join(args))
				elif self.nmemonic == "EAC":
					args.append("'%o" % self._resolve_to_value(self.fields["operand"],curr_addr,symbols))
					if "x" in self.fields and self.fields["x"]:
							args.append("1")
					str = "%s%s  %s" % (l,self.nmemonic, ",".join(args))
				elif self.nmemonic == "END":
					str = "%s%s  %s" % (l,self.nmemonic, ",".join(args))

				elif self.nmemonic == "BSS":
					lines = []
					for d in self.data:
						str = ""
						args = []
						if  not len(lines):
							str += "%s" % l.ljust(5)
						else:
							str += "     "
						args.append("'%o" % 0)
						str += "DATA  %s" % (",".join(args))
						lines.append(str)
					return lines

				elif self.nmemonic == "BES":
					str = "%s%s  %s" % (l,self.nmemonic, ",".join(args))
				else:
					str = "******!!************something bad happened" + self.nmemonic

				if self.comment:
					str += (" " * (self.comment_space - len(str)))
					str += "*" + self.comment
		else:
			str = "(bad opcode)"
		return [str]
		
	def _get_nmemonic(self,testopcode, testaugmentcode=None):
		for nmemonic,(type,decompose,opcode,augmentcode, second_word,hwtype) in SEL810_OPCODES.items():
			if testopcode == opcode:
				if testaugmentcode!=None:
					if testaugmentcode == augmentcode:
						return nmemonic
				else:
					return nmemonic

	def get_flags(self):
		if not self.ispseudo_opcode:
			self.flags["has_second_word"] = SEL810_OPCODES[self.nmemonic][4]
		return self.flags
		
	def __len__(self):
		if not self.ispseudo_opcode:
			return 1
		else:
			if self.nmemonic in ["END","EQU","ORG","ABS","REL","LIST","NOLS","MACR","EMAC"]: #more
				return 0
			elif self.nmemonic in  ["DATA","BSS","BES"]:
					return len(self.data)
			elif self.nmemonic in ["DAC","ZZZ","***"]:
				return 1
			else:
				print(self.nmemonic)


class SEL810_ASSEMBLER():
	def __init__(self,filename):
		self.file = filename
		self.macros = {}
		self.program = []
		self.symbols = {"**":0}
		self.constants = {}
		
		self.flags = {"address_mode":FLAG_ADDRESS_MODE_ABSOLUTE,
					"supress_output":False,
					"has_end_opcode":False,
					"in_macro_def":False,
					"in_macro_inst":False,
					"has_second_word": False,
					"org_address": 0
		}
		self.loaded_lines = self.load_file(self.file)
		self.set_const_location(0)
	
	def set_const_location(self,addr):
		self.const_base = addr
	
	def load_file(self, file):
		f = open(self.file)
		loaded_lines = f.readlines()
		return loaded_lines


	def _get_unique_label(self,symbols):
		n = 0
		s = "_%03d" % n
		while s in symbols: #hacky but closer to what the actuall assembler seemed to do
			n = n+1
			s = "_%03d" % n
			if n > 999:
				raise ValueError
		return s
	
	def build_symbols(self):
		print("building symbol table")
		current_offset = 0o0000
		inmacro = False
		macrostore = []
		macroname = None
		for l in self.loaded_lines:
			if len(l.strip()):
				if l[0] != "*":
					op = SELOPCODE(l,flags=self.flags)

					self.flags = op.get_flags()
					if self.flags["in_macro_inst"] == True:
						local_labels = {}
						local_args = {}
						for n in range(len(op.asmparse["args"])):
							local_args["#%d" % (n+1)] = op.asmparse["args"][n]
							
						for o in self.macros[op.nmemonic]:
							nop = SELOPCODE(o,flags=self.flags)
							nop.constants = {} #sloppy

							if nop.label: #not sure about this either #fixme
								u = self._get_unique_label(self.symbols)
								local_labels[nop.label] = u

							for s in range(len(nop.asmparse["args"])):
								if len( nop.asmparse["args"][s]):
									if nop.asmparse["args"][s][0] == "#":
										nop.asmparse["args"][s] = local_args[nop.asmparse["args"][s]]
										
									elif nop.asmparse["args"][s][:2] == "=#":
										nop.asmparse["args"][s] = "=%s" % local_args[nop.asmparse["args"][s][1:]]
										nop.add_constant(parse_arg(nop.asmparse["args"][s][1:]),0)
										
									if nop.asmparse["args"][s][0] == "@":
										nop.asmparse["args"][s] = local_labels[nop.asmparse["args"][s]]
								
							nop._update_from_asm(nop.asmparse) #dont like this block fixme
							if nop.label:
								nop.label = u #sloppy api
								nop.symbols = {} #sloppy
								nop.add_symbol(nop.label, parse_arg("*"))

							for s,v in nop.get_symbols().items():
								self.symbols[s] =  nop._resolve_to_value(v, nop.flags['org_address']+current_offset,self.symbols)
						
							self.program.append(nop)
							current_offset += len(nop)

						self.flags["in_macro_inst"] = False
						
					else:

						if op.nmemonic == "ORG":
							current_offset = 0o0000
						
						if inmacro == False and op.flags["in_macro_def"] == True:
							inmacro = True
							macrostore = []
							macroname = op.label

						elif inmacro == True and op.flags["in_macro_def"] == False:
							self.macros[macroname] = macrostore[1:]
							macroname = None
							inmacro = False
							
						if inmacro == True:
							macrostore.append(op.asmline)

						else:
							for s,v in op.get_symbols().items():
								self.symbols[s] = v(op.flags['org_address']+current_offset,self.symbols)
							self.program.append(op)
							current_offset += len(op)
							
					
		if len(self.program):
			self.set_const_location(self.program[-1].flags['org_address']+current_offset)
		else:
			self.set_const_location(0)
			
	def build_constants(self):
		print("building constant table")
		current_offset = 0o0000
		for op in self.program:
			if op.nmemonic == "ORG":
				current_offset = 0o0000
			for s,v in op.get_constants().items():
				sv  = op._resolve_to_value(s, op.flags['org_address']+current_offset,self.symbols)
				self.symbols["='%06o"%sv] = self.const_base
				if sv  not in self.symbols:
					self.symbols["='%06o"%sv] = self.const_base
					if self.flags["address_mode"] == FLAG_ADDRESS_MODE_ABSOLUTE:  #fixme
						dop = SELOPCODE("     DATA %s" % sv,flags=self.flags)
						self.program.append(dop)
						self.set_const_location(self.const_base + 1)
			current_offset += len(op)

	def build_executable(self, filebase=None):
		if filebase == None:
			filebase = self.file
		if self.flags["address_mode"] == FLAG_ADDRESS_MODE_ABSOLUTE:
			if filebase != None:
				f = open("".join(filebase.split(".")[:-1]) + "_ORG_%06o.BIN" %  self.flags["org_address"],"wb")
			self._buld_executable("pack_abs",f,self._pack_word16, "'%08o","'%06o")
		else:
			if filebase != None:
				f = open("".join(filebase.split(".")[:-1]) + ".OBJ","wb")
			self._buld_executable("pack_rel",f, self._pack_word24, "'%08o","'%08o")
		
		if f != None:
			f.close()


	def _pack_word16(self, word):
		try:
			return struct.pack(">H", word)
		except:
			print("packing error",word)
			return bytes([0])
			
	def _pack_word24(self, word):
		try:
			return struct.pack("BBB", (word&0xff0000) >> 16,(word &0xff00) >> 8, word & 0xff)
		except:
			print("packing error")
			return bytes([0])

	def _buld_executable(self,opfn,fp, wpfn, addrfmt="'%08o",opfmt="'%08o"):
		print("building executable")
		current_offset = 0o0000
		for op in self.program:
			if op.nmemonic == "ORG":
				current_offset = 0o0000
			v = getattr(op, opfn)(op.flags['org_address']+current_offset, self.symbols)
			if(v):
				if fp != None:
					fp.write(wpfn(v[0]))
					
					
				if not op.flags["supress_output"]:
					print(addrfmt % current_offset,opfmt % v[0], op.pack_asm(op.flags['org_address']+current_offset,self.symbols)[0])
				t = len(op)
				if t > 1:
					current_offset  += 1
					for i in range(1,t):
						if fp != None:
							fp.write(wpfn(v[i]))
						if not op.flags["supress_output"]:
							print(addrfmt % current_offset,opfmt % v[i], op.pack_asm(op.flags['org_address']+current_offset,self.symbols)[i])
						current_offset  += 1
				else:
					current_offset  += t

	def write_symbols(self, fn=None):
		if fn == None:
			fn = ".".join(self.file.split(".")[:-1]) + ".SYM"
		print("writing symbol file %s" % fn)
		f = open(fn,"wb")
		pickle.dump(self.symbols,f)
		f.close()





# TODO
# does not do sane things with literals in absolute mode
# EAC/DAC in object mode, not sure its correct
# BES

if __name__ == '__main__':
	asm = SEL810_ASSEMBLER(sys.argv[1]) #sel810asm/asm/HELLO_WORLD.ASM")#("sel810asm/asm/CLT4_V1.ASM")#("sel810asm/asm/boot.asm")
	asm.build_symbols()
	print(asm.macros)
	asm.build_constants()
	asm.build_executable()
	print(asm.symbols)
	asm.write_symbols()
#	for i in range(65535):
#		op = SELOPCODE(opcode=i)
#		print(op.pack_asm())

