======================
Building the man pages
======================

Dependencies
============

Sphinx_
  You'll need sphinx (the python one) and if you are
  using the virtualenv you'll need to install it in the virtualenv
  specifically so that it can load the cinder modules.

  ::

    sudo yum install python-sphinx
    sudo pip-python install sphinxcontrib-httpdomain

Use `make`
==========

To build the man pages:

  make man
