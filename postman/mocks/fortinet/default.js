const http = require('http');
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let body = req.body;
  if (!body) {
    body = await new Promise(resolve => {
      let text = ''; req.on('data', x => text += x);
      req.on('end', () => { try { resolve(JSON.parse(text || '{}')); } catch { resolve({}); } });
    });
  }
  const answer = (code, value) => { res.writeHead(code, {'Content-Type':'application/json'}); res.end(JSON.stringify(value)); };
  if (url.pathname === '/__reset' && req.method === 'POST') {
    await pm.state.set('fortinet.data', {addresses:{}, groups:{portal_group:{name:'portal_group', member:[{name:'existing'}]}}, mode:body.mode || 'success', policies:body.policies || [], writes:0, groupReads:0, devices:{}});
    return answer(200, {ok:true});
  }
  const root = await pm.state.get('fortinet.data');
  if (!root) return answer(503, {status:'error'});
  if (url.pathname === '/__state') return answer(200,root);
  let state = root;
  const device = req.headers['x-test-device'];
  if (device) {
    root.devices ||= {};
    if (!root.devices[device]) {
      let mode = root.mode === 'partial_second' ? (device === '192.0.2.2' ? 'partial' : 'success') : root.mode;
      root.devices[device] = {addresses:{}, policies:root.policies || [], groups:root.mode === 'missing_group' ? {} : {portal_group:{name:'portal_group',member:[{name:'existing'}]}},mode,writes:0,groupReads:0};
      if (mode === 'matching' || mode === 'unowned') root.devices[device].addresses.portal_host = {name:'portal_host',type:'ipmask',subnet:mode === 'matching' ? '192.0.2.1 255.255.255.255' : '192.0.2.9 255.255.255.255'};
    }
    state = root.devices[device];
    await pm.state.set('fortinet.data', root);
  }
  if (req.headers.authorization !== 'Bearer test-secret' || url.searchParams.get('vdom') !== 'root') return answer(403,{status:'error'});
  const match = url.pathname.match(/^\/api\/v2\/cmdb\/firewall\/(address|addrgrp|policy)(?:\/(.+))?$/);
  if (!match) return answer(501,{status:'error'});
  const resource=match[1], name=match[2] ? decodeURIComponent(match[2]) : null;
  const records=resource==='address' ? state.addresses : resource==='addrgrp' ? state.groups : Object.fromEntries((state.policies || []).map((policy,index)=>[index,policy]));
  if(req.method === 'GET') {
    if(state.mode==='read_failure' && state.writes>0 && resource==='address') return answer(500,{status:'error'});
    if(resource==='addrgrp' && name) {
      state.groupReads++;
      if(state.mode==='conflict' && state.groupReads===2) state.groups[name].member.push({name:'external'});
      await pm.state.set('fortinet.data',root);
    }
    if(name && !records[name]) return answer(404,{status:'error'});
    return answer(200,{status:'success',version:'simulation',results:name ? [records[name]] : Object.values(records),limit_reached:false});
  }
  if(state.mode==='reject' || (resource==='addrgrp' && state.mode==='partial')) return answer(403,{status:'error'});
  if(req.method==='POST' && (resource==='address' || resource==='addrgrp')) {
    if(records[body.name]) return answer(409,{status:'error'});
    records[body.name]=body;
  } else if(req.method==='PUT' && name && records[name]) {
    records[name]={...records[name],...body};
  } else if(req.method==='DELETE' && name) {
    delete records[name];
  } else return answer(501,{status:'error'});
  state.writes++;
  await pm.state.set('fortinet.data',root);
  if(state.mode==='uncertain') return answer(500,{status:'error'});
  return answer(200,{status:'success',http_status:200});
});
server.listen(process.env.PORT || 4901);
