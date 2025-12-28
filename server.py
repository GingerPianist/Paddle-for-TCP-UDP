# Stara wersja serwera!
import socket
import threading
import json
import time
import pygame
import struct
from collections import deque

WIDTH, HEIGHT = 400, 400
BALL_SPEED = 100
PADDLE_SPEED = 180
PADDLE_SIZE = 80
FPS = 30
TICK = 1.0 / FPS

# Funkcje sieciowe
def send_tcp_json(conn, data):
    msg = json.dumps(data).encode('utf-8')
    length = struct.pack('>I', len(msg))
    conn.sendall(length + msg)

def recv_tcp_json(conn):
    header = conn.recv(4)
    if not header:
        return None
    (length,) = struct.unpack('>I', header)
    data = conn.recv(length)
    if not data:
        return None
    return json.loads(data.decode('utf-8'))
# --
class GameState:
    def __init__(self):
        self.ball_x, self.ball_y = WIDTH / 2, HEIGHT / 2
        self.ball_vx, self.ball_vy = BALL_SPEED, BALL_SPEED
        self.paddles = {'LEFT': HEIGHT / 2, 'RIGHT': HEIGHT / 2, 'BOTTOM': WIDTH / 2}
        self.scores = {'LEFT': 0, 'RIGHT': 0, 'BOTTOM': 0}

    def to_dict(self, seq):
        return {'seq': seq,'ball': (self.ball_x, self.ball_y),'paddles': self.paddles,'scores': self.scores}

class ClientInfo:
    def __init__(self, conn, addr, side, proto):
        self.conn = conn
        self.addr = addr
        self.side = side
        self.proto = proto
        self.input = None
        self.lock = threading.Lock()
        self.sent = 0
        self.acked = 0
        self.pings = deque(maxlen=20)
        self.bytes_sent = 0

# Serwer
class PongServer:
    def __init__(self, protocol='tcp', port=5000):
        self.start_time = time.time()
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT+100))
        pygame.display.set_caption('3-Player Pong Server')
        self.font = pygame.font.SysFont(None,24)

        self.protocol = protocol
        self.port = port
        self.clients = {}
        self.seq = 0
        self.game = GameState()
        self.running = True

        if protocol=='tcp':
            self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self.sock.bind(('0.0.0.0', port))
            self.sock.listen(3)
        else:
            self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.sock.bind(('0.0.0.0', port))

        self.start_threads()
        self.gui_loop()

    def start_threads(self):
        if self.protocol=='tcp':
            threading.Thread(target=self.accept_tcp_loop,daemon=True).start()
        else:
            threading.Thread(target=self.udp_recv_loop,daemon=True).start()
        threading.Thread(target=self.game_loop,daemon=True).start()

    def accept_tcp_loop(self):
        sides=['LEFT','RIGHT','BOTTOM']
        idx=0
        while self.running:
            conn,addr=self.sock.accept()
            side=sides[idx%3]
            idx+=1
            client=ClientInfo(conn,addr,side,'tcp')
            self.clients[addr]=client
            send_tcp_json(conn,{'type':'assign','side':side})
            threading.Thread(target=self.handle_tcp_client,args=(client,),daemon=True).start()

    def handle_tcp_client(self,client):
        while self.running:
            msg=recv_tcp_json(client.conn)
            if not msg: break
            self.process_msg(msg,client)

    def udp_recv_loop(self):
        sides=['LEFT','RIGHT','BOTTOM']
        idx=0
        while self.running:
            data,addr=self.sock.recvfrom(4096)
            msg=json.loads(data.decode('utf-8'))
            if addr not in self.clients and msg.get('type')=='register':
                side=sides[idx%3]
                idx+=1
                client=ClientInfo(None,addr,side,'udp')
                self.clients[addr]=client
                assign=json.dumps({'type':'assign','side':side}).encode('utf-8')
                self.sock.sendto(assign,addr)
            else:
                client=self.clients.get(addr)
                if client: self.process_msg(msg,client)

    def process_msg(self,msg,client):
        if msg['type']=='input':
            with client.lock: client.input=msg['input']
        elif msg['type']=='ack': client.acked+=1
        elif msg['type']=='pong': client.pings.append((time.time()-msg['ts'])*1000)

    def game_loop(self):
        last_time=time.time()
        while self.running:
            now=time.time()
            dt=now-last_time
            last_time=now
            self.update_game(dt)
            self.broadcast_state()
            time.sleep(TICK)

    def update_game(self,dt):
        if time.time() - self.start_time < 15:
            return
        
        g=self.game
        g.ball_x+=g.ball_vx*dt
        g.ball_y+=g.ball_vy*dt
        if g.ball_y<=0: g.ball_vy=abs(g.ball_vy)
        for side,pos in g.paddles.items():
            if side=='LEFT' and g.ball_x<=10 and abs(g.ball_y-pos)<PADDLE_SIZE/2: g.ball_vx=abs(g.ball_vx)
            if side=='RIGHT' and g.ball_x>=WIDTH-10 and abs(g.ball_y-pos)<PADDLE_SIZE/2: g.ball_vx=-abs(g.ball_vx)
            if side=='BOTTOM' and g.ball_y>=HEIGHT-10 and abs(g.ball_x-pos)<PADDLE_SIZE/2: g.ball_vy=-abs(g.ball_vy)
        for client in self.clients.values():
            with client.lock:
                if client.side in ['LEFT','RIGHT']:
                    if client.input=='UP': g.paddles[client.side]-=PADDLE_SPEED*dt
                    elif client.input=='DOWN': g.paddles[client.side]+=PADDLE_SPEED*dt
                elif client.side=='BOTTOM':
                    if client.input=='LEFT': g.paddles[client.side]-=PADDLE_SPEED*dt
                    elif client.input=='RIGHT': g.paddles[client.side]+=PADDLE_SPEED*dt

    def broadcast_state(self):
        self.seq+=1
        state=self.game.to_dict(self.seq)
        msg={'type':'state','seq':self.seq,'state':state}
        encoded=json.dumps(msg).encode('utf-8')
        for client in list(self.clients.values()):
            client.sent+=1
            client.bytes_sent+=len(encoded)
            if self.protocol=='tcp': send_tcp_json(client.conn,msg)
            else: self.sock.sendto(encoded,client.addr)

    def gui_loop(self):
        clock=pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type==pygame.QUIT: self.running=False
            self.screen.fill((0,0,0))
            pygame.draw.circle(self.screen,(255,255,255),(int(self.game.ball_x),int(self.game.ball_y)),8)
            pygame.draw.rect(self.screen,(0,255,0),(0,int(self.game.paddles['LEFT']-PADDLE_SIZE/2),10,PADDLE_SIZE))
            pygame.draw.rect(self.screen,(255,0,0),(WIDTH-10,int(self.game.paddles['RIGHT']-PADDLE_SIZE/2),10,PADDLE_SIZE))
            pygame.draw.rect(self.screen,(0,0,255),(int(self.game.paddles['BOTTOM']-PADDLE_SIZE/2),HEIGHT-10,PADDLE_SIZE,10))
            y=HEIGHT+5
            for i,client in enumerate(self.clients.values()):
                ping=sum(client.pings)/len(client.pings) if client.pings else 0
                text=self.font.render(f'{client.side} | Sent:{client.sent} Ack:{client.acked} Ping:{ping:.1f}ms Bytes:{client.bytes_sent}',True,(255,255,0))
                self.screen.blit(text,(5,y+i*20))
            pygame.display.flip()
            clock.tick(FPS)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--protocol',choices=['tcp','udp'],default='tcp')
    parser.add_argument('--port',type=int,default=51000)
    args=parser.parse_args()

    PongServer(protocol=args.protocol,port=args.port)

