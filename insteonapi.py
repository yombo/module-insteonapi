#This file was created by Yombo for use with Yombo Gateway automation
#software.  Details can be found at http://www.yombo.net
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

The **`Yombo.net <http://www.yombo.net/>`_** team and other contributors
hopes that it will be useful, but WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

The GNU General Public License can be found here: `GNU.Org <http://www.gnu.org/licenses>`_

Implements
==========

- class InsteonCmd - A class to pass between InsteonAPI module and interface modules.
- class InsteonAPI - the command module 

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>
:copyright: Copyright 2012 by Yombo.
:license: GPL(v3)
"""
import time
#import re

from yombo.core.module import YomboModule
from yombo.core.sqldict import SQLDict
from yombo.core.helpers import getComponent, getInterfaceModule
from yombo.core.db import get_dbtools
from yombo.core.log import getLogger

logger = getLogger()

class InsteonCmd:
    """
    An Insteon command instance that is passed between this module
    and any interface modules to send insteon commands to the power line.
    """
    def __init__(self, insteonapi, message = {'msgID':None}):
        """
        Setup the class to communicate between insteon API module and any interface modules.
        
        @param insteonapi: A pointer to the insteonapi class.
        """

        self.insteonaddress = None
        """@ivar: Insteon unit address.
           @type: C{string}"""
        self.insteoncommand = None
        """@ivar: Information regarding the command. "origcmd" is the original command. "value" is the offical
             insteon command.
           @type: C{dict}"""
        self.msguuid = message.msgID
        """@ivar: The msgID that was generated to create this command. Is None if comming from interface module.
           @type: C{str}"""
        self.insteonextended = None
        """@ivar: Extended data to send with the insteon command.
           @type: C{hex}"""
        self.insteonvalue = None
        """@ivar: The updated state of the device. This is set by the interface module.
           @type: C{str} or C{int}"""
        self.deviceid =  message['payload']['deviceid']
        self.devicetype = None
        """@ivar: Either 'x10' or 'insteon'
           @type: C{str}"""
        self.chain = {}  # AKA history
        self.created = time.time()
        self.interfaceResult = None
        self.commandResult = None
        self.insteonapi = insteonapi
        self.originalMessage = message
        self.deviceid = None
        self.status1 = None
        self.status2 = None
        
    def dump(self):
        """
        Convert key class contents to a dictionary.

        @return: A dictionary of the key class contents.
        @rtype: C{dict}
        """
        return {'insteonaddress': self.insteonaddress,
                'insteoncommand': self.insteoncommand,
                'chain': self.chain,
                'created': self.created,
                'interfaceResult': self.interfaceResult,
                'commandResult': self.commandResult }
                
    def sendCmdToInterface(self):
        """
        Send to the insteon command module
        """
        pass
        
    def statusReceived(self, status, statusExtended={}):
        """
        Contains updated status of a device received from the interface.
        """
        pass
        
    def cmdDone(self):
        """
        Every command should tell the sender when the command was sent.
        
        We just need to validate that it was sent, some protocols are
        only one way.  This way the user gets some feedback.
        
        In this case, insteon may not work, but at the command was issued.
        """
        self.insteonapi.cmdDone(self)
        self.insteonapi.removeInsteonCmd(self)

    def cmdPending(self):
        """
        Used to tell the sending module that the command is pending (processing)
        """
        pass
    
    def cmdFailed(self, statusmsg):
        """
        Used to tell the sending module that the command failed.
        
        statussg should hold the failure reason.  Displayed to user.
        """
        pass

class InsteonAPI(YomboModule):
    """
    Insteon Command Module
    
    Generic module that handles all insteon commands from other modules
    and prepares it for an interface module.  Also recieves data from
    interface modules for delivery to other gateway modules.
    """

    def init(self):
        self._ModDescription = "Insteon API command interface"
        self._ModAuthor = "Mitch Schwenk @ Yombo"
        self._ModUrl = "http://www.yombo.net"

        self._RegisterDistributions = ['cmd']
        self.insteoncmds = {}         #store a copy of active x10cmds
        self.dbtools = get_dbtools()
        self.originalMessage = None
        self.deviceLinks = SQLDict(self,"deviceLinks")  # used to store what devices
                                          # listen to group broadcasts.
                                          # data saved in this dict is saved
                                          # in SQL and recreated on startup.

        self.functionToInsteon = {
          'ON'            : 0x02,
          'OFF'           : 0x03,
          'DIM'           : 0x04,
          'BRIGHTEN'      : 0x05,
          'MICRO_DIM'     : None,
          'MICRO_BRIGHTEN': None }

        self._housecodes = list('ABCDEFGHIJKLMNOP')
        self._unitcodes = range(1, 17)
        
#@todo: create irigation, alarm, etc types.
        self.deviceTypes = {
          1 : "insteonApplicance",
          2 : "insteonLamp"}        

        self.x10DeviceTypes = [1,2,18]
        self.insteonDeviceTypes = [16,17]
        
#@todo: get devicetypecommand mappings from database
            
    def load(self):
#        logger.debug("@#@#@#@#@#@#@#@:  %s", getInterfaceModule(self))
#        self.interfaceModule = getComponent(getInterfaceModule(self))

        self.interfaceModule = getComponent("yombo.gateway.modules.InsteonPLM")
        
    def start(self):
        logger.debug("Insteon API command module started") 
        
    def stop(self):
        pass

    def unload(self):
        pass

    def message(self, message):
        logger.debug("InsteonAPI got message: %s", message.dump())
        if message.msgType == 'cmd' and message.msgStatus == 'new':
            deviceid = message['payload']['deviceid']
            if self._Devices[deviceid].devicetypeid in self.x10DeviceTypes:
                self.processNewCmdMsg(message, 'x10')
            elif self._Devices[deviceid].devicetypeid in self.insteonDeviceTypes:
                self.processNewCmdMsg(message, 'insteon')

    def processNewCmdMsg(self, message, type):
        logger.debug("msg: %s", message.dump())

        insteonCmd = InsteonCmd(self, message)
        insteonCmd.insteonaddress = self._Devices[message['payload']['deviceid']].deviceaddress
        insteonCmd.insteoncommand = message['payload']['cmd'].lower()
        insteonCmd.devicetype = type

        self.insteoncmds[message.msgID] = insteonCmd
#        logger.debug("NEW: x10cmd: %s", x10cmd.dump())

        self.interfaceModule.sendInsteonCmd(message.msgID)

    def statusReceived(self, x10cmd):
        """
        Used to deliver device state changes. A lamp turns on, etc.

        The value of payload will be the final state value of
        the X10 device.
        """
        pass

    
    def cmdDone(self, insteonCmd):
        """
        Called after interface module reports the command was sent out.
        
        First update the device status value, then sent a cmdreply msg.
        Finally, send a status message.
        """
        tempcmd = insteonCmd.insteoncommand
        deviceid = insteonCmd.deviceid
        newstatus = None
#@todo: Move to interface module!!!
                
        self._Devices[deviceid].setStatus(silent=True, status=insteonCmd.status1)

        # 1 - reply to sender so they know we are done.
        replmsg = insteonCmd.originalMessage.getReply()
        replmsg.msgStatusExtra = 'done'
        replmsg.payload = {'status'  : self._Devices[deviceid].status,
                           'cmd'     : insteonCmd.insteoncommand['origcmd'],
                           'deviceid': deviceid }
        logger.debug("insteon cmddone msgreply: %s", replmsg.dump())
        replmsg.send()

        # 2 - let the rest of the world know.
        self._Devices[deviceid].sendStatus(src=self.fname)

    def cmdPending(self, x10cmd, statusmsg):
        """
        Used to tell the sending module that the command is pending.
        
        Used when it's taking longer than 1 second.  This lets the other
        module/client/device know we received the command, but it's still
        processing.
        
        A cmdDone or cmdFail is expected afterward.
        
        Statusmsg should contain the actual status to display to a user
        or to report in a log.
        """
        pass

    def cmdFailed(self, x10cmd, statusmsg="Unknown reason."):
        """
        Used to tell the sending module that the command has failed.
        
        statusmsg should contain the status messsage to display to user
        or enter on a log file.
        """
        pass
    
    def removeInsteonCmd(self, insteonCmd):
        """
        Delete an old x10cmd object
        """
        logger.debug("Purging x10cmd object: %s", insteonCmd.msguuid)
        del self.insteoncmds[insteonCmd.msguuid]
        logger.debug("pending insteonCmds: %s", self.insteoncmds)
