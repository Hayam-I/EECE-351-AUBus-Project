import socket

HOST = "127.0.0.1"
PORT = 6000

with socket.create_connection((HOST, PORT)) as s:
    msg = '{"type":"PING","id":"b3b8c2e2-7e2a-4e2a-9e2a-7e2a4e2a9e2a","payload":{}}\n'
    s.sendall(msg.encode("utf-8"))
    print(s.recv(4096).decode("utf-8"))
    
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