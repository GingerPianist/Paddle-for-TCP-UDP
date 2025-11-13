import json, struct

def send_tcp_json(conn, data):
    try:
        msg = json.dumps(data).encode('utf-8')
        length = struct.pack('>I', len(msg))
        conn.sendall(length + msg)
    except Exception:
        pass

def recv_tcp_json(conn):
    try:
        header = conn.recv(4)
        if not header:
            return None
        (length,) = struct.unpack('>I', header)
        data = b''
        while len(data) < length:
            chunk = conn.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
       # print("otrzymano")
        return json.loads(data.decode('utf-8'))
    except Exception:
        return None