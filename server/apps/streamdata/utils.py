from apps.utils.mdo.helpers import MdoHelper


def get_stream_mdo(stream):
    if stream.mdo_type == 'V':
        var = stream.variable
        return_mdo = MdoHelper(var.multiplication_factor, var.division_factor, var.offset)
    elif stream.mdo_type == 'S':
        m = 1
        d = 1
        if stream.multiplication_factor is not None:
            m = stream.multiplication_factor
        if stream.division_factor is not None:
            d = stream.division_factor

        return_mdo = MdoHelper(m, d, stream.offset)
    else:
        return_mdo = MdoHelper(1, 1, 0)
    return return_mdo


def get_stream_input_mdo(stream):
    input_mdo = None
    if stream.input_unit:
        input_mdo = MdoHelper(stream.input_unit.m, stream.input_unit.d, stream.input_unit.o)
    else:
        var = stream.variable
        if var and var.input_unit:
            input_mdo = MdoHelper(var.input_unit.m, var.input_unit.d, var.input_unit.o)
    return input_mdo


def get_stream_output_mdo(stream):
    output_mdo = None
    if stream.output_unit:
        output_mdo = MdoHelper(stream.output_unit.m, stream.output_unit.d, stream.output_unit.o)
    else:
        var = stream.variable
        if var and var.output_unit:
            output_mdo = MdoHelper(var.output_unit.m, var.output_unit.d, var.output_unit.o)
    return output_mdo


def get_stream_output_unit(stream):
    output_unit = None
    if stream.output_unit:
        output_unit = stream.output_unit
    else:
        var = stream.variable
        if var and var.output_unit:
            output_unit = var.output_unit
    return output_unit
