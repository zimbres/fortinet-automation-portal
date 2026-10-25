import json
import pytest


def test_saved_development_oidc_config_is_loaded(tmp_path):
    from config.settings.local_oidc import load_local_oidc
    cache=tmp_path/'.cache';cache.mkdir()
    (cache/'oidc-test.json').write_text(json.dumps({'PORTAL_AUTH_MODE':'oidc','OIDC_RP_CLIENT_ID':'saved-client','OIDC_OP_ISSUER':'https://idp.example','UNRELATED_SETTING':'ignored'}))
    (cache/'oidc-test-client-secret').write_text('test-only-secret')
    env={}
    load_local_oidc(env,tmp_path)
    assert env['PORTAL_AUTH_MODE']=='oidc'
    assert env['OIDC_RP_CLIENT_ID']=='saved-client'
    assert env['OIDC_RP_CLIENT_SECRET_FILE']==str(cache/'oidc-test-client-secret')
    assert 'UNRELATED_SETTING' not in env
    assert 'OIDC_RP_CLIENT_SECRET' not in env


def test_local_oidc_does_not_override_explicit_settings(tmp_path):
    from config.settings.local_oidc import load_local_oidc
    cache=tmp_path/'.cache';cache.mkdir()
    (cache/'oidc-test.json').write_text(json.dumps({'PORTAL_AUTH_MODE':'oidc','OIDC_RP_CLIENT_ID':'saved-client'}))
    env={'PORTAL_AUTH_MODE':'local'}
    load_local_oidc(env,tmp_path)
    assert env=={'PORTAL_AUTH_MODE':'local'}
    env={'OIDC_RP_CLIENT_ID':'explicit-client','OIDC_RP_CLIENT_SECRET':'explicit-test-secret'}
    load_local_oidc(env,tmp_path)
    assert env['OIDC_RP_CLIENT_ID']=='explicit-client'
    assert env['OIDC_RP_CLIENT_SECRET']=='explicit-test-secret'
    assert 'OIDC_RP_CLIENT_SECRET_FILE' not in env


def test_no_saved_oidc_config_leaves_defaults_unchanged(tmp_path):
    from config.settings.local_oidc import load_local_oidc
    env={};load_local_oidc(env,tmp_path);assert env=={}
