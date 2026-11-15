/** Authenticated Domain capability plus live gateway challenge, no secret output. */
import {readFileSync} from 'node:fs';
import {createDomainClient} from '../web/src/domain-client.mjs';
try {
  if(process.argv.length!==3)throw new Error('configuration path required');
  const config=JSON.parse(readFileSync(process.argv[2],'utf8'));
  const [host,portText]=config.endpoint.split(':');
  if(host!=='127.0.0.1'||!/^\d{1,5}$/.test(portText))throw new Error('endpoint');
  const secret=readFileSync(config.secret_file,'utf8');
  const domain=createDomainClient({host,port:Number(portText),secret,camouflage:true});
  const description=await domain.call('describe',null,'',null,2000);
  const ping=await domain.call('ping',null,'',null,2000);
  if(description.status!==200||ping.status!==200)throw new Error('capability or live guard unavailable');
  console.log('DOMAIN_LIVE_GUARD_PASS');
} catch {console.error('DOMAIN_LIVE_GUARD_FAIL');process.exitCode=1;}
