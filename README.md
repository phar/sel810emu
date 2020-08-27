<pre>
# connect to asr33 console:
socat - UNIX-CONNECT:/tmp/SEL810_asr33

#load a paper tape into the tape reader
python sel810_papertape.py  sel810asm/obj/clt2_v2.227 #fix me, this is wrong, i probably shouldnt be using the 227 library to load it

lil-Euclid-10:sel810emu phar$ python sel810emu.py HELLO_WORLD-ORG_0000.bin 
000000 SPB '15
000016 SPB '7
000010 MOP '01, W
asr33 write -29440
000012 MOP '01, W
asr33 write -30208
000014 BRU '7
-> 15
000000 SPB '15
000016 SPB '7
000010 MOP '01, W
asr33 write -29440
000012 MOP '01, W
asr33 write -30208
000014 BRU '7
-> 15
000000 SPB '15
000016 SPB '7
000010 MOP '01, W
asr33 write -29440
000012 MOP '01, W
asr33 write -30208
000014 BRU '7
-> 15
000000 SPB '15
000016 SPB '7
000010 MOP '01, W
asr33 write -29440
000012 MOP '01, W
asr33 write -30208
000014 BRU '7
-> 15
halted


i dont know why im writing this
</pre>
