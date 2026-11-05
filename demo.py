"""Original generated demo assets; no downloaded memes or gameplay."""
import math
import struct
import wave

from PIL import Image, ImageDraw

from core import DATA, assets, uid, write
from render import font, run


def make_demo():
    existing = [a for a in assets() if a.get('demo')]
    if len(existing) >= 3: return existing
    output = []
    for kind, suffix, name in [('background','.mp4','Nền chuyển động minh họa.mp4'),
                               ('image','.png','Ủa khoan đã — meme chữ gốc.png'),
                               ('sound','.wav','Hiệu ứng boing tổng hợp.wav')]:
        aid = uid(); target = DATA / 'assets' / (aid + suffix)
        if kind == 'background':
            # An abstract moving background, explicitly not substitute gameplay.
            run(['-f','lavfi','-i','testsrc2=size=360x640:rate=30', '-vf',
                 'hue=h=35:s=0.35,boxblur=12:2', '-t','12','-an','-c:v','libx264','-preset','ultrafast',
                 '-pix_fmt','yuv420p',target], DATA / 'cache', lambda:False, timeout=90)
        elif kind == 'image':
            im = Image.new('RGB',(720,500),'#f3df42'); d = ImageDraw.Draw(im)
            d.text((360,190),'ỦA… KHOAN ĐÃ!',anchor='mm',font=font(54,True),fill='#20251e')
            d.text((360,285),'Cho tôi xử lý thông tin một chút.',anchor='mm',font=font(27),fill='#20251e')
            d.text((360,450),'MEME CHỮ MINH HỌA · COMMENTCUT',anchor='mm',font=font(15),fill='#444a25')
            im.save(target)
        else:
            rate = 48000
            with wave.open(str(target),'wb') as f:
                f.setparams((1,2,rate,0,'NONE','not compressed'))
                samples = bytearray()
                phase = 0
                for n in range(int(rate * .85)):
                    t=n/rate; freq=120+700*math.exp(-t*7); phase += 2*math.pi*freq/rate
                    sample=int(16000*math.sin(phase)*math.exp(-t*4)*min(1,t*60))
                    samples.extend(struct.pack('<h',sample))
                f.writeframes(samples)
        row={'id':aid,'kind':kind,'file':target.name,'name':name,'bytes':target.stat().st_size,'demo':True}
        if kind=='background':row['duration']=12
        if kind=='sound':row['duration']=.85
        write(DATA/'assets'/(aid+'.json'),row);output.append(row)
    return output


if __name__=='__main__':
    print('Created', len(make_demo()), 'original demo assets')
