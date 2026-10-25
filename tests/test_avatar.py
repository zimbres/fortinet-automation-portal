import hashlib
from io import BytesIO
from pathlib import Path
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User

pytestmark=pytest.mark.django_db


def picture(name='photo.png'):
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    metadata=PngInfo();metadata.add_text('Author','private metadata')
    data=BytesIO();Image.new('RGB',(320,180),'red').save(data,'PNG',pnginfo=metadata)
    return SimpleUploadedFile(name,data.getvalue(),content_type='image/png')


def test_gravatar_uses_normalized_email():
    user=User(username='person',email=' Person@Example.test ')
    digest=hashlib.sha256(b'person@example.test').hexdigest()
    assert user.avatar_url.startswith('https://www.gravatar.com/avatar/'+digest)
    assert '@' not in user.avatar_url
    user.email='';assert user.avatar_url==''


def test_picture_upload_override_and_reset(client,scope,settings,tmp_path,django_capture_on_commit_callbacks):
    settings.MEDIA_ROOT=tmp_path
    user=scope[0];user.email='operator@example.test';user.save(update_fields=['email'])
    client.force_login(user)
    response=client.post('/profile/',{'action':'avatar','avatar':picture(),'user_id':scope[1].pk})
    assert response.status_code==302
    user.refresh_from_db();scope[1].refresh_from_db()
    assert user.avatar and not scope[1].avatar
    assert user.avatar_url.startswith('/profile/picture/?v=')
    from PIL import Image
    with Image.open(user.avatar.path) as image:
        assert image.format=='PNG' and image.size==(256,256)
        assert not image.info
    result=client.get(user.avatar_url)
    assert result.status_code==200 and result['Content-Type']=='image/png'
    result.close()
    old_path=Path(user.avatar.path)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post('/profile/',{'action':'avatar_remove'}).status_code==302
    user.refresh_from_db();assert not user.avatar
    assert user.avatar_url.startswith('https://www.gravatar.com/') and not old_path.exists()


def test_picture_rejects_invalid_oversize_and_cross_account_access(client,scope,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    client.force_login(scope[0])
    for upload in [SimpleUploadedFile('evil.svg',b'<svg onload="alert(1)"/>',content_type='image/svg+xml'),SimpleUploadedFile('large.png',b'x'*(2*1024*1024+1),content_type='image/png')]:
        assert client.post('/profile/',{'action':'avatar','avatar':upload}).status_code==200
        scope[0].refresh_from_db();assert not scope[0].avatar
    assert client.get('/profile/picture/').status_code==404
    client.logout();assert client.get('/profile/picture/').status_code==302


def test_oidc_user_can_change_picture_but_not_identity(client,scope,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path
    user=scope[0];user.external_issuer='https://idp.example';user.external_subject='subject';user.save()
    client.force_login(user)
    assert client.post('/profile/',{'action':'avatar','avatar':picture()}).status_code==302
    user.refresh_from_db();assert user.avatar
    assert client.post('/profile/',{'action':'profile','first_name':'forged'}).status_code==403
