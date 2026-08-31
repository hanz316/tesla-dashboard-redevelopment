from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import math

W, H = 1920, 480
OUT = Path('/mnt/data/tesla_v3_flagship')
OUT.mkdir(parents=True, exist_ok=True)

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)

F = {
    'speed': font(176, True),
    'hero': font(70, True),
    'title': font(52, True),
    'primary': font(38, True),
    'secondary': font(25, False),
    'small': font(18, False),
    'micro': font(15, False),
}

C = {
    'bg': (11, 14, 17),
    'bg2': (15, 19, 23),
    'graphite': (24, 29, 34),
    'line': (52, 60, 67),
    'muted': (128, 137, 145),
    'faint': (82, 90, 97),
    'white': (238, 241, 243),
    'warm': (196, 184, 169),
    'amber': (214, 155, 74),
    'green': (95, 177, 131),
    'red': (217, 79, 76),
    'accent': (93, 132, 159),
}

def t(draw, xy, text, f, fill, anchor='mm'):
    draw.text(xy, text, font=f, fill=fill, anchor=anchor)

def line(draw, coords, fill, width=1):
    draw.line(coords, fill=fill, width=width)

def rr(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def trapezoid_mask(im):
    d = ImageDraw.Draw(im)
    d.polygon([(0,0),(116,0),(51,H),(0,H)], fill=(0,0,0))
    d.polygon([(W,0),(W-116,0),(W-51,H),(W,H)], fill=(0,0,0))

def vignette(base=(11,14,17), glow=(22,28,33), center=(960,240), rx=920, ry=340):
    im = Image.new('RGB',(W,H),base)
    px = im.load()
    cx,cy=center
    for y in range(H):
        for x in range(W):
            dx=(x-cx)/rx; dy=(y-cy)/ry
            r=min(1.0, math.sqrt(dx*dx+dy*dy))
            g=max(0.0, 1.0-r)
            edge=min(x/(W/2),(W-x)/(W/2),y/(H/2),(H-y)/(H/2))
            edge=max(0,min(1,edge))
            v=0.72+0.28*edge
            color=tuple(int((base[i]*(1-g)+glow[i]*g)*v) for i in range(3))
            px[x,y]=color
    return im

def status_header(draw, left='18:42', right='18°C   LTE'):
    # Automotive header: sparse, aligned to outer grid, no icon soup.
    t(draw,(150,30),left,F['small'],C['muted'],'lm')
    t(draw,(1770,30),right,F['small'],C['muted'],'rm')

def safety_strip(draw, speed='72', gear='D', soc='68%'):
    # Persistent safety info at lower corners, no card container.
    t(draw,(122,426),gear,F['secondary'],C['white'],'lm')
    t(draw,(168,426),speed,F['primary'],C['white'],'lm')
    t(draw,(1770,426),soc,F['primary'],C['white'],'rm')

def draw_vehicle(draw, cx, cy, scale=1.0, body=(46,52,57), edge=(123,131,137), glass=(20,24,27)):
    w=int(154*scale); h=int(224*scale)
    rr(draw,(cx-w//2,cy-h//2,cx+w//2,cy+h//2),int(46*scale),body,edge,2)
    rr(draw,(cx-int(51*scale),cy-int(60*scale),cx+int(51*scale),cy+int(48*scale)),int(20*scale),glass)
    line(draw,(cx-w//2+8,cy-int(27*scale),cx+w//2-8,cy-int(27*scale)),(92,100,106),1)
    # wheels as low-contrast mass, not icon outlines
    for sx in (-1,1):
        rr(draw,(cx+sx*int(72*scale)-int(7*scale),cy-int(58*scale),cx+sx*int(72*scale)+int(7*scale),cy-int(12*scale)),int(4*scale),(22,25,27))
        rr(draw,(cx+sx*int(72*scale)-int(7*scale),cy+int(15*scale),cx+sx*int(72*scale)+int(7*scale),cy+int(61*scale)),int(4*scale),(22,25,27))

def draw_road_environment(draw):
    # Calm road-space. Lane geometry kept behind vehicle and at low contrast.
    horizon_y=177
    road_col=(31,36,40)
    lane_col=(65,72,78)
    line(draw,(460,H,770,horizon_y),road_col,2)
    line(draw,(1460,H,1150,horizon_y),road_col,2)
    line(draw,(720,H,865,horizon_y),lane_col,2)
    line(draw,(1200,H,1055,horizon_y),lane_col,2)
    for y,half in [(218,8),(260,12),(315,18),(382,28)]:
        ratio=(y-horizon_y)/(H-horizon_y)
        lx=int(960-(85+220*ratio)); rx=int(960+(85+220*ratio))
        line(draw,(lx,y,lx-int(5+10*ratio),y+int(14+18*ratio)),(55,62,67),2)
        line(draw,(rx,y,rx+int(5+10*ratio),y+int(14+18*ratio)),(55,62,67),2)
    # AP corridor is a soft bounded field, not neon line art.
    rr(draw,(808,202,1112,430),42,(17,22,26),outline=(41,48,53),width=1)

def horizon_v3():
    im=vignette((10,13,16),(22,27,31),(950,270),1050,360)
    d=ImageDraw.Draw(im)
    status_header(d)
    draw_road_environment(d)

    # surrounding traffic, same perspective system
    draw_vehicle(d,735,287,.31,(31,36,40),(68,75,80),(16,19,21))
    draw_vehicle(d,1275,267,.27,(31,36,40),(68,75,80),(16,19,21))
    draw_vehicle(d,1410,340,.37,(34,39,43),(74,82,87),(17,20,22))
    draw_vehicle(d,960,330,.70,(50,55,59),(150,155,159),(19,23,26))

    # speed anchored to central optical axis
    t(d,(960,78),'D',F['secondary'],C['muted'])
    t(d,(960,165),'72',F['speed'],C['white'])
    t(d,(960,272),'km/h',F['secondary'],C['faint'])

    # Right information column = one structural rail, not cards.
    x=1515
    line(d,(1410,86,1410,380),(39,45,50),1)
    t(d,(x,110),'68%',F['hero'],C['white'])
    t(d,(x,164),'284 km',F['secondary'],C['muted'])
    t(d,(x,220),'BATTERY',F['micro'],C['faint'])
    line(d,(1465,252,1735,252),(38,44,48),1)
    t(d,(x,292),'↰  800 m',F['primary'],C['white'])
    t(d,(x,333),'Don Mills Rd',F['secondary'],C['muted'])
    t(d,(x,369),'22 min · 18.4 km',F['small'],C['faint'])

    # left contextual AP indicator, extremely restrained
    t(d,(205,294),'AP',F['secondary'],C['muted'],'lm')
    t(d,(205,328),'Lane centered',F['small'],C['faint'],'lm')
    safety_strip(d)
    trapezoid_mask(im)
    return im

def pulse_v3():
    im=vignette((10,12,14),(24,22,19),(960,255),1020,360)
    d=ImageDraw.Draw(im)
    status_header(d, right='18°C')

    # Main mechanical datum line and stage envelope.
    t(d,(960,56),'PACK POWER',F['small'],C['muted'])
    t(d,(960,122),'+126',F['hero'],C['white'])
    t(d,(960,166),'kW',F['secondary'],C['faint'])

    stage_y=266
    line(d,(270,stage_y,1650,stage_y),(59,62,62),3)
    line(d,(960,236,960,296),(151,145,137),2)
    # Filled power response: warm metal, not cyan.
    line(d,(960,stage_y,1390,stage_y),C['amber'],10)
    t(d,(270,227),'REGEN',F['secondary'],C['muted'],'lm')
    t(d,(1650,227),'POWER',F['secondary'],C['muted'],'rm')

    # Motors orbit stage using aligned mechanical markers.
    for x,label,val,dirn in [(520,'FRONT MOTOR','+42 kW',1),(1400,'REAR MOTOR','+84 kW',-1)]:
        # Motor readouts lock directly to the stage through mechanical datum ticks.
        line(d,(x,300,x,348),(58,61,61),2)
        line(d,(x-82,348,x+82,348),(58,61,61),1)
        t(d,(x,370),label,F['micro'],C['faint'])
        t(d,(x,397),val,F['secondary'],C['white'])
        attach=700 if x<960 else 1220
        line(d,(attach,stage_y,x,300),(45,48,49),1)

    # speed intentionally subordinate
    t(d,(220,107),'72',F['hero'],C['white'],'lm')
    t(d,(220,160),'km/h',F['small'],C['muted'],'lm')
    t(d,(220,194),'D',F['secondary'],C['faint'],'lm')

    # performance structure grouped on left-bottom rail
    t(d,(270,426),'0–100   READY',F['small'],C['green'],'lm')

    # accelerator and brakes share a single precision baseline.
    line(d,(760,431,1160,431),(47,50,51),5)
    line(d,(760,431,1016,431),C['warm'],5)
    t(d,(960,414),'ACCEL 64%',F['small'],C['muted'])
    t(d,(1285,426),'FL 73°   FR 76°   RL 61°   RR 63°',F['small'],C['muted'],'lm')
    t(d,(1770,426),'68%',F['secondary'],C['white'],'rm')

    trapezoid_mask(im)
    return im

def create_album_art(size=300):
    art=Image.new('RGB',(size,size),(41,35,37))
    px=art.load()
    for y in range(size):
        for x in range(size):
            nx=(x-size*.5)/(size*.5); ny=(y-size*.5)/(size*.5)
            r=min(1,math.sqrt(nx*nx+ny*ny))
            horizon=0.5+0.5*math.sin((x*.026)+(y*.013))
            base=(56,45,49)
            glow=(132,85,68)
            g=max(0,1-r)*0.45 + horizon*0.10
            px[x,y]=tuple(int(base[i]*(1-g)+glow[i]*g) for i in range(3))
    d=ImageDraw.Draw(art)
    # abstract night road photograph treatment
    d.polygon([(42,285),(128,152),(172,152),(258,285)],fill=(27,29,31))
    d.line((150,150,150,286),fill=(213,186,144),width=3)
    for i in range(7):
        y=174+i*18
        d.line((40+i*3,y,90+i*9,y-8),fill=(117,76,64),width=2)
        d.line((260-i*3,y,210-i*9,y-8),fill=(117,76,64),width=2)
    d.text((24,24),'MIDNIGHT',font=font(25,True),fill=(231,222,213))
    d.text((25,54),'DRIVE',font=font(18,False),fill=(172,154,148))
    return art

def studio_v3():
    # Precomputed dominant-colour atmosphere; no runtime blur in production.
    im=vignette((12,12,14),(47,34,32),(470,245),900,360)
    # add a low-saturation warm floor sweep
    atmosphere=Image.new('RGBA',(W,H),(0,0,0,0)); ad=ImageDraw.Draw(atmosphere)
    ad.ellipse((90,160,1080,610),fill=(82,49,39,38))
    atmosphere=atmosphere.filter(ImageFilter.GaussianBlur(70))
    im=Image.alpha_composite(im.convert('RGBA'),atmosphere).convert('RGB')
    d=ImageDraw.Draw(im)
    status_header(d,right='18°C')

    art=create_album_art(280)
    # subtle shadow gives physical weight
    shadow=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(shadow)
    sd.rounded_rectangle((150,105,430,385),radius=26,fill=(0,0,0,100))
    shadow=shadow.filter(ImageFilter.GaussianBlur(18))
    im=Image.alpha_composite(im.convert('RGBA'),shadow)
    im.paste(art,(135,90))
    d=ImageDraw.Draw(im)
    rr(d,(135,90,415,370),26,None,(104,90,85),1)

    t(d,(470,100),'Midnight Drive',F['primary'],C['white'],'lm')
    t(d,(470,138),'Dashboard Studio',F['secondary'],(167,153,149),'lm')

    # Lyrics dominate visual field. Previous/next recede hard.
    t(d,(1115,187),'City lights disappear behind us',F['secondary'],(112,104,103))
    t(d,(1115,260),'Every mile becomes',F['title'],C['white'])
    t(d,(1115,320),'a memory',F['title'],C['white'])
    t(d,(1115,374),'Keep the horizon in your sight',F['secondary'],(112,104,103))

    # Playback is intentionally quiet and structurally aligned.
    line(d,(470,407,1540,407),(65,56,54),2)
    line(d,(470,407,1100,407),(160,137,128),2)
    t(d,(470,435),'02:14',F['micro'],(120,108,105),'lm')
    t(d,(1540,435),'03:47',F['micro'],(120,108,105),'rm')
    t(d,(1745,435),'▶',F['secondary'],(162,151,147))
    # Keep safety without competing with lyric hero.
    t(d,(105,430),'D',F['small'],C['white'],'lm')
    t(d,(145,430),'72',F['secondary'],C['white'],'lm')
    t(d,(1790,430),'68%',F['secondary'],C['white'],'rm')

    trapezoid_mask(im)
    return im.convert('RGB')

pages=[('horizon-v3',horizon_v3()),('pulse-v3',pulse_v3()),('studio-v3',studio_v3())]
for name,im in pages:
    im.save(OUT/f'{name}.png')

overview=Image.new('RGB',(1920,720),(5,7,9))
for i,(name,im) in enumerate(pages):
    overview.paste(im.resize((960,240)),((i%2)*960,(i//2)*240))
# fill lower right with a title tile using same system rather than duplicate artwork
od=ImageDraw.Draw(overview)
od.rectangle((960,480,1920,720),fill=(10,13,16))
t(od,(1440,575),'FLAGSHIP V3',F['title'],C['white'])
t(od,(1440,630),'HORIZON · PULSE · STUDIO',F['secondary'],C['muted'])
t(od,(1440,672),'1920×480 production cockpit studies',F['small'],C['faint'])
overview.save(OUT/'flagship-v3-overview.png')
print(OUT)
