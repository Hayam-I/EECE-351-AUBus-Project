# test_profile_set.py (minimal)
import socket, json, uuid
HOST, PORT = "127.0.0.1", 6000
TOKEN = "dev_token_123"
msg = {
    "type":"PROFILE.SET_REQ","id":str(uuid.uuid4()),
    "auth":{"token":TOKEN},
    "payload":{"name":"Mohammad Jaffal","email":"mohammadjaffal35@gmail.com","area":"Beirut-Mar Elias","is_driver":False}
}
with socket.create_connection((HOST, PORT)) as s:
    s.sendall((json.dumps(msg)+"\n").encode("utf-8"))
    print(s.recv(4096).decode().strip())

    
"""
in terminal, run:
$client = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 6000)
$stream = $client.GetStream()
$writer = New-Object System.IO.StreamWriter($stream)
$writer.AutoFlush = $true
$writer.WriteLine('{"type":"PING","id":"b3b8c2e2-7e2a-4e2a-9e2a-7e2a4e2a9e2a","payload":{}}')
$reader = New-Object System.IO.StreamReader($stream)
$reader.ReadLine()
$client.Close()
"""
