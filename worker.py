"""Independent scheduler; call once a minute or use Vercel cron."""
import time,argparse
from core import Service,send_notification
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');args=p.parse_args();s=Service()
    while True:
        print({'overdue':s.sweep(),'processed':s.dispatch(send_notification)},flush=True)
        if args.once:break
        time.sleep(60)
