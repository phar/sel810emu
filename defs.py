

CPU_HERTZ = 572000 #changing this number does not make the CPU go faster
MINUS_FULL_SCALE = -32767 #according to the internets

IDLE_UPDATE_MILLISECONDS = 64#number of milliseconds between updates to the controlpanel with no change on the bus

MAX_MEM_SIZE = 0x7fff
		
SEL_OPTION_NONE						= 0x00
SEL_OPTION_PROTECT_1B_AND_TRAP_MEM	= 0x01
SEL_OPTION_PROTECT_2B_AND_TRAP_MEM	= 0x02
SEL_OPTION_VBR						= 0x04
SEL_OPTION_HW_INDEX					= 0x08
SEL_OPTION_STALL_ALARM				= 0x10
SEL_OPTION_AUTO_START				= 0x20
SEL_OPTION_IO_PARITY				= 0x40
SEL_OPTION_60HZ_RTC					= 0x80


CONSOLE_HISTORY_FILE = '~/.sel810_console_history'

CORE_MEMORY_FILE ="sel810.coremem"
