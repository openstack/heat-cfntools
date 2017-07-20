==========
cfn-signal
==========

.. program:: cfn-signal

SYNOPSIS
========

``cfn-signal``

DESCRIPTION
===========
Implements cfn-signal CloudFormation functionality


OPTIONS
=======
.. cmdoption:: -s, --success

  signal status to report

.. cmdoption:: -r, --reason

  The reason for the failure

.. cmdoption:: --data

  The data to send

.. cmdoption:: -i, --id

  the unique id to send back to the WaitCondition

.. cmdoption:: -e, --exit

  The exit code from a procecc to interpret


BUGS
====
Heat bugs are managed through Launchpad <https://launchpad.net/heat-cfntools>