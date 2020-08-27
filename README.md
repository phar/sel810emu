<pre>
# connect to asr33 console:
socat - UNIX-CONNECT:/tmp/SEL810_asr33

#load a paper tape into the tape reader
python sel810_papertape.py  sel810asm/obj/clt2_v2.227 #fix me, this is wrong, i probably shouldnt be using the 227 library to load it

lil-Euclid-10:sel810emu phar$ python sel810emu.py asr33_bootloader.bin 
006000 CEU
asr33 command 2048
006002 AIP
asr33 read 104
006003 SAZ
006004 BRU
000006 HLT
000006 HLT
000006 HLT
000006 HLT


i dont know why im writing this
</pre>
