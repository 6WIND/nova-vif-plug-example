#!/usr/bin/python
#
# Copyright 2015 6WIND S.A.

import os, argparse

from oslo_concurrency import processutils


#-------------------------------------------------------------------------------
# utils section
ROOTWRAP_CONFIG = '/etc/nova_vif_ovs_plug/rootwrap.conf'

def execute(*cmd, **kwargs):
    if 'run_as_root' in kwargs:
        kwargs['root_helper'] = 'sudo nova-rootwrap %s' % ROOTWRAP_CONFIG
    return processutils.execute(*cmd, **kwargs)

def device_exists(device):
    """Check if ethernet device exists."""
    return os.path.exists('/sys/class/net/%s' % device)

def create_veth_pair(dev1_name, dev2_name):
    execute('ip', 'link', 'add', dev1_name, 'type', 'veth', 'peer',
            'name', dev2_name, run_as_root=True)

    for dev in [dev1_name, dev2_name]:
        execute('ip', 'link', 'set', dev, 'up', run_as_root=True)
        execute('ip', 'link', 'set', dev, 'promisc', 'on', run_as_root=True)

#-------------------------------------------------------------------------------
# ovs vif section
def is_hybrid_plug(vif):
    if vif['port_filter'].lower() == 'true':
        return True
    if vif['ovs_hybrid_plug'].lower() == 'true':
        return True
    return False

NIC_NAME_LEN = 14

def get_br_name(iface_id):
    return ('qbr' + iface_id)[:NIC_NAME_LEN]

def get_veth_pair_names(iface_id):
    return (('qvb%s' % iface_id)[:NIC_NAME_LEN],
            ('qvo%s' % iface_id)[:NIC_NAME_LEN])

def plug(vif):
    # nothing to do for non hybrid plug method
    if not is_hybrid_plug(vif):
        return

    iface_id = vif['ovs_interfaceid']
    br_name = get_br_name(vif['id'])
    v1_name, v2_name = get_veth_pair_names(vif['id'])
    if not device_exists(br_name):
        execute('brctl', 'addbr', br_name, run_as_root=True)
        execute('brctl', 'setfd', br_name, 0, run_as_root=True)
        execute('brctl', 'stp', br_name, 'off', run_as_root=True)
        execute('tee', '/sys/class/net/%s/bridge/multicast_snooping' % br_name,
                process_input='0',
                run_as_root=True,
                check_exit_code=[0, 1])

    if not device_exists(v2_name):
        create_veth_pair(v1_name, v2_name)
        execute('ip', 'link', 'set', br_name, 'up', run_as_root=True)
        execute('brctl', 'addif', br_name, v1_name, run_as_root=True)
        execute('ovs-vsctl', '--timeout=120', '--', '--if-exists',
                'del-port', v2_name, '--', 'add-port', vif['bridge_name'],
                v2_name, '--', 'set', 'Interface', v2_name,
                'external-ids:iface-id=%s' % iface_id,
                'external-ids:iface-status=active',
                'external-ids:attached-mac=%s' % vif['address'],
                'external-ids:vm-uuid=%s' % vif['instance_id'],
                run_as_root=True)

def unplug(vif):
    if not is_hybrid_plug(vif):
        return

    br_name = get_br_name(vif['id'])
    v1_name, v2_name = get_veth_pair_names(vif['id'])

    if device_exists(br_name):
        execute('brctl', 'delif', br_name, v1_name, run_as_root=True)
        execute('ip', 'link', 'set', br_name, 'down', run_as_root=True)
        execute('brctl', 'delbr', br_name, run_as_root=True)

    execute('ovs-vsctl', '--timeout=120', '--', '--if-exists',
            'del-port', vif['bridge_name'], v2_name, run_as_root=True)

    if device_exists(v2_name):
        execute('ip', 'link', 'delete', v2_name, run_as_root=True)

#-------------------------------------------------------------------------------
# main
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', metavar='ACTION',
                        help='Action to perform with vif on the ovs bridge',
                        choices=['plug', 'unplug'])
    args = parser.parse_args()

    args.vif = {}
    args.vif['id'] = os.getenv('VIF_ID')
    args.vif['ovs_interfaceid'] = os.getenv('VIF_OVS_INTERFACEID', args.vif['id'])
    args.vif['address'] = os.getenv('VIF_ADDRESS')
    args.vif['bridge_name'] = os.getenv('VIF_NETWORK_BRIDGE', 'br-int')
    args.vif['instance_id'] = os.getenv('VIF_INSTANCE_ID')
    args.vif['port_filter'] = os.getenv('VIF_DETAILS_PORTS_FILTER', 'false')
    args.vif['ovs_hybrid_plug'] = os.getenv('VIF_DETAILS_OVS_HYBRID_PLUG', 'false')

    if args.vif['id'] is None:
        parser.error('missing VIF_ID environment variable')
    if args.vif['address'] is None:
        parser.error('missing VIF_ADDRESS environment variable')
    if args.vif['instance_id'] is None:
        parser.error('missing VIF_INSTANCE_ID environment variable')

    return args

def main(args):
    if args.action == 'plug':
        plug(args.vif)
    else:
        unplug(args.vif)

if __name__ == '__main__':
    main(parse_args())
