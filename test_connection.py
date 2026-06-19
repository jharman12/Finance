# test_tls_connection.py
import ssl
import socket
import sys

host = "192.168.56.1"
port = 45881
ca_cert = r"C:\FinanceVoice\finance-voice-cert.pem"

try:
    context = ssl.create_default_context()
    context.check_hostname = False  # Allow IP address instead of hostname
    context.load_verify_locations(ca_cert)
    
    with socket.create_connection((host, port), timeout=5) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            print("✅ TLS connection successful!")
            print(f"TLS version: {ssock.version}")
            print(f"Cipher: {ssock.cipher()}")
except FileNotFoundError:
    print(f"❌ Certificate file not found: {ca_cert}")
except ConnectionRefusedError:
    print(f"❌ Main PC not listening on {host}:{port}")
except socket.timeout:
    print(f"❌ Connection timed out to {host}:{port}")
except Exception as e:
    print(f"❌ Error: {e}")