#This file was created by Yombo for use with Yombo Gateway automation
#software.  Details can be found at https://yombo.net
"""
Insteon API
===========

This module provides command interface for Insteon based devices.  It
will forward any insteon requests to any attached insteon interface
module.  It will also process any status updates and send to the rest
of the Yombo gateway modules.

Parts of this file are from the the Yombo X10API and the PyInsteon project
located at https://github.com/zonyl/pyinsteon.  As such, this file is not
distributed as part of the Yombo gateway software, due to licensing
requirements, but as a seperate download to be optionally installed seperately
at the users request.

License
=======

This module is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

The `Yombo.net <http://www.yombo.net/>`_ team and other contributors
hopes that it will be useful, but WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

The GNU General Public License can be found here: `GNU.Org <http://www.gnu.org/licenses>`_

Implements
==========

- class InsteonCmd - A class to pass between InsteonAPI module and interface modules.
- class InsteonAPI - the command module 

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>
:copyright: Copyright 2012-2016 by Yombo.
:license: GPL(v3)
"""
try:  # Prefer simplejson if installed, otherwise json will work swell.
    import simplejson as json
except ImportError:
    import json
from time import time

from collections import OrderedDict

from twisted.internet.defer import inlineCallbacks

from yombo.lib.webinterface.auth import require_auth
from yombo.utils import global_invoke_all
from yombo.core.module import YomboModule
from yombo.core.log import get_logger
from yombo.utils.decorators import memoize_ttl
from yombo.utils import translate_int_value

logger = get_logger("modules.insteonapi")

        
class InsteonAPI(YomboModule):
    """
    Insteon Command Module
    
    Generic module that handles all insteon commands from other modules
    and prepares it for an interface module.  Also receives data from
    interface modules for delivery to other gateway modules.
    """
    @inlineCallbacks
    def _init_(self, **kwargs):
        self.interface_module = None
        self.devices = yield self._SQLDict.get(self, "devices")

    @inlineCallbacks
    def _load_(self, **kwargs):
        results = yield global_invoke_all('insteonapi_interfaces', called_by=self)
        temp = {}
        for component_name, data in results.items():
            temp[data['priority']] = {'name': component_name, 'module': data['module']}

        interfaces = OrderedDict(sorted(temp.items()))
        self.interface_module = None
        if len(interfaces) == 0:
            logger.error("Insteon API - No Insteon interface module found, disabling Insteon support.")
        else:
            key = list(interfaces.keys())[-1]
            self.interface_module = temp[key]['module']  # we can only have one interface, highest priority wins!!
            self.interface_module.insteonapi_init(self)  # tell the interface module about us.

    def _start_(self, **kwargs):
        logger.debug("Insteon API command module started")
        
    def _stop_(self, **kwargs):
        pass

    def _unload_(self, **kwargs):
        pass
    #
    # def _device_type_loaded_(self, **kwargs):
    #     print("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1")
    #     return "aaaaaaaaaa"

    def _webinterface_add_routes_(self, **kwargs):
        """
        Adds a configuration block to the web interface. This allows users to view their nest account for
        thermostat ID's which they can copy to the device setup page.
        :param kwargs:
        :return:
        """
        return {
            'nav_side': [
                {
                    'label1': 'Device Tools',
                    'label2': 'Insteon',
                    'priority1': None,  # Even with a value, 'Tools' is already defined and will be ignored.
                    'priority2': 15001,
                    'icon': 'fa fa-info fa-fw',
                    'url': '/tools/module_insteonapi',
                    'tooltip': '',
                    'opmode': 'run',
                },
            ],
            'routes': [
                self.web_interface_routes,
            ],
        }

    def web_interface_routes(self, webapp):
        """
        Adds routes to the webinterface module.

        :param webapp: A pointer to the webapp, it's used to setup routes.
        :return:
        """
        with webapp.subroute("/") as webapp:
            @webapp.route("/tools/module_insteonapi", methods=['GET'])
            @require_auth()
            def page_tools_module_insteonap_get(webinterface, request, session):
                interface_devices = self.interface_module.get_found_devices()
                insteon_addresses = self.insteon_addresses
                appliance_dt = self._DeviceTypes['insteon_appliance']
                light_dt = self._DeviceTypes['insteon_lamp']
                for address, device in interface_devices.items():
                    if address in insteon_addresses:
                        device['device_id'] = self.get_insteon_device(address)
                    else:
                        device['device_id'] = None
                        if 'light' in device['capabilities']:
                            device['device_type'] = light_dt
                        elif 'switch' in device['capabilities']:
                            device['device_type'] = appliance_dt
                        else:
                            device['device_type'] = None

                        variables = {
                            'address': {
                                'new_99': address
                            },
                        }
                        device['json_output'] = json.dumps({
                        # 'device_id': '',
                        'label': '',
                        'machine_label': '',
                        'description': device['description'] + " - " + device['model'],
                        # 'statistic_label': "myhouse." +
                        # 'statistic_lifetime': 0,
                        'device_type_id': device['device_type'].device_type_id,
                        'vars': variables,
                        # 'variable_data': json_output['vars'],
                        })


                page = webinterface.webapp.templates.get_template('modules/insteonapi/web/home.html')
                return page.render(alerts=webinterface.get_alerts(),
                                   devices=interface_devices
                                   )


    def _device_command_(self, **kwargs):
        """
        Implements the system hook to process commands.

        This will only process commands for insteon devices. X10 commands must come from an API based module.
        """
        if self.interface_module is None:
            logger.info("InstonAPI module cannot process device commands: no insteon interface module found.")
            return False

        device = kwargs['device']
        request_id = kwargs['request_id']

        if self._is_my_device(device) is False:
            logger.warn("InsteonAPI module cannot handle device_type_id: {device_type_id}", device_type_id=device.device_type_id)
            return False

        if self.interface_module.status is not True:
            device.device_command_failed(
                request_id,
                message="Problem with Homevision connection, requested command could not be completed"
            )
            logger.debug("InstonAPI interface module ({interface_module}) reports an invalid status: {status}",
                         interface_module=self.interface_module._Name, status = self.interface_module.status)
            return False

        module_device_types = self._ModuleDeviceTypes()

        kwargs['device_type'] = module_device_types[device.device_type_id]
        device.device_command_processing(request_id)
        results = self.interface_module.device_command(**kwargs)
        if results[0] == 'failed':
            device.device_command_failed(request_id, message=results[1])
        elif results[0] == 'done':
            device.device_command_done(request_id, message=results[1])
        else:
            device.device_command_done(request_id)

    @property
    def insteon_addresses(self):
        devices = self._ModuleDevices()
        addresses = []
        for device_id, device in devices.items():
            addresses.append(device.device_variables['address']['values'][0].upper())
        return addresses

    @memoize_ttl(60)
    def insteon_devices(self):
        my_devices = self._ModuleDevices()
        devices = {}
        for device_id, device in my_devices.items():
            devices[device.device_variables['address']['values'][0].upper()] = device
        return devices

    @memoize_ttl(60)
    def get_insteon_device(self, address):
        """
        Looks for an insteon device given the provided address. 
        :param address: 
        :return: the device pointer
        """
        address = address.upper()
        devices = self._ModuleDevices()
        for device_id, device in devices.items():
            temp_address = device.device_variables['address']['values'][0].upper()
            if address == temp_address:
                return device
        return None

    def insteon_device_update(self, device, command_label):
        """
        Called by interface modules when a device has a change of status.
        """
        # print("insteon got update...")
        try:
            yombo_device = self.get_insteon_device(device['address'])
        except Exception as e:
            yombo_device = None

        if device['address'] not in self.devices:
            self.devices[device['address']] = {
                'onlevel': 0,
            }
            if yombo_device is None:
                self._Notifications.add({
                    'title': 'New Insteon device found',
                    'message': 'The insteon PLM module found a new insteon device. <p>Address: %s <br>Type: %s <br>Description: %s <br>Capabilities: %s' %
                               (device['address'], device['model'], device['description'], str.join(", ", device['capabilities'])),
                    'source': 'Insteon PLM Module',
                    'persist': True,
                    'priority': 'high',
                    'always_show': True,
                    'always_show_allow_clear': True,
                    'id': 'insteonplm_%s' % device['address_hex'],
                })

        if self.devices[device['address']]['onlevel'] != device['onlevel']:
            self.devices[device['address']]['onlevel'] = device['onlevel']
            if yombo_device != None:
                human_status = str(round(translate_int_value(device['onlevel'], 0, 255, 0, 100),1)) + "%"

                # now try to associate device status change with any recently sent commands.
                commands_pending = yombo_device.commands_pending(
                    criteria =
                        {
                            'status': ['sent', 'received', 'pending', 'done'],
                        },
                    limit = 1)
                # print("insteon found commands pending")
                # import json
                # print(json.dumps(commands_pending))
                # print(type(commands_pending))
                # for k, vals in commands_pending.items():
                #     print("* k = %s" % k)

                last_request_id = None
                cur_time = time()
                for request_id, device_command in commands_pending.items():
                    if cur_time - device_command.created_at < 1:
                        last_command = device_command.command.machine_label
                        if command_label is 'on' and last_command in ('on', 'on_fast', 'dim', 'brighten', 'dim_stop', 'brighten_stop'):
                            last_request_id = request_id
                            break
                        if command_label is 'off' and last_command in ('off', 'off_fast'):
                            last_request_id = request_id
                            break

                if last_request_id is not None:
                    yombo_device.device_command_done(last_request_id)

                yombo_device.set_status(
                    human_status=human_status,
                    human_message="%s is now %s" % (yombo_device.label, human_status),
                    machine_status=device['onlevel'],
                    command=command_label,
                    request_id=last_request_id,
                    reported_by=self.interface_module._FullName)
