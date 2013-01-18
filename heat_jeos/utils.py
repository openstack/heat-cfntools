import base64
from glob import glob
import logging
import os.path
from StringIO import StringIO

from lxml import etree
import oz.TDL
import oz.GuestFactory
from oz import ozutil


jeos_module_path = os.path.abspath(os.path.dirname(__file__))
DEFAULT_JEOS_DIR = os.path.join(jeos_module_path, 'jeos')
DEFAULT_CFNTOOLS_DIR = os.path.join(jeos_module_path, 'cfntools')


def template_metadata(template_path):
    """
    Parse the given TDL and return its metadata (name, arch, distro, version).
    """
    tdl = etree.parse(template_path)
    name = tdl.findtext('name', default='n/a')
    distro = tdl.findtext('os/name', default='n/a')
    architecture = tdl.findtext('os/arch', default='n/a')
    version = tdl.findtext('os/version', default='n/a')
    return [name, distro, version, architecture]


def find_template_by_name(template_dir, template_name):
    """
    Look through the templates in the given directory, find the one with
    matching name and return its path.

    Return `None` otherwise.
    """
    if not template_dir:
        template_dir = DEFAULT_JEOS_DIR
    for template_path in glob('%s/*.tdl' % template_dir):
        name, distro, version, arch = template_metadata(template_path)
        if name == template_name:
            return template_path

def get_oz_guest(tdl_xml, auto=None):
    """
    Returns Oz Guest instance based on the passed template.
    """
    tdl = oz.TDL.TDL(tdl_xml)
    config = ozutil.parse_config(None)
    return oz.GuestFactory.guest_factory(tdl, config, auto, None)


def build_image_from_tdl(tdl_xml):
    oz_guest = get_oz_guest(tdl_xml)
    dsk_path, qcow2_path, image_name = target_image_paths(oz_guest)
    final_tdl = create_tdl(tdl_xml, None, DEFAULT_CFNTOOLS_DIR)
    return build_jeos(get_oz_guest(final_tdl))


def ensure_xml_path(element, path):
    """
    Make sure the given path in the XML element exists. Create the elements as
    needed.
    """
    if not path:
        return
    tag = path[0]
    el = element.find(tag)
    if not el:
        el = etree.Element(tag)
        element.append(el)
    ensure_xml_path(el, path[1:])


def create_tdl(tdl, iso_path, cfn_dir):
    """
    Prepare the template for use with Heat.

    If the `iso_path` is specified, override the template's ISO with it.

    Returns the TDL contents as a string.
    """
    tdl_xml = etree.parse(StringIO(tdl))

    # Load the cfntools into the cfntool image by encoding them in base64
    # and injecting them into the TDL at the appropriate place
    cfn_tools = ['cfn-init', 'cfn-hup', 'cfn-signal',
                'cfn-get-metadata', 'cfn_helper.py', 'cfn-push-stats']
    for cfnname in cfn_tools:
        cfnpath = "files/file[@name='/opt/aws/bin/%s']" % cfnname
        elem = tdl_xml.find(cfnpath)
        if elem is not None:
            f = open('%s/%s' % (cfn_dir, cfnname), 'r')
            cfscript_e64 = base64.b64encode(f.read())
            f.close()
            elem.text = cfscript_e64
    if iso_path:
        root = tdl_xml.getroot()
        ensure_xml_path(root, ['os', 'install', 'iso'])
        elem = root.find('os/install/iso')
        elem.text = 'file:%s' % iso_path

    string_writer = StringIO()
    tdl_xml.write(string_writer, xml_declaration=True)
    return string_writer.getvalue()


def build_jeos(guest):
    """
    Use Oz to build the JEOS image.
    """
    logging.debug("Running Oz")
    dsk_path, qcow2_path, image_name = target_image_paths(guest)
    if os.path.exists(qcow2_path):
        os.remove(qcow2_path)
    if os.path.exists(dsk_path):
        os.remove(dsk_path)

    guest.check_for_guest_conflict()
    try:
        force_download = False
        guest.generate_install_media(force_download)
        try:
            guest.generate_diskimage(force=force_download)
            libvirt_xml = guest.install(50000, force_download)
        except:
            guest.cleanup_old_guest()
            raise
    finally:
        guest.cleanup_install()

    guest.customize(libvirt_xml)

    if not os.access(dsk_path, os.R_OK):
        logging.error('oz-install did not create the image,'
                      ' check your oz installation.')
        sys.exit(1)

    logging.info('Converting raw disk image to a qcow2 image.')
    os.system("qemu-img convert -c -O qcow2 %s %s" % (dsk_path, qcow2_path))
    return qcow2_path


def target_image_paths(oz_guest):
    """
    Return the image paths and the image name that Oz will generate.
    """
    dsk_path = oz_guest.diskimage
    qcow2_path = os.path.splitext(dsk_path)[0] + '.qcow2'
    image_name = oz_guest.name
    return dsk_path, qcow2_path, image_name
