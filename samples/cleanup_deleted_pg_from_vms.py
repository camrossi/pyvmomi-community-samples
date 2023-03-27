#!/usr/bin/env python
"""
Written by camrossi
Github: https://github.com/camrossi
Note: Example code For testing purposes only
This code has been released under the terms of the Apache-2.0 license
http://opensource.org/licenses/Apache-2.0
"""
import re
from pyVmomi import vmodl, vim
from tools import cli, service_instance, pchelper, tasks

def find_orphaned_pg(si):
    content = si.RetrieveContent()
    task = content.taskManager
    pg_to_delete = {}
    for t in task.recentTask:
        if (t.info.state == 'error' and t.info.error.faultMessage ) and t.info.error.faultMessage[0].key == 'com.vmware.vim.vpxd.dvs.pgPortInUse.label':
            if t.info.entity.parent:
                for child in t.info.entity.parent.childEntity:
                    if child.name == t.info.entityName:
                        #print("I want to delete:")
                        #print("DVS " + child.config.distributedVirtualSwitch.config.name
                        #    + " PG: " + child.name)
                        pg_to_delete[child.key] = child.name

    
    return pg_to_delete

def change_vm_if(si,pg_to_delete, new_pg, is_VDS):
    content = si.RetrieveContent()
    vms = pchelper.get_all_obj(content, [vim.VirtualMachine])
    for vm in vms:
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard) :
                nicspec = vim.vm.device.VirtualDeviceSpec()
                nicspec.operation = \
                    vim.vm.device.VirtualDeviceSpec.Operation.edit
                nicspec.device = device
                nicspec.device.wakeOnLanEnabled = True
                #Check only for DVSs
                if isinstance(nicspec.device.backing, vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo):
                    if nicspec.device.backing.port.portgroupKey in pg_to_delete.keys():
                        device_change = []
                        print("VM Name: ",vm.name)
                        print("\tI will remove: ", pg_to_delete[nicspec.device.backing.port.portgroupKey])
                        answer = input("Modify This VM?")
                        if answer.lower() in ["y","yes"]:
                            nicspec = vim.vm.device.VirtualDeviceSpec()
                            nicspec.operation = \
                                vim.vm.device.VirtualDeviceSpec.Operation.edit
                            nicspec.device = device
                            nicspec.device.wakeOnLanEnabled = True
                            if not is_VDS:
                                nicspec.device.backing = \
                                    vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
                                nicspec.device.backing.network = \
                                    pchelper.get_obj(content, [vim.Network], new_pg)
                                nicspec.device.backing.deviceName = new_pg
                            else:
                                network = pchelper.get_obj(
                                    content, [vim.dvs.DistributedVirtualPortgroup], new_pg)
                                dvs_port_connection = vim.dvs.PortConnection()
                                dvs_port_connection.portgroupKey = network.key
                                dvs_port_connection.switchUuid = \
                                    network.config.distributedVirtualSwitch.uuid
                                nicspec.device.backing = \
                                    vim.vm.device.VirtualEthernetCard. \
                                    DistributedVirtualPortBackingInfo()
                                nicspec.device.backing.port = dvs_port_connection
                            nicspec.device.connectable = \
                                vim.vm.device.VirtualDevice.ConnectInfo()
                            nicspec.device.connectable.startConnected = True
                            nicspec.device.connectable.allowGuestControl = True
                            device_change.append(nicspec)
                            config_spec = vim.vm.ConfigSpec(deviceChange=device_change)
                            task = vm.ReconfigVM_Task(config_spec)
                            tasks.wait_for_tasks(si, [task])
                            print("Successfully changed network for VM", vm.name)

def main():
    """
    Simple command-line program that finds PG that can;t be deleted because in use and 
    reconfigure all the VMs using them to use a user provided port grout. 
    i.e for SVS:
    python3 cleanup_deleted_pg_from_vms.py  -s <vcIP>  -u <user> --password <pass> -nossl \
        --network-name "VM Network" 
    i.e for dVS:
    python3 cleanup_deleted_pg_from_vms.py  -s <vcIP>  -u <user> --password <pass> -nossl \
        --network-name "PG Name" --is_VDS
    """

    parser = cli.Parser()
    parser.add_optional_arguments(cli.Argument.NETWORK_NAME)
    parser.add_custom_argument('--is_VDS',
                               action="store_true",
                               default=False,
                               help='The provided network is in VSS or VDS')
    args = parser.get_args()
    si = service_instance.connect(args)
    
    try:
        pg_to_delete = find_orphaned_pg(si)
        change_vm_if(si,pg_to_delete,args.network_name,args.is_VDS)
        

    except vmodl.MethodFault as error:
        print("Caught vmodl fault : {0}".format(error.msg))
        return -1

    return 0


# Start program
if __name__ == "__main__":
    main()
