from tests.group_helpers import group_for
import json
import ssl
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from types import SimpleNamespace
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@pytest.mark.django_db
@pytest.mark.parametrize('protocol,port',[('http',80),('https',443)])
def test_register_protocol_and_clear_form_labels(client,scope,protocol,port):
    from apps.firewalls.models import Firewall
    user=scope[0]; user.is_superuser=True; user.save()
    client.force_login(user)
    page=client.get('/firewalls/new/')
    assert b'API Token' in page.content
    assert b'Object name prefix' in page.content
    assert b'Allowed groups' not in page.content
    assert b'Login:' not in page.content
    response=client.post('/firewalls/new/',{'name':'New','hostname':'192.0.2.2','protocol':protocol,'port':'','token':'new-secret','vdom_name':'root','allowed_namespace':'portal_','enabled':'on','firewall_groups':[group_for(scope[2]).pk]})
    assert response.status_code == 302
    fw=Firewall.objects.get(name='New')
    assert fw.protocol == protocol
    assert fw.port == port
    assert fw.get_token() == 'new-secret'
    assert f'{protocol}://192.0.2.2:{port}'.encode() in client.get('/firewalls/').content


@pytest.mark.django_db
def test_edit_protocol_custom_port_and_keep_token(client,scope):
    from apps.firewalls.models import Firewall
    user=scope[0]; user.is_superuser=True; user.save()
    client.force_login(user)
    response=client.post(f'/firewalls/{scope[2].firewall_id}/edit/',{'name':'Edge','hostname':'192.0.2.1','protocol':'http','port':8080,'token':'','allowed_namespace':'portal_','enabled':'on','firewall_groups':[group_for(scope[2]).pk]})
    assert response.status_code == 302
    fw=Firewall.objects.get(pk=scope[2].firewall_id)
    assert fw.protocol == 'http' and fw.port == 8080
    assert fw.get_token() == 'test-secret'


@pytest.mark.parametrize('protocol',['http','https'])
def test_real_http_and_self_signed_https(tmp_path,protocol):
    from apps.fortinet.client import FortinetClient
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path,self.headers.get('Authorization')))
            data=json.dumps({'status':'success','results':[{'name':'local_test'}]}).encode()
            self.send_response(200); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    if protocol == 'https':
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'self-signed-local-test')])
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc)-timedelta(days=1)).not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256()))
        cert_path=tmp_path/'cert.pem'; key_path=tmp_path/'key.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert_path,key_path)
        server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        fw=SimpleNamespace(protocol=protocol,hostname='127.0.0.1',port=server.server_port,get_token=lambda:'local-test-token')
        with FortinetClient(fw,SimpleNamespace(name='root')) as client:
            assert client.get_address('local_test') == {'name':'local_test'}
        assert received == [('/api/v2/cmdb/firewall/address/local_test?vdom=root','Bearer local-test-token')]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
