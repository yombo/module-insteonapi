#This file was created by Yombo for use with Yombo Gateway automation
#software.  Details can be found at http://yombo.net
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
import time
#import re

from yombo.core.module import YomboModule
from yombo.core.log import get_logger

logger = get_logger("modules.insteonapi")

class InsteonCmd:
    """
    An Insteon command instance that is passed between this module
    and any interface modules to send insteon commands to the power line.
    
    :ivar insteonaddress: Insteon unit address.
    :type insteonaddress: string
    """
    def __init__(self, apimodule, message = {'msgID':None}):
        """
        Setup the class to communicate between insteon API module and any interface modules.
        
        :param insteonapi: A pointer to the insteonapi class.
        :type insteonapi: instance
        :param message: ???
        :type message: ??
        """
        self.deviceobj = message.payload['deviceobj']
        """@ivar: The device itself
           @type: C{YomboDevice}"""
        self.cmdobj = message.payload['cmdobj']
        """@ivar: The command itself
           @type: C{YomboDevice}"""
        self.device_class = "insteon"

        self.address = self.deviceobj.deviceVariables['insteonaddress']['value'][0].upper()
        """@ivar: Insteon unit address.
           @type: C{string}"""
        self.command = message['payload']['cmdobj'].cmd.upper()
        """@ivar: Text representing the command - on, off, dim, etc.
           @type: C{string}"""

        self.msguuid = message.msgUUID
        """@ivar: The msgID that was generated to create this command. Is None if comming from interface module.
           @type: C{str}"""
        self.extended = None
        """@ivar: Extended data to send with the insteon command.
           @type: C{hex}"""
        self.deviceState = None
        """@ivar: The updated state of the device. This is set by the interface module.
           @type: C{str} or C{int}"""
        self.interfaceResult = None
        """@ivar: Interface Result. This is set by the interface module.
           @type: C{str} or C{int}"""
        self.commandResult = None
        """@ivar: The result from the command. Will be set by the interface module.
           @type: C{str} or C{int}"""

        self.created = int(time.time())
        self.interfaceResult = None
        self.commandResult = None
        self.status1 = None
        self.status2 = None
        self.originalMessage = message
        self.apimodule = apimodule

    def dump(self):
        """
        Convert key class contents to a dictionary.

        @return: A dictionary of the key class contents.
        @rtype: C{dict}
        """
        return {'address': self.address,
                'command': self.command,
                'extended': self.extended,
                'deviceState': self.deviceState,
                'interfaceResult': self.interfaceResult,
                'commandResult': self.commandResult,
                'deviceobj': self.deviceobj,
                'cmdobj': self.cmdobj,
                'device_class': self.device_class,
                'created': self.created,
                }
                
    def sendCmdToInterface(self):
        """
        Send to the insteon command module
        """
        self.apimodule.interfaceModule.sendInsteonCmd(self)
        
    def statusReceived(self, status, statusExtended={}):
        """
        Contains updated status of a device received from the interface.
        """
        pass
        
    def done(self):
        """
        Called by the interface module once the command has been completed.
        
        Note: the interface module will call the insteonapi module when a device
        has a status change.  This is a different process then a command.
        """
        self.apimodule.cmdDone(self)
        self.apimodule.removeInsteonCmd(self)

    def cmdPending(self):
        """
        Used to tell the sending module that the command is pending (processing)
        """
        reply = self.originalMessage.getReply(msgStatus='processing', msgStatusExtra="interface module processing request")
        reply.send()
    
    def cmdFailed(self, statusmsg):
        """
        Used to tell the sending module that the command failed.
        
        statussg should hold the failure reason.  Displayed to user.
        """
        reply = self.originalMessage.getReply(msgStatus='failed', msgStatusExtra="interface module failed to process request")
        self.apimodule.removeInsteonCmd(self)
        reply.send()
        
class InsteonAPI(YomboModule):
    """
    Insteon Command Module
    
    Generic module that handles all insteon commands from other modules
    and prepares it for an interface module.  Also receives data from
    interface modules for delivery to other gateway modules.
    """

    def _init_(self):
#        logger.info("&&&&: Insteon Module Devices: {devices}", devices=self._Devices)
#        logger.info("&&&&: Insteon Module DeviceTypes: {devicesTypes}", deviceTypes=self._DeviceTypes)
        self._ModDescription = "Insteon API command interface"
        self._ModAuthor = "Mitch Schwenk @ Yombo"
        self._ModUrl = "http://www.yombo.net"

        self.insteoncmds = {}         #store a copy of active x10cmds
        self.originalMessage = None
        self.interfaceSupport = False

        self.deviceLinks = {}
#        self.deviceLinks = SQLDict(self,"deviceLinks")  # used to store what devices
                                          # listen to group broadcasts.
                                          # data saved in this dict is saved
                                          # in SQL and recreated on startup.

        self.insteonDevices = {} # used to lookup insteon address to a device
#        for devkey, device in self._LocalDevicesByUUID.iteritems():
#            self.insteonDevices[device.deviceVariables['address'][0].upper()] = device

#        logger.warn("Device types: {dt}", dt=self._DeviceTypes)

    def _load_(self):
        self._reload_()

    def _reload_(self):
        try:
            interface_device_type = self._DeviceTypes[0]  # We only handle x10. Only x10 device types come here. Just pick the first one.
            self.interfaceModule = self._Libraries['devices'].get_device_routing(interface_device_type, 'Interface', 'module')
            self.interfaceSupport = True
            print "interfaceModule: %s" % self.interfaceModule
            logger.error("Insteon API - Interface Module: {mmm}", mmm=self.interfaceModule)
        except:
            # no X10API module!
            logger.error("Insteon API - No Insteon interface module found, disabling Insteon support.")
            self.interfaceSupport = False

        if self.interfaceSupport:
            self.insteonDevices.clear()
            logger.info("devicesByType--: {out}", out=self._DevicesByType('insteon_appliance'))
            for devkey, device in self._DevicesByType('insteon_appliance').iteritems():
                logger.info("devicevariables: {vars}", vars=device.deviceVariables)
                iaddress = device.deviceVariables['insteonaddress']['value'][0].upper()
                self.insteonDevices[iaddress] = device
            for devkey, device in self._DevicesByType('insteon_lamp').iteritems():
                logger.info("devicevariables: {vars}", vars=device.deviceVariables)
                iaddress = device.deviceVariables['insteonaddress']['value'][0].upper()
                self.insteonDevices[iaddress] = device

    def _start_(self):
        logger.debug("Insteon API command module started")
        
    def _stop_(self):
        pass

    def _unload_(self):
        pass

    def message(self, message):
        logger.debug("InsteonAPI got message: {message}", message=message.dump())
        logger.debug("InsteonAPI device: {message}", message=message['payload']['deviceobj'].device_route)
        if message.msgType == 'cmd' and message.msgStatus == 'new':
#            print self._Devices
            if message.payload['deviceobj'].device_id in self._Devices:
#              try:
                self.processNewCmdMsg(message)
#              except:
#                logger.info("")

    def processNewCmdMsg(self, message):
        logger.debug("in insteponapi::processNewCmdMsg")

        insteonCmd = InsteonCmd(self, message)

        self.insteoncmds[message.msgUUID] = insteonCmd
        logger.debug("NEW: insteonCmd: {insteonCmd}", insteonCmd=insteonCmd.dump())

#        x10cmd.deviceobj.getRouting('interface')
#        self._ModulesLibrary.getDeviceRouting(x10cmd.deviceobj.device_type_id, 'Interface')
        self.interfaceModule.insteonapi_send_command(insteonCmd)

    def statusUpdate(self, address, command, status=None):
        """
        Called by interface modules when a device has a change of status.
        """
        if address in self.insteonDevices:
          device =  self.insteonDevices[address]
          newstatus = None
          tempcmd = command.upper()

          if device.device_type_id == self._DeviceTypes["Insteon Lamp"]:
            if tempcmd == 'ON':
              newstatus = 'ON'
            elif tempcmd == 'OFF':
              newstatus = 'OFF'
          elif device.device_type_id == self._DeviceTypes["Insteon Appliance"]:
            if tempcmd == 'ON':
              newstatus = 100
            elif tempcmd == 'OFF':
              newstatus = 0
            elif tempcmd == 'DIM':
              if type(device.status[0]['status']) is int:
                  newstatus = device.status[0]['status'] - 12
              else:
                  newstatus = 88
            elif tempcmd == 'BRIGHT':
              if type(device.status[0]['status']) is int:
                  newstatus = device.status[0]['status'] + 12
              else:
                  newstatus = 100

            if type(newstatus) is int:
              if newstatus > 100:
                  newstatus = 100
              elif newstatus < 0:
                  newstatus = 0
            else:
                newstatus = 0

          logger.debug("status update... {newstatus}", newstatus=newstatus)
          device.set_status(status=newstatus, source="x10api")

    def cmdDone(self, insteonCmd):
        """
        Called after interface module reports the command was sent out.
        
        First update the device status value, then sent a cmdreply msg.
        Finally, send a status message.
        """
        replmsg = insteonCmd.originalMessage.getReply(status='done', statusExtra="Command completed.")
        logger.debug("msgreply: {msgreply}", msgreply=replmsg.dump())
        replmsg.send()

    def cmdFailed(self, x10cmd, statusmsg="Unknown reason."):
        """
        Used to tell the sending module that the command has failed.
        
        statusmsg should contain the status messsage to display to user
        or enter on a log file.
        """
        pass
    
    def removeX10Cmd(self, x10cmd):
        """
        Delete an old x10cmd object
        """
        logger.debug("Purging x10cmd object: {x10cmd}", x10cmd=x10cmd.x10uuid)
        del self.x10cmds[x10cmd.x10uuid]
        logger.debug("pending x10cmds: {x10cmds}", x10cmds=self.x10cmds)
    
    def removeInsteonCmd(self, insteonCmd):
        """
        Delete an old x10cmd object
        """
        logger.debug("Purging insteon command instance: {msguuid}", msguuid=insteonCmd.msguuid)
        del self.insteoncmds[insteonCmd.msguuid]
        logger.debug("pending insteonCmds: {insteoncmds}", insteoncmds=self.insteoncmds)
