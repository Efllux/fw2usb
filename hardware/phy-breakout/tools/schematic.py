#!/usr/bin/env python3
"""Create a self-contained, labeled KiCad8 schematic from the reviewed net table."""
from design import ROOT,parts,uid,q

def effect(justify=''):
 return '(effects (font (size 1.0 1.0))'+(' (justify '+justify+')' if justify else '')+')'
def geometry(p):
 n=len(p['pins']);rows=(n+1)//2
 if n>20:return [(-17.78,round((rows-1)*1.27-i*2.54,4),0) for i in range(rows)]+[(17.78,round((rows-1)*1.27-i*2.54,4),180) for i in range(n-rows)]
 if n==2:return [(-5.08,0,0),(5.08,0,180)]
 return [(-10.16,round((n-1)*1.27-i*2.54,4),0) for i in range(n)]

def library(p):
 ref=p['ref'];pins=p['pins'];geo=geometry(p);width=12.7 if len(pins)>20 else 5.08 if len(pins)>2 else 2.54
 height=max(1.27,(len(pins)+1)//2*1.27) if len(pins)>20 else max(1.27,len(pins)*1.27) if len(pins)>2 else 1.27
 s=f'''(symbol "fw2usb:{ref}" (pin_names (offset 0.508)) (in_bom yes) (on_board yes)
 (property "Reference" {q(ref[0])} (at 0 {height+2.54} 0) {effect()})
 (property "Value" {q(p['value'])} (at 0 {-height-2.54} 0) {effect()})
 (symbol "{ref}_0_1" (rectangle (start {-width} {height}) (end {width} {-height}) (stroke (width 0.254) (type default)) (fill (type background))))'''
 # append symbol pins before final enclosing closing
 s=s+f'(symbol "{ref}_1_1" '
 for (num,name,net,kind),(x,y,angle) in zip(pins,geo):
  length=abs(x)-width
  s+=f'(pin {kind} line (at {x} {y} {angle}) (length {length}) (name {q(name)} {effect()}) (number {q(num)} {effect()}))'
 return s+'))'

root=uid('schematic')
s=f'''(kicad_sch (version 20231120) (generator "fw2usb") (uuid {root}) (paper "A2")
 (title_block (title "fw2usb legacy PHY breakout - engineering WIP") (rev "0.1") (comment 1 "Public TI SLLSFA1; legacy link, port2 DS; external3.3V; VP NC"))
 (lib_symbols {''.join(library(p) for p in parts)})'''
for index,p in enumerate(parts):
 if p['ref']=='U1':x,y=60.96,101.6
 elif p['ref']=='J2':x,y=109.22,76.2
 elif p['ref']=='J3':x,y=109.22,121.92
 elif p['ref']=='J1':x,y=109.22,152.4
 else:i=index-1;x=132.08+(i//12)*68.58;y=38.1+(i%12)*22.86
 instance=uid(p['ref']);geometry_p=geometry(p)
 half=((len(p['pins'])+1)//2*1.27 if len(p['pins'])>20 else len(p['pins'])*1.27 if len(p['pins'])>2 else 1.27)+2.54
 s+=f'''(symbol (lib_id "fw2usb:{p['ref']}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {instance})
 (property "Reference" {q(p['ref'])} (at {x} {y-half} 0) {effect()})
 (property "Value" {q(p['value'])} (at {x} {y+half} 0) {effect()})
 (property "Footprint" "fw2usb:{p['foot']}" (at {x} {y} 0) (effects (font (size 1 1)) hide))
 (property "MPN" {q(p['mpn'])} (at {x} {y} 0) (effects (font (size 1 1)) hide))
 (property "Verify" {q(p['verify'])} (at {x} {y} 0) (effects (font (size 1 1)) hide))
 (instances (project "phy-breakout" (path "/{root}" (reference {q(p['ref'])}) (unit 1)))))'''
 for (number,name,net,kind),(dx,dy,angle) in zip(p['pins'],geometry_p):
  px=round(x+dx,4);py=round(y-dy,4)
  if net is None:
   s+=f'(no_connect (at {px} {py}) (uuid {uid(p["ref"]+number+"nc")}))';continue
  end=round(px+(-5.08 if angle==0 else 5.08),4)
  s+=f'(wire (pts (xy {px} {py}) (xy {end} {py})) (stroke (width 0) (type default)) (uuid {uid(p["ref"]+number+"w")}))'
  s+=f'(label {q(net)} (at {end} {py} 0) {effect("right" if angle==0 else "left")} (uuid {uid(p["ref"]+number+"label")}))'
s+='(text "WIP: Not released for fabrication. ERC/layout/BOM verification pending. No cable VP connection." (at 60 190 0) '+effect('left')+' (uuid '+uid('notice')+'))'
s+='(sheet_instances (path "/" (page "1"))))\n'
(ROOT/'phy-breakout.kicad_sch').write_text(s)
(ROOT/'phy-breakout.kicad_pro').write_text('{}\n')
(ROOT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "fw2usb") (type "KiCad") (uri "${KIPRJMOD}/fw2usb.kicad_sym") (options "") (descr "Original TI fact based symbols")))\n')
(ROOT/'fw2usb.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "fw2usb") '+''.join(library(p).replace('"fw2usb:'+p['ref']+'"','"'+p['ref']+'"',1) for p in parts)+')\n')
print('wrote',ROOT/'phy-breakout.kicad_sch')
