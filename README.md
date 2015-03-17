Based on patch adding support of vif_plug from:
- nova-specs: https://review.openstack.org/162468
- nova: https://review.openstack.org/162470
- neutron: https://review.openstack.org/162471

1) install vif_plug_script

cp vif_ovs_plug_script.py /usr/bin
mkdir /etc/nova_vif_ovs_plug/
cp -a rootwrap/* /etc/nova_vif_ovs_plug/.

2) configure neutron

Add to /etc/neutron/neutron.conf in [DEFAULT] section: 
vif_plugin_script = vif_ovs_plug_script.py
