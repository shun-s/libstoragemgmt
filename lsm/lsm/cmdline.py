#!/usr/bin/env python

# Copyright (C) 2012 Red Hat, Inc.
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Author: tasleson

from optparse import OptionParser, OptionGroup
import optparse
import os
import re
import string
import textwrap
import sys
import getpass
import datetime
import lsm
import lsm.common
import lsm.client
import lsm.data
import time

class MyWrapper:
    """
    Handle \n in text for the command line help etc.
    """
    @staticmethod
    def wrap(text, width=70, **kw):
        rc = []
        for line in text.split("\n"):
            rc.extend(textwrap.wrap(line, width, **kw))
        return rc

    @staticmethod
    def fill(text, width=70, **kw):
        rc = []
        for line in text.split("\n"):
            rc.append(textwrap.fill(line, width, **kw))
        return "\n".join(rc)

class ArgError(Exception):
    def __init__(self, message, *args, **kwargs):
        """
        Class represents an error.
        """
        Exception.__init__(self, *args, **kwargs)
        self.msg = message
    def __str__(self):
        return "%s: error: %s\n" % ( os.path.basename(sys.argv[0]), self.msg)

def _c(cmd):
    return "cmd_" + cmd

def _o(option):
    return "opt_" + option

class CmdLine:
    """
    Command line interface class.
    """

    #Constants for some common units
    MiB = 1048576
    GiB = 1073741824
    TiB = 1099511627776

    def cli(self):
        """
        Command line interface parameters
        """
        usage = "usage: %prog [options]... [command]... [command options]..."
        optparse.textwrap = MyWrapper
        parser = OptionParser(usage=usage, version="%prog 0.0.2")
        parser.description = ('libStorageMgmt command line interface. \n')

        parser.epilog = ( 'Copyright 2012 Red Hat, Inc.\n'
                          'Please report bugs to <libstoragemgmt-devel@lists.sourceforge.net>\n')

        parser.add_option( '-u', '--uri', action="store", type="string", dest="uri",
            help='uniform resource identifier (env LSMCLI_URI)')
        parser.add_option( '-P', '--prompt', action="store_true", dest="prompt",
            help='prompt for password (env LSMCLI_PASSWORD)')
        parser.add_option( '-H', '--human', action="store_true", dest="human",
            help='print sizes in human readable format\n'
                 '(e.g., MiB, GiB, TiB)')
        parser.add_option( '-t', '--terse', action="store", dest="sep",
            help='print output in terse form with "SEP" as a record separator')

        #What action we want to take
        commands = OptionGroup(parser, 'Commands')

        commands.add_option('-l', '--list', action="store", type="choice",
            dest="cmd_list",
            metavar='<[VOLUMES|INITIATORS|POOLS|FS|SNAPSHOTS|EXPORTS]>',
            choices = ['VOLUMES', 'INITIATORS', 'POOLS', 'FS', 'SNAPSHOTS', 'EXPORTS'],
            help='List records of type [VOLUMES|INITIATORS|POOLS|FS|SNAPSHOTS|EXPORTS]\n'
                 'Note: SNAPSHOTS requires --fs <fs id>')

        commands.add_option( '', '--create-initiator', action="store", type="string",
            dest=_c("create-initiator"),
            metavar='<initiator name>',
            help='Create an initiator record, requires:\n'
                 '--id <initiator id>\n'
                 '--type [WWPN|WWNN|ISCSI|HOSTNAME]')

        commands.add_option( '', '--delete-initiator', action="store", type="string",
            dest=_c("delete-initiator"),
            metavar='<initiator id>',
            help='Delete an initiator record')

        commands.add_option( '', '--delete-fs', action="store", type="string",
            dest=_c("delete-fs"),
            metavar='<fs id>',
            help='Delete a filesystem')

        commands.add_option( '', '--create-volume', action="store", type="string",
            dest=_c("create-volume"),
            metavar='<volume name>',
            help="Creates a volume (logical unit) requires:\n"
                 "--size <volume size> (Can use M, G, T)\n"
                 "--pool <pool id>\n"
                 "--provisioning (optional) [DEFAULT|THIN|FULL]\n")

        commands.add_option( '', '--create-fs', action="store", type="string",
            dest=_c("create-fs"),
            metavar='<fs name>',
            help="Creates a file system requires:\n"
                 "--size <fs size> (Can use M, G, T)\n"
                 "--pool <pool id>")

        commands.add_option( '', '--create-ss', action="store", type="string",
            dest=_c("create-ss"),
            metavar='<snapshot name>',
            help="Creates a snapshot requires:\n"
                 "--file <repeat for each file>(default is all files)\n"
                 "--fs <file system id>")

        commands.add_option( '', '--clone-fs', action="store", type="string",
            dest=_c("clone-fs"),
            metavar='<source file system id>',
            help="Creates a file system clone requires:\n"
                 "--name <file system clone name>\n"
                 "--backing-snapshot <backing snapshot id> (optional)")

        commands.add_option( '', '--clone-file', action="store", type="string",
            dest=_c("clone-file"),
            metavar='<file system>',
            help="Creates a clone of a file (thin provisioned):\n"
                 "--src  <source file to clone (relative path)>\n"
                 "--dest <destination file (relative path)>\n"
                 "--backing-snapshot <backing snapshot id> (optional)")

        commands.add_option( '', '--delete-volume', action="store", type="string",
            metavar='<volume id>',
            dest=_c("delete-volume"), help='Deletes a volume given its id' )

        commands.add_option( '', '--delete-ss', action="store", type="string",
            metavar='<snapshot id>',
            dest=_c("delete-ss"), help='Deletes a snapshot requires --fs' )

        commands.add_option( '-r', '--replicate-volume', action="store", type="string",
            metavar='<volume id>',
            dest=_c("replicate-volume"), help='replicates a volume, requires:\n'
                                              "--type [RW_SNAP|CLONE|MIRROR]\n"
                                              "--pool <pool id>\n"
                                              "--name <human name>")

        commands.add_option( '', '--access-grant', action="store", type="string",
            metavar='<initiator id>',
            dest=_c("access-grant"), help='grants access to an initiator to a volume\n'
                                          'requires:\n'
                                          '--volume <volume id>\n'
                                          '--access [RO|RW], read-only or read-write')

        commands.add_option( '', '--access-revoke', action="store", type="string",
            metavar='<initiator id>',
            dest=_c("access-revoke"), help= 'removes access for an initiator to a volume\n'
                                            'requires:\n'
                                            '--volume <volume id>')

        commands.add_option( '', '--resize-volume', action="store", type="string",
            metavar='<volume id>',
            dest=_c("resize-volume"), help= 're-sizes a volume, requires:\n'
                                            '--size <new size>')

        commands.add_option( '', '--resize-fs', action="store", type="string",
            metavar='<fs id>',
            dest=_c("resize-fs"), help= 're-sizes a file system, requires:\n'
                                        '--size <new size>')

        commands.add_option( '', '--nfs-export-remove', action="store", type="string",
            metavar='<nfs export id>',
            dest=_c("nfs-export-remove"), help= 'removes a nfs export')

        commands.add_option( '', '--nfs-export-fs', action="store", type="string",
            metavar='<file system id>',
            dest=_c("nfs-export-fs"), help= 'creates a nfs export\n'
                                            'Required:\n'
                                            '--exportpath e.g. /foo/bar\n'
                                            'Optional:\n'
                                            'Note: root, ro, rw are to be repeated for each host\n'
                                            '--root <no_root_squash host>\n'
                                            '--ro <read only host>\n'
                                            '--rw <read/write host>\n'
                                            '--anonuid <uid to map to anonymous>\n'
                                            '--anongid <gid to map to anonymous>\n'
        )

        parser.add_option_group(commands)

        #Options to the actions
        #We could hide these with help = optparse.SUPPRESS_HELP
        #Should we?
        command_args = OptionGroup(parser, 'Command options')
        command_args.add_option('', '--size', action="store", type="string",
            metavar='size',
            dest=_o("size"), help='size (Can use M, G, T postfix)')
        command_args.add_option('', '--pool', action="store", type="string",
            metavar='pool id',
            dest=_o("pool"), help='pool ID')
        command_args.add_option('', '--provisioning', action="store", type="choice",
            default = 'DEFAULT',
            choices=['DEFAULT','THIN','FULL'], dest="provisioning", help='[DEFAULT|THIN|FULL]')

        command_args.add_option('', '--type', action="store", type="choice",
            choices=['WWPN', 'WWNN', 'ISCSI', 'HOSTNAME', 'RW_SNAP', 'CLONE', 'MIRROR'],
            metavar = "type",
            dest=_o("type"), help='type specifier')

        command_args.add_option('', '--name', action="store", type="string",
            metavar = "name",
            dest=_o("name"),
            help='human readable name')

        command_args.add_option('', '--volume', action="store", type="string",
            metavar = "volume",
            dest=_o("volume"), help='volume ID')

        command_args.add_option('', '--access', action="store", type="choice",
            metavar = "access",
            dest=_o("access"), choices=['RO', 'RW'] ,help='[RO|RW], read-only or read-write access')

        command_args.add_option('', '--id', action="store", type="string",
            metavar = "initiator id",
            dest=_o("id"), help="initiator id")

        command_args.add_option('', '--backing-snapshot', action="store", type="string",
            metavar = "<backing snapshot>", default=None,
            dest="backing_snapshot", help="backing snap shot name for operation")

        command_args.add_option('', '--src', action="store", type="string",
            metavar = "<source file>", default=None,
            dest=_o("src"), help="source of operation")

        command_args.add_option('', '--dest', action="store", type="string",
            metavar = "<source file>", default=None,
            dest=_o("dest"), help="destination of operation")

        command_args.add_option('', '--file', action="append", type="string",
            metavar = "<file>", default=None,
            dest="file", help="file to include in operation, option can be repeated")

        command_args.add_option('', '--fs', action="store", type="string",
            metavar = "<file system>", default=None,
            dest=_o("fs"), help="file system of interest")

        command_args.add_option('', '--exportpath', action="store", type="string",
            metavar = "<path for export>", default=None,
            dest=_o("exportpath"), help="desired export path on array")

        command_args.add_option('', '--root', action="append", type="string",
            metavar = "<no_root_squash_host>", default=[],
            dest="nfs_root", help="list of hosts with no_root_squash")

        command_args.add_option('', '--ro', action="append", type="string",
            metavar = "<read only host>", default=[],
            dest="nfs_ro", help="list of hosts with read/only access")

        command_args.add_option('', '--rw', action="append", type="string",
            metavar = "<read/write host>", default=[],
            dest="nfs_rw", help="list of hosts with read/write access")

        command_args.add_option('', '--anonuid', action="store", type="string",
            metavar = "<anonymous uid>", default=None,
            dest="anonuid", help="uid to map to anonymous")

        command_args.add_option('', '--anongid', action="store", type="string",
            metavar = "<anonymous uid>", default=None,
            dest="anongid", help="gid to map to anonymous")

        parser.add_option_group(command_args)

        (self.options, self.args) = parser.parse_args()

    def _cmd(self):
        cmds = [ e[4:] for e in dir(self.options)
                 if e[0:4]  == "cmd_" and self.options.__dict__[e] is not None ]
        if len(cmds) > 1:
            raise ArgError("More than one command operation specified (" + ",".join(cmds) + ")")

        if len(cmds) == 1:
            return cmds[0], self.options.__dict__['cmd_' + cmds[0]]
        else:
            return None, None


    def _validate(self):
        expected_opts = self.verify[self.cmd]['options']
        actual_ops = [ e[4:] for e in dir(self.options)
                       if e[0:4]  == "opt_" and self.options.__dict__[e] is not None ]

        if len(expected_opts):
            if len(expected_opts) == len(actual_ops):
                for e in expected_opts:
                    if e not in actual_ops:
                        print "expected=", ":".join(expected_opts)
                        print "actual=", ":".join(actual_ops)
                        raise ArgError("missing option " + e)

            else:
                raise ArgError("expected options = (" +
                               ",".join(expected_opts) + ") actual = (" +
                               ",".join(actual_ops) + ")")

        #Check size
        if self.options.opt_size:
            self._size(self.options.opt_size)

    #Need to redo these display routines...
    def display_volumes(self, vols):
        if self.options.sep is not None:
            s = self.options.sep
            for v in vols:
                out = (v.id, s, v.name, s, v.vpd83, s, v.block_size, s,
                       v.num_of_blocks, s, v.status, s, self._sh(v.size_bytes))
                print "%s"*len(out) % out
        else:
            format = "%-20s%-40s%-34s%-6s%-10s%-8s%-20s"
            print format % ('ID', 'Name', 'vpd83', 'bs', '#blocks', 'status', 'size')
            for v in vols:
                out = (v.id, v.name, v.vpd83, v.block_size, v.num_of_blocks,
                       v.status, self._sh(v.size_bytes))
                print format % out

    def display_pools(self, pools):
        if self.options.sep is not None:
            s = self.options.sep
            for p in pools:
                out = (p.id, s, p.name, s, self._sh(p.total_space), s,
                       self._sh(p.free_space))
                print "%s"*len(out) % out
        else:
            print "%-40s%-32s%-32s%-32s" % ('ID', 'Name', 'Total space', 'Free space')
            for p in pools:
                out = (p.id, p.name, self._sh(p.total_space),
                       self._sh(p.free_space))
                print "%-40s%-32s%-32s%-32s" % out

    def display_initiators(self, inits):
        if self.options.sep is not None:
            s = self.options.sep
            for i in inits:
                out = (i.id, s, i.name, s, i.type)
                print "%s"*len(out) % out
        else:
            format = "%-40s%-16s%-5s"
            print format % ('ID', 'Name', 'Type')
            for i in inits:
                out = (i.id, i.name, i.type)
                print format % out

    def display_fs(self, fss):
        if self.options.sep is not None:
            s = self.options.sep
            for f in fss:
                out = (f.id, s, f.name, s, self._sh(f.total_space), s,
                       self._sh(f.free_space), s, f.pool)
                print "%s"*len(out) % out
        else:
            format = "%-40s%-32s%-21s%-21s%-32s"
            print format %( 'ID', 'Name', 'Total space', 'Free space', 'Pool ID')
            for f in fss:
                out = (f.id, f.name, self._sh(f.total_space),
                       self._sh(f.free_space), f.pool)
                print format % out

    def display_snaps(self, ss):

        if self.options.sep is not None:
            p = self.options.sep
            for s in ss:
                out = (s.id, p, s.name, p, datetime.datetime.fromtimestamp(s.ts))
                print "%s"*len(out) % out
        else:
            format = "%-40s%-32s%-32s"
            print format % ( 'ID', 'Name', 'Created')
            for s in ss:
                out = (s.id, s.name, datetime.datetime.fromtimestamp(s.ts))
                print format % out

    def _list(self,l):
        if l and len(l):
            if self.options.sep:
                return self.options.sep.join(l)
            else:
                return ", ".join(l)
        else:
            return "None"

    def display_exports(self, exports):
        if self.options.sep is not None:
            s = self.options.sep
            for e in exports:
                print "id%s%s" % (s, e.id)
                print "export%s%s" %(s, e.export_path)
                print "fs_id%s%s" %(s, e.fs_id )
                print "root%s%s" % (s, self._list(e.root))
                print "ro%s%s" % (s, self._list(e.ro))
                print "rw%s%s" % (s, self._list(e.rw))
                print "anonuid%s%s" % ( s, e.anonuid )
                print "anongid%s%s" % ( s, e.anongid )
                print "options%s%s" % ( s, e.options )
        else:
            for e in exports:
                print "id:\t\t", e.id
                print "export:\t\t", e.export_path
                print "fs_id:\t\t", e.fs_id
                print "root:\t\t", self._list(e.root)
                print "ro:\t\t", self._list(e.ro)
                print "rw:\t\t", self._list(e.rw)
                print "anonuid:\t", e.anonuid
                print "anongid:\t", e.anongid
                print "options:\t", e.options, "\n"

    def list(self):
        if self.cmd_value == 'VOLUMES':
            self.display_volumes(self.c.volumes())
        elif self.cmd_value == 'POOLS':
            self.display_pools(self.c.pools())
        elif self.cmd_value == 'FS':
            self.display_fs(self.c.fs())
        elif self.cmd_value == 'SNAPSHOTS':
            if self.options.opt_fs is None:
                raise ArgError("--fs <file system id> required")

            fs = self._get_item(self.c.fs(),self.options.opt_fs)
            if fs:
                self.display_snaps(self.c.snapshots(fs))
            else:
                raise ArgError("filesystem %s not found!" % self.options.opt_volume)
        elif self.cmd_value == 'INITIATORS':
            self.display_initiators(self.c.initiators())
        elif self.cmd_value == 'EXPORTS':
            self.display_exports(self.c.exports())
        else:
            raise ArgError(" unsupported listing type=%s", self.cmd_value)

    def create_init(self):
        type = self.options.opt_type

        if type == 'WWPN':
            i = lsm.data.Initiator.TYPE_PORT_WWN
        elif type == 'WWNN':
            i = lsm.data.Initiator.TYPE_NODE_WWN
        elif type == 'ISCSI':
            i = lsm.data.Initiator.TYPE_ISCSI
        elif type == 'HOSTNAME':
            i = lsm.data.Initiator.TYPE_HOSTNAME
        else:
            raise ArgError("invalid initiator type " + type)

        init = self.c.initiator_create(self.cmd_value, self.options.opt_id,i)
        self.display_initiators([init])

    def delete_init(self):
        #get init object from id
        i = self._get_item(self.c.initiators(), self.cmd_value)
        if i:
            self.c.initiator_delete(i)
        else:
            raise ArgError("initiator with id = %s not found!" % self.cmd_value)

    def fs_delete(self):

        fs = self._get_item(self.c.fs(), self.cmd_value)
        if fs:
            self._wait_for_it("delete-fs", self.c.fs_delete(fs), None)
        else:
            raise ArgError("fs with id = %s not found!" % self.cmd_value)

    def fs_create(self):
        #Need a name, size and pool
        size = self._size(self.options.opt_size)
        p = self._get_item(self.c.pools(), self.options.opt_pool)
        name = self.cmd_value
        fs = self._wait_for_it("create-fs", *self.c.fs_create(p, name, size))
        self.display_fs([fs])

    def fs_resize(self):
        fs = self._get_item(self.c.fs(), self.cmd_value)
        size = self._size(self.options.opt_size)
        fs = self._wait_for_it("resize-fs", *self.c.fs_resize(fs, size))
        self.display_fs([fs])

    def fs_clone(self):
        src_fs = self._get_item(self.c.fs(), self.cmd_value)
        name = self.options.opt_name

        if not src_fs:
            raise ArgError(" source file system with id=%s not found!" % self.cmd_value)

        if self.options.backing_snapshot:
            #go get the snapsnot
            ss = self._get_item(self.c.snapshots(src_fs), self.options.backing_snapshot)
            if not ss:
                raise ArgError(" snapshot with id= %s not found!" % self.options.backing_snapshot)
        else:
            ss = None

        fs = self._wait_for_it("fs_clone", *self.c.fs_clone(src_fs, name, ss))
        self.display_fs([fs])

    def file_clone(self):
        fs = self._get_item(self.c.fs(), self.cmd_value)
        src = self.options.opt_src
        dest = self.options.opt_dest

        if self.options.backing_snapshot:
            #go get the snapsnot
            ss = self._get_item(self.c.snapshots(fs), self.options.backing_snapshot)
        else:
            ss = None

        self._wait_for_it("file_clone", self.c.file_clone(fs, src, dest, ss), None)

    def _get_item(self, l, id):
        for i in l:
            if i.id == id:
                return i
        return None

    @staticmethod
    def _size(s):
        s = string.upper(s)
        m = re.match('([0-9]+)([MGT]?)', s)
        if m:
            unit = m.group(2)
            rc = int(m.group(1))
            if unit == 'M':
                rc *= CmdLine.MiB
            elif unit == 'G':
                rc *= CmdLine.GiB
            else:
                rc *= CmdLine.TiB
        else:
            raise ArgError(" size is not in form <number>|<number[M|G|T]>")
        return rc

    def _sh(self, size):
        """
        Size for humans
        """
        units = None

        if self.options.human:
            if size >= CmdLine.TiB:
                size /= float(CmdLine.TiB)
                units = "TiB"
            elif size >= CmdLine.GiB:
                size /= float(CmdLine.GiB)
                units = "GiB"
            elif size >= CmdLine.MiB:
                size /= float(CmdLine.MiB)
                units = "MiB"

        if units:
            return "%.2f " % size + units
        else:
            return str(size)

    def create_volume(self):
        #Get pool
        p = self._get_item(self.c.pools(), self.options.opt_pool)
        if p:
            vol = self._wait_for_it("create-volume",
                *self.c.volume_create(p, self.cmd_value,
                self._size(self.options.opt_size),
                lsm.data.Volume.prov_string_to_type(self.options.provisioning)))

            self.display_volumes([vol])
        else:
            raise ArgError(" pool with id= %s not found!" % self.options.opt_pool)

    def create_ss(self):
        #Get fs
        fs = self._get_item(self.c.fs(), self.options.opt_fs)
        if fs:
            ss = self.c.snapshot_create(fs, self.cmd_value, self.options.file)
            self.display_snaps([ss])
        else:
            raise ArgError( "fs with id= %s not found!" % self.options.opt_fs)

    def delete_volume(self):
        v = self._get_item(self.c.volumes(), self.cmd_value)

        if v:
            self.c.volume_delete(v)
        else:
            raise ArgError(" volume with id= %s not found!" % self.cmd_value)

    def delete_ss(self):
        fs = self._get_item(self.c.fs(), self.options.opt_fs)
        if fs:
            ss = self._get_item(self.c.snapshots(fs), self.cmd_value)
            if ss:
                self._wait_for_it("delete-snapshot", self.c.snapshot_delete(fs,ss), None)
            else:
                raise ArgError(" snapshot with id= %s not found!" % self.cmd_value)
        else:
            raise ArgError(" file system with id= %s not found!" % self.options.opt_fs)

    def _wait_for_it(self, msg, job, item):
        if not job:
            return item
        else:
            while True:
                (s, percent, i) = self.c.job_status(job)

                if s == lsm.common.JobStatus.INPROGRESS:
                    #Add an option to spit out progress?
                    #print "Percent %s complete" % percent
                    time.sleep(0.25)
                elif s == lsm.common.JobStatus.COMPLETE:
                    self.c.job_free(job)
                    return i
                else:
                    #Something better to do here?
                    ArgError(msg + " job error code= %s" % s)

    def replicate_volume(self):
        p = self._get_item(self.c.pools(), self.options.opt_pool)
        v = self._get_item(self.c.volumes(), self.cmd_value)

        if p and v:

            type = lsm.data.Volume.rep_String_to_type(self.options.opt_type)
            if type == lsm.data.Volume.REPLICATE_UNKNOWN:
                raise ArgError("invalid replication type= %s" % type)

            vol = self._wait_for_it("replicate volume", *self.c.volume_replicate(p, type, v,
                self.options.opt_name))
            self.display_volumes([vol])
        else:
            if not p:
                raise ArgError("pool with id= %s not found!" % self.options.opt_pool)
            if not v:
                raise ArgError("Volume with id= %s not found!" % self.cmd_value)


    def _access(self, map=True):
        i = self._get_item(self.c.initiators(), self.cmd_value)
        v = self._get_item(self.c.volumes(), self.options.opt_volume)

        if i and v:

            if map:
                access = lsm.data.Volume.access_string_to_type(self.options.opt_access)
                self.c.access_grant(i,v,access)
            else:
                self.c.access_revoke(i,v)
        else:
            if not i:
                raise ArgError("initiator with id= %s not found!" % self.cmd_value)
            if not v:
                raise ArgError("volume with id= %s not found!" % self.options.opt_volume)

    def access_grant(self):
        return self._access()

    def access_revoke(self):
        return self._access(False)

    def resize_volume(self):
        v = self._get_item(self.c.volumes(), self.cmd_value)
        if v:
            size = self._size(self.options.opt_size)
            vol = self._wait_for_it("resize", *self.c.volume_resize(v, size))
            self.display_volumes([vol])
        else:
            ArgError("volume with id= %s not found!" % self.cmd_value)

    def nfs_export_remove(self):
        export = self._get_item(self.c.exports(), self.cmd_value)
        if export:
            self.c.export_remove(export)
        else:
            ArgError("nfs export with id= %s not found!" % self.cmd_value)

    def nfs_export_fs(self):
        fs = self._get_item(self.c.fs(), self.cmd_value)
        if fs:
            #Check to see if we have some type of access specified
            if len(self.options.nfs_root) == 0 and\
               len(self.options.nfs_rw) == 0 and\
               len(self.options.nfs_ro) == 0:
                raise ArgError(" please specify --root, --ro or --rw access")
            else:
                export = lsm.data.NfsExport( 'NA',        #Not needed on create
                    fs.id,
                    self.options.opt_exportpath,
                    None,
                    self.options.nfs_root,
                    self.options.nfs_rw,
                    self.options.nfs_ro,
                    self.options.anonuid,
                    self.options.anongid,
                    None)  #No options at this time
            export = self.c.export_fs(export)
            self.display_exports([export])
        else:
            raise ArgError(" file system with id=%s not found!" % self.cmd_value)


    def __init__(self):
        self.c = None
        self.cli()

        #Get and set the command and command value we will be executing
        (self.cmd, self.cmd_value) = self._cmd()

        if self.cmd is None:
            raise ArgError("no command specified, try --help")

        #Check for extras
        if len(self.args):
            raise ArgError("Extra command line arguments (" + ",".join(self.args) + ")")

        #Data driven validation
        self.verify = {'list': {'options': [], 'method': self.list},
                       'create-initiator': {'options': ['id', 'type'],
                                            'method': self.create_init},
                       'delete-initiator': {'options': [],
                                            'method': self.delete_init},
                       'delete-fs': {'options': [],
                                     'method': self.fs_delete},
                       'create-volume': {'options': ['size', 'pool'],
                                         'method': self.create_volume},
                       'create-fs': {'options': ['size', 'pool'],
                                     'method': self.fs_create},
                       'clone-fs': {'options': ['name'],
                                    'method': self.fs_clone},
                       'create-ss': {'options': ['fs'],
                                     'method': self.create_ss},
                       'clone-file': {'options': ['src', 'dest'],
                                      'method': self.file_clone},
                       'delete-volume': {'options': [],
                                         'method': self.delete_volume},
                       'delete-ss': {'options': ['fs'],
                                     'method': self.delete_ss},
                       'replicate-volume': {'options': ['type', 'pool', 'name'],
                                            'method': self.replicate_volume},
                       'access-grant': {'options': ['volume', 'access'],
                                        'method': self.access_grant},
                       'access-revoke': {'options': ['volume'],
                                         'method': self.access_revoke},
                       'resize-volume': {'options': ['size'],
                                         'method': self.resize_volume},
                       'resize-fs': {'options': ['size'],
                                     'method': self.fs_resize},
                       'nfs-export-remove': {'options': [],
                                             'method': self.nfs_export_remove},
                       'nfs-export-fs': {'options': ['exportpath'],
                                         'method': self.nfs_export_fs}}
        self._validate()

        self.uri = os.getenv('LSMCLI_URI')
        self.password = os.getenv('LSMCLI_PASSWORD')
        if self.options.uri is not None:
            self.uri = self.options.uri

        if self.uri is None:
            raise ArgError("--uri missing or export LSMCLI_URI")

        #Lastly get the password if requested.
        if self.options.prompt is not None:
            self.password = getpass.getpass()

        if self.password is not None:
            #Check for username
            u = lsm.common.uri_parse(self.uri)
            if u['username'] is None:
                raise ArgError("password specified with no user name in uri")

    def process(self):
        """
        Process the parsed command.
        """
        self.c = lsm.client.Client(self.uri,self.password)
        self.verify[self.cmd]['method']()
        self.c.close()