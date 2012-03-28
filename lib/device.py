#!env python
# -*- coding: utf-8 -*-
# vim: tabstop=4:softtabstop=4:shiftwidth=4:expandtab
#  M Newville <newville@cars.uchicago.edu>
#  The University of Chicago, 2010
#  Epics Open License
"""
basic device object defined
"""
from . import ca
from .pv import PV
import time
from functools import partial


class Device(object):
    """A simple collection of related PVs, sharing a common prefix
    string for their names, but having many 'attributes'.

    Many groups of PVs will have names made up of
         Prefix+Delimiter+Attribute
    with common Prefix and Delimiter, but a range of Attribute names.
    Many Epics Records follow this model, but a Device is only about
    PV names, and so is not exactly a mapping to an Epics Record.

    This class allows a collection of PVs to be represented simply.

      >>> dev = epics.Device('XX:m1', delim='.')
      >>> dev.put('OFF',0 )
      >>> dev.put('VAL', 0.25)
      >>> dev.get('RBV')
      >>> print dev.FOFF
      >>> print dev.get('FOFF', as_string=True)

    This will put a 0 to XX:m1.OFF, a 0.25 to XX:m1.VAL, and then
    get XX:m1.RBV and XX.m1.FOFF.

    Note access to the underlying PVs can either be with get()/put()
    methods or with attributes derived from the Attribute (Suffix) for
    that PV.  Thus
      >>> print dev.FOFF
      >>> print dev.get('FOFF')

    are equivalent, as are:
      >>> dev.VAL = 1
      >>> dev.put('VAL', 1)

    The methods do provide more options.  For example, to get the PV
    value as a string,
       Device.get(Attribute, as_string=True)
    must be used.   To put-with-wait, use
       Device.put(Attribute, value, wait=True)

    The list of attributes can be pre-loaded at initialization time.


    The attribute PVs are built as needed and held in an internal
    buffer (self._pvs).  This class is kept intentionally simple
    so that it may be subclassed.

    To pre-load attribute names on initialization, provide a
    list or tuple of attributes:

      >>> struck = epics.Device('13IDC:str:',
      ...                       attrs=('ChannelAdvance',
      ...                              'EraseStart','StopAll'))
      >>> print struck.PV('ChannelAdvance').char_value
      'External'

    The prefix is optional, and when left off, this class can
    be used as an arbitrary container of PVs, or to turn
    any subclass into an epics Device:

      >>> class MyClass(epics.Device):
      ...     def __init__(self,**kw):
      ...         epics.Device.__init__() # no Prefix!!
      ...
      >>> x = MyClass()
      >>> pv_m1 = x.PV('13IDC:m1.VAL')
      >>> x.put('13IDC:m3.VAL', 2)
      >>> print x.PV('13IDC:m3.DIR').get(as_string=True)

    you can all get
    """

    def _add_pv_property(self, pv_name, name=None):
        "compose property"
        pv_name = pv_name.upper()
        name = name or pv_name

        def get(self, pv_name):
            "helper for getter, return value"
            _pv = self.get_pv(pv_name)
            val = _pv.get()
            if val == None:
                raise AttributeError("'%s' object could not get '%s'" %
                                     (self._prefix.strip("."),
                                     _pv.pvname))
            return val

        def put(self, pv_name, val):
            "helper for setter, put value"
            _pv = self.get_pv(pv_name)
            if not _pv.wait_for_connection():
                raise IOError("'%s' object could not connect to '%s'" %
                              (self._prefix.strip("."), _pv.pvname))
            if _pv.put(val, wait=True, use_complete=False, timeout=1) == -1:
                raise IOError("'%s' object could not put '%s'" %
                              (self._prefix.strip("."), _pv.pvname))

        if not hasattr(self.__class__, name):
            setattr(self.__class__,
                    name.lower(),
                    property(lambda self: get(self, pv_name),
                             lambda self, val: put(self, pv_name, val),
                             None,
                             ))

    def __init__(self, prefix='', attrs=None, alias=None, delim='',
                 timeout=None):
        self._pvs = {}
        self._delim = delim
        self._prefix = prefix + delim

        if attrs:
            map(self._add_pv_property, attrs)
        if alias:
            map(partial(self._add_pv_property),
                alias.values(),
                alias.keys())
        ca.poll()

    def get_pv(self, attr, connect=True, timeout=None):
        """return epics.PV for a device attribute"""
        attr = attr.lower()
        if attr not in self._pvs:
            self._pvs[attr] = PV("".join((self._prefix, attr.upper())),
                                 connection_timeout=timeout)
        if connect and not self._pvs[attr].connected:
            self._pvs[attr].wait_for_connection()
        return self._pvs[attr]

    def add_pv(self, pvname, attr=None):
        """add a PV with an optional attribute name that may not exactly
        correspond to the mapping of Attribute -> Prefix + Delim + Attribute
        That is, with a device defined as
        >>> dev = Device('XXX', delim='.')

        getting the VAL attribute
        >>> dev.get('VAL')   # or dev.VAL

        becomes   'caget(XXX.VAL)'.  With add_pv(), one can add a
        non-conforming PV to the collection:
        >>> dev.add_pv('XXX_status.VAL', attr='status')

        and then use as
        >>> dev.get('status')  # or dev.status

        If attr is not specified, the full pvname will be used.
        """
        if attr is None:
            attr = pvname
        self._add_pv_property(attr)

        return self._pvs[attr]

    def put(self, attr, value, wait=False, use_complete=False, timeout=None):
        """put an attribute value,
        optionally wait for completion or
        up to a supplied timeout value"""
        thispv = self.get_pv(attr)
        if not thispv.wait_for_connection():
            raise RuntimeError("'%s' object could not connect to '%s'" %
                               (self._prefix.strip("."), attr))
        if thispv.put(value,
            wait=wait,
            use_complete=use_complete,
            timeout=timeout) == -1:
            raise RuntimeError("'%s' object could not put '%s'" %
                               (self._prefix.strip("."), attr))

    def get(self, attr, as_string=False, count=None):
        """get an attribute value,
        option as_string returns a string representation"""
        val = self.get_pv(attr).get(as_string=as_string, count=count)
        if val == None:
            raise AttributeError("'%s' could not get '%s'" %
                                 (self._prefix.strip("."), attr))
        return val

    def save_state(self):
        """return a dictionary of the values of all
        current attributes"""
        out = {}
        for key in self._pvs:
            out[key] = self._pvs[key].get()
            if  (self._pvs[key].count > 1 and
                 'char' == self._pvs[key].type):
                out[key] = self._pvs[key].get(as_string=True)
        return out

    def restore_state(self, state):
        """restore a dictionary of the values, as saved from save_state"""
        for key, val in state.items():
            if key in self._pvs and  'write' in self._pvs[key].access:
                self._pvs[key].put(val)

    def write_state(self, fname, state=None):
        """write save state  to external file.
        If state is not provided, the current state is used

        Note that this only writes data for PVs with write-access,
        and count=1 (except CHAR """
        if state is None:
            state = self.save_state()
        out = ["#Device Saved State for %s, prefx='%s': %s\n" %
            (self.__class__.__name__,
            self._prefix,
            time.ctime())]
        for key in sorted(state.keys()):
            if (key in self._pvs and
                'write' in self._pvs[key].access and
                (1 == self._pvs[key].count or
                 'char' == self._pvs[key].type)):
                out.append("%s  %s\n" % (key, state[key]))
        fout = open(fname, 'w')
        fout.writelines(out)
        fout.close()

    def read_state(self, fname, restore=False):
        """read state from file, optionally restore it"""
        finp = open(fname, 'r')
        textlines = finp.readlines()
        finp.close()
        state = {}
        for line in textlines:
            if line.startswith('#'):
                continue
            key, strval = line[:-1].split(' ', 1)
            if key in self._pvs:
                dtype = self._pvs[key].type
                val = strval
                if dtype in ('double', 'float'):
                    val = float(val)
                elif dtype in ('int', 'long', 'short', 'enum'):
                    val = int(val)
                state[key] = val
        if restore:
            self.restore_state(state)
        return state

    def get_all(self):
        """return a dictionary of the values of all
        current attributes"""
        return self.save_state()

    def add_callback(self, attr, callback, **kws):
        """add a callback function to an attribute PV,
        so that the callback function will be run when
        the attribute's value changes"""
        self.get_pv(attr).get()
        return self.get_pv(attr).add_callback(callback, **kws)

    def remove_callbacks(self, attr, index=None):
        """remove a callback function to an attribute PV"""
        self.get_pv(attr).remove_callback(index=index)

    def __repr__(self):
        "string representation"
        return "<Device '%s' %i attributes>" % (self._prefix.strip("."),
            len(self._pvs))

    @staticmethod
    def pv_property(attr, as_string=False, wait=False, timeout=10.0):
        "return PV property"
        return property(lambda self: \
                        self.get(attr, as_string=as_string),
                        lambda self, val: \
                        self.put(attr, val, wait=wait, timeout=timeout),
                        None, None)
