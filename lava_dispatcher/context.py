# Copyright (C) 2011 Linaro Limited
#
# Author: Paul Larson <paul.larson@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import atexit
import logging
import os
import subprocess
import sys
import tempfile

from lava_dispatcher.config import get_device_config
from lava_dispatcher.client.targetdevice import TargetBasedClient
from lava_dispatcher.test_data import LavaTestData
from lava_dispatcher.utils import (
    logging_spawn,
    rmtree,
    )


def _write_and_flush(fobj, data):
    fobj.write(data)
    fobj.flush()


class _Forwarder(object):
    """A file-like object that just forwards data written to it to a callable.
    """

    def __init__(self, callback):
        self.callback = callback

    def write(self, data):
        self.callback(data)

    def flush(self):
        pass


class Outputter(object):

    def __init__(self, output_dir):
        self.output_dir = output_dir
        if output_dir:
            self.output_txt = open(os.path.join(output_dir, 'output.txt'), 'w')
        else:
            self.output_txt = None

        self.logfile_read = _Forwarder(self.serial_output)

        self._log_handler = logging.StreamHandler(_Forwarder(self.log_output))
        FORMAT = '<LAVA_DISPATCHER>%(asctime)s %(levelname)s: %(message)s'
        DATEFMT = '%Y-%m-%d %I:%M:%S %p'
        self._log_handler.setFormatter(
            logging.Formatter(fmt=FORMAT, datefmt=DATEFMT))
        del logging.root.handlers[:]
        del logging.root.filters[:]
        logging.root.addHandler(self._log_handler)

    def serial_output(self, data):
        _write_and_flush(sys.stdout, data)
        if self.output_txt is not None:
            _write_and_flush(self.output_txt, data)

    # Currently all output is treated the same way.
    log_output = serial_output

    def write_named_data(self, name, data):
        if self.output_dir is None:
            return
        with open(os.path.join(self.output_dir, name), 'w') as outf:
            outf.write(data)


class LavaContext(object):
    def __init__(self, target, dispatcher_config, oob_file, job_data, output_dir):
        self.config = dispatcher_config
        self.job_data = job_data
        self.output = Outputter(output_dir)
        self.logfile_read = self.output.logfile_read
        device_config = get_device_config(
            target, dispatcher_config.config_dir)
        self._client = TargetBasedClient(self, device_config)
        self.test_data = LavaTestData()
        self.oob_file = oob_file
        self._host_result_dir = None
        self.any_device_bundles = False

    @property
    def client(self):
        return self._client

    @property
    def any_host_bundles(self):
        return (self._host_result_dir is not None
                and len(os.listdir(self._host_result_dir)) > 0)

    @property
    def host_result_dir(self):
        if self._host_result_dir is None:
            self._host_result_dir = tempfile.mkdtemp()
            atexit.register(rmtree, self._host_result_dir)
        return self._host_result_dir

    def get_device_version(self):
        return self.client.target_device.get_device_version()

    def spawn(self, command, timeout=30):
        proc = logging_spawn(command, timeout)
        proc.logfile_read = self.logfile_read
        return proc

    def run_command(self, command, failok=True):
        """run command 'command' with output going to output-dir if specified"""
        if isinstance(command, (str, unicode)):
            command = ['sh', '-c', command]
            output_txt = self.client.context.output.output_txt
        if self.output_txt:
            output_args = {'stdout': output_txt, 'stderr': subprocess.STDOUT}
        else:
            output_args = {}
        logging.debug("Executing on host : '%r'" % command)
        if failok:
            rc = subprocess.call(command, **output_args)
        else:
            rc = subprocess.check_call(command, **output_args)
        return rc

