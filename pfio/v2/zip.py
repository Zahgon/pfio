import io
import logging
import os
import zipfile
from datetime import datetime
from typing import Optional, Set

from pfio._profiler import record, record_iterable

from .fs import FS, FileStat, format_repr

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


class ZipProfileIOWrapper:
    def __init__(self, fp):
        self.fp = fp

    def __enter__(self):
        self.fp.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with record("pfio.v2.Zip:exit-context", trace=True):
            self.fp.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        attr = getattr(self.fp, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                pass
            return wrapper
        else:
            return attr


class ZipFileStat(FileStat):
    """Detailed information of a file in a Zip

    Attributes:
        filename (str): Derived from `~FileStat`.
        orig_filename (str): ``ZipFile.orig_filename``.
        comment (str): ``ZipFile.comment``.
        last_modifled (float): Derived from `~FileStat`.
            No sub-second precision.
        mode (int): Derived from `~FileStat`.
        size (int): Derived from `~FileStat`.
        create_system (int): ``ZipFile.create_system``.
        create_version (int): ``ZipFile.create_version``.
        extract_version (int): ``ZipFile.extract_version``.
        flag_bits (int): ``ZipFile.flag_bits``.
        volume (int): ``ZipFile.volume``.
        internal_attr (int): ``ZipFile.internal_attr``.
        external_attr (int): ``ZipFile.external_attr``.
        header_offset (int): ``ZipFile.header_offset``.
        compress_size (int): ``ZipFile.compress_size``.
        compress_type (int): ``ZipFile.compress_type``.
        CRC (int): ``ZipFile.CRC``.
    """

    def __init__(self, zip_info):
        self.last_modified = float(datetime(*zip_info.date_time).timestamp())
        # https://github.com/python/cpython/blob/3.8/Lib/zipfile.py#L392
        self.mode = zip_info.external_attr >> 16
        self.size = zip_info.file_size

        for k in ('filename', 'orig_filename', 'comment', 'create_system',
                  'create_version', 'extract_version', 'flag_bits',
                  'volume', 'internal_attr', 'external_attr', 'CRC',
                  'header_offset', 'compress_size', 'compress_type'):
            setattr(self, k, getattr(zip_info, k))


class Zip(FS):
    _readonly = True

    def __init__(self, backend, file_path, mode='r',
                 create=False, local_cache=False, local_cachedir=None,
                 trace=False, **kwargs):
        super().__init__()
        self.backend = backend
        self.file_path = file_path
        self.mode = mode
        self.kwargs = kwargs
        self.trace = trace

        if create:
            raise ValueError("create option is not supported")

        if 'r' in mode and 'w' in mode:
            raise io.UnsupportedOperation('Read-write mode is not supported')

        if 'w' in mode:
            self._readonly = False

        if local_cache or local_cachedir:
            raise NotImplementedError("Sparse file cache has been removed.")

        self._reset()

    def _reset(self):
        with record("pfio.v2.Zip:create-zipfile-obj", trace=self.trace):
            obj = self.backend.open(self.file_path,
                                    self.mode + 'b',
                                    **self.kwargs)
            self.fileobj = obj

            assert self.fileobj is not None
            self.zipobj = zipfile.ZipFile(self.fileobj, self.mode)

        self.name_cache: Optional[Set[str]] = None
        if self._readonly:
            self.name_cache = self._names()

    def __getstate__(self):
        state = self.__dict__.copy()
        state['fileobj'] = None
        state['zipobj'] = None
        state['name_cache'] = None
        return state

    def __setstate__(self, state):
        self.__dict__ = state

    def __repr__(self):
        return format_repr(
            Zip,
            {
                "file_path": self.file_path,
                "mode": self.mode,
                "backend": self.backend,
            },
        )

    def open(self, file_path, mode='r',
             buffering=-1, encoding=None, errors=None,
             newline=None, closefd=True, opener=None):
        pass

    def subfs(self, path):
        # TODO
        raise NotImplementedError()

    def close(self):
        with record("pfio.v2.Zip:close", trace=self.trace):
            self._checkfork()
            self.zipobj.close()
            self.fileobj.close()

    def stat(self, path):
        with record("pfio.v2.Zip:stat", trace=self.trace):
            self._checkfork()
            names = self._names()
            path = os.path.join(self.cwd, os.path.normpath(path))
            if path in names:
                actual_path = path
            elif not path.endswith('/') and path + '/' in names:
                # handles cases when path is a directory
                # but without trailing slash
                # see issue $67
                actual_path = path + '/'
            else:
                raise FileNotFoundError(
                    "{} is not found".format(path))

            return ZipFileStat(self.zipobj.getinfo(actual_path))

    def list(self, path_or_prefix: Optional[str] = "", recursive=False,
             detail=False):
        pass

    def _list(self, path_or_prefix: Optional[str] = "", recursive=False,
              detail=False):
        pass

    def isdir(self, file_path: str):
        with record("pfio.v2.Zip:isdir", trace=self.trace):
            self._checkfork()
            file_path = os.path.join(self.cwd, file_path)
            if self.exists(file_path):
                return self.stat(file_path).isdir()
            else:
                file_path = os.path.normpath(file_path)
                # check if directories are NOT included in the zip
                if any(name.startswith(file_path + "/")
                       for name in self._names()):
                    return True

                return False

    def mkdir(self, file_path: str, mode=0o777, *args, dir_fd=None):
        raise io.UnsupportedOperation("zip does not support mkdir")

    def makedirs(self, file_path: str, mode=0o777, exist_ok=False):
        raise io.UnsupportedOperation("zip does not support makedirs")

    def exists(self, file_path: str):
        with record("pfio.v2.Zip:exists", trace=self.trace):
            self._checkfork()
            file_path = os.path.join(self.cwd, os.path.normpath(file_path))
            namelist = self.zipobj.namelist()
            return (file_path in namelist
                    or file_path + "/" in namelist)

    def rename(self, *args):
        raise io.UnsupportedOperation

    def remove(self, file_path, recursive=False):
        raise io.UnsupportedOperation

    def _canonical_name(self, file_path: str) -> str:
        pass

    def _names(self) -> Set[str]:
        if self.name_cache is not None:
            return self.name_cache
        else:
            return set(
                data.filename for data in self.zipobj.infolist()
            )


def _open_zip(fs, file_path, mode, **kwargs) -> Zip:
    return Zip(fs, file_path, mode, **kwargs)
