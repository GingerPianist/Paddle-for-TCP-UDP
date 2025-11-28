# ========================
# klient.py
# ========================
import socket
import threading
import json
import time
import pygame
import struct
from tcp_json import recv_tcp_json, send_tcp_json

WIDTH, HEIGHT = 600, 600
PADDLE_SPEED = 100
PADDLE_SIZE = 80
FPS = 60

# --- Klient GUI ---
class PongClient:
    def __init__(self, host, port=5000, protocol='tcp'):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('3-Player Pong Client')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None,24)

        self.host = host
        self.port = port
        self.protocol = protocol
        self.side = None
        self.state = {
            'ball': (WIDTH/2, HEIGHT/2),
            'paddles': {'LEFT': HEIGHT/2, 'RIGHT': HEIGHT/2, 'BOTTOM': WIDTH/2},
            'scores': {'LEFT':0, 'RIGHT':0, 'BOTTOM':0},
            'seq': 0
        }
        self.running = True
        self.input = None

        if protocol=='tcp':
            self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self.sock.connect((host,port))
            threading.Thread(target=self.tcp_recv_loop,daemon=True).start()
        elif protocol=='udp':
            self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.sock.settimeout(0.5)
            self.addr = (host, port)
            self.sock.sendto(json.dumps({'type':'register'}).encode('utf-8'), self.addr)
            threading.Thread(target=self.udp_recv_loop,daemon=True).start()

    def tcp_recv_loop(self):
        while self.running:
            msg = recv_tcp_json(self.sock)
            if not msg: break
            self.process_msg(msg)


    def udp_recv_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                msg = json.loads(data.decode('utf-8'))
                self.process_msg(msg)
            except socket.timeout:
                continue


    def process_msg(self, msg):
        t = msg.get('type')
        if t == 'assign':
            self.side = msg['side']
            print(f"Przypisano stronę: {self.side}")
        elif t == 'state':
            self.state = msg['state']
            if self.protocol == 'tcp':
                send_tcp_json(self.sock, {'type':'ack','seq': msg['seq']})
        elif t == 'ping':  
            if self.protocol == 'tcp':
                send_tcp_json(self.sock, {'type':'pong','ts': msg['ts']})
            else:
                self.sock.sendto(json.dumps({'type':'pong','ts': msg['ts']}).encode('utf-8'), self.addr)

    def send_input(self):
        if self.input and self.side:
            msg = {'type':'input','input':self.input}
            if self.protocol == 'tcp':
                send_tcp_json(self.sock, msg)
            else:
                self.sock.sendto(json.dumps(msg).encode('utf-8'), self.addr)
            self.input = None


    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type==pygame.QUIT:
                    self.running=False
            keys=pygame.key.get_pressed()
            if self.side=='LEFT' or self.side=='RIGHT':
                if keys[pygame.K_UP]: self.input='UP'
                elif keys[pygame.K_DOWN]: self.input='DOWN'
            elif self.side=='BOTTOM':
                if keys[pygame.K_LEFT]: self.input='LEFT'
                elif keys[pygame.K_RIGHT]: self.input='RIGHT'

            self.send_input()
            self.draw()
            self.clock.tick(FPS)

    def draw(self):
        self.screen.fill((255,255,255))
        ball_x, ball_y = self.state['ball']
        pygame.draw.circle(self.screen,(255,255,255),(int(ball_x),int(ball_y)),8)

        paddles = self.state['paddles']
        left_y = max(PADDLE_SIZE/2, min(HEIGHT-PADDLE_SIZE/2, paddles['LEFT']))
        right_y = max(PADDLE_SIZE/2, min(HEIGHT-PADDLE_SIZE/2, paddles['RIGHT']))
        bottom_x = max(PADDLE_SIZE/2, min(WIDTH-PADDLE_SIZE/2, paddles['BOTTOM']))

        pygame.draw.rect(self.screen,(0,255,0),(0,int(left_y-PADDLE_SIZE/2),10,PADDLE_SIZE))
        pygame.draw.rect(self.screen,(255,0,0),(WIDTH-10,int(right_y-PADDLE_SIZE/2),10,PADDLE_SIZE))
        pygame.draw.rect(self.screen,(0,0,255),(int(bottom_x-PADDLE_SIZE/2),HEIGHT-10,PADDLE_SIZE,10))

        pygame.display.flip()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=51000)
    parser.add_argument('--protocol',choices=['tcp','udp'],default='tcp')
    args=parser.parse_args()

    client=PongClient(host=args.host,port=args.port,protocol=args.protocol)
    client.run()
