"""Verify real server sequence zero, deliberate duplicate, and two native ACKs."""
import argparse
import json
from client_audit import output_dir,save_json
from verify_channel_capture import analyze

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True)
    args=parser.parse_args();root=output_dir(args.run);result=analyze(root,'server')
    save_json(root/'server-reliable-verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('client_frames','server_acks','base_replies','callbacks','server_reliable_packets','client_transport_acks')}))
    raise SystemExit(0 if result['status']=='PASS' else 2)
