int16gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 1)[::-1]])
int32gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 2)[::-1]])
int48gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 3)[::-1]])
int64gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 4)[::-1]])

int2did = lambda n: int64gid(n)
int2did_short = lambda n: int48gid(n)
int2fleet_id = lambda n: int48gid(n)
int2pid = lambda n: int32gid(n)
int2vid = lambda n: int16gid(n)
int2bid = lambda n: int16gid(n)

gid_split = lambda val: val.split('--')


def gid_join(elements):
    return '--'.join(elements)


def fix_gid(gid, num_terms):
    elements = gid.split('-')
    if len(elements) < num_terms:
        # Prepend '0000' as needed to get proper format (in groups of '0000')
        extras = ['0000' for i in range(num_terms - len(elements))]
        elements = extras + elements
    elif len(elements) > num_terms:
        # Only keep right most terms
        elements = elements[(len(elements) - num_terms):]

    return'-'.join(elements)


def formatted_dbid(bid, did):
    """Formatted Global Data Block ID: d--<block>-<device>"""
    # The old Deviuce ID was 4 4-hex blocks, but the new is only three. Remove the left side block if needed
    device_id_parts = did.split('-')
    if (len(device_id_parts) == 4):
        device_id_parts = device_id_parts[1:]
    elif (len(device_id_parts) < 3):
        extras = ['0000' for i in range(3 - len(device_id_parts))]
        device_id_parts = extras + device_id_parts
    return gid_join(['b', '-'.join([bid,] + device_id_parts)])


def formatted_gpid(pid):
    pid = fix_gid(pid, 2)
    return gid_join(['p', pid])


def formatted_gdid(did, bid='0000'):
    """Formatted Global Device ID: d--0000-0000-0000-0001"""
    # ID should only map
    did = '-'.join([bid, fix_gid(did, 3)])
    return gid_join(['d', did])


def formatted_gvid(pid, vid, is_template=False):
    """
    Formatted Global Variable ID: v--0000-0001--5000
    (or ptv--0000-0001-5000 for Project Teamplate Variables)
    """
    pid = fix_gid(pid, 2)
    if is_template:
        return gid_join(['ptv', pid, vid])
    return gid_join(['v', pid, vid])


def formatted_gsid(pid, did, vid):
    """Formatted Global Stream ID: s--0000-0001--0000-0000-0000-0001--5000"""
    pid = fix_gid(pid, 2)
    did = fix_gid(did, 4)
    return gid_join(['s', pid, did, vid])


def formatted_gfid(pid, did, vid):
    """
    Formatted Global Filter ID: f--0000-0001--0000-0000-0000-0001--5000
    or if no device: f--0000-0001----5000
    """
    pid = fix_gid(pid, 2)
    if did:
        did = fix_gid(did, 4)
    else:
        did = ''
    return gid_join(['f', pid, did, vid])


def formatted_gtid(did, index):
    """
    Formatted Global Streamer ID: t--0000-0000-0000-0001--0001
    """
    did = fix_gid(did, 4)
    return gid_join(['t', did, index])


def formatted_alias_id(id):
    """Formatted Global Alias ID: a--0000-0000-0000-0001"""
    return gid_join(['a', fix_gid(id, 4)])


def formatted_fleet_id(id):
    """Formatted Global Fleet ID: g--0000-0000-0001"""
    return gid_join(['g', fix_gid(id, 3)])


def gid2int(gid):
    elements = gid.split('-')
    hex_value = ''.join(elements)
    return int(hex_value, 16)


def get_vid_from_gvid(gvid):
    parts = gid_split(gvid)
    return parts[2]


def get_device_and_block_by_did(gid):
    parts = gid_split(gid)
    if parts[0] == 'd' or parts[0] == 'b':
        elements = parts[1].split('-')
        block_hex_value = elements[0]
        device_hex_value = ''.join(elements[1:])
        return int(block_hex_value, 16), int(device_hex_value, 16)
    else:
        return None, None


def get_device_slug_by_block_slug(block_slug):
    parts = gid_split(block_slug)
    return gid_join(['d', parts[1]])
