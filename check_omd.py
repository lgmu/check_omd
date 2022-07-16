#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
check_omd.py - a script for checking a particular
OMD site status

2018 By Christian Stankowic
<info at cstan dot io>
https://github.com/stdevel/check_omd
"""

import argparse
import subprocess
import io
import sys
import logging
import stat
import os.path
import time

__version__ = "1.4.0"
"""
str: Program version
"""
LOGGER = logging.getLogger('check_omd')
"""
logging: Logger instance
"""

def raise_timeout(cmd, timeout):
    """
    Raises a timeout and exits the program
    """
    _cmd = " ".join(cmd)
    print(f"CRITICAL - executing command '{_cmd}' exceeded {timeout} seconds timeout")
    if OPTIONS.heal:
        os.remove(lockfile)
        LOGGER.debug("removing lockfile %s", lockfile)
    sys.exit(2)

def get_site_status():
    """
    Retrieves a particular site's status
    """
    # get username
    proc = subprocess.run(["whoami"], stdout=subprocess.PIPE, check=False)
    site = proc.stdout.decode('utf-8').rstrip()
    LOGGER.debug("It seems like I'm OMD site '%s'", site)

    # get OMD site status
    cmd = ['omd', 'status', '-b']
    LOGGER.debug("running command '%s'", cmd)

    try:
        proc = subprocess.run(
            cmd,
            timeout=OPTIONS.timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )
    except subprocess.TimeoutExpired:
        raise_timeout(cmd,timeout=OPTIONS.timeout)

    if proc.stderr:
        err = proc.stderr.decode('utf-8')
        if "no such site" in err:
            print(f"UNKNOWN: unable to check site: '{err.rstrip()}' - did you miss "
                "running this plugin as OMD site user?"
            )
        else:
            print(f"UNKNOWN: unable to check site: '{err.rstrip()}'")
        return_code = 3

    if proc.stdout:
        # try to find out whether omd was executed as root
        if proc.stdout.count(bytes("OVERALL", "utf-8")) > 1:
            print(
                "UNKNOWN: unable to check site, it seems this plugin is "
                "executed as root (use OMD site context!)"
            )
            return_code = 3

        # check all services
        fail_srvs = []
        warn_srvs = []
        restarted_srvs = []

        LOGGER.debug("Got result '%s'", proc.stdout)
        for line in io.StringIO(proc.stdout.decode('utf-8')):
            service = line.rstrip().split(" ")[0]
            status = line.rstrip().split(" ")[1]
            if service not in OPTIONS.exclude:
                # check service
                if status != "0":
                    if service in OPTIONS.warning:
                        LOGGER.debug(
                            "%s service marked for warning has failed"
                            " state (%s)", service, status
                        )
                        warn_srvs.append(service)
                    else:
                        if OPTIONS.heal:
                            cmd = ['omd', 'restart', service]
                            LOGGER.debug("running command '%s'", cmd)
                            try:
                                proc = subprocess.run(cmd,timeout=OPTIONS.timeout, check=False)
                            except subprocess.TimeoutExpired:
                                raise_timeout(cmd,OPTIONS.timeout)

                            if proc.returncode == 0:
                                restarted_srvs.append(service)
                                LOGGER.debug("%s restarted successfully", service)
                            else:
                                fail_srvs.append(service)
                                LOGGER.debug("%s restart FAILED", service)

                        else:
                            fail_srvs.append(service)
                            LOGGER.debug(
                                "%s service has failed state "
                                "(%s)", service, status
                            )
            else:
                LOGGER.debug(
                    "Ignoring '%s' as it's blacklisted.", service
                )
        if OPTIONS.heal:
            if len(fail_srvs) == 0 and len(restarted_srvs) == 0:
               return 0
            returncode = 1
            if len(fail_srvs) > 0:
                _count = len(fail_srvs)
                _srvs = ' '.join(fail_srvs)
                print(
                    f"CRITICAL - could not restart {_count} service(s) on site '{site}': '{_srvs}'"
                )
                returncode = 2
            if len(restarted_srvs) > 0:
                _count = len(restarted_srvs)
                _srvs = ' '.join(restarted_srvs)
                print(
                    f"WARNING: Restarted {_count} service(s) on site '{site}': '{_srvs}'"
                )
            return returncode

        if len(fail_srvs) == 0 and len(warn_srvs) == 0:
            print(f"OK: OMD site '{site}' services are running.")
            return_code = 0
        elif len(fail_srvs) > 0:
            _services = ' '.join(fail_srvs)
            print(
                f"CRITICAL: OMD site 'site' has failed service(s): '{_services}'"
            )
            return_code = 2
        else:
            _services = ' '.join(warn_srvs)
            print(
                f"WARNING: OMD site 'site' has service(s) in warning state: '{_services}'"
            )
            return_code = 1
    return return_code


if __name__ == "__main__":
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 6):
        print(f"Unsupported python version, 3.6 required, you have {sys.version}")
        sys.exit(2)
    # define description, version and load parser
    DESC = '''%prog is used to check a particular OMD site status. By default,
 the script only checks a site's overall status. It is also possible to exclude
 particular services and only check the remaining services (e.g. rrdcached,
 npcd, icinga, apache, crontab).'''
    EPILOG = 'See also: https://github.com/stdevel/check_omd'
    PARSER = argparse.ArgumentParser(description=DESC, epilog=EPILOG)
    PARSER.add_argument('--version', action='version', version=__version__)

    # define option groups
    GEN_OPTS = PARSER.add_argument_group("generic arguments")
    FILTER_OPTS = PARSER.add_argument_group("filter arguments")

    # -d / --debug
    GEN_OPTS.add_argument(
        "-d", "--debug", dest="debug", default=False, action="store_true",
        help="enable debugging outputs (default: no)"
    )

    # -H / --heal
    FILTER_OPTS.add_argument(
        "-H", "--heal", dest="heal", default=False, action="store_true",
        help="automatically restarts failed services (default: no)"
    )

    # -e / --exclude
    FILTER_OPTS.add_argument(
        "-x", "--exclude", dest="exclude", default=["OVERALL"],
        action="append", metavar="SERVICE", help="defines one or more "
        "services that should be excluded (default: none)"
    )

    # -w / --warning
    FILTER_OPTS.add_argument(
        "-w", "--warning", dest="warning", default=[""], action="append",
        metavar="SERVICE", help="defines one or more services that only "
        "should throw a warning if not running (useful for fragile stuff "
        "like npcd, default: none)"
    )

    # -t / --timeout
    FILTER_OPTS.add_argument(
        "-t", "--timeout", dest="timeout", default=1800, action="store",
        help="after how many seconds a process should run into a timeout", type=int
    )

    # parse arguments
    OPTIONS = PARSER.parse_args()

    # set logging level
    logging.basicConfig()
    if OPTIONS.debug:
        LOGGER.setLevel(logging.DEBUG)
    else:
        LOGGER.setLevel(logging.ERROR)

    LOGGER.debug("OPTIONS: %s", OPTIONS)

    lockfile = '/tmp/check_omd.lock'

    if OPTIONS.heal:
        if (os.path.isfile(lockfile)):
            fileage = int(time.time() - os.stat(lockfile)[stat.ST_MTIME])
            LOGGER.debug("%s is %s seconds old", lockfile, fileage)
            if fileage > OPTIONS.timeout:
                print ("Lockfile too old, deleting lockfile")
                os.remove(lockfile)
                sys.exit(0)
            print ("CRITICAL - Lockfile exists, exit program")
            sys.exit(2)
        else:
            f = open(lockfile, 'x')
            f.close()
            LOGGER.debug("created lockfile %s", lockfile)
            # check site status
            exitcode = get_site_status()
            os.remove(lockfile)
            LOGGER.debug("removing lockfile %s", lockfile)
            sys.exit(exitcode)
    else:
        exitcode = get_site_status()
        sys.exit(exitcode)
