#!/usr/bin/env python3
"""Apply the Carby Component pin map (measured by diag.py on the real board) to ~/gcvideo."""
import os, re, sys
G = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi/src")
def edit(name, fn):
    p = os.path.join(G, name); s = open(p).read(); t = fn(s)
    if t == s: sys.exit(f"no change made to {name} - stopping")
    open(p, "w").write(t); print("patched", name)

# Console inputs as measured live on the Carby (diag capture):
MAP = {"VData[0]": 72, "VData[1]": 68, "VData[2]": 71, "VData[3]": 65,
       "VData[4]": 64, "VData[5]": 61, "VData[6]": 62, "VData[7]": 60,
       "CSel": 73, "VClockN": 90,
       "I2S_Data": 56, "I2S_LRClock": 59, "I2S_BClock": 57}

def ucf(s):
    for net, pin in MAP.items():
        s, n = re.subn(r'(NET "%s"\s+LOC = )P\d+;' % re.escape(net), r'\g<1>P%d;' % pin, s)
        if n != 1: sys.exit(f"could not find LOC for {net}")
    s, n = re.subn(r'NET "SPDIF_Out"\s+LOC = P\d+;\n', '', s)   # P73 is CSel on the Carby; no S/PDIF output
    if n != 1: sys.exit("could not find SPDIF_Out LOC")
    return s
edit("constraints-dualgc.ucf", ucf)
edit("constraints-common.ucf", lambda s: re.sub(r'NET "SPDIF_Out"\s+IOSTANDARD = LVCMOS33;\n', '', s))
edit("constraints-audio.ucf", lambda s: re.sub(r'NET "Inst_Datapipe/audio_main\.Inst_Audio/Inst_SPDIFEnc/shifter\*" TNM_NET = "TN_SPDIF_Shifter";\nTIMESPEC TS_AudioIgnore = FROM "CLOCK_54" TO "TN_SPDIF_Shifter" TIG;\n', '', s))
def top(s):
    s = s.replace("    -- audio out\n    SPDIF_Out  : out std_logic;\n\n", "")
    s = s.replace("    SPDIF_Out   => SPDIF_Out,", "    SPDIF_Out   => open,")
    return s
edit("toplevel_gcdual.vhd", top)
print("Carby pin map applied.")
