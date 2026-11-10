#!/usr/bin/env python3
"""Original KiCad8 source generator; public TI pin/function facts, no vendor CAD.
Run with KiCad's bundled Python for PCB export. All dimensions in mm.
"""
import csv,json,math,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def uid(name):return str(uuid.uuid5(uuid.NAMESPACE_URL,'fw2usb-phy-breakout-v0/'+name))
def q(s):return json.dumps(str(s))
PINS={1:'PINT',2:'S5_LKON',3:'LREQ',4:'DGND',5:'PCLK',6:'DVDD33',7:'LCLK_PMC',8:'DVDD_CORE',9:'CTL0',10:'CTL1',11:'D0',12:'D1',13:'D2',14:'DGND',15:'D3',16:'D4',17:'D5',18:'DVDD33',19:'D6',20:'D7',21:'AGND',22:'R1',23:'R0',24:'AVDD',25:'PLLGND',26:'XO',27:'XI',28:'PLLGND',29:'PLLVDD_CORE',30:'PLLVDD_CORE',31:'PLLVDD33',32:'S4',33:'S3',34:'CPS',35:'SE',36:'SM',37:'DVDD_CORE',38:'DGND',39:'AVDD',40:'AGND',41:'TPB0-',42:'TPB0+',43:'AGND',44:'AVDD',45:'TPA0-',46:'TPA0+',47:'TPBIAS0',48:'TPB1-',49:'TPB1+',50:'AGND',51:'AVDD',52:'TPA1-',53:'TPA1+',54:'TPBIAS1',55:'TPB2-',56:'TPB2+',57:'AVDD',58:'TPA2-',59:'TPA2+',60:'TPBIAS2',61:'AGND',62:'AGND',63:'AVDD',64:'DGND',65:'DVDD_CORE',66:'S2_PC0',67:'S1_PC1',68:'S0_PC2',69:'DVDD33',70:'DVDD33',71:'DVDD_CORE',72:'DGND',73:'VREG_PD',74:'BMODE',75:'RESET_N',76:'DGND',77:'PD',78:'TESTM',79:'ENHANCE_EN',80:'LPS',81:'EP'}
assert set(PINS)==set(range(1,82))
SUPPLY={'AVDD','DVDD33','PLLVDD33'}
GROUND={'AGND','DGND','PLLGND','EP','LCLK_PMC','BMODE','VREG_PD','PD','SM','SE','TPB1-','TPB1+'}
NC={'PINT','TPB0-','TPB0+','TPA0-','TPA0+','TPBIAS0','TPA1-','TPA1+','TPBIAS1'}
UPINS=[]
for number,name in PINS.items():
 net='3V3' if name in SUPPLY else 'GND' if name in GROUND else None if name in NC else name
 kind='power_in' if name in SUPPLY|{'AGND','DGND','PLLGND','EP','DVDD_CORE','PLLVDD_CORE'} else 'bidirectional'
 if name in {'LREQ','LPS','RESET_N','TESTM','ENHANCE_EN','S4','S3','S2_PC0','S1_PC1','S0_PC2','CPS','XI','LCLK_PMC','VREG_PD','BMODE','PD','SM','SE'}:kind='input'
 if name in {'PCLK','XO','PINT'}:kind='output'
 if name.startswith('TP'):kind='passive'
 if number in {8,29}:kind='power_out'
 UPINS.append((str(number),name,net,kind))
parts=[]
def add(ref,value,foot,pins,xy,mpn,verify='[verify] assembly/stock'):
 parts.append(dict(ref=ref,value=value,foot=foot,pins=pins,xy=xy,mpn=mpn,verify=verify))
def two(ref,value,a,b,xy,mpn,kind='R',verify='[verify] assembly/stock'):
 add(ref,value,kind,[('1','1',a,'passive'),('2','2',b,'passive')],xy,mpn,verify)
add('U1','TSB41BA3FTPFPEP','HTQFP80',UPINS,(50,50),'TSB41BA3FTPFPEP','[verify] legacy register/timing cross-check; EP6x6; electrical bring-up')
# Header is a signal interposer; 18 is reference only, not a power source.
header=['GND','SCLK_H','D0','D1','D2','D3','D4','D5','D6','D7','CTL0','CTL1','LREQ','LPS_H','LKON_H','RESET_N','GND','3V3','GND',None]
add('J2','ECP5_PHY_2x10','Header20',[(str(i+1),n or 'NC',n,'bidirectional' if n not in ['GND','3V3',None] else 'passive') for i,n in enumerate(header)],(78,37),'Samtec TSW-110-07-G-D','[verify] header orientation; ULX3S net map in README; no ULX supply tie')
add('J3','BENCH_3V3','Header2',[('1','3V3','3V3','power_out'),('2','GND','GND','power_out')],(80,67),'Samtec TSW-102-07-G-S','[verify] external regulated3.3V current budget')
add('J1','FW400_6PIN','FW6',[('1','VP',None,'passive'),('2','VG','GND','passive'),('3','TPB-','TPB2-','passive'),('4','TPB+','TPB2+','passive'),('5','TPA-','TPA2-','passive'),('6','TPA+','TPA2+','passive'),('SH','SHELL','SHIELD','passive')],(50,79),'Molex 53460-0639','[verify] vendor drawing/receptacle view and retention holes; VP deliberately NC')
# Legacy mode20: S5/S4=1,S3/S2/S1/S0=0. Port2/1 DS, unusedport0 bilingual.
for ref,a,b,xy in [('R1','S5_LKON','3V3',(60,37)),('R2','S4','3V3',(44,64)),('R3','S3','GND',(42,64)),('R4','S2_PC0','GND',(60,45)),('R5','S1_PC1','GND',(60,43)),('R6','S0_PC2','GND',(60,41)),('R7','TESTM','3V3',(58,36)),('R8','ENHANCE_EN','3V3',(56,36)),('R9','CPS','GND',(40,64)),('R10','LPS','LPS_H',(54,36)),('R11','S5_LKON','LKON_H',(62,37))]:two(ref,'1k',a,b,xy,'Yageo RC0402FR-071KL')
two('R12','22','PCLK','SCLK_H',(40,44),'Yageo RC0402FR-0722RL')
two('R13','6.34k 1%','R0','R1',(40,60),'Yageo RC0402FR-076K34L')
for ref,a,b,xy in [('R14','TPA2-','TPBIAS2',(59,61)),('R15','TPA2+','TPBIAS2',(59,59)),('R16','TPB2-','TPB_CM',(62,61)),('R17','TPB2+','TPB_CM',(62,59))]:two(ref,'56.2 1%',a,b,xy,'Yageo RC0402FR-0756R2L')
two('R18','4.99k 1%','TPB_CM','GND',(64,62),'Yageo RC0402FR-074K99L')
two('C1','270p C0G','TPB_CM','GND',(64,64),'Murata GRM1555C1H271JA01D','C')
two('C2','1u','TPBIAS2','GND',(58,64),'Murata GRM155R61A105KE15D','C')
two('R19','1M','SHIELD','GND',(54,75),'Yageo RC0603FR-071ML',kind='R0603')
two('C3','10n 50V','SHIELD','GND',(56,75),'Murata GRM188R71H103KA01D','C0603')
two('C4','1n 50V','SHIELD','GND',(58,75),'Murata GRM1885C1H102JA01D','C0603')
two('C5','220n','RESET_N','GND',(52,36),'Murata GRM155R71C224KA12D','C','[verify] ramp/clock startup and minimum2ms reset; FPGA open-drain hold')
add('Y1','49.152MHz fundamental CL6p','Crystal4',[('1','XI','XI','passive'),('2','GND','GND','passive'),('3','XO','XO','passive'),('4','GND','GND','passive')],(39,57),'Abracon ABM8W-49.1520MHZ-6-K1Z-T3','[verify] fundamental mode/ESR/drive/CL and assembled PCLK ppm')
two('C6','6.8p C0G','XI','GND',(37,55),'Murata GRM1555C1H6R8CA01D','C','[verify] tune for PCB+PHY parasitics, measure PCLK within100ppm')
two('C7','6.8p C0G','XO','GND',(37,59),'Murata GRM1555C1H6R8CA01D','C','[verify] tune for PCB+PHY parasitics')
# One100n+1n per power terminal; two core rails must remain distinct.
cap=8
for number in [6,18,24,31,39,44,51,57,63,69,70,8,37,65,71,29,30]:
 rail='3V3' if PINS[number] in SUPPLY else PINS[number]
 # Place near the corresponding package side. Revised interactively after routing.
 side=(number-1)//20;idx=(number-1)%20;along=-4.75+idx*.5
 xy={6:(39,46),18:(39,54),24:(44,63),31:(49,63),39:(55,63),44:(63,55),51:(63,49),57:(63,44),63:(55,37),69:(49,37),70:(47,35),8:(37,48),37:(53,65),65:(53,35),71:(45,37),29:(47,65),30:(45,63)}[number]
 for offset,value,mpn in [(0,'100n','Murata GRM155R71C104KA88D'),(1,'1n','Murata GRM1555C1H102JA01D')]:
  # Alternating radial rows keep paired footprints physically distinct.
  if side in [0,2]:pos=(xy[0]+(-2 if side==0 else 2)*offset,xy[1])
  else:pos=(xy[0],xy[1]+(2 if side==1 else -2)*offset)
  two('C'+str(cap),value,rail,'GND',pos,mpn,'C');cap+=1
for rail,xy in [('DVDD_CORE',(61,40)),('PLLVDD_CORE',(43,62))]:two('C'+str(cap),'1u',rail,'GND',xy,'Murata GRM155R61A105KE15D','C');cap+=1
for xy in [(38,48),(62,48),(46,36)]:two('C'+str(cap),'10u 10V','3V3','GND',xy,'Murata GRM21BR61A106KE19L','C0805');cap+=1

# Resolve initial placement collisions deterministically; this is placement only,
# not evidence of SI, decoupling inductance or a routed board.
def halfsize(foot):
 return {'HTQFP80':(7.8,7.8),'Header20':(2.2,12.3),'Header2':(1.1,2.4),'Crystal4':(1.9,1.5),'FW6':(6,5),'C0805':(1.7,.95),'R0603':(1.35,.75),'C0603':(1.35,.75)}.get(foot,(1,.5))
placed=[]
for p in parts:
 x,y=p['xy'];hx,hy=halfsize(p['foot'])
 if p['foot']=='Header20':x+=1.27;y+=11.43
 if p['foot']=='Header2':y+=1.27
 candidates=[(x,y)]
 for radius in [.5,1,1.5,2,2.5,3,4,5,6]:
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:candidates.append((x+dx*radius,y+dy*radius))
 for nx,ny in candidates:
  if all(abs(nx-px)>=hx+phx+.2 or abs(ny-py)>=hy+phy+.2 for px,py,phx,phy in placed):
   placed.append((nx,ny,hx,hy))
   p['xy']=(nx-(1.27 if p['foot']=='Header20' else 0),ny-(11.43 if p['foot']=='Header20' else 1.27 if p['foot']=='Header2' else 0));break
 else:raise RuntimeError('placement collision for '+p['ref'])

if __name__=='__main__':
 (ROOT/'design.json').write_text(json.dumps(parts,indent=2)+'\n')
 with (ROOT/'BOM.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['Reference','Value','Footprint','Manufacturer part','Verification'])
  for p in parts:w.writerow([p['ref'],p['value'],'fw2usb:'+p['foot'],p['mpn'],p['verify']])
 print(len(parts),'components',cap-1,'capacitors')
