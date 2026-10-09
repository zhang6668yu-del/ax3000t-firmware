import pathlib, struct, hashlib, zlib, json

def parse(data):
    h=struct.unpack_from('>10I',data)
    assert h[0]==0xd00dfeed and h[1]<=len(data)
    strings=data[h[3]:h[3]+h[8]]; pos=h[2]; stack=[]; nodes={}
    while pos<h[1]:
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token==1:
            end=data.index(0,pos);stack.append(data[pos:end].decode());pos=(end+4)&~3
            nodes['/'.join(stack)]={}
        elif token==2: stack.pop()
        elif token==3:
            n,idx=struct.unpack_from('>II',data,pos);pos+=8
            key=strings[idx:strings.index(0,idx)].decode()
            nodes['/'.join(stack)][key]=data[pos:pos+n];pos=(pos+n+3)&~3
        elif token==9: break
        elif token!=4: raise ValueError(token)
    end=h[4]
    while data[end:end+16]!=bytes(16): end+=16
    return nodes,data[h[4]:end+16],h[7]

def build(nodes,reserve,cpu):
    strings=bytearray(); indexes={}; body=bytearray()
    def word(x): body.extend(struct.pack('>I',x))
    def pad(): body.extend(bytes((-len(body))%4))
    def emit(path):
        word(1);body.extend(path.rsplit('/',1)[-1].encode()+b'\0');pad()
        for key,val in nodes[path].items():
            if key not in indexes: indexes[key]=len(strings);strings.extend(key.encode()+b'\0')
            word(3);word(len(val));word(indexes[key]);body.extend(val);pad()
        for child in nodes:
            if child and child.rsplit('/',1)[0]==path: emit(child)
        word(2)
    emit('');word(9)
    so=40+len(reserve);st=so+len(body);total=st+len(strings)
    return struct.pack('>10I',0xd00dfeed,total,so,st,40,17,16,cpu,len(strings),len(body))+reserve+body+strings

