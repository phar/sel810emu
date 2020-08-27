<pre>
# connect to asr33 console:
socat - UNIX-CONNECT:/tmp/SEL810_asr33

#load a paper tape into the tape reader
python sel810_papertape.py  sel810asm/obj/clt2_v2.227 #fix me, this is wrong, i probably shouldnt be using the 227 library to load it

lil-Euclid-10:sel810emu phar$ python sel810emu.py 
started external unit nulldev on /tmp/SEL810_nulldev
started external unit asr33 on /tmp/SEL810_asr33
started external unit paper tape on /tmp/SEL810_paper_tape
started external unit card punch on /tmp/SEL810_card_punch
started external unit card reader on /tmp/SEL810_card_reader
started external unit line printer on /tmp/SEL810_line_printer
started external unit TCU 1 on /tmp/SEL810_TCU_1
started external unit TCU 2 on /tmp/SEL810_TCU_2
started external unit INVALID 1 on /tmp/SEL810_INVALID_1
started external unit INVALID 2 on /tmp/SEL810_INVALID_2
started external unit typewriter on /tmp/SEL810_typewriter
started external unit X-Y plotter on /tmp/SEL810_X-Y_plotter
started external unit interval timer on /tmp/SEL810_interval_timer
started external unit movable head disc on /tmp/SEL810_movable_head_disc
started external unit CRT on /tmp/SEL810_CRT
started external unit fixed head disc on /tmp/SEL810_fixed_head_disc
Welcome to the SEL emulator/debugger. Type help or ? to list commands.

(SEL810x) load 0 HELLO_WORLD-ORG_0000.bin
ok
(SEL810x) disassemble 0 20
0x0000	 SPB	'15
0x0001	 HLT	
0x0002	 HLT	
0x0003	 AOP	'01, W
0x0004	 LSL	8
0x0005	 AOP	'01, W
0x0006	 BRU*	'2
0x0007	 HLT	
0x0008	 MOP	'01, W
0x0009	 DIV*	'400, 1
0x000a	 MOP	'01, W
0x000b	 DIV	'0, 1
0x000c	 BRU*	'7
0x000d	 HLT	
0x000e	 SPB	'7
0x000f	 HLT	
0x0010	 LAA	'33, 1
0x0011	 SPB	'2
0x0012	 IBS	
0x0013	 BRU	'20
ok
(SEL810x) step
00000000 SPB '15
ok
(SEL810x) 
00000014 SPB '7
ok
(SEL810x) 
00000008 MOP '01, W
asr33 write -29440
ok
(SEL810x) 
00000010 MOP '01, W
asr33 write -30208
ok
(SEL810x) quit
nulldev external unit shutting down
asr33 external unit shutting down
paper tape external unit shutting down
card punch external unit shutting down
card reader external unit shutting down
line printer external unit shutting down
TCU 1 external unit shutting down
TCU 2 external unit shutting down
INVALID 1 external unit shutting down
INVALID 2 external unit shutting down
typewriter external unit shutting down
X-Y plotter external unit shutting down
interval timer external unit shutting down
movable head disc external unit shutting down
CRT external unit shutting down
fixed head disc external unit shutting down
ok
None
lil-Euclid-10:sel810emu phar$ 

i dont know why im writing this
</pre>
