#!/usr/bin/env python
#
#   Copyright Toby Sears 2013
#  
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
"""
Nagios plugin to check the status of software raid arrays 
on a remote ubuntu 12.04 server.
Required packages:
Python:
 - argparse
 - paramiko
"""

import paramiko
import string
import sys 
import argparse
import logging

logging_format = "%(asctime)s:%(levelname)s:%(message)s"

class NagiosSoftwareRaid():
    def __init__(self,args=None):
        """Initialize the plugin."""

        if args.hostname is None:
            print "Error: No hostname given."
            sys.exit(3)
        if args.username is None:
            print "Error: No username given."
            sys.exit(3)
        if args.password is None and args.keyfile is None:
            print "Error: please provide either a password or an ssh key."
            sys.exit(3)
        if args.password is None:
            self.password   = ""
        else:
            self.password   = args.password
        if args.keyfile is None:
            self.keyfile    = ""
        else:
            self.keyfile    = args.keyfile

        self.hostname       = args.hostname
        self.username       = args.username
        self.exit_message   = ""
        self.exit_code      = 0
        self.sudo           = args.sudo
        self.arrays         = []
        self.array_count    = 0

        logging.debug("Initializing plugin with the following:")
        logging.debug("hostname: {0}".format(self.hostname))
        logging.debug("username: {0}".format(self.username))
        logging.debug("password: {0}".format(self.password))
        logging.debug("keyfile : {0}".format(self.keyfile))
        logging.debug("sudo    : {0}".format(self.sudo))

    def _ssh_for_data(self,command):
        """Use the paramiko library to a remote server
           and execute a command"""

        logging.debug("Initializing ssh client library.")
        ssh = paramiko.SSHClient()

        logging.debug("Ignoring missing host keys.")
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.password is "":
            logging.debug("Initializing ssh connection.")
            ssh.connect(self.hostname, username=self.username,
                        key_filename=self.keyfile)
        else:
            logging.debug("Initializing ssh connection.")
            ssh.connect(self.hostname, username=self.username,
                        password=self.password)

        logging.debug("Executing command: {0}".format(command))
        stdin, stdout, stderr = ssh.exec_command(command)

        if self.sudo:
            logging.debug("Sudoing.")
            stdin.write('{0}\n'.format(self.password))
            stdin.flush()

        data = stdout.readlines()
        logging.debug("Received: {0}".format(data))
        
        return data

    def _get_arrays(self):
        """Get a list of all configured software RAID
           arrays on the remote server."""

        command = "sudo mdadm --detail --scan | grep ARRAY | awk '{print $2}'"
        logging.debug("Retrieving list of arrays with command: {0}".format(command))
        data = self._ssh_for_data(command)
    
        for array in data:
            array = array.rstrip('\n')
            self.arrays.append(array)
    
        self.array_count = len(self.arrays)

    def _test_arrays(self):
        """Test a list of arrays for problems."""

        logging.debug("Testing {0} arrays:".format(self.array_count))
        for array in self.arrays:
            logging.debug("Testing array {0}".format(array))
            command = "sudo mdadm --detail %s | grep 'State :' | awk '{print $3}'" % (array)
            state = self._ssh_for_data(command)

            if state in ['dirty']:
                logging.debug("State: Dirty")
                self.exit_message =+ "WARNING: array {0} is in a {1} state. ".format(array,state)
                if self.exit_code < 1:
                    self.exit_code = 1

            elif state in ['recovering','resyncing']:
                logging.debug("State: Recovering or Resyncing")
                self.exit_message =+ "WARNING: array {0} is in a {1} state. ".format(array,state)
                if self.exit_code < 1:
                    self.exit_code = 1

            elif state in ['Not Started']:
                logging.debug("State: Not Started")
                self.exit_message =+ "WARNING: array {0} is in a {1} state. ".format(array,state)
                if self.exit_code < 1:
                    self.exit_code = 1

            elif state in ['degraded']:
                logging.debug("State: Degraded")
                self.exit_message =+ "CRITICAL: array {0} is in a {1} state. ".format(array,state)
                if self.exit_code < 2:
                    self.exit_code = 2

    def _exit_with_status(self):
        """Exit with the correct status and information."""
        logging.debug("Checking exit code: {0} and exit message: {1}".format(
                      self.exit_code,self.exit_message))
        if self.exit_code >= 1:
            print self.exit_message
            sys.exit(self.exit_code)
        else:
            print "OK: {0} arrays checked as healthy.".format(self.array_count)
            sys.exit(0)

    def go(self):
        """Fire off the plugin!"""
        logging.debug("Starting the plugin.")
        self._get_arrays()
        self._test_arrays()
        self._exit_with_status()

def parse_args():
    """Command line argument parser."""
    parser = argparse.ArgumentParser(description=
        "A nagios plugin to check all configured software RAID arrays configured on a server")

    parser.add_argument("-H","--hostname",
                        action="store",
                        help="The hostname of the remote server.")
    parser.add_argument("-u","--username",
                        action="store",
                        help="The username to log in as.")
    parser.add_argument("-p","--password",
                        action="store",
                        help="The users password.")
    parser.add_argument("-k","--keyfile",
                        action="store",
                        help="If a password isn't supplied, please supply the location of a valid ssh key.")
    parser.add_argument("-s","--sudo", action='store_true', default=False,
                        help="Use this flag if your user needs to run as sudo.")
    parser.add_argument("-v","--verbose",
                        choices=[1,2],
                        default=1,
                        type=int,
                        help="Verbosity level, for debugging use. 1=Quiet(default), 2=Debug.")
    args = parser.parse_args()
    return args

def main():
    """Parse args, initialize plugin and start."""
    args = parse_args()
    if args.verbose == 2:
        logging_level = logging.DEBUG
    else:
        logging_level = logging.CRITICAL

    logging.basicConfig(format=logging_format,
                        level=logging_level)

    nsr = NagiosSoftwareRaid(args=args)
    nsr.go()


if __name__ == "__main__":
        main()