#!/usr/bin/env python
#
#  Copyright (c) 2010-2011 Corey Goldberg (http://goldb.org)
#
#  License: MIT (http://www.opensource.org/licenses/mit-license)
# 
#  This file is part of linux-stats-dashboard.
#


"""stats2rrd.py - collect and graph linux operating system stats"""


import os.path
import shlex
import socket
import subprocess
import time



# Config Settings
NET_INTERFACE = 'eth0'
DISK = 'sda'
INTERVAL = 60  # 1 min
GRAPH_MINS = (60, 240, 1440)  # 1hour, 4hours, 1day
GRAPH_DIR = './linux-stats-web/'
STORAGE_DIR = './'



def main():  
    cpu_pct = cpu_util(5)

    mem_used, mem_total = mem_stats()

    rx_bits, tx_bits = net_stats(NET_INTERFACE)

    load_avg = load_avg_1min()

    disk_pct = disk_busy(DISK, 5)

    localhost_name = socket.gethostname()

    # store values in rrd and update graphs
    rrd_ops('cpu_percent', cpu_pct, 'GAUGE', 'FF0000', localhost_name, 1000, upper_limit=100)
    rrd_ops('mem_used', mem_used, 'GAUGE', '00FF00', localhost_name, 1024, upper_limit=mem_total)
    rrd_ops('net_bps_in', rx_bits, 'DERIVE', '6666FF', localhost_name, 1000)
    rrd_ops('net_bps_out', tx_bits, 'DERIVE', '000099', localhost_name, 1000)
    rrd_ops('load_avg', load_avg, 'GAUGE', 'FF9933', localhost_name, 1000)
    rrd_ops('disk_busy_percent', disk_pct, 'GAUGE', '663366', localhost_name, 1000, upper_limit=100)


def rrd_ops(stat, value, ds_type, color, title, base, upper_limit=None):
    rrd_name = '%s.rrd' % stat
    rrd = RRD(rrd_name, stat)
    rrd.upper_limit = upper_limit
    rrd.base = base
    rrd.graph_title = title
    rrd.graph_color = color
    rrd.graph_dir = GRAPH_DIR
    rrd.storage_dir = STORAGE_DIR
    if not os.path.exists(os.path.join(STORAGE_DIR, rrd_name)):
        rrd.create(INTERVAL, ds_type)
    rrd.update(value)
    for mins in GRAPH_MINS:
        rrd.graph(mins)
    print time.strftime('%Y/%m/%d %H:%M:%S', time.localtime()), stat, value


def net_stats(interface):
    for line in open('/proc/net/dev'):
        if interface in line:
            data = line.split('%s:' % interface)[1].split()
            rx_bits, tx_bits = (int(data[0]) * 8, int(data[8]) * 8)
            return (rx_bits, tx_bits)


def mem_stats():
    with open('/proc/meminfo') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                mem_total = int(line.split()[1]) * 1024
            if line.startswith('MemFree:'):
                mem_used = mem_total - (int(line.split()[1]) * 1024)
    return mem_used, mem_total


def cpu_util(sample_duration=1):
    with open('/proc/stat') as f1:
        with open('/proc/stat') as f2:
            line1 = f1.readline()
            time.sleep(sample_duration)
            line2 = f2.readline()
    deltas = [int(b) - int(a) for a, b in zip(line1.split()[1:], line2.split()[1:])]
    idle_delta = deltas[3]
    total = sum(deltas)
    util_pct = 100 * (float(total - idle_delta) / total)
    return util_pct


def disk_busy(device, sample_duration=1):
    with open('/proc/diskstats') as f1:
        with open('/proc/diskstats') as f2:
            content1 = f1.read()
            time.sleep(sample_duration)
            content2 = f2.read()
    sep = '%s ' % device
    io_ms1 = '0'
    io_ms2 = '0'
    for line in content1.splitlines():
        if sep in line:
            io_ms1 = line.strip().split(sep)[1].split()[9]
            break
    for line in content2.splitlines():
        if sep in line:
            io_ms2 = line.strip().split(sep)[1].split()[9]
            break            
    delta = int(io_ms2) - int(io_ms1)
    total = sample_duration * 1000
    busy_pct = 100 - (100 * (float(total - delta) / total))
    return busy_pct


def load_avg_1min():
    with open('/proc/loadavg') as f:
        line = f.readline()
    load_avg = float(line.split()[0])  # 1 minute load average
    return load_avg   



class RRD(object):
    def __init__(self, rrd_name, stat):
        self.stat = stat
        self.rrd_name = rrd_name
        self.rrd_exe = 'rrdtool'
        self.upper_limit = None
        self.base = 1000  # for traffic measurement, 1 kb/s is 1000 b/s.  for sizing, 1 kb is 1024 bytes. 
        self.graph_title = ''
        self.graph_dir = './' 
        self.storage_dir = './' 
        self.graph_color = 'FF6666'
        self.graph_width = 480
        self.graph_height = 160
        

    def create(self, interval, ds_type='GAUGE'):  
        interval = str(interval) 
        interval_mins = float(interval) / 60  
        heartbeat = str(int(interval) * 2)
        ds_string = ' DS:ds:%s:%s:0:U' % (ds_type, heartbeat)
        cmd_create = ''.join((self.rrd_exe, 
            ' create ', os.path.join(self.storage_dir, self.rrd_name), ' --step ', interval, ds_string,
            ' RRA:AVERAGE:0.5:1:', str(int(4000 / interval_mins)),
            ' RRA:AVERAGE:0.5:', str(int(30 / interval_mins)), ':800',
            ' RRA:AVERAGE:0.5:', str(int(120 / interval_mins)), ':800',
            ' RRA:AVERAGE:0.5:', str(int(1440 / interval_mins)), ':800'))
        p = subprocess.Popen(shlex.split(cmd_create), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        cmd_output = p.communicate()[0].rstrip()
        if len(cmd_output) > 0:
            raise RRDError('unable to create RRD: %s' % cmd_output)


    def update(self, value):
        cmd_update = '%s update %s N:%s' % (self.rrd_exe, os.path.join(self.storage_dir, self.rrd_name), value)
        p = subprocess.Popen(shlex.split(cmd_update), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        cmd_output = p.communicate()[0].rstrip()
        if len(cmd_output) > 0:
            raise RRDError('unable to update RRD: %s' % cmd_output)


    def graph(self, mins):       
        start_time = 'now-%s' % (mins * 60)  
        output_filename = '%s_%i.png' % (self.rrd_name, mins)
        end_time = 'now'
        cur_date = time.strftime('%m/%d/%Y %H\:%M\:%S', time.localtime())    
        cmd = [self.rrd_exe, 'graph', os.path.join(self.graph_dir, output_filename)]
        cmd.append('COMMENT:\\s')
        cmd.append('COMMENT:%s    ' % cur_date)
        cmd.append('DEF:ds=%s:ds:AVERAGE' % os.path.join(self.storage_dir, self.rrd_name))
        cmd.append('AREA:ds#%s:%s  ' % (self.graph_color, self.stat))
        cmd.append('VDEF:dslast=ds,LAST')
        cmd.append('VDEF:dsavg=ds,AVERAGE')
        cmd.append('VDEF:dsmin=ds,MINIMUM')
        cmd.append('VDEF:dsmax=ds,MAXIMUM')
        cmd.append('COMMENT:\\s')
        cmd.append('COMMENT:\\s')
        cmd.append('COMMENT:\\s')
        cmd.append('COMMENT:\\s')
        cmd.append('GPRINT:dslast:last %.1lf%S    ') 
        cmd.append('GPRINT:dsavg:avg %.1lf%S    ')
        cmd.append('GPRINT:dsmin:min %.1lf%S    ')
        cmd.append('GPRINT:dsmax:max %.1lf%S    ')
        cmd.append('COMMENT:\\s')
        cmd.append('COMMENT:\\s')
        cmd.append('--title=%s' % self.graph_title)
        cmd.append('--vertical-label=%s' % self.stat)
        cmd.append('--start=%s' % start_time)
        cmd.append('--end=%s' % end_time)
        cmd.append('--width=%i' % self.graph_width)
        cmd.append('--height=%i' % self.graph_height)
        cmd.append('--base=%i' % self.base)
        cmd.append('--slope-mode')
        if self.upper_limit is not None:
            cmd.append('--upper-limit=%i' % self.upper_limit)
        cmd.append('--lower-limit=0')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        cmd_output = p.communicate()[0].rstrip()
        if len(cmd_output) > 10:
            raise RRDError('unable to graph RRD: %s' % cmd_output)
            
          
          
class RRDError(Exception): pass

    

if __name__ == '__main__':
    main()
