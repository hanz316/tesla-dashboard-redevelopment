#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

W,H=1920,480
TOP_CUT=116
BOTTOM_CUT=51
OUT=Path('horizon-v6-preview.png')
REG='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def font(n,b=False):
    try: return ImageFont.truetype(BOLD if b else REG,n)
    except: return ImageFont.load_default()

def trapezoid_mask(im):
    d=ImageDraw.Draw(im)
    d.polygon([(0,0),(TOP_CUT,0),(BOTTOM_CUT,H),(0,H)],fill=(0,0,0))
    d.polygon([(W,0),(W-TOP_CUT,0),(W-BOTTOM_CUT,H),(W,H)],fill=(0,0,0))

def gradient():
    im=Image.new('RGB',(W,H),(9,14,18)); p=im.load()
    for y in range(H):
        for x in range(W):
            nx=(x-960)/960; ny=(y-245)/300
            glow=max(0.0,1.0-(nx*nx+ny*ny))*0.45
            horizon=max(0.0,1-abs(y-150)/180)*0.17
            p[x,y]=(int(9+18*glow+5*horizon),int(14+27*glow+8*horizon),int(18+34*glow+14*horizon))
    return im

def draw_fallback_vehicle(d,cx,cy,s=1.0):
    # Engineering fallback only. Runtime asset contract expects layered PNG vehicle assets.
    shadow=(cx-120*s,cy+72*s,cx+120*s,cy+105*s)
    d.ellipse(shadow,fill=(4,7,9))
    body=[(cx-104*s,cy+50*s),(cx-116*s,cy+9*s),(cx-89*s,cy-60*s),(cx-48*s,cy-90*s),(cx+48*s,cy-90*s),(cx+89*s,cy-60*s),(cx+116*s,cy+9*s),(cx+104*s,cy+50*s),(cx+72*s,cy+84*s),(cx-72*s,cy+84*s)]
    d.polygon(body,fill=(126,132,136),outline=(212,218,221))
    d.polygon([(cx-61*s,cy-56*s),(cx-41*s,cy-78*s),(cx+41*s,cy-78*s),(cx+61*s,cy-56*s),(cx+50*s,cy-15*s),(cx-50*s,cy-15*s)],fill=(20,30,37))
    d.rounded_rectangle((cx-82*s,cy+18*s,cx+82*s,cy+60*s),radius=int(14*s),fill=(96,102,106))
    d.line((cx-70*s,cy+48*s,cx-31*s,cy+52*s),fill=(242,76,56),width=max(2,int(5*s)))
    d.line((cx+31*s,cy+52*s,cx+70*s,cy+48*s),fill=(242,76,56),width=max(2,int(5*s)))
    d.line((cx-71*s,cy-52*s,cx-42*s,cy-60*s),fill=(222,232,238),width=max(2,int(3*s)))
    d.line((cx+42*s,cy-60*s,cx+71*s,cy-52*s),fill=(222,232,238),width=max(2,int(3*s)))

def text(d,xy,s,f,c,anchor='mm'):
    d.text(xy,s,font=f,fill=c,anchor=anchor)

def main():
    im=gradient(); d=ImageDraw.Draw(im)
    # L1 spatial road: filled surface, multiple depth bands, faded lane hierarchy.
    road=[(435,480),(1485,480),(1168,152),(752,152)]
    d.polygon(road,fill=(15,22,27))
    for i in range(7):
        y0=170+i*43
        t=(y0-152)/(480-152)
        lx=752+(435-752)*t; rx=1168+(1485-1168)*t
        d.line((lx,y0,rx,y0),fill=(18+i*2,26+i*2,31+i*2),width=1)
    # lane boundaries
    for side in (-1,1):
        pts=[]
        for y in range(165,481,28):
            t=(y-152)/(480-152)
            x=960+side*(112+250*t)
            pts.append((x,y))
        for i in range(0,len(pts)-1,2):
            d.line((*pts[i],*pts[min(i+1,len(pts)-1)]),fill=(120,139,148),width=max(1,1+i//4))
    # AP corridor area
    corridor=[(770,480),(1150,480),(1030,182),(890,182)]
    d.polygon(corridor,fill=(18,46,58))
    d.line((770,480,890,182),fill=(72,135,161),width=3)
    d.line((1150,480,1030,182),fill=(72,135,161),width=3)
    # coarse surrounding regions: no fake exact coordinates/distances
    d.rounded_rectangle((792,204,874,258),14,fill=(47,57,62),outline=(82,98,104))
    d.rounded_rectangle((1185,300,1292,365),18,fill=(43,51,55),outline=(70,82,87))
    d.ellipse((1210,280,1340,390),outline=(154,104,55),width=5)
    # L2 shared vehicle fallback
    draw_fallback_vehicle(d,960,330,1.12)
    # L3 primary information
    text(d,(320,176),'72',font(126,True),(241,244,245))
    text(d,(320,264),'km/h',font(22),(145,154,160))
    text(d,(320,315),'D',font(36,True),(220,225,227))
    # left context
    text(d,(154,47),'18:42',font(18),(151,160,166),'lm')
    text(d,(154,86),'AP ACTIVE',font(17,True),(154,195,211),'lm')
    text(d,(154,115),'Coarse surrounding state',font(14),(100,112,118),'lm')
    # right smart context rail
    d.rounded_rectangle((1430,58,1774,386),26,fill=(16,23,28),outline=(44,59,68),width=2)
    text(d,(1470,92),'BATTERY',font(14,True),(111,124,132),'lm')
    text(d,(1470,142),'68%',font(50,True),(238,241,242),'lm')
    text(d,(1470,184),'284 km',font(22),(174,183,188),'lm')
    d.line((1470,211,1735,211),fill=(47,60,66),width=1)
    text(d,(1470,245),'NAVIGATION',font(14,True),(111,124,132),'lm')
    d.line((1490,295,1548,295),fill=(216,226,229),width=6)
    d.line((1548,295,1548,259),fill=(216,226,229),width=6)
    d.polygon([(1536,262),(1548,246),(1560,262)],fill=(216,226,229))
    text(d,(1590,272),'800 m',font(30,True),(238,241,242),'lm')
    text(d,(1470,326),'Don Mills Rd',font(20),(183,190,194),'lm')
    text(d,(1470,360),'22 min  ·  18.4 km',font(17),(137,148,154),'lm')
    # L4 shared safety baseline
    d.line((95,414,1825,414),fill=(47,57,62),width=1)
    text(d,(960,446),'READY',font(15,True),(126,145,153))
    trapezoid_mask(im)
    im.save(OUT)
    print(OUT)

if __name__=='__main__': main()
