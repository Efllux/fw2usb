#!/usr/bin/env python3
"""KiCad8 PCB source construction. Connector footprint still requires drawing.
No routing result or clean DRC is implied by creating a placed board.
"""
import json,sys
from pathlib import Path
import wx
app=wx.App(False)
import pcbnew as k
from design import ROOT,parts,uid
mm=k.FromMM
def pos(x,y):return k.VECTOR2I(mm(x),mm(y))
def pad(fp,number,x,y,w,h,drill=None):
 p=k.PAD(fp);p.SetNumber(str(number));p.SetPosition(pos(x,y));p.SetSize(pos(w,h))
 p.SetShape(k.PAD_SHAPE_RECT if drill is None else k.PAD_SHAPE_OVAL)
 p.SetAttribute(k.PAD_ATTRIB_SMD if drill is None else k.PAD_ATTRIB_PTH)
 layers=k.LSET()
 for layer in ([k.F_Cu,k.F_Paste,k.F_Mask] if drill is None else [k.F_Cu,k.In1_Cu,k.In2_Cu,k.B_Cu,k.F_Mask,k.B_Mask]):layers.AddLayer(layer)
 p.SetLayerSet(layers)
 if drill is not None:p.SetDrillSize(pos(drill,drill))
 fp.Add(p);return p

def footprint(name):
 f=k.FOOTPRINT(None);f.SetFPID(k.LIB_ID('fw2usb',name))
 if name in ['R','C','R0603','C0603','C0805']:
  spacing=.55;w=.6;h=.6
  if '0603' in name:spacing=.8;w=.9;h=.95
  if '0805' in name:spacing=1.0;w=1.0;h=1.4
  pad(f,1,-spacing,0,w,h);pad(f,2,spacing,0,w,h)
 elif name=='HTQFP80':
  for i in range(20):
   pad(f,i+1,-6.8,-4.75+i*.5,1.5,.3)
   pad(f,i+21,-4.75+i*.5,6.8,.3,1.5)
   pad(f,i+41,6.8,4.75-i*.5,1.5,.3)
   pad(f,i+61,4.75-i*.5,-6.8,.3,1.5)
  pad(f,81,0,0,6,6)
 elif name=='Header20':
  for i in range(20):pad(f,i+1,(i%2)*2.54,(i//2)*2.54,1.7,1.7,1.0)
 elif name=='Header2':
  for i in range(2):pad(f,i+1,0,i*2.54,1.7,1.7,1.0)
 elif name=='Crystal4':
  for number,x,y in [(1,-1.1,.8),(2,1.1,.8),(3,1.1,-.8),(4,-1.1,-.8)]:pad(f,number,x,y,1.2,1.0)
 elif name=='FW6':
  raise RuntimeError('Molex mechanical drawing unavailable: do not invent pad or retention dimensions')
 else:raise ValueError(name)
 f.Reference().SetVisible(False);f.Value().SetVisible(False)
 return f

if __name__=='__main__':
 (ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name \"fw2usb\") (type \"KiCad\") (uri \"${KIPRJMOD}/fw2usb.pretty\") (options \"\") (descr \"Original footprints\")))\n')
 board=k.BOARD();board.SetCopperLayerCount(4)
 nets={}
 for name in sorted({pin[2] for p in parts for pin in p['pins'] if pin[2]}):
  net=k.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
 for p in parts:
  if p['foot']=='FW6':continue # explicitly incomplete; schematic/BOM retain connector
  fp=footprint(p['foot']);fp.SetReference(p['ref']);fp.SetValue(p['value']);fp.SetPosition(pos(*p['xy']))
  fp.SetPath(k.KIID_PATH('/'+uid('schematic')+'/'+uid(p['ref'])))
  net_by_pad={pin[0]:pin[2] for pin in p['pins']}
  for pad_ in fp.Pads():
   name=net_by_pad[pad_.GetNumber()]
   if name:pad_.SetNet(nets[name])
  board.Add(fp)
  k.PCB_IO_KICAD_SEXPR().FootprintSave(str(ROOT/'fw2usb.pretty'),fp)
 for a,b in [((30,28),(86,28)),((86,28),(86,85)),((86,85),(30,85)),((30,85),(30,28))]:
  line=k.PCB_SHAPE();line.SetShape(k.SHAPE_T_SEGMENT);line.SetStart(pos(*a));line.SetEnd(pos(*b));line.SetLayer(k.Edge_Cuts);line.SetWidth(mm(.05));board.Add(line)
 board.GetDesignSettings().m_MinClearance=mm(.125)
 k.SaveBoard(str(ROOT/'phy-breakout.kicad_pcb'),board)
 print('Placed69 components; J1/route pending. NOT DRC clean.')
