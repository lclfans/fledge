#!/usr/bin/env python3.5

import argparse
import logging
import daemon
from daemon import pidfile

from foglamp.coap.server import CoAPServer

def do_something(logf):
    fh = logging.FileHandler(logf)
    fh.setLevel(logging.DEBUG)

    formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(formatstr)

    fh.setFormatter(formatter)

    logger = logging.getLogger('')

    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)

    CoAPServer.start()

def start_daemon(pidf, logf, wd):
    ### This launches the daemon in its context

    ### XXX pidfile is a context
    with daemon.DaemonContext(
        working_directory=wd,
        umask=0o002,
        pidfile=pidfile.TimeoutPIDLockFile(pidf),
        ) as context:
            do_something(logf)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FogLAMP daemon in Python")
    parser.add_argument('-p', '--pid-file', default='~/var/run/foglamp.pid')
    parser.add_argument('-l', '--log-file', default='~/var/log/foglamp.log')
    parser.add_argument('-w', '--working-dir', default='/var/log/foglamp')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file, logf=args.log_file, wd=args.working_dir)
