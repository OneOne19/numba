from __future__ import absolute_import, print_function, division
import numpy

from .. import jit, typeof, utils, types, numpy_support
from . import _internal, ufuncbuilder

class DUFunc(_internal._DUFunc):
    # NOTE: __base_kwargs must be kept in synch with the kwlist in
    # _internal.c:dufunc_init()
    __base_kwargs = set(('identity', '_keepalive', 'nin', 'nout'))

    def __init__(self, py_func, **kws):
        dispatcher = jit(target='npyufunc')(py_func)
        self.targetoptions = {}
        # Loop over a copy of the keys instead of the keys themselves,
        # since we're changing the dictionary while looping.
        kws_keys = tuple(kws.keys())
        for key in kws_keys:
            if key not in self.__base_kwargs:
                self.targetoptions[key] = kws.pop(key)
        kws['identity'] = ufuncbuilder._BaseUFuncBuilder.parse_identity(
            kws.pop('identity', None))
        super(DUFunc, self).__init__(dispatcher, **kws)

    def _compile_for_args(self, *args, **kws):
        nin = self.ufunc.nin
        args_len = len(args)
        assert (args_len == nin) or (args_len == nin + self.ufunc.nout)
        assert len(kws) == 0
        argtys = []
        # To avoid a mismatch in how Numba types values as opposed to
        # Numpy, we need to first check for scalars.  For example, on
        # 64-bit systems, numba.typeof(3) => int32, but
        # numpy.array(3).dtype => int64.
        for arg in args[:nin]:
            if numpy_support.is_arrayscalar(arg):
                argtys.append(numpy_support.map_arrayscalar_type(arg))
            else:
                argty = typeof(arg)
                if isinstance(argty, types.Array):
                    argty = argty.dtype
                argtys.append(argty)
        element_wise_signature = tuple(argtys)
        cres, args, return_type = ufuncbuilder._compile_element_wise_function(
            self._dispatcher, self.targetoptions, element_wise_signature)
        sig = ufuncbuilder._finalize_ufunc_signature(cres, args, return_type)
        dtypenums, ptr, env = ufuncbuilder._build_element_wise_ufunc_wrapper(
            cres, sig)
        self._add_loop(utils.longint(ptr), dtypenums)
        self._keepalive.append((ptr, cres.library, env))
        return