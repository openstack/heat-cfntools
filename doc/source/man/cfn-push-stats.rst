==============
cfn-push-stats
==============

.. program:: cfn-push-stats

SYNOPSIS
========

``cfn-push-stats``

DESCRIPTION
===========
Implements cfn-push-stats CloudFormation functionality


OPTIONS
=======
.. cmdoption:: -v, --verbose

  Verbose logging

.. cmdoption:: --credential-file

  credential-file

.. cmdoption:: --service-failure

  Reports a service falure.

.. cmdoption:: --mem-util

  Reports memory utilization in percentages.

.. cmdoption:: --mem-used

  Reports memory used (excluding cache and buffers) in megabytes.

.. cmdoption:: --mem-avail

  Reports available memory (including cache and buffers) in megabytes.

.. cmdoption:: --swap-util

  Reports swap utilization in percentages.

.. cmdoption:: --swap-used

  Reports allocated swap space in megabytes.

.. cmdoption:: --disk-space-util

  Reports disk space utilization in percentages.

.. cmdoption:: --disk-space-used

  Reports allocated disk space in gigabytes.

.. cmdoption:: --disk-space-avail

  Reports available disk space in gigabytes.

.. cmdoption:: --memory-units

  Specifies units for memory metrics.

.. cmdoption:: --disk-units

  Specifies units for disk metrics.

.. cmdoption:: --disk-path

  Selects the disk by the path on which to report.

.. cmdoption:: --cpu-util

  Reports cpu utilization in percentages.

.. cmdoption:: --haproxy

  Reports HAProxy loadbalancer usage.

.. cmdoption:: --haproxy-latency

  Reports HAProxy latency

.. cmdoption:: --heartbeat

  Sends a Heartbeat.

.. cmdoption:: --watch

  the name of the watch to post to.


BUGS
====
Heat bugs are managed through Launchpad <https://launchpad.net/heat-cfntools>